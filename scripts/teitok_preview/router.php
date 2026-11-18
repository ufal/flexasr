<?php
// Preview of the flexasr TEITOK module without TEITOK: a stand-in for the few things the module needs
// (settings, login, fatal). No login: everyone is an admin. Started by scripts/teitok_preview.py.
error_reporting(E_ALL & ~E_WARNING & ~E_NOTICE & ~E_DEPRECATED);
$settings = array('flexasr' => array_filter(array(
	'bin' => getenv('FA_BIN'), 'models_dir' => getenv('FA_MODELS_DIR'),
	'language' => getenv('FA_LANGUAGE'), 'restricted' => getenv('FA_RESTRICTED'))));
function getset($path, $default = '') {
	global $settings; $v = $settings;
	foreach ( explode('/', $path) as $k ) { if ( !is_array($v) || !isset($v[$k]) ) return $default; $v = $v[$k]; }
	return ($v === '' || $v === null) ? $default : $v;
}
function check_login($t = 'user') { }
function fatal($m) { print "<p style='color: #b00;'>$m</p>"; exit(1); }
$action = $_GET['action'] ?? 'flexasr'; $act = $_GET['act'] ?? '';
$username = 'preview@example.org'; $user = array('permissions' => 'admin', 'fullname' => 'Preview User'); $maintext = '';
chdir(getenv('FA_PREVIEW_PROJ'));
include(__DIR__.'/../../teitok/flexasr.php');
$maintext = preg_replace('/\{%([^}]*)\}/', '$1', $maintext);      // TEITOK translates {%text}; here: the English text
print "<!doctype html><meta charset=utf-8><title>flexasr preview</title>
<body style='font-family: sans-serif; margin: 1.5em;'><p style='color: #777; font-size: smaller;'>
preview without TEITOK (no login) &middot; project: ".htmlspecialchars(getenv('FA_PREVIEW_PROJ'))."</p>".$maintext;
