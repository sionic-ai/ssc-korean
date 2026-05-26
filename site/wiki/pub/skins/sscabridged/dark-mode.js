if (window.GW == null)
	window.GW = { };

if (GW.mediaQueries == null)
	GW.mediaQueries = { };

GW.mediaQueries.mobileNarrow = matchMedia("(max-width: 520px)");
GW.mediaQueries.systemDarkModeActive = matchMedia("(prefers-color-scheme: dark)");

GW.modeOptions = [
	[ 'auto', 'Auto', 'Set light or dark mode automatically, according to system-wide setting' ], 
	[ 'light', 'Light', 'Light mode at all times' ], 
	[ 'dark', 'Dark', 'Dark mode at all times' ]
];
GW.modeStyles = `
	:root {
		--ssca-body-background-color: #000;

		--ssca-header-hyperlink-color: #2655a5;
		--ssca-header-hyperlink-color-hover: #7e9eda;
	}
	#wikitext {
		color: #ccc;
	}
	hr::after {
		color: #ddd;
	}
	blockquote {
		border-color: #666;
	}
	h2 + p::after,
	.trail-nav::before {
		filter: drop-shadow(0 0 1px #aaa);
	}
	.searchbox {
		background-color: #000;
		color: #ccc;
	}

	#ui-elements-container {
		filter: invert(90%);
	}
	#mode-selector button {
		text-shadow: 0 0 0 #000;
	}
	#mode-selector {
		opacity: 0.6;
	}
	#mode-selector:hover {
		background-color: #fff;
	}
`;

/****************/
/* DEBUG OUTPUT */
/****************/

function GWLog (string) {
	if (GW.loggingEnabled || localStorage.getItem("logging-enabled") == "true")
		console.log(string);
}

/***********/
/* HELPERS */
/***********/

/*************************************************************************/
/*	Given an HTML string, creates an element from that HTML, adds it to 
	#ui-elements-container (creating the latter if it does not exist), and 
	returns the created element.
	*/
function addUIElement(element_html) {
	var ui_elements_container = document.querySelector("#ui-elements-container");
	if (!ui_elements_container) {
		ui_elements_container = document.createElement("div");
		ui_elements_container.id = "ui-elements-container";
		document.querySelector("body").appendChild(ui_elements_container);
	}

	ui_elements_container.insertAdjacentHTML("beforeend", element_html);
	return ui_elements_container.lastElementChild;
}

/****************************************************************************/
/*	Run the given function immediately if the page is already loaded, or add
	a listener to run it as soon as the page loads.
	*/
function doWhenPageLoaded(f) {
	if (document.readyState == "complete")
		f();
	else
		window.addEventListener("load", f);
}

/******************************************************************************/
/*	Adds an event listener to a button (or other clickable element), attaching 
	it to both "click" and "keyup" events (for use with keyboard navigation).
	Optionally also attaches the listener to the 'mousedown' event, making the 
	element activate on mouse down instead of mouse up.
	*/
Element.prototype.addActivateEvent = function(func, includeMouseDown) {
	let ael = this.activateEventListener = (event) => { if (event.button === 0 || event.key === ' ') func(event) };
	if (includeMouseDown) this.addEventListener("mousedown", ael);
	this.addEventListener("click", ael);
	this.addEventListener("keyup", ael);
}

/********************************************/
/*	Adds a scroll event listener to the page.
	*/
function addScrollListener(fn, name) {
	let wrapper = (event) => {
		requestAnimationFrame(() => {
			fn(event);
			document.addEventListener("scroll", wrapper, { once: true, passive: true });
		});
	}
	document.addEventListener("scroll", wrapper, { once: true, passive: true });

	// Retain a reference to the scroll listener, if a name is provided.
	if (typeof name != "undefined")
		GW[name] = wrapper;
}

/************************/
/* ACTIVE MEDIA QUERIES */
/************************/

/*******************************************************************************/
/*	This function provides two slightly different versions of its functionality,
	depending on how many arguments it gets.

	If one function is given (in addition to the media query and its name), it
	is called whenever the media query changes (in either direction).

	If two functions are given (in addition to the media query and its name), 
	then the first function is called whenever the media query starts matching, 
	and the second function is called whenever the media query stops matching.

	If you want to call a function for a change in one direction only, pass an
	empty closure (NOT null!) as one of the function arguments.

	There is also an optional fifth argument. This should be a function to be 
	called when the active media query is canceled.
	*/
function doWhenMatchMedia(mediaQuery, name, ifMatchesOrAlwaysDo, otherwiseDo = null, whenCanceledDo = null) {
	if (typeof GW.mediaQueryResponders == "undefined")
		GW.mediaQueryResponders = { };

	let mediaQueryResponder = (event, canceling = false) => {
		if (canceling) {
			GWLog(`Canceling media query “${name}”`);

			if (whenCanceledDo != null)
				whenCanceledDo(mediaQuery);
		} else {
			let matches = (typeof event == "undefined") ? mediaQuery.matches : event.matches;

			GWLog(`Media query “${name}” triggered (matches: ${matches ? "YES" : "NO"})`);

			if (otherwiseDo == null || matches) ifMatchesOrAlwaysDo(mediaQuery);
			else otherwiseDo(mediaQuery);
		}
	};
	mediaQueryResponder();
	mediaQuery.addListener(mediaQueryResponder);

	GW.mediaQueryResponders[name] = mediaQueryResponder;
}

/******************************************************************************/
/*	Deactivates and discards an active media query, after calling the function
	that was passed as the whenCanceledDo parameter when the media query was
	added.
	*/
function cancelDoWhenMatchMedia(name) {
	GW.mediaQueryResponders[name](null, true);

	for ([ key, mediaQuery ] of Object.entries(GW.mediaQueries))
		mediaQuery.removeListener(GW.mediaQueryResponders[name]);

	GW.mediaQueryResponders[name] = null;
}

/******************/
/* MODE SELECTION */
/******************/

function injectModeSelector() {
	GWLog("injectModeSelector");
	
	// Get saved mode setting (or default).
	let currentMode = localStorage.getItem("selected-mode") || 'auto';

	// Inject the mode selector widget and activate buttons.
	let modeSelector = addUIElement(
		"<div id='mode-selector'>" +
		String.prototype.concat.apply("", GW.modeOptions.map(modeOption => {
			let [ name, label, desc ] = modeOption;
			let selected = (name == currentMode ? ' selected' : '');
			let disabled = (name == currentMode ? ' disabled' : '');
			return `<button type='button' class='select-mode-${name}${selected}'${disabled} tabindex='-1' data-name='${name}' title='${desc}'>${label}</button>`})) +
		"</div>");

	modeSelector.querySelectorAll("button").forEach(button => {
		button.addActivateEvent(GW.modeSelectButtonClicked = (event) => {
			GWLog("GW.modeSelectButtonClicked");

			// Determine which setting was chosen (i.e., which button was clicked).
			let selectedMode = event.target.dataset.name;

			// Save the new setting.
			if (selectedMode == "auto") localStorage.removeItem("selected-mode");
			else localStorage.setItem("selected-mode", selectedMode);

			// Actually change the mode.
			setMode(selectedMode);
		});
	});

	document.querySelector("head").insertAdjacentHTML("beforeend", `<style id='mode-selector-styles'>
	#ui-elements-container {
		position: fixed;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		z-index: 10000;
		pointer-events: none;
	}
	#ui-elements-container > * {
		pointer-events: auto;
	}
	#mode-selector {
		position: absolute;
		right: 3px;
		top: 4px;
		display: flex;
		background-color: #fff;
		padding: 0.125em 0.25em;
		border: 3px solid transparent;
		opacity: 0.4;
		transition:
			opacity 2s ease;
	}
	#mode-selector.hidden {
		opacity: 0;
	}	
	#mode-selector:hover {
		transition: none;
		opacity: 1.0;
		border: 3px double #aaa;
	}
	#mode-selector button {
		-moz-appearance: none;
		appearance: none;
		border: none;
		background-color: transparent;
		padding: 0.5em;
		margin: 0;
		line-height: 1;
		font-family: Lucida Sans Unicode, Helvetica, Trebuchet MS, sans-serif;
		font-size: 0.75rem;
		text-align: center;
		color: #777;
		position: relative;
	}
	#mode-selector button:hover,
	#mode-selector button.selected {
		box-shadow:
			0 2px 0 6px #fff inset,
			0 1px 0 6px currentColor inset;
	}
	#mode-selector button:not(:disabled):hover {
		color: #000;
		cursor: pointer;
	}
	#mode-selector button:not(:disabled):active {
		transform: translateY(2px);
		box-shadow:
			0 0px 0 6px #fff inset,
			0 -1px 0 6px currentColor inset;
	}
	#mode-selector button.active:not(:hover)::after {
		content: "";
		position: absolute;
		bottom: 0.25em;
		left: 0;
		right: 0;
		border-bottom: 1px dotted currentColor;
		width: calc(100% - 12px);
		margin: auto;
	}
	</style>`);

	document.querySelector("head").insertAdjacentHTML("beforeend", `<style id='mode-styles'></style>`);

	setMode(currentMode);

	// We pre-query the relevant elements, so we don’t have to run 
	// querySelectorAll on every firing of the scroll listener.
	GW.scrollState = {
		"lastScrollTop":					window.pageYOffset || document.documentElement.scrollTop,
		"unbrokenDownScrollDistance":		0,
		"unbrokenUpScrollDistance":			0,
		"modeSelector":						document.querySelectorAll("#mode-selector"),
	};
	addScrollListener(updateModeSelectorVisibility, "updateModeSelectorVisibilityScrollListener");
	GW.scrollState.modeSelector[0].addEventListener("mouseover", () => { showModeSelector(); });
	doWhenMatchMedia(GW.mediaQueries.systemDarkModeActive, "updateModeSelectorStateForSystemDarkMode", () => { updateModeSelectorState(); });
}

/******************************************************************************/
/*	Show/hide the mode selector in response to scrolling.

	Called by the ‘updateModeSelectorVisibilityScrollListener’ scroll listener.
	*/
function updateModeSelectorVisibility(event) {
	GWLog("updateModeSelectorVisibility");

	let newScrollTop = window.pageYOffset || document.documentElement.scrollTop;
	GW.scrollState.unbrokenDownScrollDistance = (newScrollTop > GW.scrollState.lastScrollTop) ? 
														(GW.scrollState.unbrokenDownScrollDistance + newScrollTop - GW.scrollState.lastScrollTop) : 
													 	0;
	GW.scrollState.unbrokenUpScrollDistance = (newScrollTop < GW.scrollState.lastScrollTop) ?
													 (GW.scrollState.unbrokenUpScrollDistance + GW.scrollState.lastScrollTop - newScrollTop) :
													 0;
	GW.scrollState.lastScrollTop = newScrollTop;

	// Hide mode selector when scrolling a full page down.
	if (GW.scrollState.unbrokenDownScrollDistance > window.innerHeight) {
		hideModeSelector();
	}

	// On desktop, show mode selector when scrolling to top of page, 
	// or a full page up.
	// On mobile, show mode selector on ANY scroll up.
	if (GW.mediaQueries.mobileNarrow.matches) {
		if (GW.scrollState.unbrokenUpScrollDistance > 0 || GW.scrollState.lastScrollTop <= 0)
			showModeSelector();
	} else if (   GW.scrollState.unbrokenUpScrollDistance > window.innerHeight
			   || GW.scrollState.lastScrollTop == 0) {
		showModeSelector();
	}
}

function hideModeSelector() {
	GWLog("hideModeSelector");

	GW.scrollState.modeSelector[0].classList.add("hidden");
}

function showModeSelector() {
	GWLog("showModeSelector");

	GW.scrollState.modeSelector[0].classList.remove("hidden");
}

/**************************************************/
/*	Update the states of the mode selector buttons.
	*/
function updateModeSelectorState() {
	// Get saved mode setting (or default).
	let currentMode = localStorage.getItem("selected-mode") || 'auto';

	// Clear current buttons state.
	let modeSelector = document.querySelector("#mode-selector");
	modeSelector.childNodes.forEach(button => {
		button.classList.remove("active", "selected");
		button.disabled = false;
	});

	// Set the correct button to be selected.
	modeSelector.querySelectorAll(`.select-mode-${currentMode}`).forEach(button => {
		button.classList.add("selected");
		button.disabled = true;
	});

	// Ensure the right button (light or dark) has the “currently active”
	// indicator, if the current mode is ‘auto’.
	if (currentMode == "auto") {
		if (GW.mediaQueries.systemDarkModeActive.matches)
			modeSelector.querySelector(".select-mode-dark").classList.add("active");
		else
			modeSelector.querySelector(".select-mode-light").classList.add("active");
	}
}

/************************************************/
/*	Set specified color mode (auto, light, dark).
	*/
function setMode(modeOption) {
	GWLog("setMode");

	// Inject the appropriate styles.
	let modeStyles = document.querySelector("#mode-styles");
	if (modeOption == 'auto') {
		modeStyles.innerHTML = `@media (prefers-color-scheme:dark) {${GW.modeStyles}}`;
	} else if (modeOption == 'dark') {
		modeStyles.innerHTML = GW.modeStyles;
	} else {
		modeStyles.innerHTML = "";
	}
	
	// Update selector state.
	updateModeSelectorState();
}

/******************/
/* INITIALIZATION */
/******************/

doWhenPageLoaded(() => {
	injectModeSelector();
});
