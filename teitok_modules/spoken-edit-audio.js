// spoken-edit: playing the recording from a word, and following the playback
var SE = window.SE = window.SE || {};
SE.audio = (function () {
	var el = null, onTick = null, raf = 0, stopAt = null;
	function tick () {
		if ( !el ) return;
		if ( stopAt !== null && el.currentTime >= stopAt ) { el.pause(); stopAt = null; }
		if ( onTick ) onTick(el.currentTime, !el.paused);
		raf = el.paused ? 0 : requestAnimationFrame(tick);
	}
	return {
		init: function ( url, cb ) {
			onTick = cb;
			if ( !url ) return false;
			el = document.createElement("audio"); el.preload = "auto"; el.src = url;
			el.addEventListener("play", function () { if ( !raf ) raf = requestAnimationFrame(tick); });
			el.addEventListener("pause", function () { tick(); });
			el.addEventListener("error", function () { if ( onTick ) onTick(null, false, "The recording cannot be loaded"); });
			return true;
		},
		available: function () { return !!el; },
		playing: function () { return !!el && !el.paused; },
		time: function () { return el ? el.currentTime : 0; },
		// from: seconds; to: stop there (optional)
		playFrom: function ( from, to ) {
			if ( !el ) return;
			stopAt = to === undefined ? null : to;
			el.currentTime = Math.max(0, from - 0.15);
			el.play();
		},
		toggle: function ( from ) {
			if ( !el ) return;
			if ( el.paused ) { stopAt = null; if ( from !== undefined ) el.currentTime = Math.max(0, from - 0.15); el.play(); } else el.pause();
		},
		stop: function () { if ( el ) el.pause(); },
		rate: function ( r ) { if ( el ) el.playbackRate = r; }
	};
})();
