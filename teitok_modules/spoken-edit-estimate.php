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

	# The time at the cut before item $i of an untimed utterance: its start plus its length times the share of the
	# utterance's vowel groups that come before the cut. Null when there is nothing to go by.
	function se_estimate_cut ( $u, $items, $i ) {
		$total = se_items_weight($items);
		if ( $total <= 0 ) return null;
		$s = (float)$u->attrs['start']; $e = (float)$u->attrs['end'];
		return $s + ($e - $s) * se_items_weight(array_slice($items, 0, $i)) / $total;
	};
