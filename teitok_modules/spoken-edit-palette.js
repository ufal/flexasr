// spoken-edit: the actions and keys window. Every action of the editor as a button (with its key), in a window that
// can be dragged and is opened from an icon in the bar (or with ?). The buttons do what the keys do; they never
// take the focus away from the editor, so the cursor stays where it is.
var SE = window.SE = window.SE || {};
SE.palette = (function () {
	var GROUPS = [
		["Move", ["left", "right", "up", "down", "home", "end", "extendLeft", "extendRight"]],
		["Utterance", ["split", "mergeNext", "mergePrev", "movePrev", "moveNext", "detok", "tokenize", "detokAll", "tokAll"]],
		["Word", ["edit", "insertBefore", "insertAfter", "delete", "join", "extract"]],
		["Speaker", "speakers"],
		["Audio", ["play", "playUtt", "stop", "adjust"], "audio"],
		["Uncertain words", ["toggleConf", "nextLow", "prevLow", "accept"], "conf"],
		["File", ["undo", "redo", "save", "fullscreen"]]
	];
	var SHORT = {
		left: "‹ word", right: "word ›", up: "‹ utterance", down: "utterance ›", home: "first word", end: "last word", extendLeft: "‹ select", extendRight: "select ›", extract: "extract to new utterance",
		split: "split here", mergeNext: "merge with next", mergePrev: "merge with previous",
		movePrev: "this word and before → previous", moveNext: "this word and after → next",
		detok: "detokenize", tokenize: "tokenize", detokAll: "detokenize speaker", tokAll: "tokenize speaker",
		edit: "edit", insertBefore: "insert before", insertAfter: "insert after", delete: "delete", join: "join with next",
		play: "play / pause", playUtt: "play utterance", stop: "stop", adjust: "adjust times",
		toggleConf: "show / hide marking", nextLow: "next uncertain", prevLow: "previous uncertain", accept: "accept",
		undo: "undo", redo: "redo", save: "save", fullscreen: "full screen"
	};
	var KEY = "spoken-edit-palette", opts, win, body, toggleB, buttons = {}, speakerBox, pos = { x: null, y: null, open: false };

	function el ( tag, cls, text ) { var e = document.createElement(tag); if ( cls ) e.className = cls; if ( text !== undefined ) e.textContent = text; return e; }
	function load () { try { var v = JSON.parse(localStorage.getItem(KEY) || "null"); if ( v ) pos = v; } catch ( e ) {} }
	function store () { try { localStorage.setItem(KEY, JSON.stringify(pos)); } catch ( e ) {} }

	// inside the viewport, also after a resize, a smaller screen than last time or full screen on / off. While it is
	// dragged (loose) it may go partly off the screen; when let go it snaps back so that all of it can be seen.
	function place ( loose ) {
		var w = win.offsetWidth || 300, h = win.offsetHeight || 200;
		var x = pos.x === null ? Math.max(8, window.innerWidth - w - 24) : pos.x, y = pos.y === null ? 80 : pos.y;
		var fw = loose ? Math.min(w, 120) : w, fh = loose ? 40 : h;
		x = Math.min(Math.max(0, x), Math.max(0, window.innerWidth - fw));
		y = Math.min(Math.max(0, y), Math.max(0, window.innerHeight - fh));
		pos.x = x; pos.y = y;                  // what is kept is what is shown (never off the screen)
		win.style.left = x + "px"; win.style.top = y + "px";
	}

	function drag ( head ) {
		head.addEventListener("pointerdown", function ( ev ) {
			if ( ev.target.closest("button") ) return;
			var dx = ev.clientX - win.offsetLeft, dy = ev.clientY - win.offsetTop;
			head.setPointerCapture(ev.pointerId); ev.preventDefault();
			function move ( e ) { pos.x = e.clientX - dx; pos.y = e.clientY - dy; place(true); }
			function up () { head.removeEventListener("pointermove", move); head.removeEventListener("pointerup", up); head.removeEventListener("pointercancel", up); place(); store(); }
			head.addEventListener("pointermove", move); head.addEventListener("pointerup", up); head.addEventListener("pointercancel", up);
		});
	}

	function actionButton ( action, label ) {
		var info = SE.keys.info(action), b = el("button");
		b.type = "button"; b.tabIndex = -1; b.title = info ? info.text : "";
		b.appendChild(el("span", "se-pl", label || SHORT[action] || action));
		if ( info ) b.appendChild(el("kbd", "", SE.keys.label(info.key)));
		b.addEventListener("mousedown", function ( ev ) { ev.preventDefault(); });      // keep the focus in the editor
		b.addEventListener("click", function () { opts.run(action); opts.focus(); });
		return b;
	}

	function drawSpeakers () {
		speakerBox.textContent = "";
		opts.speakers().slice(0, 9).forEach(function ( id, k ) {
			var b = el("button"); b.type = "button"; b.tabIndex = -1; b.title = "speaker " + (k + 1) + " for this utterance";
			b.appendChild(el("span", "se-pl", id)); b.appendChild(el("kbd", "", String(k + 1)));
			b.addEventListener("mousedown", function ( ev ) { ev.preventDefault(); });
			b.addEventListener("click", function () { opts.run("who" + (k + 1)); opts.focus(); });
			speakerBox.appendChild(b);
		});
	}

	function build () {
		win = el("div", "se-palette"); win.hidden = true; win.setAttribute("role", "dialog"); win.setAttribute("aria-label", "Actions and keys");
		var head = el("div", "se-pal-head"), close = el("button", "", "×");
		head.appendChild(el("span", "", "Actions and keys")); close.type = "button"; close.title = "close (?)"; close.tabIndex = -1;
		close.addEventListener("click", function () { api.toggle(false); opts.focus(); }); head.appendChild(close); win.appendChild(head); drag(head);
		body = el("div", "se-pal-body"); win.appendChild(body);
		var VIEW = { left: 1, right: 1, up: 1, down: 1, home: 1, end: 1, play: 1, playUtt: 1, stop: 1, toggleConf: 1, nextLow: 1, prevLow: 1, fullscreen: 1 };
		if ( opts.readonly ) speakerBox = el("div");
		GROUPS.forEach(function ( g ) {
			if ( opts.readonly && g[1] === "speakers" ) return;
			if ( g[2] === "audio" && !opts.audio ) return;
			if ( g[2] === "conf" && !opts.hasconf ) return;
			var sec = el("div", "se-pal-group"); sec.appendChild(el("div", "se-pal-title", g[0]));
			var row = el("div", "se-pal-row");
			if ( g[1] === "speakers" ) { speakerBox = row; }
			else g[1].forEach(function ( a ) { if ( opts.readonly && !VIEW[a] ) return; var b = actionButton(a); buttons[a] = b; row.appendChild(b); });
			if ( row.childNodes.length || g[1] === "speakers" ) { sec.appendChild(row); body.appendChild(sec); }
		});
		drawSpeakers();
		document.body.appendChild(win);
		window.addEventListener("resize", function () { if ( !win.hidden ) place(); });
	}

	var api = {
		// the window has to live inside the full screen element to be seen in full screen
		mount: function ( parent ) { if ( win && win.parentNode !== parent ) { parent.appendChild(win); if ( !win.hidden ) place(); } },
		// opts: { run(action), focus(), speakers() -> ids, audio, hasconf }; returns the icon button for the bar
		init: function ( o ) {
			opts = o; load(); build();
			toggleB = el("button", "", "⌨"); toggleB.type = "button"; toggleB.title = "actions and keys (?)"; toggleB.setAttribute("aria-expanded", "false");
			toggleB.addEventListener("click", function () { api.toggle(); opts.focus(); });
			if ( pos.open ) api.toggle(true);
			return toggleB;
		},
		toggle: function ( on ) {
			on = on === undefined ? win.hidden : !!on;
			win.hidden = !on; toggleB.setAttribute("aria-expanded", on ? "true" : "false");
			if ( on ) place();
			pos.open = on; store();
		},
		// the state of the buttons that depend on it: { undo, redo, save } true when the action is possible, { conf } whether the
		// marking of uncertain words is shown (the buttons not named keep their state)
		sync: function ( st ) {
			["undo", "redo", "save"].forEach(function ( a ) { if ( st[a] !== undefined && buttons[a] ) buttons[a].disabled = !st[a]; });
			if ( st.conf !== undefined && buttons.toggleConf ) buttons.toggleConf.classList.toggle("se-on", !!st.conf);
			drawSpeakers();
		}
	};
	return api;
})();
