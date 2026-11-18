<?php
	// spoken-edit: the speakers, as TEI's teiHeader/profileDesc/particDesc/listPerson/person[@id @role @n], and the
	// utterances' @who that refers to them (as 'spk1' or '#spk1')

	function se_persons ( $doc ) {
		$out = array();
		foreach ( $doc['all'] as $n ) if ( $n->name === "person" ) $out[] = $n;
		return $out;
	};

	function se_person_idattr ( $p ) { return isset($p->attrs['xml:id']) && !isset($p->attrs['id']) ? "xml:id" : "id"; };
	function se_person_id ( $p ) { return $p->attrs[se_person_idattr($p)] ?? ""; };

	function se_find_person ( $doc, $id ) {
		foreach ( se_persons($doc) as $p ) if ( se_person_id($p) === ltrim($id, "#") ) return $p;
		throw new Exception("no speaker $id");
	};

	function se_person_name ( $doc, $p ) {
		foreach ( $p->kids as $k ) if ( $k->name === "persName" ) return array($k, trim(se_node_text($doc, $k)));
		return array(null, "");
	};

	# The whitespace in front of an element on its own line
	function se_indent ( $doc, $n ) {
		$raw = $doc['raw']; $b = $n->s;
		while ( $b > 0 && strpos(" \t", $raw[$b - 1]) !== false ) $b--;
		return substr($raw, $b, $n->s - $b);
	};

	function se_who_splices ( $doc, $from, $to ) {
		$out = array();
		foreach ( se_utterances($doc) as $u ) {
			$w = $u->attrs['who'] ?? "";
			if ( $w === "" || ltrim($w, "#") !== $from ) continue;
			$out[] = array($u->s, $u->te, se_tag_set(se_start_tag($doc, $u), "who", (substr($w, 0, 1) === "#" ? "#" : "") . $to));
		};
		return $out;
	};

	function se_op_rename_speaker ( $doc, $a ) {
		$p = se_find_person($doc, $a['id'] ?? ""); $new = trim($a['new'] ?? "");
		if ( $new === "" || preg_match('/[\s#"<>&]/', $new) ) throw new Exception("a speaker's id has no spaces or special characters");
		if ( $new === se_person_id($p) ) return array();
		foreach ( se_persons($doc) as $q ) if ( se_person_id($q) === $new ) throw new Exception("there is a speaker $new already");
		$out = se_who_splices($doc, se_person_id($p), $new);
		$out[] = array($p->s, $p->te, se_tag_set(se_start_tag($doc, $p), se_person_idattr($p), $new));
		return $out;
	};

	function se_op_set_role ( $doc, $a ) {
		$p = se_find_person($doc, $a['id'] ?? ""); $role = trim($a['role'] ?? "");
		return array(array($p->s, $p->te, se_tag_set(se_start_tag($doc, $p), "role", $role === "" ? null : $role)));
	};

	function se_op_set_name ( $doc, $a ) {
		$p = se_find_person($doc, $a['id'] ?? ""); $name = trim($a['name'] ?? "");
		list($pn, $old) = se_person_name($doc, $p);
		if ( $name === $old ) return array();
		if ( $pn && $name === "" ) return array(se_removal($doc, $pn));
		if ( $pn ) return array(array($pn->te, $pn->ce, se_esc_text($name)));
		if ( $name === "" ) return array();
		$ind = se_indent($doc, $p); $el = "\n$ind  <persName>" . se_esc_text($name) . "</persName>";
		if ( $p->ce === null ) return array(array($p->s, $p->e, se_tag_open(se_start_tag($doc, $p)) . "$el\n$ind</person>"));
		return array(array($p->te, $p->te, $el));
	};

	function se_op_merge_speakers ( $doc, $a ) {
		$from = se_find_person($doc, $a['from'] ?? ""); $to = se_find_person($doc, $a['to'] ?? "");
		if ( $from === $to ) throw new Exception("these are the same speaker");
		$out = se_who_splices($doc, se_person_id($from), se_person_id($to));
		$out[] = se_removal($doc, $from);
		return $out;
	};

	function se_op_add_speaker ( $doc, $a ) {
		$id = trim($a['id'] ?? ""); $role = trim($a['role'] ?? ""); $name = trim($a['name'] ?? "");
		if ( $id === "" || preg_match('/[\s#"<>&]/', $id) ) throw new Exception("a speaker's id has no spaces or special characters");
		$ps = se_persons($doc);
		foreach ( $ps as $q ) if ( se_person_id($q) === $id ) throw new Exception("there is a speaker $id already");
		if ( !$ps ) throw new Exception("the header has no list of speakers (listPerson) to add to");
		$last = $ps[count($ps) - 1]; $ind = se_indent($doc, $last);
		$tag = "<person id=\"" . se_esc_attr($id) . "\"" . ($role !== "" ? " role=\"" . se_esc_attr($role) . "\"" : "");
		$el = $name === "" ? "$tag />" : "$tag>\n$ind  <persName>" . se_esc_text($name) . "</persName>\n$ind</person>";
		return array(array($last->e, $last->e, "\n$ind$el"));
	};
?>
