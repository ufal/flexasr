<?php
	// spoken-edit: a keyboard-driven correction editor for spoken transcripts (utterances with @who, timed tokens)
	// index.php?action=spoken-edit&cid=FILE
	//   act=apply  POST {ops, hash}: the document as it would be with these operations, as JSON (nothing is written)
	//   act=save   POST {ops, hash}: apply the operations and write the document (logged-in staff only)
	//   act=ping   nothing: keeps the session alive while the editor is open
	// The editor keeps the list of operations (its undo stack); the server holds no state and re-applies the list to
	// the file each time, so a save writes exactly those operations, as splices of the original text.
	// Settings (optional), in settings.xml: <spokenedit lowconf="0.7" media="Audio"/>
	//   lowconf: the confidence under which a word is marked as uncertain; media: the folder of audio files

	check_login(getset('flexasr/admin') ? 'admin' : 'user');     # any staff login, or only administrators with <flexasr admin="1"/> as for the flexasr page
	require_once(__DIR__ . "/spoken-edit-io.php");
	require_once(__DIR__ . "/spoken-edit-scripts.php");

	function se_json ( $data, $code = 200 ) {
		http_response_code($code);
		header("Content-Type: application/json; charset=utf-8");
		print json_encode($data, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
		exit;
	};

	$se = getset('spokenedit', array());
	$cid = $_GET['cid'] ?? "";
	$path = se_path($cid);

	if ( ($_GET['act'] ?? "") == "ping" ) se_json(array("user" => $username ? 1 : 0));
	if ( !$path ) fatal("No such XML file: " . htmlspecialchars($cid));

	if ( in_array($_GET['act'] ?? "", array("apply", "save")) ) {
		$in = json_decode(file_get_contents("php://input"), true);
		if ( !is_array($in) || !isset($in['ops']) || !is_array($in['ops']) ) se_json(array("error" => "bad request"), 400);
		if ( $_GET['act'] == "save" && !$username ) se_json(array("error" => "not logged in"), 403);
		try {
			$raw = $_GET['act'] == "save" ? se_save($path, $in['ops'], $in['hash'] ?? "") : se_run($path, $in['ops'], $in['hash'] ?? "");
			se_json(se_model($raw));
		} catch ( Exception $e ) {
			se_json(array("error" => $e->getMessage()), 409);
		};
	};

	$model = se_model(file_get_contents($path));
	$media = $model['media'];
	if ( $media && !preg_match('#^(https?:)?//#', $media) && strpos($media, "/") === false ) $media = ($se['media'] ?? "Audio") . "/" . $media;
	$cfg = array("cid" => $cid, "base" => "index.php?action=$action&cid=" . rawurlencode($cid), "audio" => $media,
		"lowconf" => (float)($se['lowconf'] ?? 0.7), "canwrite" => $username ? 1 : 0, "wave" => "index.php?action=wavesurfer&cid=" . rawurlencode($cid),
		"waveedit" => $username ? "index.php?action=wavesurfer&act=edit&cid=" . rawurlencode(preg_match('/\.xml$/i', $cid) ? $cid : "$cid.xml") : "");
	$cfgjson = json_encode($cfg, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP);
	$modeljson = json_encode($model, JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_AMP | JSON_INVALID_UTF8_SUBSTITUTE);

	$scripts = "";
	foreach ( array("model", "audio", "view", "keys", "palette", "main") as $part )
		$scripts .= "<script src=\"" . htmlspecialchars(se_asset("spoken-edit-$part.js"), ENT_QUOTES) . "\"></script>\n";
	$cssurl = se_asset("spoken-edit.css", "spoken-edit-main.js");

	$maintext .= "<link rel='stylesheet' href=\"" . htmlspecialchars($cssurl, ENT_QUOTES) . "\">
		<h1>" . htmlspecialchars($model['title'] ?: $cid) . "</h1>
		<div id='se-app' class='se-app' tabindex='0'></div>
		$scripts<script>SE.main.init($cfgjson, $modeljson);</script>";
?>
