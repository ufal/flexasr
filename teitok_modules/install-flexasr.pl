#!/usr/bin/env perl
# Install flexasr's TEITOK pages (teitok_modules/) into a TEITOK *shared* project.
# (Deliberately a copy of flexicorp's install-teitok-ui.pl: each repo installs its own pages.)
#
# TEITOK looks for an action's page in the project's Sources/, then in
# $sharedfolder/Sources/, then in $ttroot/common/Sources/ (and similarly for
# Pages/), so files placed in the shared project work as TEITOK pages without
# touching the TEITOK git checkout:
#
#   *.php  (not *-test.php)   -> SHARED/Sources/
#   *.js, *.css               -> SHARED/Scripts/   (flexasr.php reads them from there)
#   *.html                    -> SHARED/Pages/     (help pages)
#
# Re-running upgrades in place. A manifest (SHARED/Resources/flexasr-teitok.json)
# records what was installed, with checksums and the flexasr version and commit;
# a file that was changed locally since the last install (or that was there before
# the first one) is kept as FILE.local-YYYYmmdd-HHMMSS before it is replaced.
#
# Usage:
#   sudo perl install-flexasr.pl [--modules DIR | --shared DIR] [--user USER] [--dry-run]
#
#   --shared DIR   the TEITOK shared project (default: TT_SHARED from the TEITOK
#                  .htaccess, else /var/www/html/teitok/shared)
#   --modules DIR  the TEITOK modules layer (TT_MODULES: install-level, outside the web root, for every
#                  TEITOK on the server). Without --modules/--shared, TT_MODULES (environment, or the TEITOK
#                  .htaccess) is used when it is set, and the shared project otherwise.
#   --remove-old   with the modules layer: remove, without asking, the files an earlier run of this installer put in the
#                  shared project (unchanged since). Otherwise the installer asks on a terminal.
#   --keep-old     leave them, and do not ask. Copies it did not install (group, project, changed) are only reported.
#   --user USER    owner of the installed files (default: owner of DIR)
#   --dry-run      show what would change, change nothing
use strict;
use warnings;
use File::Basename qw(dirname basename);
use File::Copy qw(copy);
use File::Path qw(make_path);
use Cwd qw(abs_path);
use Digest::SHA;
use POSIX qw(strftime);

my ( $shared, $user, $dry, $modules ) = ( '', '', 0, '' );
my $layer = 'shared project';
my $remove_old = 'ask';    # ask | yes (--remove-old) | keep (--keep-old)
while ( @ARGV ) {
	my $a = shift @ARGV;
	if    ( $a eq '--modules' ) { $modules = shift @ARGV // ''; }
	elsif ( $a eq '--remove-old' ) { $remove_old = 'yes'; }
	elsif ( $a eq '--keep-old' )   { $remove_old = 'keep'; }
	elsif ( $a eq '--shared' )  { $shared = shift @ARGV // ''; }
	elsif ( $a eq '--user' )    { $user = shift @ARGV // ''; }
	elsif ( $a eq '--dry-run' ) { $dry = 1; }
	elsif ( $a eq '-h' || $a eq '--help' ) {
		open my $me, '<', $0 or die; while ( <$me> ) { last if !/^#/; next if /^#!/; s/^# ?//; print; } exit 0;
	} else { die "install-flexasr.pl: unknown option $a (see --help)\n"; }
}

my $src = dirname( abs_path($0) );
my $repo = dirname($src);

# ── where to install: the modules layer (TT_MODULES) when there is one, else the shared project ──
# The modules layer is install-level (outside the web root, for every TEITOK on the server); the shared project is
# the user's. An explicit --modules or --shared wins; otherwise TT_MODULES (environment, or SetEnv in the TEITOK
# .htaccess) is used when it is set, and the shared project (TT_SHARED, or the default) when not.
my @htaccess = ( '/var/www/html/teitok/.htaccess', '/srv/www/htdocs/teitok/.htaccess',
	             '/Library/WebServer/Documents/teitok/.htaccess', '/var/www/localhost/htdocs/teitok/.htaccess' );
sub tt_env {    # TT_xxx from the environment, else from SetEnv in the TEITOK .htaccess: ( value, where ) or ()
	my $var = shift;
	return ( $ENV{$var}, "\$$var" ) if defined $ENV{$var} && $ENV{$var} ne '';
	for my $ht ( @htaccess ) {
		next unless -r $ht;
		open my $fh, '<', $ht or next;
		while ( <$fh> ) { if ( /^\s*SetEnv\s+\Q$var\E\s+(\S+)/ ) { close $fh; return ( $1, "$var in $ht" ); } }
		close $fh;
	}
	return ();
}
my $found_by = '--shared';
my $explicit_shared = $shared;    # with --modules, the shared project is only looked in for older copies
if ( $modules ne '' ) {
	$shared = $modules; $layer = 'modules layer'; $found_by = '--modules';
} elsif ( $shared eq '' ) {
	my ( $m, $why ) = tt_env('TT_MODULES');
	if ( defined $m ) {
		$shared = $m; $layer = 'modules layer'; $found_by = $why;
	} else {
		my ( $s, $swhy ) = tt_env('TT_SHARED');
		if ( defined $s ) { $shared = $s; $found_by = $swhy; }
		else { $shared = '/var/www/html/teitok/shared'; $found_by = 'the default (no TT_SHARED or TT_MODULES found; pass --shared DIR or --modules DIR)'; }
	}
}
$shared =~ s{/+$}{};
if ( $layer eq 'modules layer' ) {
	unless ( -d $shared ) {
		die "install-flexasr.pl: $shared is not a directory (create it, or pass another --modules DIR)\n" if $dry || !make_path($shared);
	}
	make_path("$shared/Resources") unless $dry || -d "$shared/Resources";
} else {
	die "install-flexasr.pl: $shared is not a directory (pass --shared DIR)\n" unless -d $shared;
	die "install-flexasr.pl: $shared does not look like a TEITOK project (no Resources/)\n" unless -d "$shared/Resources";
}

my ( $uid, $gid ) = ( -1, -1 );
if ( $user ne '' ) {
	my @pw = getpwnam($user) or die "install-flexasr.pl: no such user $user\n";
	( $uid, $gid ) = @pw[ 2, 3 ];
} else {
	( $uid, $gid ) = ( stat $shared )[ 4, 5 ];
	$user = getpwuid($uid) // $uid;
}

# ── what to install ─────────────────────────────────────────────────────────
opendir my $dh, $src or die "cannot read $src: $!\n";
my @plan;    # [ source file, relative target ]
for my $f ( sort readdir $dh ) {
	next if $f =~ /^\./ || !-f "$src/$f";
	if    ( $f =~ /-test\.php$/ )    { next; }
	elsif ( $f =~ /\.php$/ )         { push @plan, [ $f, "Sources/$f" ]; }
	elsif ( $f =~ /\.(js|css)$/ )    { push @plan, [ $f, "Scripts/$f" ]; }
	elsif ( $f =~ /\.html$/ )        { push @plan, [ $f, "Pages/$f" ]; }
}
closedir $dh;
die "install-flexasr.pl: nothing to install in $src\n" unless @plan;

sub sha { my $p = shift; return '' unless -f $p; return Digest::SHA->new(256)->addfile($p, 'b')->hexdigest; }
sub read_manifest_files {    # "files" of an installer manifest: relative path => sha256 (empty when there is none)
	my $path = shift; my %h;
	open my $fh, '<', $path or return %h;
	while ( <$fh> ) { $h{$1} = $2 if /^\s*"([^"]+)"\s*:\s*"([0-9a-f]{64})"/; }
	close $fh;
	return %h;
}

# version + commit of the flexasr checkout these files come from
my $version = '';
if ( open my $pp, '<', "$repo/flexasr/__init__.py" ) {
	while ( <$pp> ) { if ( /^__version__\s*=\s*["']([^"']+)["']/ ) { $version = $1; last; } }
	close $pp;
}
if ( $version eq '' && open my $tp, '<', "$repo/pyproject.toml" ) {
	while ( <$tp> ) { if ( /^version\s*=\s*["']([^"']+)["']/ ) { $version = $1; last; } }
	close $tp;
}
my $commit = '';
if ( -d "$repo/.git" ) {
	$commit = `git -C '$repo' rev-parse --short HEAD 2>/dev/null` // ''; chomp $commit;
	my $dirty = `git -C '$repo' status --porcelain -- '$src' 2>/dev/null` // '';
	$commit .= '-dirty' if $commit ne '' && $dirty ne '';
}

# previous manifest: { "rel": "sha", ... } (tiny JSON, read without a JSON module)
my $manifest = "$shared/Resources/flexasr-teitok.json";
my %old;
if ( open my $mf, '<', $manifest ) {
	local $/; my $j = <$mf>; close $mf;
	if ( $j =~ /"files"\s*:\s*\{(.*?)\}/s ) {
		my $body = $1;
		while ( $body =~ /"([^"]+)"\s*:\s*"([0-9a-f]{64})"/g ) { $old{$1} = $2; }
	}
}

# ── install ─────────────────────────────────────────────────────────────────
my $stamp = strftime( '%Y%m%d-%H%M%S', localtime );
my ( %new, @changed, @kept_local, $unchanged );
$unchanged = 0;
for my $p ( @plan ) {
	my ( $f, $rel ) = @$p;
	my $from = "$src/$f";
	my $to   = "$shared/$rel";
	my $want = sha($from);
	$new{$rel} = $want;
	my $have = sha($to);
	if ( $have eq $want ) { $unchanged++; next; }
	# changed locally since our last install, or present before the first one: keep a copy
	if ( $have ne '' && ( !exists $old{$rel} || $old{$rel} ne $have ) ) {
		push @kept_local, "$rel -> $rel.local-$stamp";
		copy( $to, "$to.local-$stamp" ) or die "cannot back up $to: $!\n" unless $dry;
	}
	push @changed, ( $have eq '' ? "new      $rel" : "updated  $rel" );
	next if $dry;
	my $dir = dirname($to);
	unless ( -d $dir ) { make_path($dir) or die "cannot create $dir: $!\n"; chown $uid, $gid, $dir; }
	my $tmp = "$to.part-$$";
	copy( $from, $tmp ) or die "cannot write $tmp: $!\n";
	chmod 0644, $tmp;
	chown $uid, $gid, $tmp;
	rename( $tmp, $to ) or die "cannot replace $to: $!\n";
}
my @gone = grep { !exists $new{$_} && -e "$shared/$_" } sort keys %old;

unless ( $dry ) {
	my $tmp = "$manifest.part-$$";
	open my $out, '>', $tmp or die "cannot write $tmp: $!\n";
	print $out "{\n  \"component\": \"flexasr-teitok\",\n  \"version\": \"$version\",\n",
	           "  \"commit\": \"$commit\",\n  \"source\": \"$src\",\n",
	           "  \"installed\": \"", strftime( '%Y-%m-%dT%H:%M:%S%z', localtime ), "\",\n  \"files\": {\n",
	           join( ",\n", map { "    \"$_\": \"$new{$_}\"" } sort keys %new ), "\n  }\n}\n";
	close $out;
	chmod 0644, $tmp; chown $uid, $gid, $tmp;
	rename( $tmp, $manifest ) or die "cannot replace $manifest: $!\n";
}

# ── copies elsewhere that win over the shared ones ──────────────────────────
# A project's own Sources/ or Scripts/ copy is used before the shared one.
my @shadow;
# the projects live next to the shared project (also when the pages go to the modules layer: then the shared
# project is only looked at for what is in it, and is not itself a project)
my ($tr_shared) = grep { defined $_ && $_ ne '' && -d $_ } ( $explicit_shared, ( tt_env('TT_SHARED') )[0] );
my $teitokroot = $layer eq 'modules layer' ? ( defined $tr_shared ? dirname($tr_shared) : '' ) : dirname($shared);
if ( $teitokroot ne '' && opendir my $td, $teitokroot ) {
	for my $proj ( sort readdir $td ) {
		next if $proj =~ /^\./;
		my $pd = "$teitokroot/$proj";
		next if !-d $pd || abs_path($pd) eq abs_path($shared) || ( defined $tr_shared && abs_path($pd) eq abs_path($tr_shared) );
		for my $p ( @plan ) {
			push @shadow, "$pd/$p->[1]" if -f "$pd/$p->[1]";
		}
	}
	closedir $td;
}
# Installing into the modules layer: what an earlier run of this installer left in the shared project is now
# a second copy (and a closer layer, so it would win). Those files (listed in this installer's manifest there,
# unchanged since) can be removed; anything else in the shared project or the group was not put there by this
# installer, so it is only reported.
my ( @old_ours, @old_changed, %old_manifest );
if ( $layer eq 'modules layer' ) {
	my %seen = ( abs_path($shared) => 1 );
	my $mbase = basename($manifest);
	for my $d ( $explicit_shared, ( tt_env('TT_SHARED') )[0] ) {
		next unless defined $d && $d ne '' && -d $d;
		$d =~ s{/+$}{};
		next if $seen{ abs_path($d) }++;
		my %om = read_manifest_files("$d/Resources/$mbase");
		$old_manifest{$d} = [ "$d/Resources/$mbase", scalar keys %om ] if %om;
		for my $p ( @plan ) {
			my $f = "$d/$p->[1]";
			next unless -f $f;
			if    ( exists $om{ $p->[1] } && sha($f) eq $om{ $p->[1] } ) { push @old_ours, [ $f, $d ]; }
			elsif ( exists $om{ $p->[1] } )                               { push @old_changed, $f; }
			else                                                         { push @shadow, $f; }
		}
	}
	for my $d ( ( tt_env('TT_GROUP') )[0] ) {
		next unless defined $d && $d ne '' && -d $d;
		$d =~ s{/+$}{};
		next if $seen{ abs_path($d) }++;
		for my $p ( @plan ) { push @shadow, "$d/$p->[1]" if -f "$d/$p->[1]"; }
	}
	push @shadow, @old_changed;
}

if ( @old_ours && $remove_old ne 'keep' ) {
	print "\n  An earlier run of this installer put these files in the shared project; the modules layer has them now:\n",
		map { "    $_->[0]\n" } @old_ours;
	my $do = $remove_old eq 'yes';
	if ( !$do && !$dry && -t STDIN ) { print "  Remove them from the shared project? [y/N] "; my $ans = <STDIN> // ''; $do = $ans =~ /^\s*y/i; }
	elsif ( !$do ) { print "  (not removed: ", ( $dry ? 'dry run' : 'no terminal' ), "; --remove-old removes them, --keep-old leaves them and stops this question)\n"; }
	if ( $do && !$dry ) {
		my %gone;
		for my $o ( @old_ours ) {
			if ( unlink $o->[0] ) { print "    removed $o->[0]\n"; $gone{ $o->[1] }++; } else { print "    cannot remove $o->[0]: $!\n"; }
		}
		for my $d ( keys %gone ) {    # a manifest with nothing left to describe goes too
			my ( $mf, $n ) = @{ $old_manifest{$d} };
			unlink $mf if $gone{$d} >= $n;
		}
	}
}

# ── report ──────────────────────────────────────────────────────────────────
my $what = $dry ? 'would install' : 'installed';
printf "flexasr TEITOK pages %s %s%s into %s (owner %s)\n", ( $version || '?' ),
	( $commit ne '' ? "($commit) " : '' ), $what, $shared, $user;
print "  $_\n" for @changed;
printf "  %d file(s) already up to date\n", $unchanged if $unchanged;
print "  local changes kept as:\n", map { "    $_\n" } @kept_local if @kept_local;
print "  no longer shipped (left in place): ", join( ', ', @gone ), "\n" if @gone;
if ( @shadow ) {
	print "  warning: these copies, in a layer closer to the project, are used instead of the installed ones:\n";
	print "    $_\n" for @shadow;
}
exit 0;
