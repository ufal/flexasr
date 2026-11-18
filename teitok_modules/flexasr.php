<?php
// flexasr TEITOK module: run the flexasr speech recognition pipeline on audio in this corpus.
//   index.php?action=flexasr                 recent tasks, start a new one
//   index.php?action=flexasr&act=configure   models and settings for one audio file
//   index.php?action=flexasr&act=run         start (POST)
//   index.php?action=flexasr&act=job&job=ID  progress, log and result
//   index.php?action=flexasr&api=status&job=ID   JSON for the progress page
//   index.php?action=flexasr&api=audio&status=todo|running|done|all&q=TEXT&offset=N&limit=N   one page of audio files
//   index.php?action=flexasr&api=media&step=start|next   the scan of xmlfiles/ for the media they use (steps)
// Settings (settings.xml): <flexasr bin="/path/to/venv/bin/flexasr" home="/path/to/flexasr-home"
//   models_dir="/big/disk/models" hf_home="..." admin="1" language="fra" restricted="1"/>
//   (any staff login may use the module (not SSO logins); admin="1": only administrators; a task can be stopped by
//   the person who started it or an administrator;
//   language: default language; restricted="1": offer restricted-licence
//   models by default, e.g. for an academic corpus, with the licence conditions shown before a job starts)

check_login(getset('flexasr/admin') ? 'admin' : 'user');       // any staff login, or only administrators with <flexasr admin="1"/>
require_once(__DIR__.'/flexasr_lib.php');

$fa_modes = array('verbatim' => '{%verbatim} ({%keeps fillers, repetitions, false starts})',
	'clean' => '{%clean} ({%readable text, disfluencies dropped})');

if ( $_GET['api'] == 'status' ) {
	header('Content-Type: application/json');
	$job = fa_job($_GET['job']);
	if ( !$job ) { http_response_code(404); print json_encode(array('error' => 'no such job')); exit; };
	print json_encode(array('status' => $job['status'], 'log' => fa_log_tail($job['id'], 20000, !empty($_GET['full']))));
	exit;

} else if ( $_GET['api'] == 'audio' ) {
	header('Content-Type: application/json');
	$status = in_array($_GET['status'], array('todo', 'running', 'done', 'all')) ? $_GET['status'] : 'todo';
	$page = fa_audio_page($status, $_GET['q'], $_GET['offset'], $_GET['limit'] ?: 100);
	print json_encode($page, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
	exit;

} else if ( $_GET['api'] == 'media' ) {
	header('Content-Type: application/json');
	print json_encode(fa_media_scan($_GET['step'] == 'start' ? 'start' : 'next'));
	exit;

} else if ( $act == 'stop' ) {
	$audio = fa_audio_path($_POST['audio'] ?? '');
	if ( !$audio || $_SERVER['REQUEST_METHOD'] != 'POST' ) fatal('No such audio file');
	$job = fa_lock_info($audio);
	if ( $job && $user['permissions'] != 'admin' && $job['user'] != $username ) fatal('Only the person who started a task, or an administrator, can stop it');
	if ( $job ) fa_stop_job($job);
	fa_lock_release($audio);              // also when there was no process left: a dead task must not keep the file
	header("Location: index.php?action=$action");
	exit;

} else if ( $act == 'configure' ) {
	$audio = fa_audio_path($_GET['audio']);
	if ( !$audio ) fatal('No such audio file in '.fa_h(fa_audio_folder()));
	if ( $active = fa_lock_info($audio) ) {
		$maintext .= "<h1>{%Speech recognition}: ".fa_h(basename($audio))."</h1><p>{%This file is already being processed} ("
			.fa_h($active['status']).", ".fa_h(fa_who($active)).", ".fa_h(str_replace('T', ' ', substr($active['started'], 0, 16))).").</p>
			<p><a href='index.php?action=$action&act=job&job=".urlencode($active['id'])."'>{%Follow the task}</a> &middot;
			<a href='index.php?action=$action'>{%back}</a></p>";
		return;
	};
	$lang = preg_replace('/[^A-Za-z_-]/', '', $_GET['lang'] ?: getset('flexasr/language', getset('defaults/language', '')));
	$mode = $_GET['mode'] == 'clean' ? 'clean' : 'verbatim';
	// restricted models: the project's default (settings.xml <flexasr restricted="1"/>) until the form says otherwise
	$allow = isset($_GET['restricted']) ? ($_GET['restricted'] ? 1 : 0) : (getset('flexasr/restricted') ? 1 : 0);
	$models = fa_models($lang, $mode, $allow);
	$fid = fa_file_id($audio);

	$modeopts = '';
	foreach ( $fa_modes as $k => $v ) $modeopts .= "<option value='$k'".($k == $mode ? ' selected' : '').">$v</option>";
	$maintext .= "<h1>{%Speech recognition}: ".fa_h(basename($audio))."</h1>
		<audio src='".fa_h($audio)."' controls preload='none' style='width: 100%; max-width: 600px;'></audio>
		<form action='index.php' method='get' id='fa-settings'>
		<input type='hidden' name='action' value='$action'><input type='hidden' name='act' value='configure'>
		<input type='hidden' name='audio' value='".fa_h($audio)."'>
		<table>
		<tr><th>{%Language}</th><td><input name='lang' value='".fa_h($lang)."' size='12' placeholder='fr / fra / French'>
			<span style='font-size: smaller;'>{%empty: detect automatically}</span></td></tr>
		<tr><th>{%Mode}</th><td><select name='mode' onchange='this.form.submit()'>$modeopts</select></td></tr>
		<tr><th>{%Licences}</th><td><label><input type='hidden' name='restricted' value='0'><input type='checkbox' name='restricted' value='1'".($allow ? ' checked' : '')." onchange='this.form.submit()'>
			{%also offer models with restricted licences (e.g. non-commercial use only)}</label></td></tr>
		</table>
		<p><input type='submit' value='{%Update the models}'></p></form><hr>";
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
		<tr><th>{%Language}</th><td>".fa_h($models['language_name'] ?: '{%detect automatically}')."</td></tr>";
	$notices = array();
	foreach ( array('diarize' => '{%Speakers}', 'transcribe' => '{%Transcription}', 'align' => '{%Word times}') as $task => $label ) {
		$choice = $models['choice'][$task];
		$opts = "<option value=''>{%automatic}: ".fa_h($choice['id'] ?: '{%none usable}')."</option>";
		$unusable = array();
		foreach ( $models['entries'] as $e ) {
			if ( $e['task'] == $task && !$e['usable'] ) $unusable[] = fa_h($e['id']).': '.fa_h(implode('; ', $e['why_not']));
			if ( $e['task'] != $task || !$e['usable'] ) continue;
			$flag = $e['restricted'] ? ' ['.implode(', ', $e['restricted']).']' : '';
			if ( $e['warning'] ) $flag .= ' ⚠ '.$e['warning'];
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
		<tr><th>{%Interviewer}</th><td><select name='interviewer'><option value=''>{%none: everybody is tokenized}</option>
			<option value='least'>{%the speaker who speaks least}</option><option value='first'>{%the first speaker}</option>
			<option value='second'>{%the second speaker}</option><option value='most'>{%the speaker who speaks most}</option></select>
			<span style='font-size: smaller;'>{%transcribed as text, without tokens}</span></td></tr>
		<tr><th>{%Roles without tokens}</th><td><input name='untokenized' size='20' placeholder='interviewer'></td></tr>
		<tr><th>{%Utterances}</th><td>{%split at pauses longer than} <input name='split_gap' value='2' size='4'> {%seconds}
			<span style='font-size: smaller;'>({%smaller: more, shorter utterances})</span></td></tr>
		<tr><th>{%Speaker changes}</th><td><label><input type='hidden' name='snap' value='0'><input type='checkbox' name='snap' value='1' checked>
			{%move them to the nearest pause or sentence end (corrects words at the edge of a turn)}</label></td></tr>
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
	if ( $active = fa_lock_info($audio) ?: fa_output_job($output) ) {
		$maintext .= "<h1>{%Speech recognition}</h1><p class='wrong'>{%This file is already being processed} ("
			.fa_h($active['status']).", ".fa_h(fa_who($active)).").</p>
			<p><a href='index.php?action=$action&act=job&job=".urlencode($active['id'])."'>{%Follow the task}</a></p>";
		return;
	};
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
		'user' => $username, 'name' => trim($user['fullname'] ?: ($user['short'] ?: $username)), 'started' => date('c'),
		'audio' => $audio, 'output' => $output, 'fid' => $fid,
		'lang' => preg_replace('/[^A-Za-z_-]/', '', $_POST['lang']),
		'mode' => $_POST['mode'] == 'clean' ? 'clean' : 'verbatim',
		'allow_restricted' => $_POST['restricted'] ? true : false,
		'speakers' => $speakers,
		'untokenized' => preg_replace('/[^A-Za-z0-9_,-]/', '', $_POST['untokenized']),
		'interviewer' => in_array($_POST['interviewer'], array('first', 'second', 'least', 'most')) ? $_POST['interviewer'] : '',
		'split_gap' => is_numeric($_POST['split_gap']) ? max(0.2, min(120, (float)$_POST['split_gap'])) : 2.0,
		'snap' => ($_POST['snap'] ?? '1') ? true : false,
		'models' => $models,
	);
	if ( !fa_start($job) ) {
		$maintext .= "<h1>{%Speech recognition}</h1><p class='wrong'>{%This file is already being processed}.</p>
			<p><a href='index.php?action=$action'>{%back}</a></p>";
		return;
	};
	header("Location: index.php?action=$action&act=job&job=".$job['id']);
	print "<script>top.location='index.php?action=$action&act=job&job=".$job['id']."';</script>";
	exit;

} else if ( $act == 'job' ) {
	$job = fa_job($_GET['job']);
	if ( !$job ) fatal('No such task');
	$id = $job['id'];
	$maintext .= "<h1>{%Speech recognition}: ".fa_h(basename($job['audio']))."</h1>
		<p>{%Started} ".fa_h($job['started'])." {%by} ".fa_h(fa_who($job))
		." &middot; ".fa_h($job['lang'] ?: 'auto')." &middot; ".fa_h($job['mode'])
		.($job['allow_restricted'] ? " &middot; {%restricted models allowed}" : '')."</p>
		<p>{%Status}: <b id='fa-status'>".fa_h($job['status'])."</b></p>";
	if ( $job['status'] == 'done' && file_exists($job['output']) ) {
		$cid = $job['fid'];
		$info = fa_result_info($job['output']);
		$maintext .= "<h2>{%Result}</h2>
			<p>".fa_h($job['output']).": {$info['utts']} {%utterances}, {$info['toks']} {%tokens}</p>
			<p><a href='index.php?action=spoken-edit&cid=".urlencode($cid)."'><b>{%Edit the transcript}</b></a>
			&middot; <a href='index.php?action=wavesurfer&cid=".urlencode($cid)."'>{%Waveform view}</a>
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
		.fa_h(fa_log_tail($id, 20000, !empty($_GET['full'])))."</pre>
		<p><a href='index.php?action=$action'>{%All tasks}</a>
		&middot; <a href='index.php?action=$action&act=job&job=".urlencode($id).(empty($_GET['full']) ? "&full=1'>{%Full log}" : "'>{%Short log}")."</a></p>";
	if ( $job['status'] == 'queued' || $job['status'] == 'running' ) {
		$maintext .= "<script>
		(function () {
			var url = 'index.php?action=$action&api=status&job=".urlencode($id).(empty($_GET['full']) ? '' : '&full=1')."';
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
		$audiourl = "index.php?action=$action&api=audio";
		$mediaurl = "index.php?action=$action&api=media";
		$maintext .= "<div id='fa-audio-bar'><input id='fa-search' placeholder='{%search}' size='20'>
			<span id='fa-scan' style='font-size: smaller; color: #777;'></span></div>
			<div id='fa-audio-sections'></div>
			<script>
			(function () {
				var PAGE = 100, checking = true, folder = '', timer = null;
				var SEC = {todo: {items: [], n: 0}, running: {items: [], n: 0}, done: {items: [], n: 0}};
				var box = document.getElementById('fa-audio-sections'), S = document.getElementById('fa-search');
				var TITLES = {todo: '{%No TEITOK file yet}', running: '{%In progress}', done: '{%Already in a TEITOK file}'};
				function json(u, opt) { return fetch(u, opt).then(function (r) { return r.json(); }); }
				function cell(tr, text) { var td = document.createElement('td'); td.textContent = text; tr.appendChild(td); return td; }
				function name(a) { return a.p.substring(folder.length + 1); }
				function stopform(a) {
					var f = document.createElement('form'); f.method = 'post'; f.action = 'index.php?action=$action&act=stop';
					f.style.display = 'inline'; f.onsubmit = function () { return confirm('{%Stop this task and release the file?}'); };
					var h = document.createElement('input'); h.type = 'hidden'; h.name = 'audio'; h.value = a.p; f.appendChild(h);
					var b = document.createElement('input'); b.type = 'submit'; b.value = '{%Stop}'; f.appendChild(b);
					return f;
				}
				function note(g, a) {
					var td = document.createElement('td'); td.style.fontSize = 'smaller';
					if ( g == 'running' ) { td.textContent = a.j + ' '; td.appendChild(stopform(a)); }
					else if ( g == 'done' ) {
						a.x.forEach(function (id, i) {
							if ( i ) td.appendChild(document.createTextNode(', '));
							var l = document.createElement('a'); l.textContent = id;
							l.href = 'index.php?action=wavesurfer&cid=' + encodeURIComponent(id); td.appendChild(l);
							var e = document.createElement('a'); e.textContent = '{%edit}'; e.style.marginLeft = '4px';
							e.href = 'index.php?action=spoken-edit&cid=' + encodeURIComponent(id); td.appendChild(document.createTextNode(' (')); td.appendChild(e); td.appendChild(document.createTextNode(')'));
						});
						if ( a.xn > a.x.length ) td.appendChild(document.createTextNode(', …'));
					} else if ( a.j == 'failed' ) td.textContent = '{%last run failed}';
					else if ( a.j == 'cancelled' ) td.textContent = '{%last run was stopped}';
					else if ( a.j == 'stalled' ) td.textContent = '{%last run did not finish}';
					return td;
				}
				function draw() {
					box.innerHTML = '';
					['todo', 'running', 'done'].forEach(function (g) {
						var sec = SEC[g];
						if ( !sec.n && g != 'todo' ) return;
						var h = document.createElement('h3');
						h.textContent = (g == 'todo' && checking ? '{%Audio files}' : TITLES[g]) + ' (' + sec.n + ')'; box.appendChild(h);
						var T = document.createElement('table'); box.appendChild(T);
						sec.items.forEach(function (a) {
							var tr = document.createElement('tr');
							cell(tr, name(a)); tr.appendChild(note(g, a));
							var td = document.createElement('td');
							if ( g != 'running' ) {
								var b = document.createElement('a'); b.className = 'fa-go';
								b.textContent = g == 'done' ? '{%Transcribe again}' : '{%Transcribe}';
								b.href = 'index.php?action=$action&act=configure&audio=' + encodeURIComponent(a.p);
								b.style.cssText = 'border: 1px solid #888; border-radius: 4px; padding: 1px 8px; text-decoration: none; white-space: nowrap;';
								td.appendChild(b);
							}
							tr.appendChild(td); T.appendChild(tr);
						});
						if ( sec.n > sec.items.length ) {
							var p = document.createElement('p'), l = document.createElement('a');
							l.href = '#'; l.textContent = '{%show more}' + ' (' + (sec.n - sec.items.length) + ')';
							l.onclick = function (e) { e.preventDefault(); more(g); };
							p.appendChild(l); box.appendChild(p);
						}
					});
				}
				function url(g, offset) {
					return '$audiourl&status=' + g + '&limit=' + PAGE + '&offset=' + offset + '&q=' + encodeURIComponent(S.value);
				}
				function load(g) {
					return json(url(g, 0)).then(function (d) {
						folder = d.folder; checking = d.checking;
						SEC[g].items = d.items; SEC.todo.n = d.counts.todo; SEC.running.n = d.counts.running; SEC.done.n = d.counts.done;
					});
				}
				function more(g) {
					json(url(g, SEC[g].items.length)).then(function (d) { SEC[g].items = SEC[g].items.concat(d.items); draw(); });
				}
				function loadAll() {
					var gs = checking ? ['todo'] : ['todo', 'running', 'done'];
					Promise.all(gs.map(load)).then(function () {
						SEC.running.items = checking ? [] : SEC.running.items; draw();
					});
				}
				S.oninput = function () { clearTimeout(timer); timer = setTimeout(loadAll, 300); };
				function scan() {
					var out = document.getElementById('fa-scan');
					json('$mediaurl&step=start').then(function loop(d) {
						out.textContent = '{%checking TEITOK files}: ' + d.pos + ' / ' + d.total;
						if ( d.done ) { out.textContent = ''; checking = false; return loadAll(); }
						return json('$mediaurl&step=next').then(loop);
					}).catch(function () { out.textContent = '{%could not check the TEITOK files}'; });
				}
				loadAll(); scan();
			})();
			</script>";
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
				$res = "<a href='index.php?action=wavesurfer&cid=".urlencode($job['fid'])."'>".fa_h($job['fid'])."</a> (<a href='index.php?action=spoken-edit&cid=".urlencode($job['fid'])."'>{%edit}</a>)";
			$maintext .= "<tr><td><a href='index.php?action=$action&act=job&job=".urlencode($job['id'])."'>"
				.fa_h(str_replace('T', ' ', substr($job['started'], 0, 16)))."</a></td>
				<td>".fa_h(basename($job['audio']))."</td><td>".fa_h($job['lang'] ?: 'auto')."</td>
				<td>".fa_h($job['mode'])."</td><td>".fa_h(fa_who($job))."</td>
				<td>".fa_h($job['status'])."</td><td>$res</td></tr>";
		};
		$maintext .= "</table>";
	};
};
