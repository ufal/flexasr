<?php
	// spoken-edit: finding the document and writing it back. The edits are splices of the original text (see
	// spoken-edit-ops.php), the file is written in place after TEITOK's once-a-day backup, and a save is refused when
	// the file is not the one the editor loaded.

	require_once(__DIR__ . "/spoken-edit-model.php");

	# xmlfiles/NAME.xml for a cid (NAME, NAME.xml or xmlfiles/NAME.xml); null when it is not a file there
	function se_path ( $cid ) {
		$cid = preg_replace('#^xmlfiles/#', "", trim($cid . ""));
		if ( $cid === "" || strpos($cid, "..") !== false || $cid[0] === "/" || strpos($cid, "\0") !== false ) return null;
		if ( substr($cid, -4) !== ".xml" ) $cid .= ".xml";
		return is_file("xmlfiles/$cid") ? "xmlfiles/$cid" : null;
	};

	# The result of the operations on the file, without writing: array(raw, model). Throws when they do not apply or
	# when the file is no longer the one with this hash.
	function se_run ( $path, $ops, $hash ) {
		$raw = file_get_contents($path);
		if ( $raw === false ) throw new Exception("the document cannot be read");
		if ( $hash !== "" && sha1($raw) !== $hash ) throw new Exception("the document changed since it was loaded: reload the page");
		return se_apply($raw, $ops);
	};

	# Backup (backups/NAME-YYYYMMDD.xml, when there is none for today yet), then the file itself, in place
	function se_write_doc ( $path, $old, $new, $backups = "backups" ) {
		if ( !is_dir($backups) ) @mkdir($backups);
		$bu = "$backups/" . preg_replace("/\.xml$/", "-" . date("Ymd") . ".xml", basename($path));
		if ( !file_exists($bu) && @file_put_contents($bu, $old) === false ) return "no backup could be made";
		$fh = @fopen($path, "c+");
		if ( !$fh || !flock($fh, LOCK_EX) ) return "the document cannot be written";
		if ( stream_get_contents($fh) !== $old ) { flock($fh, LOCK_UN); fclose($fh); return "the document changed in the meantime"; };
		ftruncate($fh, 0); rewind($fh);
		$ok = fwrite($fh, $new) === strlen($new);
		fflush($fh); flock($fh, LOCK_UN); fclose($fh);
		return $ok ? "" : "the document could not be written completely";
	};

	# Apply and write; returns the new text. With no operations (or none that change anything) the file is left alone.
	function se_save ( $path, $ops, $hash ) {
		$old = file_get_contents($path);
		$new = se_run($path, $ops, $hash);
		if ( $new === $old ) return $new;
		$err = se_write_doc($path, $old, $new);
		if ( $err !== "" ) throw new Exception($err);
		return $new;
	};
?>
