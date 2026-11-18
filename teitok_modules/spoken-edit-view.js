// spoken-edit: drawing the utterances, the cursor, the uncertain words, and editing a word in place
var SE = window.SE = window.SE || {};
SE.view = (function () {
	var root, list, cfg, cur = { u: 0, i: 0 }, hl = null, lowconf = 0.7, nowEl = null, sel = null;
	var PALETTE = ["#1f6feb", "#b8860b", "#2e7d32", "#8e24aa", "#c62828", "#00838f", "#6d4c41", "#455a64"];

	function el ( tag, cls, text ) { var e = document.createElement(tag); if ( cls ) e.className = cls; if ( text !== undefined ) e.textContent = text; return e; }
	function fmt ( t ) { if ( t === null || t === undefined ) return ""; var m = Math.floor(t / 60), s = t - m * 60; return m + ":" + (s < 10 ? "0" : "") + s.toFixed(1); }

	function color ( data, who ) {
		var k = 0;
		data.speakers.forEach(function ( p, n ) { if ( p.id === who ) k = n; });
		return PALETTE[k % PALETTE.length];
	}
	function uncertain ( it ) { return it.c !== undefined && it.c < lowconf && !it.rv; }

	function drawItem ( it, ui, ii ) {
		var s;
		if ( it.k === "tok" || it.k === "word" ) { s = el("span", "se-w", it.t); if ( uncertain(it) ) { s.classList.add("se-low"); s.style.setProperty("--se-conf", (1 - it.c / lowconf).toFixed(2)); s.title = "confidence " + it.c.toFixed(2); } else if ( it.c !== undefined ) s.title = "confidence " + it.c.toFixed(2); if ( it.rv ) s.classList.add("se-rv"); if ( it.k === "word" ) s.classList.add("se-plainw"); }
		else if ( it.k === "pause" ) s = el("span", "se-pause", "⏸" + (it.x && it.x.dur ? " " + parseFloat(it.x.dur).toFixed(1) : ""));
		else if ( it.k === "vocal" ) s = el("span", "se-vocal", "♪ " + (it.t || (it.x && it.x.orig) || "vocal"));
		else if ( it.k === "incident" ) s = el("span", "se-vocal", "⚑ " + (it.t || "incident"));
		else if ( it.k === "del" ) { s = el("span", "se-del", it.t); s.title = (it.x && it.x.reason) || "deleted"; }
		else s = el("span", "se-other", it.k === "other" ? "…" : "‹" + it.k + "›");
		if ( it.g ) s.classList.add("se-glue");
		s.dataset.u = ui; s.dataset.i = ii;
		return s;
	}

	function drawU ( data, u, ui ) {
		var row = el("div", "se-u"), who = el("button", "se-who", u.who || "?");
		row.dataset.u = ui;
		who.style.background = color(data, u.who); who.title = "speaker (1–9 to change)"; who.dataset.u = ui; who.dataset.act = "who";
		row.appendChild(el("span", "se-time", fmt(u.s))); row.appendChild(who);
		var body = el("div", "se-body"); if ( u.plain ) body.classList.add("se-plain");
		u.items.forEach(function ( it, ii ) { body.appendChild(drawItem(it, ui, ii)); });
		if ( !u.items.length ) body.appendChild(el("span", "se-empty", "—"));
		row.appendChild(body);
		return row;
	}

	function itemEl ( u, i ) { return list.querySelector('.se-body > [data-u="' + u + '"][data-i="' + i + '"]'); }

	return {
		init: function ( rootEl, c ) { root = rootEl; cfg = c; lowconf = c.lowconf; },
		setList: function ( l ) { list = l; },
		lowconf: function ( v ) { if ( v !== undefined ) lowconf = v; return lowconf; },
		cursor: function () { return cur; },
		// some items of one utterance, in any combination (a run, or single ones added with ⌘/Ctrl-click): { u, set (sorted
		// item numbers), anchor (where a shift-click or shift-arrow range starts) }
		selection: function () { return sel; },
		select: function ( u, indices, anchor ) {
			SE.view.clearSelection();
			var set = indices.slice().sort(function ( x, y ) { return x - y; }).filter(function ( v, k, all ) { return k === 0 || v !== all[k - 1]; });
			sel = { u: u, set: set, anchor: anchor };
			set.forEach(function ( k ) { var e = itemEl(u, k); if ( e ) e.classList.add("se-sel"); });
		},
		clearSelection: function () {
			if ( !sel ) return;
			list.querySelectorAll(".se-sel").forEach(function ( e ) { e.classList.remove("se-sel"); });
			sel = null;
		},
		setCursor: function ( u, i, noscroll, keepSelection ) {
			var d = SE.model.data(); if ( !d.us.length ) return;
			u = Math.max(0, Math.min(d.us.length - 1, u)); i = Math.max(0, Math.min(Math.max(0, d.us[u].items.length - 1), i));
			cur = { u: u, i: i };
			if ( !keepSelection ) SE.view.clearSelection();
			var old = list.querySelector(".se-cur"); if ( old ) old.classList.remove("se-cur");
			var oldu = list.querySelector(".se-ucur"); if ( oldu ) oldu.classList.remove("se-ucur");
			var e = itemEl(u, i), row = list.children[u];
			if ( row ) row.classList.add("se-ucur");
			if ( e ) { e.classList.add("se-cur"); if ( !noscroll ) SE.view.reveal(e); }
			else if ( row && !noscroll ) SE.view.reveal(row);
		},
		reveal: function ( e ) {
			var r = e.getBoundingClientRect(), h = window.innerHeight;
			if ( r.top < 120 || r.bottom > h - 60 ) window.scrollTo({ top: window.scrollY + r.top - h / 3, behavior: "auto" });
		},
		render: function () {
			var d = SE.model.data(); list.textContent = "";
			var frag = document.createDocumentFragment();
			d.us.forEach(function ( u, ui ) { frag.appendChild(drawU(d, u, ui)); });
			list.appendChild(frag);
			SE.view.setCursor(cur.u, cur.i, true);
		},
		// the uncertain words, least certain first: array of {u, i, c}
		uncertainList: function () {
			var out = [];
			SE.model.data().us.forEach(function ( u, ui ) { u.items.forEach(function ( it, ii ) { if ( uncertain(it) ) out.push({ u: ui, i: ii, c: it.c }); }); });
			out.sort(function ( a, b ) { return a.c - b.c; });
			return out;
		},
		// the word being played
		follow: function ( t ) {
			var d = SE.model.data(), found = null;
			if ( t !== null ) for ( var ui = 0; ui < d.us.length && !found; ui++ ) {
				var u = d.us[ui]; if ( u.s !== null && (t < u.s - 0.5 || (u.e !== null && t > u.e + 0.5)) ) continue;
				for ( var ii = 0; ii < u.items.length; ii++ ) { var it = u.items[ii]; if ( it.s !== undefined && it.e !== undefined && t >= it.s && t < it.e ) { found = [ui, ii]; break; } }
			}
			var e = found ? itemEl(found[0], found[1]) : null;
			if ( e === nowEl ) return;
			if ( nowEl ) nowEl.classList.remove("se-now");
			nowEl = e; if ( e ) { e.classList.add("se-now"); SE.view.reveal(e); }
		},
		// the start of an item in seconds: its own, else that of the closest timed item before it in the utterance, else the utterance's
		timeOf: function ( u, i ) {
			var us = SE.model.data().us[u]; if ( !us ) return null;
			for ( var k = i; k >= 0; k-- ) if ( us.items[k] && us.items[k].s !== undefined && us.items[k].s !== null ) return us.items[k].s;
			for ( k = i; k < us.items.length; k++ ) if ( us.items[k].s !== undefined && us.items[k].s !== null ) return us.items[k].s;
			return us.s;
		},
		// edit the word at the cursor in place; done(text|null)
		edit: function ( u, i, text, done ) {
			var e = itemEl(u, i); if ( !e ) return done(null);
			var inp = el("input", "se-edit"); inp.value = text; inp.size = Math.max(4, text.length + 1);
			e.textContent = ""; e.appendChild(inp); inp.focus(); inp.select();
			var finished = false;
			function end ( v, how ) { if ( finished ) return; finished = true; done(v, how); }
			inp.addEventListener("input", function () { inp.size = Math.max(4, inp.value.length + 1); });
			inp.addEventListener("keydown", function ( ev ) {
				if ( ev.key === "Enter" ) { ev.preventDefault(); end(inp.value, "enter"); }
				else if ( ev.key === "Tab" ) { ev.preventDefault(); end(inp.value, ev.shiftKey ? "back" : "next"); }
				else if ( ev.key === "Escape" ) { ev.preventDefault(); end(null); }
				ev.stopPropagation();
			});
			inp.addEventListener("blur", function () { end(inp.value, "blur"); });
		}
	};
})();
