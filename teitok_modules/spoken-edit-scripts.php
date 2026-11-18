<?php
	// spoken-edit: the URL of a script (or stylesheet) in Scripts/, for the pages of spoken-edit. TEITOK's
	// getjsurl() turns a file in the shared project into an absolute URL from the document root, which loses the
	// prefix of a proxy in front of the server (/teitok-dev/teitok/… becomes /teitok/…). When the shared project
	// lies in the same web tree as the project, a path relative to the project works behind any prefix.

	if ( !function_exists("se_scripturl") ) {
		// NAME: the file in Scripts/ (deptree-edit-main.js, deptree-edit.css); VIA: for a stylesheet, a script next to
		// it (getjsurl() only finds scripts)
		function se_scripturl ( $name, $via = "" ) {
			global $sharedfolder, $ttlayers;
			if ( file_exists("Scripts/$name") ) return "Scripts/$name";
			# A TEITOK with layers ($ttlayers: project, group, site, modules, common): the first layer that has the file
			if ( !empty($ttlayers) ) {
				foreach ( $ttlayers as $layer => $dir ) {
					if ( $layer == "project" || $layer == "common" || !$dir || !is_file("$dir/Scripts/$name") ) continue;
					$url = se_layer_url($layer, $dir, $name);
					if ( $url ) return $url;
				};
			};
			$url = se_layer_url("shared", $sharedfolder, $name);
			if ( $url ) return $url;
			$url = getjsurl(preg_replace("/\.js$/", "", $via ?: $name));  # the project, the shared project, ttroot
			$cut = strrpos($url, "/");
			return ($cut === false ? "" : substr($url, 0, $cut + 1)) . $name;
		}

		// The URL of NAME in the Scripts/ of a layer folder: from the settings (defaults/LAYER/url; defaults/shared/url for the
		// nearest shared folder), else a path relative to the project when both are served from the same web tree (works behind
		// any proxy prefix), else, for a layer the web server cannot serve (modules outside the web root), TEITOK's asset action
		// (plain file names only). null: this layer does not have it
		function se_layer_url ( $layer, $dir, $name ) {
			global $sharedfolder;
			if ( !$dir || !is_file("$dir/Scripts/$name") ) return null;
			$url = getset("defaults/$layer/url");
			if ( !$url && $dir == $sharedfolder ) $url = getset("defaults/shared/url");
			if ( $url ) return substr($url, -8) == "/Scripts" ? "$url/$name" : "$url/Scripts/$name";
			$here = realpath("."); $there = realpath("$dir/Scripts");     # the folder: the file may be a link
			$base = $here && $there ? se_webbase($here) : false;
			if ( $base && $base === se_webbase($there) ) return se_relpath($here, $there . DIRECTORY_SEPARATOR . $name);
			if ( $layer != "shared" && preg_match('/^[A-Za-z0-9_.-]+$/', $name) ) return "index.php?action=asset&f=" . rawurlencode($name);
			return null;
		}

		// The web folder a real path is served from: the document root, or (as TEITOK's getUrlFromFilesystemPath)
		// what a link in the document root points to; false when it is not served
		function se_webbase ( $path ) {
			$docroot = $_SERVER['DOCUMENT_ROOT'] ?? "";
			$real = $docroot !== "" ? realpath($docroot) : false;
			if ( !$real ) return false;
			if ( se_inside($path, $real) ) return $real;
			foreach ( @scandir($docroot) ?: array() as $entry ) {
				if ( $entry == "." || $entry == ".." ) continue;
				$to = realpath($docroot . DIRECTORY_SEPARATOR . $entry);
				if ( $to && is_dir($to) && se_inside($path, $to) ) return $to;
			};
			return false;
		}

		function se_inside ( $path, $dir ) {
			return strpos($path . DIRECTORY_SEPARATOR, rtrim($dir, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR) === 0;
		}

		// The path from folder FROM to file TO (both real paths), with / as separator
		function se_relpath ( $from, $to ) {
			$a = explode(DIRECTORY_SEPARATOR, trim($from, DIRECTORY_SEPARATOR));
			$b = explode(DIRECTORY_SEPARATOR, trim($to, DIRECTORY_SEPARATOR));
			while ( $a && $b && $a[0] === $b[0] ) { array_shift($a); array_shift($b); };
			return str_repeat("../", count($a)) . implode("/", $b);
		}
	};

	// Run a command (an array: program and arguments, no shell) in $cwd with extra environment variables; wait at most $timeout seconds.
	// Returns array(exit code or null, the output of both streams, error text or "").
	if ( !function_exists("se_run_process") ) {
		function se_run_process ( $cmd, $cwd, $extraenv = array(), $timeout = 180 ) {
			$env = getenv();
			foreach ( $extraenv as $k => $v ) $env[$k] = $v;
			$proc = @proc_open($cmd, array(1 => array("pipe", "w"), 2 => array("pipe", "w")), $pipes, $cwd, $env);
			if ( !is_resource($proc) ) return array(null, "", "the program could not be started");
			stream_set_blocking($pipes[1], false); stream_set_blocking($pipes[2], false);
			$t0 = time(); $out = ""; $err = "";
			while ( true ) {
				$out .= stream_get_contents($pipes[1]) . stream_get_contents($pipes[2]);
				$st = proc_get_status($proc);
				if ( !$st['running'] ) break;
				if ( time() - $t0 > $timeout ) { proc_terminate($proc); $err = "it took too long"; break; };
				usleep(100000);
			};
			$out .= stream_get_contents($pipes[1]) . stream_get_contents($pipes[2]);
			foreach ( $pipes as $pp ) fclose($pp);
			$code = proc_close($proc);
			return array($err === "" ? $code : null, $out, $err);
		}
	};

	// The URL of a script or stylesheet with a version in it (its modification time), so that a browser that has an older copy loads the new one: the version follows the file
	// itself, found where it is installed (the project's or the shared project's Scripts/, or next to the modules)
	if ( !function_exists("se_asset") ) {
		function se_asset ( $name, $via = "" ) {
			global $sharedfolder, $ttlayers;
			$m = 0;
			$cands = array("Scripts/$name", ($sharedfolder ? "$sharedfolder/Scripts/$name" : ""), __DIR__ . "/$name", __DIR__ . "/../Scripts/$name");
			foreach ( (array)$ttlayers as $layer => $dir ) if ( $layer != "common" && $dir ) $cands[] = "$dir/Scripts/$name";
			foreach ( $cands as $f ) if ( $f !== "" && is_file($f) ) $m = max($m, (int)@filemtime($f));
			$url = se_scripturl($name, $via);
			return $url . ($m ? (strpos($url, "?") === false ? "?" : "&") . "v=$m" : "");     # the asset action's URL has a query already
		}
	};
?>
