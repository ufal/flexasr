<?php
// flexasr TEITOK module: run the flexasr speech recognition pipeline on audio in this corpus.
//   index.php?action=flexasr                 recent tasks, start a new one
//   index.php?action=flexasr&act=configure   models and settings for one audio file
//   index.php?action=flexasr&act=run         start (POST)
//   index.php?action=flexasr&act=job&job=ID  progress, log and result
//   index.php?action=flexasr&api=status&job=ID   JSON for the progress page
// Settings (settings.xml): <flexasr bin="/path/to/venv/bin/flexasr" home="/path/to/flexasr-home"
//   models_dir="/big/disk/models" hf_home="..." admin="1"/>  (admin="1": only admins may run jobs)

check_login(getset('flexasr/admin') ? 'admin' : 'user');
require_once(__DIR__.'/flexasr_lib.php');

$fa_modes = array('verbatim' => '{%verbatim} ({%keeps fillers, repetitions, false starts})',
	'clean' => '{%clean} ({%readable text, disfluencies dropped})');

if ( $_GET['api'] == 'status' ) {
	header('Content-Type: application/json');
	$job = fa_job($_GET['job']);
	if ( !$job ) { http_response_code(404); print json_encode(array('error' => 'no such job')); exit; };
	print json_encode(array('status' => $job['status'], 'log' => fa_log_tail($job['id'])));
	exit;

} else if ( $act == 'configure' ) {
	$audio = fa_audio_path($_GET['audio']);
	if ( !$audio ) fatal('No such audio file in '.fa_h(fa_audio_folder()));
	$lang = preg_replace('/[^A-Za-z_-]/', '', $_GET['lang'] ?: getset('flexasr/language', getset('defaults/language', '')));
	$mode = $_GET['mode'] == 'clean' ? 'clean' : 'verbatim';
	$allow = $_GET['restricted'] ? 1 : 0;
	$models = fa_models($lang, $mode, $allow);
	$fid = fa_file_id($audio);

	$maintext .= "<h1>{%Speech recognition}: ".fa_h(basename($audio))."</h1>
		<audio src='".fa_h($audio)."' controls preload='none' style='width: 100%; max-width: 600px;'></audio>";
	if ( !$models ) {
		$maintext .= "<p class='wrong'>{%flexasr could not be started on the server.}</p>";
		if ( $user['permissions'] == 'admin' )
			$maintext .= "<p class='adminpart'>Check &lt;flexasr bin=\"...\"/&gt; in settings.xml (now: ".fa_h(fa_bin()).").</p>";
		return;
	};
	$maintext .= "<form action='index.php?action=$action&act=run' method='post'>
		<input type='hidden' name='audio' value='".fa_h($audio)."'>
		<input type='hidden' name='lang' value='".fa_h($lang)."'>
		<input type='hidden' name='mode' value='$mode'>
		<input type='hidden' name='restricted' value='$allow'>
		<table>
		<tr><th>{%Language}</th><td>".fa_h($models['language_name'] ?: '{%detect automatically}')."</td></tr>
		<tr><th>{%Mode}</th><td>".$fa_modes[$mode]."</td></tr>";
	$notices = array();
	foreach ( array('diarize' => '{%Speakers}', 'transcribe' => '{%Transcription}', 'align' => '{%Word times}') as $task => $label ) {
		$choice = $models['choice'][$task];
		$opts = "<option value=''>{%automatic}: ".fa_h($choice['id'] ?: '{%none usable}')."</option>";
		$unusable = array();
		foreach ( $models['entries'] as $e ) {
			if ( $e['task'] == $task && !$e['usable'] ) $unusable[] = fa_h($e['id']).': '.fa_h(implode('; ', $e['why_not']));
			if ( $e['task'] != $task || !$e['usable'] ) continue;
			$flag = $e['restricted'] ? ' ['.implode(', ', $e['restricted']).']' : '';
			$opts .= "<option value='".fa_h($e['id'])."'>".fa_h($e['id'].$flag)."</option>";
			if ( $e['restricted'] && $e['licence_note'] ) $notices[$e['licence_note']][] = $e['id'];
		};
		$notes = '';
		foreach ( (array)$choice['notes'] as $n ) $notes .= "<div style='color: #996600; font-size: smaller;'>".fa_h($n)."</div>";
		if ( $choice['error'] ) $notes .= "<div class='wrong' style='font-size: smaller;'>".nl2br(fa_h($choice['error']))."</div>";
		if ( $unusable && $user['permissions'] == 'admin' )
			$notes .= "<details class='adminpart' style='font-size: smaller;'><summary>{%not usable on this server}</summary>"
				.implode('<br>', $unusable)."</details>";
		$maintext .= "<tr><th>$label</th><td><select name='model[$task]'>$opts</select>$notes</td></tr>";
	};
	$maintext .= "
		<tr><th>{%Number of speakers}</th><td><input name='speakers' size='6' placeholder='2 / 2-4'> <span style='font-size: smaller;'>{%empty: estimate}</span></td></tr>
		<tr><th>{%Roles without tokens}</th><td><input name='untokenized' size='20' placeholder='interviewer'></td></tr>
		<tr><th>{%Output file}</th><td>xmlfiles/<input name='fid' value='".fa_h($fid)."' size='30'>.xml
			<label><input type='checkbox' name='overwrite' value='1'> {%replace if it exists}</label></td></tr>
		</table>";
	if ( $notices ) {
		$maintext .= "<h3>{%Licence conditions}</h3>";
		foreach ( $notices as $note => $ids ) $maintext .= "<p><b>".fa_h(implode(', ', $ids))."</b>: ".fa_h($note)."</p>";
	};
	$maintext .= "<p><input type='submit' value='{%Start}'> <a href='index.php?action=$action'>{%cancel}</a></p></form>";

} else if ( $act == 'run' ) {
	$audio = fa_audio_path($_POST['audio']);
	if ( !$audio ) fatal('No such audio file');
	$fid = fa_file_id($_POST['fid'] ?: $audio);
	if ( !$fid ) fatal('No valid output file name');
	$output = "xmlfiles/$fid.xml";
	if ( file_exists($output) && !$_POST['overwrite'] ) {
		$maintext .= "<h1>{%Speech recognition}</h1><p class='wrong'>".fa_h($output)." {%already exists}.</p>
			<p><a href='javascript:history.back()'>{%back}</a></p>";
		return;
	};
	$models = array();
	foreach ( array('diarize', 'transcribe', 'align') as $task ) {
		$m = $_POST['model'][$task];
		if ( $m && preg_match('/^[A-Za-z0-9_.-]+$/', $m) ) $models[$task] = $m;
	};
	$speakers = preg_match('/^\d+(-\d+)?$/', $_POST['speakers']) ? $_POST['speakers'] : '';
	$job = array(
		'id' => date('Ymd-His').'-'.substr(md5(uniqid('', true)), 0, 6),
		'user' => $username, 'started' => date('c'),
		'audio' => $audio, 'output' => $output, 'fid' => $fid,
		'lang' => preg_replace('/[^A-Za-z_-]/', '', $_POST['lang']),
		'mode' => $_POST['mode'] == 'clean' ? 'clean' : 'verbatim',
		'allow_restricted' => $_POST['restricted'] ? true : false,
		'speakers' => $speakers,
		'untokenized' => preg_replace('/[^A-Za-z0-9_,-]/', '', $_POST['untokenized']),
		'models' => $models,
	);
	fa_start($job);
	header("Location: index.php?action=$action&act=job&job=".$job['id']);
	print "<script>top.location='index.php?action=$action&act=job&job=".$job['id']."';</script>";
	exit;

} else if ( $act == 'job' ) {
	$job = fa_job($_GET['job']);
	if ( !$job ) fatal('No such task');
	$id = $job['id'];
	$maintext .= "<h1>{%Speech recognition}: ".fa_h(basename($job['audio']))."</h1>
		<p>{%Started} ".fa_h($job['started'])." {%by} ".fa_h($job['user'])
		." &middot; ".fa_h($job['lang'] ?: 'auto')." &middot; ".fa_h($job['mode'])
		.($job['allow_restricted'] ? " &middot; {%restricted models allowed}" : '')."</p>
		<p>{%Status}: <b id='fa-status'>".fa_h($job['status'])."</b></p>";
	if ( $job['status'] == 'done' && file_exists($job['output']) ) {
		$cid = $job['fid'];
		$info = fa_result_info($job['output']);
		$maintext .= "<h2>{%Result}</h2>
			<p>".fa_h($job['output']).": {$info['utts']} {%utterances}, {$info['toks']} {%tokens}</p>
			<p><a href='index.php?action=wavesurfer&cid=".urlencode($cid)."'>{%Waveform view}</a>
			&middot; <a href='index.php?action=file&cid=".urlencode($cid)."'>{%Text view}</a>";
		if ( $info['conf'] )
			$maintext .= " &middot; <a href='index.php?action=whisper&cid=".urlencode($cid)."'>{%Confidence view}</a>";
		$maintext .= "</p>";
		if ( $info['restricted'] ) {
			$maintext .= "<p style='background: #fff3cd; padding: 6px;'>{%This transcript was made with a model under a restricted licence}: ";
			foreach ( $info['restricted'] as $model => $what ) $maintext .= fa_h("$model ($what)")." ";
			$maintext .= "<br>{%The restriction is recorded in the TEI header of the file.}</p>";
		};
		$maintext .= "<table><tr><th>{%Step}</th><th>{%Model}</th><th>{%Source}</th><th>{%Licence}</th></tr>";
		foreach ( $info['layers'] as $l ) {
			if ( $l['type'] == 'pipeline' ) continue;
			$maintext .= "<tr><td>".fa_h($l['type'])."</td><td>".fa_h($l['model'] ?: $l['provider'])."</td><td>"
				.fa_h($l['source'])."</td><td>".fa_h($l['desc'])."</td></tr>";
		};
		$maintext .= "</table>";
	} else if ( $job['status'] == 'done' ) {
		$maintext .= "<p class='wrong'>{%The output file is missing}: ".fa_h($job['output'])."</p>";
	};
	$maintext .= "<h2>{%Log}</h2><pre id='fa-log' style='max-height: 400px; overflow: auto; font-size: smaller; white-space: pre-wrap;'>"
		.fa_h(fa_log_tail($id))."</pre>
		<p><a href='index.php?action=$action'>{%All tasks}</a></p>";
	if ( $job['status'] == 'queued' || $job['status'] == 'running' ) {
		$maintext .= "<script>
		(function () {
			var url = 'index.php?action=$action&api=status&job=".urlencode($id)."';
			var timer = setInterval(function () {
				fetch(url).then(function (r) { return r.json(); }).then(function (d) {
					document.getElementById('fa-status').textContent = d.status;
					var log = document.getElementById('fa-log');
					log.textContent = d.log; log.scrollTop = log.scrollHeight;
					if ( d.status != 'queued' && d.status != 'running' ) { clearInterval(timer); location.reload(); }
				});
			}, 3000);
		})();
		</script>";
	};

} else {
	$maintext .= "<h1>{%Speech recognition}</h1>
		<p>{%Transcribe an audio file of this corpus into a TEITOK file with speakers and word times.}</p>
		<h2>{%New task}</h2>";
	$files = fa_audio_files();
	if ( !$files ) {
		$maintext .= "<p>{%There are no audio files yet.}</p>";
	} else {
		$opts = '';
		foreach ( $files as $f ) $opts .= "<option value='".fa_h($f)."'>".fa_h(substr($f, strlen(fa_audio_folder()) + 1))."</option>";
		$lang = getset('flexasr/language', getset('defaults/language', ''));
		$modeopts = '';
		foreach ( $fa_modes as $k => $v ) $modeopts .= "<option value='$k'>$v</option>";
		$maintext .= "<form action='index.php' method='get'>
			<input type='hidden' name='action' value='$action'><input type='hidden' name='act' value='configure'>
			<table>
			<tr><th>{%Audio file}</th><td><select name='audio'>$opts</select></td></tr>
			<tr><th>{%Language}</th><td><input name='lang' value='".fa_h($lang)."' size='10' placeholder='fr / fra / French'>
				<span style='font-size: smaller;'>{%empty: detect automatically}</span></td></tr>
			<tr><th>{%Mode}</th><td><select name='mode'>$modeopts</select></td></tr>
			<tr><th>{%Licences}</th><td><label><input type='checkbox' name='restricted' value='1'>
				{%also offer models with restricted licences (e.g. non-commercial use only)}</label></td></tr>
			</table>
			<p><input type='submit' value='{%Choose models}'></p></form>";
	};
	$maintext .= "<form action='index.php?action=upload&act=save' method='post' enctype='multipart/form-data'>
		<input type='hidden' name='type' value='audio'><input type='hidden' name='submit' value='Save'>
		<input type='hidden' name='goon' value='index.php?action=$action'>
		{%Upload an audio file}: <input type='file' name='upfile' accept='audio/*,video/*'> <input type='submit' value='{%Upload}'>
		</form>";

	$jobs = fa_jobs();
	if ( $jobs ) {
		$maintext .= "<h2>{%Recent tasks}</h2><table><tr><th>{%Started}</th><th>{%Audio file}</th><th>{%Language}</th>
			<th>{%Mode}</th><th>{%User}</th><th>{%Status}</th><th>{%Result}</th></tr>";
		foreach ( $jobs as $job ) {
			$res = '';
			if ( $job['status'] == 'done' && file_exists($job['output']) )
				$res = "<a href='index.php?action=wavesurfer&cid=".urlencode($job['fid'])."'>".fa_h($job['fid'])."</a>";
			$maintext .= "<tr><td><a href='index.php?action=$action&act=job&job=".urlencode($job['id'])."'>"
				.fa_h(str_replace('T', ' ', substr($job['started'], 0, 16)))."</a></td>
				<td>".fa_h(basename($job['audio']))."</td><td>".fa_h($job['lang'] ?: 'auto')."</td>
				<td>".fa_h($job['mode'])."</td><td>".fa_h($job['user'])."</td>
				<td>".fa_h($job['status'])."</td><td>$res</td></tr>";
		};
		$maintext .= "</table>";
	};
};
