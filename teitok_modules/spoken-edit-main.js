// spoken-edit: the page: toolbar, speakers, and what each key does (the actions and keys window: spoken-edit-palette.js)
var SE = window.SE = window.SE || {};
SE.main = (function () {
	var busy = false, cfg, app, bar, msg, list, ask, speakersBox, counter, lowIdx = -1, undoB, redoB, saveB, confB, confOn = true;

	function el ( tag, cls, text ) { var e = document.createElement(tag); if ( cls ) e.className = cls; if ( text !== undefined ) e.textContent = text; return e; }
	function button ( label, title, fn ) { var b = el("button", "", label); b.type = "button"; b.title = title || ""; b.addEventListener("click", function () { fn(); app.focus(); }); return b; }
	// the marking of uncertain words can be hidden (to read the text as it is) and shown again; remembered in the browser
	function applyConf () {
		list.classList.toggle("se-noconf", !confOn);
		if ( confB ) { confB.classList.toggle("se-pressed", confOn); confB.setAttribute("aria-pressed", confOn ? "true" : "false"); }
		if ( SE.palette ) SE.palette.sync({ conf: confOn });
	}
	function say ( text, kind ) { msg.textContent = text || ""; msg.className = "se-msg" + (kind ? " se-" + kind : ""); }
	function data () { return SE.model.data(); }
	function curU () { var c = SE.view.cursor(); return data().us[c.u]; }

	// run an operation; where the cursor goes afterwards: cursorFn(oldData, newData) -> [u, i]
	function exec ( op, cursorFn ) {
		var old = data(), c = SE.view.cursor();
		busy = true;
		return SE.model.run(op).then(function ( d ) {
			var at = cursorFn ? cursorFn(old, d, c) : [c.u, c.i];
			busy = false; SE.view.render(); SE.view.setCursor(at[0], at[1]); refresh(); say("");
			return d;
		}, function ( e ) { busy = false; say(e.message, "error"); throw e; });
	}
	function refresh () {
		var d = data(), n = SE.model.dirty();
		undoB.disabled = !SE.model.canUndo(); redoB.disabled = !SE.model.canRedo();
		saveB.textContent = n ? "Save (" + n + ")" : "Save"; saveB.classList.toggle("se-dirty", n > 0); saveB.disabled = !n || !cfg.canwrite;
		if ( SE.palette ) SE.palette.sync({ undo: SE.model.canUndo(), redo: SE.model.canRedo(), save: n > 0 && !!cfg.canwrite, conf: confOn });
		var low = SE.view.uncertainList(); counter.textContent = d.hasconf ? low.length + " uncertain" : "";
		drawSpeakers();
	}
	function who () { var u = curU(); return u ? u.who : ""; }
	function uid () { var u = curU(); return u ? u.id : ""; }
	function ci () { return SE.view.cursor().i; }
	function nitems ( d, u ) { return d.us[u] ? d.us[u].items.length : 0; }

	// a one-line question (insert a word, a speaker's id …); cb(text)
	function question ( label, value, cb ) {
		ask.textContent = ""; ask.hidden = false;
		var inp = el("input"); inp.value = value || ""; inp.size = 30;
		ask.appendChild(el("label", "", label + " ")); ask.appendChild(inp); inp.focus(); inp.select();
		function close () { ask.hidden = true; ask.textContent = ""; app.focus(); }
		inp.addEventListener("keydown", function ( ev ) {
			ev.stopPropagation();
			if ( ev.key === "Enter" ) { var v = inp.value; close(); cb(v); }
			else if ( ev.key === "Escape" ) close();
		});
	}

	function editWord ( u, i, then ) {
		var us = data().us[u]; if ( !us || !us.items[i] ) return;
		var it = us.items[i];
		if ( it.k !== "tok" && it.k !== "word" ) return say("Only words can be edited; Delete removes this one.", "info");
		SE.view.edit(u, i, it.t, function ( text, how ) {
			if ( text === null || text === it.t ) { SE.view.render(); SE.view.setCursor(u, i, true); app.focus(); if ( how === "next" ) next(); return; };
			exec({ op: "edit", u: us.id, i: i, text: text }, function ( o, d ) { var step = how === "next" ? 1 : (how === "back" ? -1 : 0); return [u, Math.max(0, i + step)]; })
				.then(function () { if ( how === "next" || how === "back" ) startEdit(); else app.focus(); }, function () { SE.view.render(); SE.view.setCursor(u, i); });
		});
	}
	function startEdit () { var c = SE.view.cursor(); editWord(c.u, c.i); }
	function next () { var c = SE.view.cursor(); SE.view.setCursor(c.u, c.i + 1); startEdit(); }

	function step ( d ) {      // one item on, across utterances
		var c = SE.view.cursor(), us = data().us;
		var i = c.i + d, u = c.u;
		if ( i < 0 ) { if ( u === 0 ) return; u--; i = nitems(data(), u) - 1; }
		else if ( i >= nitems(data(), u) ) { if ( u >= us.length - 1 ) return; u++; i = 0; }
		SE.view.setCursor(u, i);
	}
	function jumpLow ( dir ) {
		var low = SE.view.uncertainList(); if ( !low.length ) return say("");
		lowIdx = (lowIdx + dir + low.length) % low.length;
		var t = low[lowIdx]; SE.view.setCursor(t.u, t.i);
		say("confidence " + t.c.toFixed(2) + " — " + (lowIdx + 1) + " of " + low.length, "info");
	}
	function whoNumber ( n ) {
		var p = data().speakers[n - 1]; if ( !p ) return;
		exec({ op: "set_who", u: uid(), who: p.id });
	}
	function allOf ( op, label ) {
		var w = who(), n = data().us.filter(function ( u ) { return u.who === w; }).length;
		if ( !confirm(label + " all " + n + " utterances of " + w + "?") ) return;
		exec({ op: op, who: w });
	}

	// open at a word (tid=) or, when the id is an utterance's, at its first word
	function openAt ( id ) {
		var us = data().us;
		for ( var u = 0; u < us.length; u++ ) {
			for ( var i = 0; i < us[u].items.length; i++ ) if ( us[u].items[i].id === id ) return SE.view.setCursor(u, i);      // (a third argument would mean: do not scroll)
			if ( us[u].id === id ) return SE.view.setCursor(u, 0);
		}
	}

	function range ( x, y ) { var r = []; for ( var k = Math.min(x, y); k <= Math.max(x, y); k++ ) r.push(k); return r; }
	// shift+arrow: the selection runs from where it started to one word further left or right (within the utterance)
	function extend ( dir ) {
		var c = SE.view.cursor(), sel = SE.view.selection(), n = curU().items.length;
		var anchor = sel && sel.u === c.u ? sel.anchor : c.i, head = Math.max(0, Math.min(n - 1, c.i + dir));
		SE.view.setCursor(c.u, head, false, true); SE.view.select(c.u, range(anchor, head), anchor);
	}
	// a click with shift (everything between the anchor and this word is added) or ⌘/Ctrl (this word is added or taken out)
	function clickSelect ( u, i, shift ) {
		var cc = SE.view.cursor(), sl = SE.view.selection(), same = sl && sl.u === u;
		var base = same ? sl.set.slice() : [cc.i], anchor = same ? sl.anchor : cc.i, set;
		if ( shift ) { set = base.slice(); range(anchor, i).forEach(function ( k ) { if ( set.indexOf(k) < 0 ) set.push(k); }); }
		else { set = base.filter(function ( k ) { return k !== i; }); if ( set.length === base.length ) set.push(i); anchor = i; }
		SE.view.setCursor(u, i, true, true);
		if ( set.length ) SE.view.select(u, set, anchor); else SE.view.clearSelection();
	}

	var actions = {
		right: function () { step(1); }, left: function () { step(-1); },
		down: function () { var c = SE.view.cursor(); SE.view.setCursor(c.u + 1, 0); }, up: function () { var c = SE.view.cursor(); SE.view.setCursor(c.u - 1, 0); },
		home: function () { SE.view.setCursor(SE.view.cursor().u, 0); }, end: function () { SE.view.setCursor(SE.view.cursor().u, 1e9); },
		extendLeft: function () { extend(-1); }, extendRight: function () { extend(1); },
		// words of another speaker inside this utterance (simultaneous speech) into an utterance of their own: the selected
		// words, in any combination, or the word under the cursor; with two speakers it goes to the other one. The new
		// utterance is placed by its start time (before this one when it holds the first word), so the cursor follows it
		extract: function () {
			var c = SE.view.cursor(), u = curU(), sel = SE.view.selection(), spk = data().speakers, who = "";
			var idx = sel && sel.u === c.u ? sel.set : [c.i];
			if ( spk.length === 2 ) who = spk[0].id === u.who ? spk[1].id : spk[0].id;
			exec({ op: "extract", u: uid(), idx: idx, who: who }, function ( o, d ) {
				var seen = {}; o.us.forEach(function ( x ) { seen[x.id] = 1; });
				for ( var k = 0; k < d.us.length; k++ ) if ( !seen[d.us[k].id] ) return [k, 0];
				return [c.u, 0];
			}).then(function () {
				if ( !who ) say("The new utterance has the same speaker: press 1–9 to change it.", "info");
			}, function () {});
		},
		edit: function () { startEdit(); },
		delete: function () { exec({ op: "delete", u: uid(), i: ci() }, function ( o, d, c ) { return d.us.length < o.us.length ? [Math.min(c.u, d.us.length - 1), 0] : [c.u, c.i]; }); },
		insertBefore: function () { question("Insert before:", "", function ( t ) { if ( t.trim() ) exec({ op: "insert", u: uid(), i: ci(), text: t }); }); },
		insertAfter: function () { question("Insert after:", "", function ( t ) { if ( t.trim() ) exec({ op: "insert", u: uid(), i: ci() + 1, text: t }, function ( o, d, c ) { return [c.u, c.i + 1]; }); }); },
		join: function () { exec({ op: "merge_words", u: uid(), i: ci() }); },
		movePrev: function () {
			exec({ op: "move_prev", u: uid(), i: ci() }, function ( o, d, c ) {
				return d.us.length < o.us.length ? [Math.max(0, c.u - 1), 1e9] : [c.u, 0];
			});
		},
		moveNext: function () {
			exec({ op: "move_next", u: uid(), i: ci() }, function ( o, d, c ) {
				return d.us.length < o.us.length ? [c.u, 0] : [c.u, 1e9];
			});
		},
		split: function () { exec({ op: "split", u: uid(), i: ci() }, function ( o, d, c ) { return [c.u + 1, 0]; }); },
		mergeNext: function () { exec({ op: "merge", u: uid() }); },
		mergePrev: function () { var c = SE.view.cursor(), p = data().us[c.u - 1]; if ( p ) exec({ op: "merge", u: p.id }, function ( o, d, cc ) { return [cc.u - 1, nitems(o, cc.u - 1) + cc.i]; }); },
		detok: function () { exec({ op: "detok", u: uid() }); }, tokenize: function () { exec({ op: "tok", u: uid() }); },
		detokAll: function () { allOf("detok_who", "Detokenize"); }, tokAll: function () { allOf("tok_who", "Tokenize"); },
		accept: function () { exec({ op: "accept", u: uid(), i: ci() }).then(function () { lowIdx = Math.max(-1, lowIdx - 1); jumpLow(1); }); },
		nextLow: function () { jumpLow(1); }, prevLow: function () { jumpLow(-1); },
		toggleConf: function () {
			if ( !data().hasconf ) return say("This file has no word confidences.", "info");
			confOn = !confOn; applyConf();
			try { localStorage.setItem("spoken-edit-conf", confOn ? "1" : "0"); } catch ( e ) {}
			say(confOn ? "Marking of uncertain words on." : "Marking of uncertain words off (v shows it again).", "info");
		},
		play: function () {
			if ( !SE.audio.available() ) return say("The recording is not available.", "error");
			if ( SE.audio.playing() ) SE.audio.stop(); else { var c = SE.view.cursor(); SE.audio.playFrom(SE.view.timeOf(c.u, c.i) || 0); }
		},
		playUtt: function () { var u = curU(); if ( u && u.s !== null && SE.audio.available() ) SE.audio.playFrom(u.s, u.e); },
		stop: function () { SE.audio.stop(); SE.view.clearSelection(); say(""); },
		// the waveform editor (TEITOK's wavesurfer) opened at the word under the cursor: where the times of words and
		// utterances are dragged into place; it edits the saved file, so the edits here have to be saved first
		adjust: function () {
			if ( !cfg.waveedit ) return say("Log in to adjust the times.", "error");
			if ( SE.model.dirty() ) return say("Save first (Ctrl/⌘ S), then adjust the times.", "info");
			var u = curU(), c = SE.view.cursor(), it = u && u.items[c.i], id = it && it.id;
			if ( !id && u ) { var f = u.items.filter(function ( x ) { return x.id; })[0]; id = f && f.id; }
			window.location.href = cfg.waveedit + (id ? "&tid=" + encodeURIComponent(id) : "");
		},
		undo: function () { SE.model.undo().then(function () { SE.view.render(); refresh(); }, function ( e ) { say(e.message, "error"); }); },
		redo: function () { SE.model.redo().then(function () { SE.view.render(); refresh(); }, function ( e ) { say(e.message, "error"); }); },
		save: function () {
			if ( !cfg.canwrite ) return say("Log in to save.", "error");
			if ( !SE.model.dirty() ) return;
			say("Saving…", "info");
			SE.model.save().then(function () { SE.view.render(); refresh(); say("Saved.", "ok"); }, function ( e ) { say(e.message, "error"); });
		},
		fullscreen: function () {
			var fs = document.fullscreenElement || document.webkitFullscreenElement;
			if ( fs ) return (document.exitFullscreen || document.webkitExitFullscreen).call(document);
			var f = app.requestFullscreen || app.webkitRequestFullscreen;
			if ( !f ) return say("This browser cannot show the editor full screen.", "error");
			var r = f.call(app);
			if ( r && r.catch ) r.catch(function () { say("The browser did not allow full screen here.", "error"); });
		},
		help: function () { if ( SE.palette ) SE.palette.toggle(); }
	};
	for ( var n = 1; n <= 9; n++ ) (function ( n ) { actions["who" + n] = function () { whoNumber(n); }; })(n);

	function drawSpeakers () {
		var d = data(); speakersBox.textContent = "";
		var t = el("table", "se-spk"); var head = t.insertRow();
		["", "id", "label", "name", "role", "utterances", "merge into"].forEach(function ( h ) { head.appendChild(el("th", "", h)); });
		d.speakers.forEach(function ( p, k ) {
			var r = t.insertRow(), c0 = r.insertCell(); c0.textContent = k < 9 ? String(k + 1) : "";
			var idc = r.insertCell(); var idb = button(p.id, "rename this speaker", function () {
				question("New id for " + p.id + ":", p.id, function ( v ) { exec({ op: "rename_speaker", id: p.id, new: v.trim() }); });
			}); idc.appendChild(idb);
			r.insertCell().textContent = p.n;
			[["name", "set_name", "name"], ["role", "set_role", "role"]].forEach(function ( f ) {
				var inp = el("input"); inp.value = p[f[0]]; inp.size = 14; if ( f[0] === "role" ) inp.setAttribute("list", "se-roles");
				inp.addEventListener("change", function () { var o = { op: f[1], id: p.id }; o[f[2]] = inp.value; exec(o); });
				r.insertCell().appendChild(inp);
			});
			r.insertCell().textContent = p.count;
			var sel = el("select"); sel.appendChild(el("option", "", "—"));
			d.speakers.forEach(function ( q ) { if ( q.id !== p.id ) { var o = el("option", "", q.id); o.value = q.id; sel.appendChild(o); } });
			sel.addEventListener("change", function () { if ( sel.value && confirm("Merge " + p.id + " into " + sel.value + "?") ) exec({ op: "merge_speakers", from: p.id, to: sel.value }); else sel.value = ""; });
			r.insertCell().appendChild(sel);
		});
		speakersBox.appendChild(t);
		var dl = el("datalist"); dl.id = "se-roles"; ["interviewer", "interviewee", "speaker", "moderator", "participant"].forEach(function ( r ) { var o = el("option"); o.value = r; dl.appendChild(o); });
		speakersBox.appendChild(dl);
		speakersBox.appendChild(button("add a speaker", "", function () {
			question("Id of the new speaker:", "", function ( v ) { if ( v.trim() ) exec({ op: "add_speaker", id: v.trim() }); });
		}));
	}

	return {
		actions: actions,
		init: function ( c, d ) {
			cfg = c; app = document.getElementById("se-app"); SE.model.init(c, d);
			// first of all, so that nothing that goes wrong later takes the protection away: leaving with unsaved edits asks
			window.addEventListener("beforeunload", function ( ev ) { if ( SE.model.dirty() ) { ev.preventDefault(); ev.returnValue = ""; return ""; } });
			bar = el("div", "se-bar"); msg = el("div", "se-msg"); ask = el("div", "se-ask"); ask.hidden = true; list = el("div", "se-list");
			undoB = button("Undo", "Ctrl/⌘ Z", actions.undo); redoB = button("Redo", "Ctrl/⌘ Shift Z", actions.redo); saveB = button("Save", "Ctrl/⌘ S", actions.save);
			if ( !c.readonly ) { bar.appendChild(undoB); bar.appendChild(redoB); bar.appendChild(saveB); }
			if ( c.audio ) {
				bar.appendChild(el("span", "se-sep"));
				bar.appendChild(button("▶ Play", "Space", actions.play));
				var sp = el("select"); [["0.75", "0.75×"], ["1", "1×"], ["1.25", "1.25×"], ["1.5", "1.5×"]].forEach(function ( o ) { var x = el("option", "", o[1]); x.value = o[0]; if ( o[0] === "1" ) x.selected = true; sp.appendChild(x); });
				sp.addEventListener("change", function () { SE.audio.rate(parseFloat(sp.value)); app.focus(); }); bar.appendChild(sp);
			}
			if ( d.hasconf ) {
				bar.appendChild(el("span", "se-sep"));
				try { confOn = localStorage.getItem("spoken-edit-conf") !== "0"; } catch ( e ) {}
				confB = button("◐ confidence", "show or hide the marking of uncertain words (v)", actions.toggleConf);
				bar.appendChild(confB);
				var lab = el("label", "", "uncertain below "), th = el("input"); th.type = "number"; th.min = 0; th.max = 1; th.step = 0.05; th.value = c.lowconf; th.style.width = "4.5em";
				th.addEventListener("change", function () { SE.view.lowconf(parseFloat(th.value) || 0); lowIdx = -1; SE.view.render(); refresh(); });
				lab.appendChild(th); bar.appendChild(lab); counter = el("span", "se-count"); bar.appendChild(counter);
			} else counter = el("span");
			bar.appendChild(el("span", "se-grow"));
			var w = el("a", "", "waveform view"); w.href = c.wave; bar.appendChild(w);
			if ( c.waveedit ) { var we = el("a", "", "adjust times"); we.href = c.waveedit; we.title = "the waveform editor: drag the boundaries of the words and utterances"; bar.appendChild(we); }
			var palB = !SE.palette ? null : SE.palette.init({
				readonly: !!c.readonly, run: function ( a ) { if ( !busy && actions[a] ) actions[a](); }, focus: function () { app.focus(); },
				speakers: function () { return data().speakers.map(function ( p ) { return p.id; }); }, audio: !!c.audio, hasconf: !!d.hasconf
			});
			if ( app.requestFullscreen || app.webkitRequestFullscreen ) {
				var fsB = button("⛶", "full screen on / off (f)", actions.fullscreen); fsB.setAttribute("aria-label", "full screen"); bar.appendChild(fsB);
				var onFs = function () {
					var on = (document.fullscreenElement || document.webkitFullscreenElement) === app;
					fsB.classList.toggle("se-pressed", on); if ( SE.palette ) SE.palette.mount(on ? app : document.body); app.focus();
				};
				document.addEventListener("fullscreenchange", onFs); document.addEventListener("webkitfullscreenchange", onFs);
			}
			if ( palB ) bar.appendChild(palB);      // without the palette script the keys still work
			speakersBox = el("details", "se-speakers"); speakersBox.appendChild(el("summary", "", "Speakers"));
			var spkBody = el("div"); speakersBox.appendChild(spkBody);
			app.appendChild(bar); app.appendChild(msg); app.appendChild(ask); if ( !c.readonly ) app.appendChild(speakersBox); app.appendChild(list);
			var det = speakersBox; speakersBox = spkBody;
			SE.view.init(app, c); SE.view.setList(list);
			SE.audio.init(c.audio, function ( t, playing, err ) { if ( err ) say(err, "error"); SE.view.follow(playing ? t : null); });
			list.addEventListener("click", function ( ev ) {
				var t = ev.target.closest("[data-u]"); if ( !t ) return;
				var u = parseInt(t.dataset.u, 10);
				if ( t.dataset.act === "who" ) { SE.view.setCursor(u, 0); return; }
				if ( t.dataset.i !== undefined && (ev.shiftKey || ev.metaKey || ev.ctrlKey) && u === SE.view.cursor().u ) {
					clickSelect(u, parseInt(t.dataset.i, 10), ev.shiftKey); app.focus(); return;
				}
				if ( t.dataset.i !== undefined ) SE.view.setCursor(u, parseInt(t.dataset.i, 10), true);
				app.focus();
			});
			list.addEventListener("mousedown", function ( ev ) { if ( ev.shiftKey || ev.metaKey || ev.ctrlKey ) ev.preventDefault(); });      // no text selection by the browser
			if ( !c.readonly ) list.addEventListener("dblclick", function ( ev ) {
				var t = ev.target.closest("[data-i]"); if ( t ) { SE.view.setCursor(parseInt(t.dataset.u, 10), parseInt(t.dataset.i, 10), true); startEdit(); }
			});
			var guarded = {};
			var VIEW = { left: 1, right: 1, up: 1, down: 1, home: 1, end: 1, play: 1, playUtt: 1, stop: 1, toggleConf: 1, nextLow: 1, prevLow: 1, fullscreen: 1, help: 1 };
			Object.keys(actions).forEach(function ( k ) { if ( c.readonly && !VIEW[k] ) return; guarded[k] = function ( ev ) { if ( !busy ) actions[k](ev); }; });
			SE.keys.bind(guarded);
			setInterval(function () { fetch(cfg.base + "&act=ping", { credentials: "same-origin" }).catch(function () {}); }, 600000);
			applyConf();
			SE.view.render(); SE.view.setCursor(0, 0, true); refresh(); app.focus();
			if ( c.tid ) openAt(c.tid);
			var low = SE.view.uncertainList(); if ( low.length ) say(low.length + " uncertain words: press c to go through them, least certain first.", "info");
		}
	};
})();
