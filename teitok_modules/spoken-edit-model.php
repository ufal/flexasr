<?php
	// spoken-edit: the document as JSON for the editor: utterances with their items, the speakers, the media

	require_once(__DIR__ . "/spoken-edit-ops.php");

	function se_num ( $v ) { return is_numeric($v) ? (float)$v : null; };

	function se_item_json ( $it, $doc ) {
		$o = array("k" => $it['k'], "t" => $it['text'], "g" => $it['lead'] === "" ? 1 : 0);
		if ( !isset($it['node']) || !is_object($it['node']) ) return $o;
		$at = $it['node']->attrs;
		if ( $it['id'] !== "" ) $o['id'] = $it['id'];
		if ( $it['ts'] ) { $o['s'] = $it['ts'][0]; $o['e'] = $it['ts'][1]; };
		if ( isset($at['conf']) && is_numeric($at['conf']) ) $o['c'] = (float)$at['conf'];
		if ( isset($at['reviewed']) ) $o['rv'] = 1;
		foreach ( array("reason", "type", "dur", "orig") as $x ) if ( isset($at[$x]) ) $o['x'][$x] = $at[$x];
		if ( $it['k'] === "vocal" || $it['k'] === "incident" ) {
			foreach ( $it['node']->kids as $kid ) if ( $kid->name === "desc" ) $o['t'] = trim(se_node_text($doc, $kid));
		};
		return $o;
	};

	function se_model ( $raw ) {
		$doc = se_parse($raw);
		if ( !$doc ) throw new Exception("the document does not parse");
		$us = array(); $need = 0;
		foreach ( se_utterances($doc) as $u ) {
			list($items, $trail) = se_items($doc, $u);
			if ( !isset($u->attrs['id']) ) $need++;
			$us[] = array("id" => $u->attrs['id'] ?? "", "who" => ltrim($u->attrs['who'] ?? "", "#"),
				"s" => se_num($u->attrs['start'] ?? null), "e" => se_num($u->attrs['end'] ?? null),
				"plain" => !se_tokenized($items) && count(array_filter($items, 'se_is_word')) > 0,
				"items" => array_map(function ( $it ) use ( $doc ) { return se_item_json($it, $doc); }, $items));
		};
		$people = array(); $count = array();
		foreach ( $us as $u ) $count[$u['who']] = ($count[$u['who']] ?? 0) + 1;
		foreach ( se_persons($doc) as $p ) {
			list($pn, $name) = se_person_name($doc, $p); $id = se_person_id($p);
			$people[] = array("id" => $id, "role" => $p->attrs['role'] ?? "", "n" => $p->attrs['n'] ?? "", "name" => $name, "count" => $count[$id] ?? 0);
			unset($count[$id]);
		};
		foreach ( $count as $id => $c ) if ( $id !== "" ) $people[] = array("id" => $id, "role" => "", "n" => "", "name" => "", "count" => $c, "unlisted" => 1);
		$media = null; $title = "";
		foreach ( $doc['all'] as $n ) {
			if ( $n->name === "media" && $media === null && isset($n->attrs['url']) ) $media = $n->attrs['url'];
			if ( $n->name === "title" && $title === "" ) $title = trim(se_node_text($doc, $n));
		};
		return array("hash" => sha1($raw), "title" => $title, "media" => $media, "speakers" => $people, "us" => $us, "unnumbered" => $need,
			"hasconf" => (bool)array_filter($us, function ( $u ) { foreach ( $u['items'] as $i ) if ( isset($i['c']) ) return true; return false; }));
	};
?>
