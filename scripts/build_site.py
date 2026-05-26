#!/usr/bin/env python3
"""
Build static HTML site from translated SSC Markdown files.

Uses the original SSC Abridged skin.css and dark-mode.js.
Generates index.html with category-based table of contents.
"""

import re
import json
from pathlib import Path
from html import escape

# --- Configuration ---
PROJECT_DIR = Path(__file__).parent.parent
SOURCE_DIR = PROJECT_DIR / "source"
TRANSLATED_DIR = PROJECT_DIR / "translated"
SITE_DIR = PROJECT_DIR / "site"

# Category structure from the original site
CATEGORIES = [
    {
        "num": "I",
        "title": "자유주의와 그 적들",
        "title_en": "Liberalism And its Enemies",
        "slug": "Liberalism-And-Its-Enemies",
        "essays": [
            "In-Favor-Of-Niceness-Community-And-Civilization",
            "Promising-The-Moon",
            "Reactionary-Philosophy-In-An-Enormous-Planet-Sized-Nutshell",
            "Archipelago-And-Atomic-Communitarianism",
            "Book-Review-On-The-Road",
            "The-Anti-Reactionary-FAQ",
        ]
    },
    {
        "num": "II",
        "title": "몰로크",
        "title_en": "Moloch",
        "slug": "Moloch",
        "essays": [
            "The-Non-Libertarian-FAQ",
            "Growing-Children-For-Bostroms-Disneyland",
            "Book-Review-Age-Of-Em",
            "Meditations-On-Moloch",
            "Book-Review-Red-Plenty",
            "The-Goddess-Of-Everything-Else",
        ]
    },
    {
        "num": "III",
        "title": "문화 전쟁",
        "title_en": "Culture War",
        "slug": "Culture-War",
        "essays": [
            "The-Toxoplasma-Of-Rage",
            "Beware-The-Man-Of-One-Study",
            "Infinite-Debt",
            "Bottomless-Pits-Of-Suffering",
            "Nydwracus-Fnords",
            "The-Virtue-Of-Silence",
            "Fundamental-Value-Differences-Are-Not-That-Fundamental",
            "Beware-Isolated-Demands-For-Rigor",
            "Society-Is-Fixed-Biology-Is-Mutable",
            "The-Parable-Of-The-Talents",
            "I-Can-Tolerate-Anything-Except-The-Outgroup",
            "Can-Things-Be-Both-Popular-And-Silenced",
            "Social-Censorship-The-First-Offender-Model",
            "Vote-On-Values-Outsource-Beliefs",
            "Weak-Men-Are-Superweapons",
            "How-Did-New-Atheism-Fail-So-Miserably",
            "The-Influenza-Of-Evil",
            "Guided-By-The-Beauty-Of-Our-Weapons",
            "Ethics-Offsets",
            "Sort-By-Controversial",
        ]
    },
    {
        "num": "IV",
        "title": "과학과 유사과학",
        "title_en": "Science and Pseudoscience",
        "slug": "Science-And-Pseudoscience",
        "essays": [
            "Epistemic-Learned-Helplessness",
            "If-Its-Worth-Doing-Its-Worth-Doing-With-Made-Up-Statistics",
            "Lizardmans-Constant-Is-4-Percent",
            "The-Control-Group-Is-Out-Of-Control",
            "Meat-Your-Doom",
            "SSC-Journal-Club-Expert-Prediction-Of-Experiments",
            "My-IRB-Nightmare",
            "Book-Review-The-Structure-Of-Scientific-Revolutions",
        ]
    },
    {
        "num": "V",
        "title": "정신의학, 심리학, 신경학",
        "title_en": "Psychiatry, Psychology, & Neurology",
        "slug": "Psychiatry-Psychology-And-Neurology",
        "essays": [
            "The-Phatic-And-The-Anti-Inductive",
            "CBT-In-The-Water-Supply",
            "Kerbal-Space-Program-And-The-Mote-In-Gods-Eye",
            "Tangles-And-Knots-On-Iodine-And-Cretins",
            "An-Iron-Curtain-Has-Descended-Upon-Psychopharmacology",
            "Who-By-Very-Slow-Decay",
            "What-Universal-Human-Experiences-Are-You-Missing-Without-Realizing-It",
            "Why-Were-Early-Psychedelicists-So-Weird",
        ]
    },
    {
        "num": "VI",
        "title": "의학",
        "title_en": "Medicine",
        "slug": "Medicine",
        "essays": [
            "Against-Tulip-Subsidies",
            "Considerations-On-Cost-Disease",
            "Cost-Disease-In-Medicine-The-Practical-Perspective",
        ]
    },
    {
        "num": "VII",
        "title": "사회학과 경제학",
        "title_en": "Sociology and Economics",
        "slug": "Sociology-And-Economics",
        "essays": [
            "Book-Review-Seeing-Like-A-State",
            "Book-Review-The-Secret-Of-Our-Success",
            "The-Atomic-Bomb-Considered-As-Hungarian-High-School-Science-Fair-Project",
            "Nonfiction-Writing-Advice",
            "The-Ideology-Is-Not-The-Movement",
            "Book-Review-Ages-Of-Discord",
            "Hungarian-Education-II-Four-Nobel-Truths",
            "1960-The-Year-The-Singularity-Was-Cancelled",
            "Book-Review-On-The-Road",
            "Bullshit-Jobs-Part-1-Of-Infinity",
            "What-Happened-To-90s-Environmentalism",
        ]
    },
    {
        "num": "VIII",
        "title": "권능, 완전한 정신 수정, 초지능, 포스트휴머니티",
        "title_en": "Powers, Complete Mental Revision, Ultraintelligence, Posthumanity",
        "slug": "Powers-Complete-Mental-Revision-Ultraintelligence-Posthumanity",
        "essays": [
            "Wirehead-Gods-On-Lotus-Thrones",
            "And-I-Show-You-How-Deep-The-Rabbit-Hole-Goes",
            "Answer-To-Job",
            "The-Hour-I-First-Believed",
            "Basic-Income-Not-Basic-Jobs-Against-Hijacking-Utopia",
            "Growing-Children-For-Bostroms-Disneyland",
        ]
    },
]


def markdown_to_html(md_text: str) -> str:
    """Simple markdown to HTML conversion for SSC essays.
    
    Handles: headers, paragraphs, bold, italic, links, images,
    blockquotes, lists, horizontal rules, code.
    """
    lines = md_text.split('\n')
    html_parts = []
    in_blockquote = False
    in_list = False
    in_code = False
    paragraph_buffer = []
    
    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            text = '\n'.join(paragraph_buffer)
            text = inline_format(text)
            html_parts.append(f'<p>{text}</p>')
            paragraph_buffer = []
    
    def inline_format(text):
        # Links [text](url)
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)
        # Reference links [text][N]
        text = re.sub(r'\[([^\]]+)\]\[(\d+)\]', r'<a href="#ref-\2">\1</a>', text)
        # Images ![alt](url)
        text = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', r'<img src="\2" alt="\1" />', text)
        # Bold **text** or __text__
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text)
        # Italic *text* or _text_
        text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
        text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<em>\1</em>', text)
        return text
    
    for line in lines:
        stripped = line.strip()
        
        # Code blocks
        if stripped.startswith('```'):
            if in_code:
                html_parts.append('</code></pre>')
                in_code = False
            else:
                flush_paragraph()
                html_parts.append('<pre><code>')
                in_code = True
            continue
        
        if in_code:
            html_parts.append(escape(line))
            continue
        
        # Empty line
        if not stripped:
            flush_paragraph()
            if in_blockquote:
                html_parts.append('</blockquote>')
                in_blockquote = False
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            continue
        
        # Headers
        m = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if m:
            flush_paragraph()
            level = len(m.group(1))
            text = inline_format(m.group(2))
            html_parts.append(f'<h{level}>{text}</h{level}>')
            continue
        
        # Horizontal rule
        if re.match(r'^[-*_]{3,}$', stripped):
            flush_paragraph()
            html_parts.append('<hr />')
            continue
        
        # Blockquote
        if stripped.startswith('> '):
            flush_paragraph()
            if not in_blockquote:
                html_parts.append('<blockquote>')
                in_blockquote = True
            text = inline_format(stripped[2:])
            html_parts.append(f'<p>{text}</p>')
            continue
        
        # List items
        if re.match(r'^[\*\-\+]\s', stripped):
            flush_paragraph()
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            text = inline_format(stripped[2:])
            html_parts.append(f'<li>{text}</li>')
            continue
        
        # Numbered list
        m = re.match(r'^(\d+)\.\s+(.*)', stripped)
        if m:
            flush_paragraph()
            if not in_list:
                html_parts.append('<ol>')
                in_list = True
            text = inline_format(m.group(2))
            html_parts.append(f'<li>{text}</li>')
            continue
        
        # Reference-style link definitions
        if re.match(r'^\s*\[\d+\]:\s*http', stripped):
            # Skip these, they're handled inline
            continue
        
        # Regular paragraph text
        paragraph_buffer.append(line)
    
    flush_paragraph()
    if in_blockquote:
        html_parts.append('</blockquote>')
    if in_list:
        html_parts.append('</ul>')
    
    return '\n'.join(html_parts)


def build_essay_page(slug: str, translated_md: str, meta: dict) -> str:
    """Build a full HTML page for a translated essay."""
    
    content_html = markdown_to_html(translated_md)
    
    # Extract title from the first ## heading
    title = slug.replace('-', ' ')
    m = re.search(r'^## (.+)$', translated_md, re.MULTILINE)
    if m:
        title = m.group(1)
    
    # Remove the title from content (it's in the template)
    content_html = re.sub(r'<h2>[^<]+</h2>', '', content_html, count=1)
    
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    <link href="attach/favicon.ico" type="image/png" rel="shortcut icon" />
    <link rel="stylesheet" type="text/css" href="wiki/pub/skins/sscabridged/skin.css" />
</head>
<body>
<!--PageHeaderFmt-->
    <div id="header">
        <a href="index.html" title="Slate Star Codex 요약본">Slate Star Codex <br> <span>요약본</span></a>
    </div>
<!--/PageHeaderFmt-->

<!--PageText-->
<div id="wikitext">
<h2>{escape(title)}</h2>
{content_html}
</div>

<!--PageFooterFmt-->
    <div id="footer">
        <a href="index.html" title="Slate Star Codex 요약본">Slate Star Codex 요약본</a>
        &middot;
        <a href="https://www.slatestarcodexabridged.com/{slug}" title="원문">원문 보기</a>
    </div>
<!--/PageFooterFmt-->

<script src="wiki/pub/skins/sscabridged/dark-mode.js"></script>
</body>
</html>"""


def build_index_page(categories: list, available_essays: set) -> str:
    """Build the index.html page with category-based table of contents."""
    
    toc_html = []
    for cat in categories:
        toc_html.append(f'<h2>{cat["num"]}. <a href="#">{cat["title"]}</a></h2>')
        toc_html.append(f'<p class="category-subtitle">{cat["title_en"]}</p>')
        toc_html.append('<ul>')
        for slug in cat["essays"]:
            if slug in available_essays:
                # Try to get Korean title from translated file
                title = slug.replace('-', ' ')
                translated_path = TRANSLATED_DIR / f"{slug}.md"
                if translated_path.exists():
                    md = translated_path.read_text()
                    m = re.search(r'^## (.+)$', md, re.MULTILINE)
                    if m:
                        title = m.group(1)
                toc_html.append(f'  <li><a href="{slug}.html">{title}</a></li>')
            else:
                title = slug.replace('-', ' ')
                toc_html.append(f'  <li><span class="not-yet">{title} (번역 예정)</span></li>')
        toc_html.append('</ul>')
    
    toc = '\n'.join(toc_html)
    
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Slate Star Codex 요약본 — 한국어</title>
    <link href="attach/favicon.ico" type="image/png" rel="shortcut icon" />
    <link rel="stylesheet" type="text/css" href="wiki/pub/skins/sscabridged/skin.css" />
    <style>
        .not-yet {{ color: #999; }}
        .category-subtitle {{ font-size: 0.85em; color: #666; margin-top: -0.5em; }}
    </style>
</head>
<body>
<!--PageHeaderFmt-->
    <div id="header">
        <a href="index.html" title="Slate Star Codex 요약본">Slate Star Codex <br> <span>요약본</span></a>
    </div>
<!--/PageHeaderFmt-->

<!--PageText-->
<div id="wikitext" class="toc">
<h2>Slate Star Codex 요약본에 오신 것을 환영합니다</h2>
<p>이 사이트는 정신과 의사이자 작가인 스콧 알렉산더(Scott Alexander)가 그의 블로그 <em>Slate Star Codex</em>에 쓴 최고의 에세이들을 한국어로 번역한 것입니다.</p>
<p>원문은 <a href="https://www.slatestarcodexabridged.com/">Slate Star Codex Abridged</a>에서 볼 수 있으며, <a href="https://creativecommons.org/licenses/by/4.0/">Creative Commons BY</a> 라이선스에 따라 제공됩니다.</p>
<hr />
{toc}
</div>

<!--PageFooterFmt-->
    <div id="footer">
        <a href="index.html" title="Slate Star Codex 요약본">Slate Star Codex 요약본</a>
    </div>
<!--/PageFooterFmt-->

<script src="wiki/pub/skins/sscabridged/dark-mode.js"></script>
</body>
</html>"""


def build_site():
    """Build the complete static site."""
    
    # Find all translated essays
    translated_files = list(TRANSLATED_DIR.glob("*.md"))
    available = {f.stem for f in translated_files}
    print(f"Found {len(available)} translated essays")
    
    # Build essay pages
    for md_path in translated_files:
        slug = md_path.stem
        md_text = md_path.read_text()
        
        # Parse basic metadata
        meta = {"title": slug.replace('-', ' ')}
        
        html = build_essay_page(slug, md_text, meta)
        out_path = SITE_DIR / f"{slug}.html"
        out_path.write_text(html)
        print(f"  Built: {slug}.html")
    
    # Build index
    index_html = build_index_page(CATEGORIES, available)
    (SITE_DIR / "index.html").write_text(index_html)
    print(f"  Built: index.html")
    
    print(f"\nSite built in: {SITE_DIR}")


if __name__ == "__main__":
    build_site()
