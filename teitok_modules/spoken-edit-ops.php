<?php
	// spoken-edit: the edit operations. Each takes the parsed document and its arguments and returns splices
	// (array( start, end, replacement )) of the original text; se_apply() applies a list of operations one after the
	// other, parses the result again each time, and checks that the operations that only rearrange text left the
	// text itself alone. An operation that fails throws an Exception whose message is shown to the user.

	require_once(__DIR__ . "/spoken-edit-doc.php");
	require_once(__DIR__ . "/spoken-edit-items.php");
	require_once(__DIR__ . "/spoken-edit-estimate.php");

	# operation => whether it only rearranges the words (so that the text of the document must come out the same)
	function se_op_table () {
		return array("set_who" => true, "move_prev" => true, "move_next" => true, "split" => true, "merge" => true,
			"detok" => true, "detok_who" => true, "tok" => true, "tok_who" => true, "number" => true, "accept" => true,
			"edit" => false, "delete" => false, "insert" => false, "merge_words" => true, "extract" => false,
			"rename_speaker" => true, "set_role" => true, "set_name" => true, "merge_speakers" => true, "add_speaker" => true);
	};

	# The text of the utterances without whitespace: what the rearranging operations must keep
	function se_squeeze ( $doc ) {
		$o = "";
		foreach ( se_utterances($doc) as $u ) $o .= se_node_text($doc, $u);
		return preg_replace('/\s+/u', "", $o);
	};

	function se_apply ( $raw, $ops ) {
		$table = se_op_table();
		foreach ( $ops as $op ) {
			$name = $op['op'] ?? "";
			if ( !isset($table[$name]) ) throw new Exception("unknown operation $name");
			$doc = se_parse($raw);
			if ( !$doc ) throw new Exception("the document does not parse");
			$before = $table[$name] ? se_squeeze($doc) : null;
			$new = se_splice($raw, call_user_func("se_op_$name", $doc, $op));
			$ndoc = se_parse($new);
			if ( !$ndoc ) throw new Exception("the change would give a document that does not parse");
			if ( $table[$name] && se_squeeze($ndoc) !== $before ) throw new Exception("the change would alter the text");
			$raw = $new;
		};
		return $raw;
	};

	function se_item_index ( $items, $a ) {
		$i = (int)($a['i'] ?? -1);
		if ( $i < 0 || $i >= count($items) ) throw new Exception("no such item");
		return $i;
	};

	# The range to cut to remove an element with the whitespace in front of it
	function se_removal ( $doc, $n ) {
		$s = $n->s; $raw = $doc['raw'];
		while ( $s > 0 && strpos(" \t\r\n", $raw[$s - 1]) !== false ) $s--;
		return array($s, $n->e, "");
	};

	function se_u_neighbour ( $doc, $k, $d ) {
		$us = se_utterances($doc);
		if ( !isset($us[$k + $d]) ) throw new Exception($d < 0 ? "there is no utterance before this one" : "there is no utterance after this one");
		return $us[$k + $d];
	};

	# Replace an utterance by its new content, or remove it when nothing is left
	function se_u_replace ( $doc, $u, $items, $trail, $set = array() ) {
		if ( !$items ) return se_removal($doc, $u);
		$items[0]['lead'] = "";
		return array($u->s, $u->e, se_u_raw($doc, $u, $items, $trail, $set + se_u_times($u, $items)));
	};

	function se_op_set_who ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		$who = trim($a['who'] ?? "");
		if ( $who === "" ) throw new Exception("no speaker given");
		$old = $u->attrs['who'] ?? "";
		if ( substr($old, 0, 1) === "#" && substr($who, 0, 1) !== "#" ) $who = "#$who";
		return array(array($u->s, $u->te, se_tag_set(se_start_tag($doc, $u), "who", $who)));
	};

	function se_op_move_prev ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		$p = se_u_neighbour($doc, $k, -1);
		list($items, $trail) = se_items($doc, $u); list($pitems, $ptrail) = se_items($doc, $p);
		$i = se_item_index($items, $a); $ctr = se_id_counter($doc, "tok", "w-");
		$new = se_join($pitems, se_adapt(array_slice($items, 0, $i + 1), $pitems, $ctr));
		$pset = array(); $uset = array();
		if ( se_untimed_words($u, $items) && se_untimed_words($p, $pitems) && ($cut = se_estimate_cut($u, $items, $i + 1)) !== null ) {
			$pset = array("end" => sprintf("%.3f", $cut), "timing" => "estimated");       # the moved words end where the cut falls
			$uset = array("start" => sprintf("%.3f", $cut), "timing" => "estimated");
		};
		return array(se_u_replace($doc, $p, $new, $ptrail, $pset), se_u_replace($doc, $u, array_slice($items, $i + 1), $trail, $uset));
	};

	function se_op_move_next ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		$n = se_u_neighbour($doc, $k, 1);
		list($items, $trail) = se_items($doc, $u); list($nitems, $ntrail) = se_items($doc, $n);
		$i = se_item_index($items, $a); $ctr = se_id_counter($doc, "tok", "w-");
		$new = se_join(se_adapt(array_slice($items, $i), $nitems, $ctr), $nitems);
		$nset = array(); $uset = array();
		if ( se_untimed_words($u, $items) && se_untimed_words($n, $nitems) && ($cut = se_estimate_cut($u, $items, $i)) !== null ) {
			$uset = array("end" => sprintf("%.3f", $cut), "timing" => "estimated");       # what stays ends where the cut falls
			$nset = array("start" => sprintf("%.3f", $cut), "timing" => "estimated");
		};
		return array(se_u_replace($doc, $n, $new, $ntrail, $nset), se_u_replace($doc, $u, array_slice($items, 0, $i), $trail, $uset));
	};

	function se_op_split ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		list($items, $trail) = se_items($doc, $u);
		$i = se_item_index($items, $a);
		if ( $i === 0 ) throw new Exception("the utterance starts here already");
		$head = array_slice($items, 0, $i); $tail = array_slice($items, $i); $tail[0]['lead'] = "";
		$uc = se_id_counter($doc, "u", "u-");
		$raw = $doc['raw']; $b = $u->s;
		while ( $b > 0 && strpos(" \t\r\n", $raw[$b - 1]) !== false ) $b--;
		$ind = substr($raw, $b, $u->s - $b);
		$hset = se_u_times($u, $head); $tset = se_u_times($u, $tail, true);
		if ( se_untimed_words($u, $items) && ($cut = se_estimate_cut($u, $items, $i)) !== null ) {     # no word times: estimate the cut
			$hset = array("end" => sprintf("%.3f", $cut), "timing" => "estimated");
			$tset = array("start" => sprintf("%.3f", $cut), "end" => $u->attrs['end'], "timing" => "estimated");
		};
		$new = se_u_raw($doc, $u, $tail, $trail, array("id" => se_new_id($uc)) + $tset);
		return array(array($u->s, $u->e, se_u_raw($doc, $u, $head, $trail, $hset) . $ind . $new));
	};

	# Words out of an utterance into a new one (simultaneous speech: another speaker's words inside an utterance whose
	# speaker goes on, also when the ASR has interwoven the words of the two). "idx" lists the items that move (any set,
	# they need not be next to each other); i (and to) name a run instead. "who" is the speaker of the new utterance
	# (default: the same). The new utterance keeps its words' times; where the words have none, it gets the stretch from
	# its first to its last word by vowel groups (marked timing="estimated"); the utterance they leave keeps its span.
	# Utterances are in order of start: the new one goes before the old one when it starts first (when the first word
	# moves), else after it. The order of the document changes, so this is not one of the operations whose text is
	# compared afterwards.
	function se_op_extract ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		list($items, $trail) = se_items($doc, $u);
		if ( isset($a['idx']) && is_array($a['idx']) ) {
			$idx = array_values(array_unique(array_map('intval', $a['idx']))); sort($idx);
			foreach ( $idx as $x ) if ( $x < 0 || $x >= count($items) ) throw new Exception("no such item");
		} else {
			$i = se_item_index($items, $a); $j = isset($a['to']) ? (int)$a['to'] : $i;
			if ( $j < $i || $j >= count($items) ) throw new Exception("no such item");
			$idx = range($i, $j);
		};
		if ( !$idx ) throw new Exception("nothing is selected");
		$moved = array(); $rest = array();
		foreach ( $items as $n => $it ) { if ( in_array($n, $idx, true) ) $moved[] = $it; else $rest[] = $it; };
		if ( !count(array_filter($moved, 'se_is_word')) ) throw new Exception("there is no word in the selection");
		if ( !count(array_filter($rest, 'se_is_word')) ) throw new Exception("these are all the words of the utterance: change its speaker instead");
		$moved[0]['lead'] = "";
		if ( $idx[0] === 0 ) $rest[0]['lead'] = "";
		$hset = se_u_times($u, $rest); $tset = se_u_times($u, $moved, true);
		$first = $idx[0]; $last = $idx[count($idx) - 1];
		list($ms, $me) = se_items_span($moved);
		if ( $ms === null && $me === null && se_untimed_words($u, $items) && ($cs = se_estimate_cut($u, $items, $first)) !== null && ($ce = se_estimate_cut($u, $items, $last + 1)) !== null ) {
			$hset = array();        # the speaker who goes on keeps the whole span
			$tset = array("start" => sprintf("%.3f", $cs), "end" => sprintf("%.3f", $ce), "timing" => "estimated");
		};
		# which one starts first: the new one only when it has the earliest word (the first, or one earlier in time)
		$ns = isset($tset['start']) && is_numeric($tset['start']) ? (float)$tset['start'] : null;
		list($rs, $re) = se_items_span($rest);
		$os = $hset ? ($rs !== null ? $rs : null) : (is_numeric($u->attrs['start'] ?? null) ? (float)$u->attrs['start'] : null);
		if ( $ns !== null && $os !== null && abs($ns - $os) > 0.0005 ) $newfirst = $ns < $os;
		else $newfirst = $idx[0] === 0;
		$who = trim($a['who'] ?? "");
		if ( $who !== "" ) {
			$old = $u->attrs['who'] ?? "";
			if ( substr($old, 0, 1) === "#" && substr($who, 0, 1) !== "#" ) $who = "#$who";
			$tset['who'] = $who;
		};
		$uc = se_id_counter($doc, "u", "u-");
		$raw = $doc['raw']; $b = $u->s;
		while ( $b > 0 && strpos(" \t\r\n", $raw[$b - 1]) !== false ) $b--;
		$ind = substr($raw, $b, $u->s - $b);
		$new = se_u_raw($doc, $u, $moved, $trail, array("id" => se_new_id($uc)) + $tset);
		$old = se_u_raw($doc, $u, $rest, $trail, $hset);
		return array(array($u->s, $u->e, $newfirst ? $new . $ind . $old : $old . $ind . $new));
	};

	function se_op_merge ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		$n = se_u_neighbour($doc, $k, 1);
		if ( empty($a['force']) && ($u->attrs['who'] ?? "") !== ($n->attrs['who'] ?? "") ) throw new Exception("the two utterances have different speakers");
		if ( trim(substr($doc['raw'], $u->e, $n->s - $u->e), " \t\r\n") !== "" ) throw new Exception("there is other markup between the two utterances");
		list($items, $trail) = se_items($doc, $u); list($nitems, $ntrail) = se_items($doc, $n);
		$ctr = se_id_counter($doc, "tok", "w-");
		$all = se_join($items, se_adapt($nitems, $items, $ctr));
		$all[0]['lead'] = "";
		$set = se_u_times($u, $all);
		# where the words have no times (the utterances do), the merged utterance runs from the earlier start to the later end
		list($ws, $we) = se_items_span($all);
		foreach ( array("start" => array($ws, "min"), "end" => array($we, "max")) as $name => $how ) {
			if ( $how[0] !== null ) continue;
			$c = array();
			foreach ( array($u, $n) as $x ) if ( isset($x->attrs[$name]) && is_numeric($x->attrs[$name]) ) $c[] = (float)$x->attrs[$name];
			if ( !$c ) continue;
			$v = $how[1] === "min" ? min($c) : max($c); $old = $u->attrs[$name] ?? null;
			if ( $old === null || !is_numeric($old) || abs((float)$old - $v) > 0.0005 ) $set[$name] = sprintf("%.3f", $v);
		};
		return array(array($u->s, $n->e, se_u_raw($doc, $u, $all, $ntrail, $set)));
	};

	function se_op_number ( $doc, $a ) {
		$uc = se_id_counter($doc, "u", "u-"); $out = array();
		foreach ( se_utterances($doc) as $u ) if ( !isset($u->attrs['id']) ) $out[] = array($u->s, $u->te, se_tag_set(se_start_tag($doc, $u), "id", se_new_id($uc)));
		return $out;
	};

	# One utterance with its words as plain text; null when it has no tokens
	function se_detok_u ( $doc, $u ) {
		list($items, $trail) = se_items($doc, $u); $any = false;
		foreach ( $items as $j => $it ) {
			if ( !isset($it['node']) || !se_has_words($it) ) continue;
			$any = true;
			$items[$j]['raw'] = se_flatten($doc, $it['node']);
		};
		return $any ? array($u->s, $u->e, se_u_raw($doc, $u, $items, $trail)) : null;
	};

	# One utterance of plain text as tokens; null when it has no plain words
	function se_tok_u ( $doc, $u, &$ctr ) {
		list($items, $trail) = se_items($doc, $u); $out = array(); $any = false;
		foreach ( $items as $it ) {
			if ( $it['k'] !== "word" ) { $out[] = $it; continue; };
			$any = true;
			foreach ( se_tokenize_text($it['text'], $ctr, $it['lead']) as $t ) $out[] = $t;
		};
		return $any ? array($u->s, $u->e, se_u_raw($doc, $u, $out, $trail)) : null;
	};

	function se_who_is ( $u, $who ) { return ltrim($u->attrs['who'] ?? "", "#") === ltrim($who, "#"); };

	function se_op_detok ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']);
		$r = se_detok_u($doc, $u);
		if ( !$r ) throw new Exception("this utterance has no tokens");
		return array($r);
	};

	function se_op_detok_who ( $doc, $a ) {
		$out = array();
		foreach ( se_utterances($doc) as $u ) if ( se_who_is($u, $a['who'] ?? "") && ($r = se_detok_u($doc, $u)) ) $out[] = $r;
		if ( !$out ) throw new Exception("this speaker has no tokenized utterances");
		return $out;
	};

	function se_op_tok ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']); $ctr = se_id_counter($doc, "tok", "w-");
		$r = se_tok_u($doc, $u, $ctr);
		if ( !$r ) throw new Exception("this utterance is tokenized already");
		return array($r);
	};

	function se_op_tok_who ( $doc, $a ) {
		$out = array(); $ctr = se_id_counter($doc, "tok", "w-");
		foreach ( se_utterances($doc) as $u ) if ( se_who_is($u, $a['who'] ?? "") && ($r = se_tok_u($doc, $u, $ctr)) ) $out[] = $r;
		if ( !$out ) throw new Exception("this speaker has no plain-text utterances");
		return $out;
	};

	function se_op_accept ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']); list($items, $trail) = se_items($doc, $u);
		$i = se_item_index($items, $a);
		if ( $items[$i]['k'] !== "tok" ) throw new Exception("this is not a word");
		$items[$i] = se_item_set_attr($items[$i], "reviewed", "1");
		return array(array($u->s, $u->e, se_u_raw($doc, $u, $items, $trail)));
	};

	# Edit the text of a word; with a space in it the word becomes several, sharing the time of the one
	function se_op_edit ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']); list($items, $trail) = se_items($doc, $u);
		$i = se_item_index($items, $a); $it = $items[$i];
		if ( !se_is_word($it) ) throw new Exception("this is not a word");
		$parts = preg_split('/\s+/u', trim($a['text'] ?? ""), -1, PREG_SPLIT_NO_EMPTY);
		if ( !$parts ) return se_op_delete($doc, $a);
		$ctr = se_id_counter($doc, "tok", "w-"); $new = array();
		if ( $it['k'] === "word" ) {
			foreach ( $parts as $j => $t ) $new[] = se_make_word($t, $j ? " " : $it['lead']);
		} else {
			if ( $it['node']->kids ) throw new Exception("this word has markup inside it");
			$ts = $it['ts']; $total = max(1, array_sum(array_map('mb_strlen', $parts))); $cum = 0; $conf = se_item_attr($it, "conf");
			foreach ( $parts as $j => $t ) {
				$from = $cum; $cum += mb_strlen($t);
				$pts = $ts && $ts[0] !== null && $ts[1] !== null ? array($ts[0] + ($ts[1] - $ts[0]) * $from / $total, $ts[0] + ($ts[1] - $ts[0]) * $cum / $total) : $ts;
				if ( !$j ) {
					$tag = se_tag_open(se_item_tag($it));
					if ( count($parts) > 1 && $pts ) $tag = se_tag_set($tag, "end", sprintf("%.3f", $pts[1]));
					$tag = se_tag_set($tag, "reviewed", "1");
					$new[] = array("k" => "tok", "raw" => $tag . se_esc_text($t) . "</tok>", "lead" => $it['lead'], "tl" => strlen($tag), "text" => $t,
						"id" => $it['id'], "ts" => $pts, "node" => $it['node']);
				} else {
					$n = se_make_tok(se_new_id($ctr), $t, $pts, $conf);
					$new[] = se_item_set_attr($n, "reviewed", "1");
				};
			};
		};
		array_splice($items, $i, 1, $new);
		return array(array($u->s, $u->e, se_u_raw($doc, $u, $items, $trail, se_u_times($u, $items))));
	};

	function se_op_delete ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']); list($items, $trail) = se_items($doc, $u);
		$i = se_item_index($items, $a);
		array_splice($items, $i, 1);
		if ( $items && $i === 0 ) $items[0]['lead'] = "";
		return array(se_u_replace($doc, $u, $items, $trail));
	};

	function se_op_insert ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']); list($items, $trail) = se_items($doc, $u);
		$i = (int)($a['i'] ?? 0);
		if ( $i < 0 || $i > count($items) ) throw new Exception("no such place");
		$parts = preg_split('/\s+/u', trim($a['text'] ?? ""), -1, PREG_SPLIT_NO_EMPTY);
		if ( !$parts ) throw new Exception("nothing to insert");
		$ctr = se_id_counter($doc, "tok", "w-"); $plain = $items && !se_tokenized($items); $new = array();
		foreach ( $parts as $j => $t ) $new[] = $plain ? se_make_word($t) : se_make_tok(se_new_id($ctr), $t);
		$new[0]['lead'] = $i === 0 ? "" : " ";
		if ( $i === 0 && $items ) $items[0]['lead'] = " ";
		array_splice($items, $i, 0, $new);
		return array(array($u->s, $u->e, se_u_raw($doc, $u, $items, $trail, se_u_times($u, $items))));
	};

	function se_op_merge_words ( $doc, $a ) {
		list($k, $u) = se_find_u($doc, $a['u']); list($items, $trail) = se_items($doc, $u);
		$i = se_item_index($items, $a);
		if ( !isset($items[$i + 1]) || !se_is_word($items[$i]) || $items[$i]['k'] !== $items[$i + 1]['k'] ) throw new Exception("there is no word to join this one with");
		$x = $items[$i]; $y = $items[$i + 1]; $text = $x['text'] . $y['text'];
		if ( $x['k'] === "word" ) $m = se_make_word($text, $x['lead']);
		else {
			if ( $x['node']->kids || $y['node']->kids ) throw new Exception("these words have markup inside them");
			$tag = se_tag_open(se_item_tag($x));
			$ts = array($x['ts'][0] ?? null, $y['ts'][1] ?? ($x['ts'][1] ?? null));
			if ( $ts[1] !== null && $ts[1] !== ($x['ts'][1] ?? null) ) $tag = se_tag_set($tag, "end", sprintf("%.3f", $ts[1]));
			$cx = se_item_attr($x, "conf"); $cy = se_item_attr($y, "conf");
			if ( $cx !== null && $cy !== null && (float)$cy < (float)$cx ) $tag = se_tag_set($tag, "conf", $cy);
			$tag = se_tag_set($tag, "reviewed", "1");
			$m = array("k" => "tok", "raw" => $tag . se_esc_text($text) . "</tok>", "lead" => $x['lead'], "tl" => strlen($tag), "text" => $text, "id" => $x['id'], "ts" => $ts, "node" => $x['node']);
		};
		array_splice($items, $i, 2, array($m));
		return array(array($u->s, $u->e, se_u_raw($doc, $u, $items, $trail, se_u_times($u, $items))));
	};

	require_once(__DIR__ . "/spoken-edit-speakers.php");
?>
