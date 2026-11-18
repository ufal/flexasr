<?php
	// spoken-edit: times estimated from the text. Where the words of an utterance carry no times (a transcript that was
	// not made with flexasr: the utterance has start and end, its tokens have none), a split, or words moved to a
	// neighbouring utterance, need a new boundary in time. It is taken from where in the utterance the cut falls, by
	// the vowel groups before it: a vowel group (a run of vowels, so a diphthong counts once) is about one syllable,
	// and syllables follow time better than letters or words do. Always an estimate: the utterances it touches get
	// timing="estimated", so that they can be told from measured times.

	# The vowel groups of a word: 0 for something that is not a word (punctuation), at least 1 for a word
	function se_vowel_weight ( $text ) {
		$t = mb_strtolower((string)$text, "UTF-8");
		if ( !preg_match('/\p{L}/u', $t) ) return 0;
		$n = preg_match_all('/[aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿœ]+/u', $t);
		return max(1, (int)$n);
	};

	# Punctuation stands for a pause, whose length the text does not give: a sentence end is about a syllable and a half,
	# a comma half a syllable or a little more (the usual figures: a syllable ~0.2 s, a pause at a sentence end 0.3-0.5 s)
	function se_punct_weight ( $text ) {
		$t = trim((string)$text);
		if ( in_array($t, array(".", "?", "!", "…", "...", "。"), true) ) return 1.5;
		if ( in_array($t, array(",", ";", ":", "—", "–"), true) ) return 0.6;
		return 0;
	};

	# What an item takes of an utterance's time: array(share, seconds). A word: its vowel groups (a punctuation mark:
	# the weight of the pause it stands for) as a share; a <pause> that says how long it is: those seconds, known.
	function se_item_time ( $it ) {
		if ( $it['k'] === "pause" ) {
			$d = se_item_attr($it, "dur");
			return array(0.0, is_numeric($d) && (float)$d > 0 ? (float)$d : 0.0);
		};
		if ( !se_is_word($it) ) return array(0.0, 0.0);
		$p = se_punct_weight($it['text']);
		return array($p > 0 ? $p : (float)se_vowel_weight($it['text']), 0.0);
	};

	# The weight of an item list: the vowel groups of its words
	function se_items_weight ( $items ) {
		$w = 0;
		foreach ( $items as $it ) if ( se_is_word($it) ) $w += se_vowel_weight($it['text']);
		return $w;
	};

	# Does this utterance have times of its own (start before end) but no times on its words?
	function se_untimed_words ( $u, $items ) {
		$s = $u->attrs['start'] ?? null; $e = $u->attrs['end'] ?? null;
		if ( !is_numeric($s) || !is_numeric($e) || (float)$e <= (float)$s ) return false;
		list($ws, $we) = se_items_span($items);
		return $ws === null && $we === null;
	};

	# The time at the cut before item $i of an untimed utterance (i = the number of items: its end). The utterance's
	# own length, less the pauses that say how long they are, is shared out by the weights before the cut; the pauses
	# before the cut are added back. Every operation that moves a boundary takes its time from here. Null when there is
	# nothing to go by.
	function se_estimate_cut ( $u, $items, $i ) {
		$s = (float)$u->attrs['start']; $len = (float)$u->attrs['end'] - $s;
		$wt = 0.0; $pt = 0.0; $wb = 0.0; $pb = 0.0;
		foreach ( $items as $n => $it ) {
			list($w, $p) = se_item_time($it);
			$wt += $w; $pt += $p;
			if ( $n < $i ) { $wb += $w; $pb += $p; }
		};
		if ( $wt <= 0 ) return null;
		if ( $pt >= $len ) { $pt = 0.0; $pb = 0.0; }      # the pauses do not fit in the utterance: leave them out
		return $s + $pb + ($len - $pt) * $wb / $wt;
	};
