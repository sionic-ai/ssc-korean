#!/usr/bin/env python3
"""
SSC Abridged Korean Translation Pipeline

Translates Markdown essays from Slate Star Codex Abridged using
a local Gemma 4 31B server (vLLM/SGLang) via OpenAI-compatible API.

Key design decisions:
- Paragraph-level translation units (not sentence-level)
- Literary translation prompt (not academic)
- URL/image markdown protection via placeholders
- Per-paragraph hash-based caching
- Proper noun transliteration + original in parentheses (first occurrence only)
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# --- Configuration ---
DEFAULT_API_BASE = "http://100.124.119.76:8001"  # workstation
DEFAULT_MODEL = "google/gemma-4-31B-it"
CACHE_DIR = Path(__file__).parent.parent / "cache"
SOURCE_DIR = Path(__file__).parent.parent / "source"
OUTPUT_DIR = Path(__file__).parent.parent / "translated"

# --- Translation Prompt ---
SYSTEM_PROMPT = """You are a literary translator specializing in translating English essays into Korean.
You are translating essays by Scott Alexander from the blog "Slate Star Codex".

Translation guidelines:
1. TONE: These are witty, intellectually rigorous essays with heavy use of irony, humor, rhetorical questions, and cultural references. Preserve the author's distinctive voice.
2. STYLE: Translate naturally into Korean. Korean readability > preserving English sentence structure. Use 한다/이다 체 (formal written style).
3. PROPER NOUNS: Transliterate into Korean + original in parentheses on FIRST occurrence only. e.g., "Allen Ginsberg" → "앨런 긴즈버그(Allen Ginsberg)" first time, then "긴즈버그" afterwards.
4. CULTURAL REFERENCES: Keep original terms for well-known concepts that have no standard Korean equivalent. Add brief context in parentheses if the reference would be opaque to Korean readers.
5. QUOTATIONS: Poetry and literary quotations should be translated with literary quality. Preserve verse line breaks.
6. KEY RECURRING TERMS: Maintain consistent translations throughout:
   - "god's-eye-view" → "신의 시점"
   - "coordination problem" → "조정 문제"
   - "multipolar trap" → "다극적 함정"
   - "defect/cooperate" (game theory) → "배신/협력"
   - "Moloch" → "몰로크(Moloch)" (first), then "몰로크"
7. MARKDOWN: Preserve all markdown formatting exactly (headers, bold, italic, links, blockquotes, lists, images).
8. PLACEHOLDERS: Text marked with ⟦LINK:N⟧ or ⟦IMG:N⟧ are placeholders. Keep them exactly as-is in your translation.
9. Do NOT add translator's notes, explanations, or commentary. Just translate.
10. Do NOT translate text inside code blocks or URLs."""

def make_user_prompt(title: str, category: str, paragraph: str) -> str:
    return f"""Translate the following paragraph from the essay "{title}" (category: {category}) into Korean.
Output ONLY the translated paragraph, nothing else.

---
{paragraph}
---"""


# --- Paragraph Splitting ---
def split_into_paragraphs(md_text: str) -> list[dict]:
    """Split markdown into translatable paragraphs while preserving structure.
    
    Returns list of dicts:
      {"text": str, "type": "translate"|"preserve", "line_start": int}
    
    'preserve' blocks are kept as-is (empty lines, horizontal rules, reference-style links at bottom).
    """
    lines = md_text.split('\n')
    paragraphs = []
    current_block = []
    current_start = 0
    in_code_block = False
    
    def flush_block():
        nonlocal current_block, current_start
        if current_block:
            text = '\n'.join(current_block)
            # Determine if this block should be translated or preserved
            stripped = text.strip()
            if not stripped:
                block_type = "preserve"
            elif re.match(r'^\s*\[[\d]+\]:\s*http', stripped):
                # Reference-style link definitions at bottom
                block_type = "preserve"
            elif re.match(r'^\s*[-*_]{3,}\s*$', stripped):
                # Horizontal rules
                block_type = "preserve"
            elif in_code_block:
                block_type = "preserve"
            else:
                block_type = "translate"
            
            paragraphs.append({
                "text": text,
                "type": block_type,
                "line_start": current_start
            })
            current_block = []
    
    for i, line in enumerate(lines):
        # Track code blocks
        if line.strip().startswith('```'):
            if in_code_block:
                current_block.append(line)
                in_code_block = False
                flush_block()
                current_start = i + 1
                continue
            else:
                flush_block()
                current_start = i
                in_code_block = True
                current_block.append(line)
                continue
        
        if in_code_block:
            current_block.append(line)
            continue
        
        # Empty line = paragraph boundary
        if line.strip() == '':
            flush_block()
            paragraphs.append({"text": "", "type": "preserve", "line_start": i})
            current_start = i + 1
        else:
            if not current_block:
                current_start = i
            current_block.append(line)
    
    flush_block()
    return paragraphs


# --- Placeholder System ---
def protect_links(text: str) -> tuple[str, dict]:
    """Replace URLs and image markdown with placeholders, return mapping."""
    placeholders = {}
    counter = [0]
    
    def replace_img(m):
        key = f"⟦IMG:{counter[0]}⟧"
        placeholders[key] = m.group(0)
        counter[0] += 1
        return key
    
    def replace_link(m):
        # Keep the link text for translation, protect the URL
        link_text = m.group(1)
        url = m.group(2)
        key = f"⟦LINK:{counter[0]}⟧"
        placeholders[key] = url
        counter[0] += 1
        return f"[{link_text}]({key})"
    
    # Protect images first (![alt](url))
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', replace_img, text)
    
    # Protect link URLs but keep link text for translation ([text](url))
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', replace_link, text)
    
    # Protect reference-style link references [text][N]
    # These should be kept as-is
    
    return text, placeholders


def restore_links(text: str, placeholders: dict) -> str:
    """Restore placeholders back to original URLs."""
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


# --- Cache ---
def get_cache_path(essay_slug: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{essay_slug}_cache.json"


def load_cache(essay_slug: str) -> dict:
    path = get_cache_path(essay_slug)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_cache(essay_slug: str, cache: dict):
    path = get_cache_path(essay_slug)
    with open(path, 'w') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def paragraph_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# --- API Call ---
def translate_paragraph(text: str, title: str, category: str,
                        api_base: str, model: str,
                        max_retries: int = 3) -> str:
    """Call the translation API for a single paragraph."""
    
    # Protect links
    protected_text, placeholders = protect_links(text)
    
    messages = [
        {"role": "user", "content": SYSTEM_PROMPT + "\n\n" + make_user_prompt(title, category, protected_text)}
    ]
    
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
        "top_p": 0.9,
    }).encode()
    
    url = f"{api_base}/v1/chat/completions"
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                translated = result["choices"][0]["message"]["content"].strip()
                
                # Restore placeholders
                translated = restore_links(translated, placeholders)
                return translated
                
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt+1}/{max_retries} after error: {e}", file=sys.stderr)
                time.sleep(wait)
            else:
                raise


# --- Essay Metadata ---
def parse_essay_metadata(md_text: str, filename: str) -> dict:
    """Extract title, date, category from the MD file."""
    lines = md_text.strip().split('\n')
    
    title = filename.replace('-', ' ').replace('.md', '')
    date = ""
    category = ""
    
    for line in lines[:5]:
        # Title is usually the first ## heading
        if line.startswith('## '):
            title = line[3:].strip()
        # Date line
        elif re.match(r'^[A-Z][a-z]+ \d+, \d{4}', line.strip()):
            date = line.strip()
    
    # Try to get category from the footer navigation
    for line in reversed(lines[-10:]):
        if 'slatestarcodexabridged.com/' in line and 'Home' not in line:
            m = re.search(r'\[([^\]]+)\]', line)
            if m:
                category = m.group(1)
                break
    
    return {"title": title, "date": date, "category": category}


# --- Main Translation Function ---
def translate_essay(md_path: Path, api_base: str, model: str,
                    force: bool = False) -> str:
    """Translate a single essay MD file, return translated markdown."""
    
    slug = md_path.stem
    md_text = md_path.read_text()
    meta = parse_essay_metadata(md_text, md_path.name)
    
    print(f"\n{'='*60}")
    print(f"Translating: {meta['title']}")
    print(f"Category: {meta['category']}")
    print(f"File: {slug}.md")
    
    # Split into paragraphs
    paragraphs = split_into_paragraphs(md_text)
    translate_blocks = [p for p in paragraphs if p["type"] == "translate"]
    print(f"Total blocks: {len(paragraphs)}, translatable: {len(translate_blocks)}")
    
    # Load cache
    cache = {} if force else load_cache(slug)
    cached_count = 0
    
    # Translate each paragraph
    results = []
    for i, para in enumerate(paragraphs):
        if para["type"] == "preserve":
            results.append(para["text"])
            continue
        
        text = para["text"]
        h = paragraph_hash(text)
        
        if h in cache:
            results.append(cache[h])
            cached_count += 1
            continue
        
        # Translate
        block_idx = sum(1 for p in paragraphs[:i] if p["type"] == "translate")
        print(f"  [{block_idx+1}/{len(translate_blocks)}] Translating block (line {para['line_start']})...", end=" ", flush=True)
        
        try:
            translated = translate_paragraph(
                text, meta["title"], meta.get("category", ""),
                api_base, model
            )
            cache[h] = translated
            results.append(translated)
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
            results.append(text)  # Keep original on failure
        
        # Save cache periodically
        if (block_idx + 1) % 10 == 0:
            save_cache(slug, cache)
    
    # Final cache save
    save_cache(slug, cache)
    
    if cached_count > 0:
        print(f"  Used {cached_count} cached translations")
    
    translated_md = '\n'.join(results)
    
    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{slug}.md"
    out_path.write_text(translated_md)
    print(f"  Written to: {out_path}")
    
    return translated_md


# --- CLI ---
def main():
    parser = argparse.ArgumentParser(description="Translate SSC essays to Korean")
    parser.add_argument("essays", nargs="*", help="Essay slugs to translate (default: all)")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--force", action="store_true", help="Ignore cache, retranslate everything")
    parser.add_argument("--list", action="store_true", help="List available essays")
    parser.add_argument("--source-dir", default=str(SOURCE_DIR), help="Source MD directory")
    
    args = parser.parse_args()
    source = Path(args.source_dir)
    
    if args.list:
        for f in sorted(source.glob("*.md")):
            md = f.read_text()
            words = len(md.split())
            print(f"  {f.stem:<60s} {words:>6d} words")
        return
    
    essays = args.essays
    if not essays:
        # Translate all
        essays = [f.stem for f in sorted(source.glob("*.md"))]
    
    total_start = time.time()
    
    for slug in essays:
        md_path = source / f"{slug}.md"
        if not md_path.exists():
            print(f"ERROR: {md_path} not found", file=sys.stderr)
            continue
        
        translate_essay(md_path, args.api_base, args.model, args.force)
    
    elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
