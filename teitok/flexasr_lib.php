<?php
// flexasr TEITOK module: helpers (settings, audio files, jobs, command line, results).
// Used by flexasr.php; defines functions only.

function fa_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

// --- settings (settings.xml: <flexasr bin=".." home=".." models_dir=".." hf_home=".." admin="1" .../>) ---

function fa_bin() { return getset('flexasr/bin', 'flexasr'); }

function fa_env() {
	// Environment for the flexasr process (the web server user usually has no ~/.flexasr of its own).
	$env = array();
	foreach ( array('home' => 'FLEXASR_HOME', 'models_dir' => 'FLEXASR_MODELS', 'hf_home' => 'HF_HOME',
			'models_repo' => 'FLEXASR_MODELS_REPO') as $key => $var ) {
		$val = getset("flexasr/$key", '');
		if ( $val ) $env[] = $var.'='.escapeshellarg($val);
	};
	return $env ? implode(' ', $env).' ' : '';
}

function fa_cmd($args) {
	// One shell command from a binary and its arguments; every part is escaped.
	return fa_env().implode(' ', array_map('escapeshellarg', $args));
}

// --- audio ---

function fa_audio_folder() { return rtrim(getset('files/audio/folder', 'Audio'), '/'); }

function fa_audio_files() {
	$root = fa_audio_folder();
	$out = array();
	if ( !is_dir($root) ) return $out;
	$it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS));
	foreach ( $it as $f ) {
		if ( preg_match('/\.(wav|mp3|m4a|flac|ogg|opus|mp4|webm)$/i', $f->getFilename()) )
			$out[] = str_replace('\\', '/', $f->getPathname());
	};
	sort($out);
	return $out;
}

function fa_audio_path($rel) {
	// A relative audio path, only if it really is inside the audio folder (no ../ tricks).
	$root = realpath(fa_audio_folder());
	$full = realpath($rel);
	if ( !$root || !$full || strpos($full, $root.DIRECTORY_SEPARATOR) !== 0 || !is_file($full) ) return false;
	return fa_audio_folder().substr($full, strlen($root));
}

function fa_file_id($name) {
	// A safe file id (no folders, no extension): letters, digits, _ . -
	$name = preg_replace('/\.[^.\/]+$/', '', basename($name));
	return trim(preg_replace('/[^A-Za-z0-9_.-]+/', '_', $name), '._');
}

// --- models (flexasr models --json, cached briefly) ---

function fa_models($lang, $mode, $allow) {
	$key = md5("$lang|$mode|$allow");
	$cache = fa_jobdir()."/models-$key.json";
	if ( file_exists($cache) && time() - filemtime($cache) < 600 ) {
		$data = json_decode(file_get_contents($cache), true);
		if ( $data ) return $data;
	};
	$args = array(fa_bin(), 'models', '--json', '--mode', $mode);
	if ( $lang ) { $args[] = '-l'; $args[] = $lang; };
	if ( $allow ) $args[] = '--allow-restricted';
	$json = shell_exec(fa_cmd($args).' 2>/dev/null');
	$data = json_decode((string)$json, true);
	if ( $data ) file_put_contents($cache, $json);
	return $data;
}

// --- jobs: tmp/flexasr-jobs/<id>.json (spec), .status, .log, .xml (until moved), .stages/ ---

function fa_jobdir() {
	$d = 'tmp/flexasr-jobs';
	if ( !is_dir($d) ) mkdir($d, 0777, true);
	return $d;
}

function fa_valid_job($id) { return is_string($id) && preg_match('/^[A-Za-z0-9_-]{6,64}$/', $id); }

function fa_job($id) {
	if ( !fa_valid_job($id) ) return null;
	$f = fa_jobdir()."/$id.json";
	if ( !file_exists($f) ) return null;
	$job = json_decode(file_get_contents($f), true);
	$job['status'] = trim(@file_get_contents(fa_jobdir()."/$id.status")) ?: 'unknown';
	return $job;
}

function fa_jobs($limit = 30) {
	$files = glob(fa_jobdir().'/*.json');
	$files = array_filter($files, function ($f) { return strpos(basename($f), 'models-') !== 0; });
	usort($files, function ($a, $b) { return filemtime($b) - filemtime($a); });
	$out = array();
	foreach ( array_slice($files, 0, $limit) as $f ) {
		$job = fa_job(basename($f, '.json'));
		if ( $job ) $out[] = $job;
	};
	return $out;
}

function fa_log_tail($id, $bytes = 20000) {
	$f = fa_jobdir()."/$id.log";
	if ( !file_exists($f) ) return '';
	$size = filesize($f);
	$fh = fopen($f, 'r');
	if ( $size > $bytes ) fseek($fh, -$bytes, SEEK_END);
	$txt = stream_get_contents($fh);
	fclose($fh);
	return $txt;
}

function fa_run_args($job, $out) {
	// The flexasr command line for a job (as an argument list).
	$a = array(fa_bin(), 'run', $job['audio'], '-o', $out, '--media-url', $job['audio'],
		'--mode', $job['mode'], '--keep', fa_jobdir().'/'.$job['id'].'.stages');
	if ( $job['lang'] ) { $a[] = '-l'; $a[] = $job['lang']; };
	if ( $job['speakers'] ) { $a[] = '--speakers'; $a[] = $job['speakers']; };
	if ( $job['allow_restricted'] ) $a[] = '--allow-restricted';
	if ( $job['untokenized'] ) { $a[] = '--untokenized-roles'; $a[] = $job['untokenized']; };
	foreach ( $job['models'] as $stage => $model ) {
		if ( $model ) { $a[] = '--model'; $a[] = "$stage=$model"; };
	};
	return $a;
}

function fa_start($job) {
	// Write the job spec and start it in the background. Jobs run one at a time where flock exists
	// (Linux): the others wait in "queued".
	$dir = fa_jobdir();
	$id = $job['id'];
	$q = function ($s) { return escapeshellarg($s); };
	file_put_contents("$dir/$id.json", json_encode($job, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
	file_put_contents("$dir/$id.status", "queued\n");
	$tmpout = "$dir/$id.xml";
	$work = 'echo running > '.$q("$dir/$id.status").'; '
		.fa_cmd(fa_run_args($job, $tmpout)).' >> '.$q("$dir/$id.log").' 2>&1'
		.' && mkdir -p '.$q(dirname($job['output'])).' && mv -f '.$q($tmpout).' '.$q($job['output']);
	$inner = 'sh -c '.$q($work);
	$serial = 'if command -v flock >/dev/null 2>&1; then flock '.$q("$dir/run.lock").' '.$inner.'; else '.$inner.'; fi';
	$runner = '(cd '.$q(getcwd()).' && { '.$serial.'; }; rc=$?; '
		.'if [ $rc -eq 0 ]; then echo done > '.$q("$dir/$id.status").'; else echo failed > '.$q("$dir/$id.status").'; fi)'
		.' > /dev/null 2>&1 &';
	file_put_contents("$dir/$id.log", '$ '.fa_cmd(fa_run_args($job, $tmpout))."\n");
	shell_exec($runner);
}

// --- results ---

function fa_result_info($xmlfile) {
	// From the TEI header: which model produced each layer, with licence and restrictions;
	// and how many tokens carry a confidence score.
	$info = array('layers' => array(), 'restricted' => array(), 'conf' => 0, 'toks' => 0, 'utts' => 0);
	if ( !file_exists($xmlfile) ) return $info;
	$xml = @simplexml_load_file($xmlfile);
	if ( !$xml ) return $info;
	foreach ( $xml->xpath('//appInfo/application') as $app ) {
		$desc = (string)$app->desc;
		$info['layers'][] = array('type' => (string)$app['type'], 'provider' => (string)$app['ident'],
			'model' => (string)$app->label, 'source' => (string)$app->ptr['target'], 'desc' => $desc);
		if ( preg_match('/restricted: (.*)$/', $desc, $m) ) $info['restricted'][(string)$app->label] = $m[1];
	};
	$info['toks'] = count($xml->xpath('//tok'));
	$info['conf'] = count($xml->xpath('//tok[@conf]'));
	$info['utts'] = count($xml->xpath('//u'));
	return $info;
}
