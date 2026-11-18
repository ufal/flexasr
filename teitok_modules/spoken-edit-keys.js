// spoken-edit: the keys. The table maps a key (with ctrl/meta written "mod+", shift written "shift+" for non-letters)
// to the name of an action in SE.main.actions; help() lists them.
var SE = window.SE = window.SE || {};
SE.keys = (function () {
	var TABLE = [
		["ArrowRight", "right", "next word"], ["ArrowLeft", "left", "previous word"],
		["ArrowDown", "down", "next utterance"], ["ArrowUp", "up", "previous utterance"],
		["Home", "home", "first word of the utterance"], ["End", "end", "last word of the utterance"],
		["[", "movePrev", "move this word and everything before it to the previous utterance"],
		["]", "moveNext", "move this word and everything after it to the next utterance"],
		["s", "split", "split the utterance before this word"],
		["m", "mergeNext", "merge with the next utterance"], ["M", "mergePrev", "merge with the previous utterance"],
		["1", "who1", "speaker 1 for this utterance (1–9 for the speakers in the list)"],
		["d", "detok", "detokenize this utterance (plain text)"], ["t", "tokenize", "tokenize this utterance"],
		["D", "detokAll", "detokenize all utterances of this speaker"], ["T", "tokAll", "tokenize all utterances of this speaker"],
		["Enter", "edit", "edit the word (Enter: done, Tab: next word, a space splits it)"],
		["Delete", "delete", "delete the word"], ["Backspace", "delete", ""],
		["i", "insertBefore", "insert a word before"], ["o", "insertAfter", "insert a word after"],
		["-", "join", "join this word with the next"],
		[" ", "play", "play / pause from this word"], ["p", "playUtt", "play this utterance"], ["Escape", "stop", "stop"],
		["c", "nextLow", "next uncertain word (least certain first)"], ["C", "prevLow", "previous uncertain word"],
		["a", "accept", "accept this word as correct and go to the next uncertain one"],
		["mod+z", "undo", "undo"], ["mod+shift+z", "redo", "redo"], ["mod+y", "redo", ""], ["mod+s", "save", "save"],
		["?", "help", "this list"]
	];
	function name ( ev ) {
		var k = ev.key;
		if ( /^[1-9]$/.test(k) && !(ev.ctrlKey || ev.metaKey) ) return "who:" + k;
		var mod = (ev.ctrlKey || ev.metaKey) ? "mod+" : "";
		if ( mod ) return mod + (ev.shiftKey ? "shift+" : "") + k.toLowerCase();
		return k;
	}
	return {
		bind: function ( actions ) {
			document.addEventListener("keydown", function ( ev ) {
				var t = ev.target;
				if ( t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA") ) return;
				var n = name(ev), act = null;
				if ( n.indexOf("who:") === 0 ) act = "who" + n.slice(4);
				else TABLE.forEach(function ( row ) { if ( row[0] === n ) act = row[1]; });
				if ( !act || !actions[act] ) return;
				ev.preventDefault();
				actions[act](ev);
			});
		},
		help: function () {
			var d = document.createElement("div"); d.className = "se-help";
			var h = document.createElement("table");
			TABLE.forEach(function ( row ) {
				if ( !row[2] ) return;
				var tr = h.insertRow(); var k = tr.insertCell(); var kb = document.createElement("kbd");
				kb.textContent = row[0] === " " ? "Space" : row[0].replace("mod+", "Ctrl/⌘ "); k.appendChild(kb); tr.insertCell().textContent = row[2];
			});
			d.appendChild(h);
			return d;
		}
	};
})();
