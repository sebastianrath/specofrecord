#!/usr/bin/env python3
"""Builds the Claude Code plugin as a zip and proves the zip works away from this repository.

    python3 plugins/build-plugin.py [--out DIR] [--expect-version X.Y.Z] [--skip-smoke]

1. `sh plugins/sync-tools.sh --check`: the plugin's copy of tools/ (the `sor` command) and of the cheat sheet, and the
   VS Code extension's copy of tools/, must be current. The zip is the folder plugins/specofrecord as it is committed,
   so a stale copy stops the build here.
2. Zips plugins/specofrecord into DIR/specofrecord-plugin-<version>.zip (default DIR: dist/) with a top-level folder
   `specofrecord/`, a fixed timestamp and the executable bit kept on bin/sor, plus a .sha256 file next to it.
3. Smoke test: unpacks the zip into a folder with a space in its name and runs it from unrelated folders with the
   `python3` on the PATH (3.9 or newer): the launcher, the launcher through a symlink, the commands that start a
   project, and the exact hook commands from hooks.json.

Python 3.9, standard library only. Run from any folder.
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PLUGIN = os.path.join(HERE, 'specofrecord')
TOP = 'specofrecord'
SKIP_DIRS = {'__pycache__', '.git'}
SKIP_FILES = {'.DS_Store'}
REQUIRED = [
    '.claude-plugin/plugin.json', 'hooks/hooks.json', 'skills/workflow/SKILL.md',
    'tools/sor.py', 'tools/sorlib/cli.py', 'bin/sor',
]
STAMP = (1980, 1, 1, 0, 0, 0)


def fail(message):
    print('build-plugin: ' + message, file=sys.stderr)
    sys.exit(1)


def read_version():
    with open(os.path.join(PLUGIN, '.claude-plugin', 'plugin.json'), encoding='utf-8') as f:
        return json.load(f)['version']


def check_in_sync():
    result = subprocess.run(['sh', os.path.join(HERE, 'sync-tools.sh'), '--check'])
    if result.returncode != 0:
        fail('a bundled copy of tools/ is out of date: run `sh plugins/sync-tools.sh` and commit the result')


def plugin_files():
    found = []
    for folder, dirs, files in os.walk(PLUGIN):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name in SKIP_FILES or name.endswith('.pyc'):
                continue
            full = os.path.join(folder, name)
            found.append((os.path.relpath(full, PLUGIN).replace(os.sep, '/'), full))
    return sorted(found)


def build_zip(out_dir, version):
    files = plugin_files()
    names = {rel for rel, _ in files}
    missing = [r for r in REQUIRED if r not in names]
    if missing:
        fail('missing from the plugin: ' + ', '.join(missing))
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, 'specofrecord-plugin-%s.zip' % version)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel, full in files:
            executable = os.access(full, os.X_OK)
            if rel == 'bin/sor' and not executable:
                fail('plugins/specofrecord/bin/sor is not executable (the plugin puts bin/ on the PATH): '
                     'run `git update-index --chmod=+x plugins/specofrecord/bin/sor`')
            info = zipfile.ZipInfo('%s/%s' % (TOP, rel), STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            with open(full, 'rb') as f:
                z.writestr(info, f.read())
    with open(target, 'rb') as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(target + '.sha256', 'w', encoding='utf-8') as f:
        f.write('%s  %s\n' % (digest, os.path.basename(target)))
    print('built %s (%d files, sha256 %s)' % (target, len(files), digest[:12]))
    return target


def unpack(zip_path, into):
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            dest = os.path.join(into, *info.filename.split('/'))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(z.read(info))
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                os.chmod(dest, mode)


def run(argv, cwd, stdin=None, env=None, shell=False):
    return subprocess.run(argv, cwd=cwd, input=stdin, env=env, shell=shell,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def expect(ok, what, result=None):
    if ok:
        print('  ok  ' + what)
        return
    detail = ''
    if result is not None:
        detail = '\n--- stdout\n%s\n--- stderr\n%s' % (result.stdout.strip(), result.stderr.strip())
    fail('smoke test failed: ' + what + detail)


def smoke(zip_path):
    python = shutil.which('python3')
    if not python:
        fail('python3 is not on the PATH')
    version = run([python, '--version'], os.getcwd())
    print('smoke test with %s (%s)' % ((version.stdout or version.stderr).strip(), python))
    if sys.version_info < (3, 9):
        fail('Python 3.9 or newer is needed')
    work = tempfile.mkdtemp(prefix='sor plugin ')
    try:
        unpack(zip_path, os.path.join(work, 'unpacked here'))
        root = os.path.join(work, 'unpacked here', TOP)
        sor = os.path.join(root, 'bin', 'sor')
        elsewhere = os.path.join(work, 'elsewhere')
        os.makedirs(elsewhere)

        expect(os.access(sor, os.X_OK), 'bin/sor is executable after unpacking')
        result = run([sor, '--help'], elsewhere)
        expect(result.returncode == 0 and 'usage: sor' in result.stdout, 'bin/sor --help from another folder', result)

        links = os.path.join(work, 'links')
        os.makedirs(links)
        try:
            os.symlink(sor, os.path.join(links, 'sor'))
        except (OSError, NotImplementedError):
            print('  --  symlinks are not available here, link check skipped')
        else:
            result = run([os.path.join(links, 'sor'), '--help'], elsewhere)
            expect(result.returncode == 0 and 'usage: sor' in result.stdout, 'bin/sor --help through a symlink', result)

        project = os.path.join(work, 'a project')
        os.makedirs(project)
        for args, text in ((['new', '--root'], 'SPECOFRECORD.md'), (['new', 'alpha'], 'alpha.md')):
            result = run([sor] + args, project)
            expect(result.returncode == 0 and text in result.stdout, 'sor ' + ' '.join(args), result)
        result = run([sor, 'parts'], project)
        expect(result.returncode == 0 and 'alpha' in result.stdout, 'sor parts lists the new part', result)
        result = run([sor, 'status'], project)
        # a fresh skeleton is full of <fill in> placeholders, so status reports problems and exits non-zero by design
        expect('sor-lock.json' in result.stdout and 'Traceback' not in result.stderr, 'sor status reads the new project', result)

        with open(os.path.join(root, 'hooks', 'hooks.json'), encoding='utf-8') as f:
            hooks = json.load(f)['hooks']
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=root, CLAUDE_PROJECT_DIR=project)
        commands = {}
        for event, groups in hooks.items():
            for group in groups:
                for hook in group['hooks']:
                    commands[event] = hook['command']
                    expect('${CLAUDE_PLUGIN_ROOT}' in hook['command'], '%s hook finds the tools through CLAUDE_PLUGIN_ROOT' % event)
        payload = json.dumps({'session_id': 'smoke', 'cwd': project})
        result = run(commands['SessionStart'], project, stdin=payload, env=env, shell=True)
        expect(result.returncode == 0 and 'Spec of Record' in result.stdout, 'session-start hook speaks in a project with sor/', result)
        empty = os.path.join(work, 'no spec here')
        os.makedirs(empty)
        env['CLAUDE_PROJECT_DIR'] = empty
        result = run(commands['SessionStart'], empty, stdin=json.dumps({'session_id': 'smoke', 'cwd': empty}), env=env, shell=True)
        expect(result.returncode == 0 and not result.stdout.strip(), 'session-start hook is silent without sor/', result)
        env['CLAUDE_PROJECT_DIR'] = project
        edit = json.dumps({'session_id': 'smoke', 'cwd': project, 'tool_name': 'Edit',
                           'tool_input': {'file_path': os.path.join(project, 'sor', 'alpha.md'), 'old_string': 'a', 'new_string': 'b'}})
        result = run(commands['PreToolUse'], project, stdin=edit, env=env, shell=True)
        expect(result.returncode == 0, 'pre-edit hook runs on a spec edit', result)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print('smoke test passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', default=os.path.join(REPO, 'dist'), help='folder for the zip (default: dist/ in the repository)')
    parser.add_argument('--expect-version', help='fail unless plugin.json has this version (a release tag says it)')
    parser.add_argument('--skip-smoke', action='store_true', help='build only')
    args = parser.parse_args()

    check_in_sync()
    version = read_version()
    if args.expect_version and args.expect_version != version:
        fail('plugin.json says version %s but %s was asked for' % (version, args.expect_version))
    target = build_zip(os.path.abspath(args.out), version)
    if not args.skip_smoke:
        smoke(target)


if __name__ == '__main__':
    main()
