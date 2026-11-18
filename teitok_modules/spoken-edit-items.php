<?php
	// spoken-edit: the content of an utterance as a list of items (words, pauses, vocal sounds …), each with the
	// whitespace in front of it ("lead"), so that items can be moved, cut and joined without touching anything else.
	// An item is array( k, raw, lead, tl, text, id, ts ):
	//   k    'tok' | 'word' (a word of plain text) | the element's name ('pause', 'vocal', 'del' …) | 'other' (text with comments)
	//   raw  the item's text as in the file; tl: the length of its start tag inside raw (elements)
	//   text what it says (words, and elements with words in them), id, ts: array(start, end) or null

	function se_items ( $doc, $u ) {
		$raw = $doc['raw']; $items = array(); $lead = "";
		if ( $u->ce === null ) return array(array(), "");
		$pos = $u->te;
		foreach ( $u->kids as $k ) {
			se_gap($raw, $pos, $k->s, $items, $lead);
			$words = array();
			foreach ( array_merge(array($k), se_descendants($k)) as $d ) if ( $d->name === "tok" && $d->ce !== null ) $words[] = se_node_text($doc, $d);
			$items[] = array("k" => $k->name, "raw" => se_node_raw($doc, $k), "lead" => $lead, "tl" => $k->te - $k->s,
				"text" => $k->name === "tok" ? $words[0] ?? "" : implode(" ", $words), "id" => $k->attrs['id'] ?? "",
				"ts" => se_node_times($k), "node" => $k);
			$lead = ""; $pos = $k->e;
		};
		se_gap($raw, $pos, $u->ce, $items, $lead);
		return array($items, $lead);
	};

	# The text between two elements: whitespace (becomes the lead of what follows), plain words, and comments, CDATA or
	# processing instructions (each one opaque item)
	function se_gap ( $raw, $from, $to, &$items, &$lead ) {
		$gap = substr($raw, $from, $to - $from);
		while ( $gap !== "" ) {
			$lt = strpos($gap, "<");
			$text = $lt === false ? $gap : substr($gap, 0, $lt);
			se_gap_text($text, $items, $lead);
			if ( $lt === false ) return;
			$gap = substr($gap, $lt);
			$close = substr($gap, 0, 4) === "<!--" ? "-->" : (substr($gap, 0, 9) === "<![CDATA[" ? "]]>" : "?>");
			$end = strpos($gap, $close);
			$end = $end === false ? strlen($gap) : $end + strlen($close);
			$items[] = array("k" => "other", "raw" => substr($gap, 0, $end), "lead" => $lead, "tl" => 0, "text" => "", "id" => "", "ts" => null);
			$lead = ""; $gap = substr($gap, $end);
		};
	};

	function se_gap_text ( $text, &$items, &$lead ) {
		if ( $text === "" ) return;
		preg_match_all('/[ \t\r\n]+|[^ \t\r\n]+/', $text, $m);
		foreach ( $m[0] as $piece ) {
			if ( trim($piece, " \t\r\n") === "" ) { $lead .= $piece; continue; };
			$items[] = array("k" => "word", "raw" => $piece, "lead" => $lead, "tl" => 0, "text" => se_unesc($piece), "id" => "", "ts" => null);
			$lead = "";
		};
	};

	function se_is_word ( $it ) { return $it['k'] === "tok" || $it['k'] === "word"; };
	function se_has_words ( $it ) { return $it['k'] === "tok" || $it['k'] === "word" || ($it['text'] !== "" && isset($it['node']) && $it['k'] !== "vocal" && $it['k'] !== "incident"); };
	function se_tokenized ( $items ) { foreach ( $items as $it ) if ( $it['k'] === "tok" ) return true; return false; };

	function se_items_raw ( $items ) { $o = ""; foreach ( $items as $it ) $o .= $it['lead'] . $it['raw']; return $o; };

	# The utterance as text: start tag (with changes), items, trailing whitespace, end tag
	function se_u_raw ( $doc, $u, $items, $trail, $set = array(), $close = null ) {
		$tag = se_start_tag($doc, $u);
		foreach ( $set as $k => $v ) $tag = se_tag_set($tag, $k, $v);
		$tag = se_tag_open($tag);
		if ( $close === null ) $close = $u->ce !== null ? substr($doc['raw'], $u->ce, $u->e - $u->ce) : "</u>";
		return $tag . se_items_raw($items) . $trail . $close;
	};

	# The attribute changes that make the utterance's start and end those of its content (only when they differ)
	function se_u_times ( $u, $items, $abs = false ) {
		$s = null; $e = null;
		foreach ( $items as $it ) {
			if ( !$it['ts'] ) continue;
			if ( $it['ts'][0] !== null ) $s = $s === null ? $it['ts'][0] : min($s, $it['ts'][0]);
			if ( $it['ts'][1] !== null ) $e = $e === null ? $it['ts'][1] : max($e, $it['ts'][1]);
		};
		$set = array();
		foreach ( array("start" => $s, "end" => $e) as $k => $v ) {
			if ( $v === null ) { if ( $abs ) $set[$k] = null; continue; };
			$old = $abs ? null : ($u->attrs[$k] ?? null);
			if ( $old === null || !is_numeric($old) || abs((float)$old - $v) > 0.0005 ) $set[$k] = sprintf("%.3f", $v);
		};
		return $set;
	};

	function se_item_tag ( $it ) { return substr($it['raw'], 0, $it['tl']); };
	function se_item_attr ( $it, $name ) { return ($it['node']->attrs[$name] ?? null); };
	function se_item_set_tag ( $it, $tag ) { $it['raw'] = $tag . substr($it['raw'], $it['tl']); $it['tl'] = strlen($tag); return $it; };
	function se_item_set_attr ( $it, $name, $value ) { return se_item_set_tag($it, se_tag_set(se_item_tag($it), $name, $value)); };

	function se_new_id ( &$ctr ) { return $ctr[0] . $ctr[1]++; };

	function se_make_tok ( $id, $text, $ts = null, $conf = null, $lead = " " ) {
		$a = " id=\"" . se_esc_attr($id) . "\"";
		if ( $ts && $ts[0] !== null ) $a .= " start=\"" . sprintf("%.3f", $ts[0]) . "\"";
		if ( $ts && $ts[1] !== null ) $a .= " end=\"" . sprintf("%.3f", $ts[1]) . "\"";
		if ( $conf !== null ) $a .= " conf=\"" . se_esc_attr($conf) . "\"";
		$tag = "<tok$a>";
		return array("k" => "tok", "raw" => $tag . se_esc_text($text) . "</tok>", "lead" => $lead, "tl" => strlen($tag), "text" => $text, "id" => $id, "ts" => $ts,
			"node" => (object)array("attrs" => array("id" => $id, "conf" => $conf), "kids" => array()));
	};

	function se_make_word ( $text, $lead = " " ) {
		return array("k" => "word", "raw" => se_esc_text($text), "lead" => $lead, "tl" => 0, "text" => $text, "id" => "", "ts" => null);
	};

	# Plain text -> tokens: punctuation at the edges of a word becomes its own token (written together with the word);
	# apostrophes and hyphens inside a word stay. The first item gets the lead given.
	function se_tokenize_text ( $text, &$ctr, $lead = " " ) {
		$parts = array();
		if ( preg_match('/^([\p{Ps}\p{Pi}"¿¡]*)(.*?)([\p{Pe}\p{Pf}"“”.,;:!?…]*)$/us', $text, $m) && $m[2] !== "" ) {
			if ( $m[1] !== "" ) $parts[] = $m[1];
			$parts[] = $m[2];
			if ( $m[3] !== "" ) $parts[] = $m[3];
		} else $parts[] = $text;
		$out = array();
		foreach ( $parts as $k => $t ) $out[] = se_make_tok(se_new_id($ctr), $t, null, null, $k === 0 ? $lead : "");
		return $out;
	};

	# Items going to another utterance take its form: plain text where it has no tokens, tokens where it has them
	function se_adapt ( $moving, $dest, &$ctr ) {
		$mode = se_tokenized($dest) ? "tok" : (count(array_filter($dest, 'se_is_word')) ? "plain" : "keep");
		$out = array();
		foreach ( $moving as $it ) {
			if ( $mode === "plain" && $it['k'] === "tok" ) { $w = se_make_word($it['text'], $it['lead']); $out[] = $w; }
			else if ( $mode === "tok" && $it['k'] === "word" ) foreach ( se_tokenize_text($it['text'], $ctr, $it['lead']) as $t ) $out[] = $t;
			else $out[] = $it;
		};
		return $out;
	};

	# Item lists joined: the first item of B comes after a space (or directly after A when it is punctuation)
	function se_join ( $a, $b ) {
		if ( !$a || !$b ) return array_merge($a, $b);
		$b[0]['lead'] = se_is_word($b[0]) && se_is_punct($b[0]['text']) ? "" : " ";
		return array_merge($a, $b);
	};

	# An utterance's words as plain text: tokens written as text, words inside an element too
	function se_flatten ( $doc, $n ) {
		$raw = $doc['raw'];
		if ( $n->name === "tok" ) return se_esc_text(se_node_text($doc, $n));
		if ( $n->ce === null ) return se_node_raw($doc, $n);
		$out = substr($raw, $n->s, $n->te - $n->s); $pos = $n->te;
		foreach ( $n->kids as $k ) { $out .= substr($raw, $pos, $k->s - $pos) . se_flatten($doc, $k); $pos = $k->e; };
		return $out . substr($raw, $pos, $n->e - $pos);
	};
?>
