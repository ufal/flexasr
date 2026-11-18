<?php
	// spoken-edit: reading a spoken TEITOK document with the byte positions of its elements, and the small pieces to
	// change start tags and to rebuild an utterance. No regular expressions on markup: the expat parser reports where
	// elements start and end, start tags are scanned character by character, and an edit is a splice of the original
	// text (everything outside the spliced ranges stays byte for byte as it was).

	class SeNode {
		public $name, $attrs = array(), $s = 0, $te = 0, $ce = null, $e = 0, $kids = array(), $parent = null;
	}

	# The position just after the '>' that ends the start tag starting at $at (quotes in attribute values respected)
	function se_tag_end ( $raw, $at ) {
		$n = strlen($raw); $q = "";
		for ( $i = $at + 1; $i < $n; $i++ ) {
			$c = $raw[$i];
			if ( $q !== "" ) { if ( $c === $q ) $q = ""; }
			else if ( $c === '"' || $c === "'" ) $q = $c;
			else if ( $c === ">" ) return $i + 1;
		};
		return false;
	};

	# The position of the next start or end tag from $pos on, skipping comments, CDATA, processing instructions and the
	# DOCTYPE. (The positions the parser reports for end tags are not reliable, so the tags are found here.)
	function se_next_tag ( $raw, $pos ) {
		while ( ($at = strpos($raw, "<", $pos)) !== false ) {
			$two = substr($raw, $at, 4);
			if ( $two === "<!--" ) { $end = strpos($raw, "-->", $at + 4); $pos = $end === false ? strlen($raw) : $end + 3; }
			else if ( substr($raw, $at, 9) === "<![CDATA[" ) { $end = strpos($raw, "]]>", $at + 9); $pos = $end === false ? strlen($raw) : $end + 3; }
			else if ( substr($two, 0, 2) === "<?" ) { $end = strpos($raw, "?>", $at + 2); $pos = $end === false ? strlen($raw) : $end + 2; }
			else if ( substr($two, 0, 2) === "<!" ) {                        # DOCTYPE, with an internal subset in [ ]
				$depth = 0; $q = ""; $i = $at + 2; $n = strlen($raw);
				for ( ; $i < $n; $i++ ) {
					$c = $raw[$i];
					if ( $q !== "" ) { if ( $c === $q ) $q = ""; }
					else if ( $c === '"' || $c === "'" ) $q = $c;
					else if ( $c === "[" ) $depth++;
					else if ( $c === "]" ) $depth--;
					else if ( $c === ">" && $depth <= 0 ) break;
				};
				$pos = $i + 1;
			}
			else return $at;
		};
		return false;
	};

	# array( raw, root, all ) with every element as an SeNode (s: start of its start tag, te: end of the start tag,
	# ce: start of the end tag (null when empty), e: end of the element), or null when the text does not parse
	function se_parse ( $raw ) {
		$root = new SeNode(); $root->name = "#root"; $root->e = strlen($raw);
		$stack = array($root); $all = array(); $cursor = 0; $bad = false;
		$p = xml_parser_create("UTF-8");
		xml_parser_set_option($p, XML_OPTION_CASE_FOLDING, 0);
		xml_set_element_handler($p, function ( $p, $name, $attrs ) use ( $raw, &$stack, &$all, &$cursor, &$bad ) {
			$at = se_next_tag($raw, $cursor);
			if ( $at === false || substr($raw, $at + 1, strlen($name)) !== $name ) { $bad = true; return; };
			$n = new SeNode(); $n->name = $name; $n->attrs = $attrs; $n->s = $at;
			$n->te = se_tag_end($raw, $at); $n->e = $n->te; $cursor = $n->te;
			$n->parent = end($stack); $n->parent->kids[] = $n; $all[] = $n; $stack[] = $n;
		}, function ( $p, $name ) use ( $raw, &$stack, &$cursor, &$bad ) {
			$n = array_pop($stack);
			if ( $n->te === false || substr($raw, $n->te - 2, 2) === "/>" ) return;    # an empty element: no end tag
			$at = se_next_tag($raw, $cursor);
			if ( $at === false || substr($raw, $at, 2 + strlen($name)) !== "</" . $name ) { $bad = true; return; };
			$n->ce = $at; $n->e = strpos($raw, ">", $at) + 1; $cursor = $n->e;
		});
		$ok = xml_parse($p, $raw, true);
		if ( PHP_VERSION_ID < 80000 ) xml_parser_free($p);
		return $ok && !$bad ? array("raw" => $raw, "root" => $root, "all" => $all) : null;
	};

	function se_esc_text ( $t ) { return str_replace(array("&", "<", ">"), array("&amp;", "&lt;", "&gt;"), $t); };
	function se_esc_attr ( $v, $q = '"' ) {
		$v = str_replace(array("&", "<", "\t", "\n", "\r"), array("&amp;", "&lt;", "&#9;", "&#10;", "&#13;"), $v . "");
		return $q === "'" ? str_replace("'", "&apos;", $v) : str_replace('"', "&quot;", $v);
	};
	function se_unesc ( $t ) { return html_entity_decode($t, ENT_QUOTES | ENT_XML1, "UTF-8"); };

	# The attributes of a start tag as positions: array( end of the name, list of array(name, as, vs, ve, q, ae) )
	function se_tag_scan ( $tag ) {
		$n = strlen($tag); $ws = " \t\r\n";
		$i = 1 + strcspn($tag, "$ws/>", 1); $ne = $i; $out = array();
		while ( $i < $n ) {
			$as = $i; $i += strspn($tag, $ws, $i);
			if ( $i >= $n || $tag[$i] === ">" || $tag[$i] === "/" ) break;
			$ns = $i; $i += strcspn($tag, "$ws=/>", $i); $name = substr($tag, $ns, $i - $ns);
			$i += strspn($tag, $ws, $i);
			if ( ($tag[$i] ?? "") !== "=" ) break;
			$i++; $i += strspn($tag, $ws, $i);
			$q = $tag[$i] ?? "";
			if ( $q !== '"' && $q !== "'" ) break;
			$vs = $i + 1; $ve = strpos($tag, $q, $vs);
			if ( $ve === false ) break;
			$out[] = array("name" => $name, "as" => $as, "vs" => $vs, "ve" => $ve, "q" => $q, "ae" => $ve + 1);
			$i = $ve + 1;
		};
		return array($ne, $out);
	};

	# A start tag with attribute NAME set to VALUE (null: removed). An existing attribute keeps its place and quotes; a
	# new one goes after the last attribute.
	function se_tag_set ( $tag, $name, $value ) {
		list($ne, $attrs) = se_tag_scan($tag);
		foreach ( $attrs as $a ) {
			if ( $a['name'] !== $name ) continue;
			if ( $value === null ) return substr($tag, 0, $a['as']) . substr($tag, $a['ae']);
			return substr($tag, 0, $a['vs']) . se_esc_attr($value, $a['q']) . substr($tag, $a['ve']);
		};
		if ( $value === null ) return $tag;
		$at = $attrs ? $attrs[count($attrs) - 1]['ae'] : $ne;
		return substr($tag, 0, $at) . " $name=\"" . se_esc_attr($value) . "\"" . substr($tag, $at);
	};

	function se_tag_open ( $tag ) {      # <u a="b"/> -> <u a="b">
		if ( substr($tag, -2) !== "/>" ) return $tag;
		return rtrim(substr($tag, 0, -2)) . ">";
	};

	# Splices (array( start, end, replacement )) applied to the text, last first; they must not overlap
	function se_splice ( $raw, $splices ) {
		usort($splices, function ( $a, $b ) { return $b[0] <=> $a[0]; });
		$prev = strlen($raw) + 1;
		foreach ( $splices as $sp ) {
			if ( $sp[1] > $prev || $sp[0] > $sp[1] ) throw new Exception("overlapping changes");
			$raw = substr($raw, 0, $sp[0]) . $sp[2] . substr($raw, $sp[1]);
			$prev = $sp[0];
		};
		return $raw;
	};

	function se_start_tag ( $doc, $n ) { return substr($doc['raw'], $n->s, $n->te - $n->s); };
	function se_node_raw ( $doc, $n ) { return substr($doc['raw'], $n->s, $n->e - $n->s); };

	# The text of an element without its inner elements' own markup (entities decoded), inner elements' text included
	function se_node_text ( $doc, $n ) {
		if ( $n->ce === null ) return "";
		$raw = $doc['raw']; $out = ""; $pos = $n->te;
		foreach ( $n->kids as $k ) { $out .= se_unesc(substr($raw, $pos, $k->s - $pos)) . se_node_text($doc, $k); $pos = $k->e; };
		return $out . se_unesc(substr($raw, $pos, $n->ce - $pos));
	};

	function se_descendants ( $n ) {
		$out = array();
		foreach ( $n->kids as $k ) { $out[] = $k; foreach ( se_descendants($k) as $d ) $out[] = $d; };
		return $out;
	};

	# The top-level utterances (not inside another one), in document order
	function se_utterances ( $doc ) {
		$out = array();
		foreach ( $doc['all'] as $n ) {
			if ( $n->name !== "u" ) continue;
			for ( $p = $n->parent; $p; $p = $p->parent ) if ( $p->name === "u" ) continue 2;
			$out[] = $n;
		};
		return $out;
	};

	function se_find_u ( $doc, $id ) {
		foreach ( se_utterances($doc) as $k => $n ) if ( ($n->attrs['id'] ?? null) === $id ) return array($k, $n);
		throw new Exception("no utterance $id");
	};

	function se_is_punct ( $t ) { return $t !== "" && preg_match('/^[\p{P}\p{S}]+$/u', $t) === 1; };

	# The earliest start and latest end among an element and everything in it: array(start, end) or null
	function se_node_times ( $n ) {
		$s = null; $e = null;
		foreach ( array_merge(array($n), se_descendants($n)) as $d ) {
			if ( isset($d->attrs['start']) && is_numeric($d->attrs['start']) ) $s = $s === null ? (float)$d->attrs['start'] : min($s, (float)$d->attrs['start']);
			if ( isset($d->attrs['end']) && is_numeric($d->attrs['end']) ) $e = $e === null ? (float)$d->attrs['end'] : max($e, (float)$d->attrs['end']);
		};
		return $s === null && $e === null ? null : array($s, $e);
	};

	# The next number for ids like PREFIX123: highest in the document + 1. Returns array( prefix, next number ).
	function se_id_counter ( $doc, $elname, $default ) {
		$prefix = $default; $max = 0; $all = array();
		foreach ( $doc['all'] as $n ) if ( isset($n->attrs['id']) ) $all[] = $n;
		foreach ( $all as $n ) if ( $n->name === $elname && preg_match('/^(.*?)(\d+)$/', $n->attrs['id'], $m) ) { $prefix = $m[1]; break; };
		foreach ( $all as $n ) if ( strpos($n->attrs['id'], $prefix) === 0 && ctype_digit(substr($n->attrs['id'], strlen($prefix))) ) $max = max($max, (int)substr($n->attrs['id'], strlen($prefix)));
		return array($prefix, $max + 1);
	};
?>
