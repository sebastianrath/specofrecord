"""Running the tests of a target in its own framework (SPEC §9).

A target says how in the Rules of its part: `{run: python3 -m pytest -q}` is the command, `{results: out/results-py.json}` the file the
command writes `{"part/test:name": "pass"}` to, as `sor test --out` does (the tool reads no pytest or jest output), and `{lcov: out/lcov-py.info}`
the coverage it writes, in the lcov format that coverage.py, c8, nyc and istanbul all produce.

`sor test --targets py` runs that command from the project root, with no shell, when the call names the target and never otherwise: the command is
text in a spec file, so what a call runs is written in the call. A results file the run did not write (it is as it was before) is never read. The
command runs in a process group of its own, so that a timeout or Ctrl-C ends the programs it started too.
"""
import json
import os
import posixpath
import signal
import subprocess

from . import lock as lockfile
from . import testrun   # the web runner: which tests a call selects, and which it leaves to CI
from .markers import Scan
from .model import Item, split_command

TIMEOUT = 600   # seconds a target's test run may take


class TargetError(Exception):
    """A target's test run could not be done or read: `sor test` says why and exits with 2."""


def names_of(project, text):
    """([target names], error): the targets a call names with `--targets`, which must say how their tests run."""
    names = [n.strip() for n in text.split(',')] if text.strip() else []
    declared = project.target_commands()
    for n in names:
        if n not in project.target_names():
            return [], f'--targets names {n or "an empty name"}, which is no target (targets: {", ".join(project.target_names()) or "none"})'
        if 'run' not in declared.get(n, {}):
            return [], (f'--targets names {n}, which does not say how its tests run: give the rules of its part a `{{run: …}}` and a '
                        '`{results: …}` (SPEC §9)')
    return sorted(set(names)), None


def hints(project, named):
    """The targets that say how their tests run and were not named: one line to tell what a call would run."""
    return [f'{name} says how its tests run ({kinds["run"]}): `sor test --targets {name}` runs it'
            for name, kinds in sorted(project.target_commands().items()) if 'run' in kinds and name not in named]


def stamp(path):
    """What tells that a file was written by a run: its time and size, or None when it is not there."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def tail(text, lines=12):
    rows = [r for r in text.splitlines() if r.strip()]
    return '\n'.join('    ' + r for r in rows[-lines:])


def stop(proc):
    """Ends a command and every program it started (a test runner starts workers that would go on writing, and on Windows hold the pipes), then
    reaps it. The pipes are closed here and not read: a program that left the group could hold them open for good."""
    try:
        if os.name == 'posix':
            os.killpg(proc.pid, signal.SIGKILL)   # its own group: the command was started in a new session
        else:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
    except OSError:
        pass   # it had ended
    proc.kill()
    proc.wait()
    for pipe in (proc.stdout, proc.stderr):
        if pipe:
            pipe.close()


def run_command(project, name, say=print, timeout=TIMEOUT):
    """Runs the command of a target. Returns (the results file, the coverage file or None, what the command printed, its exit code, a note or
    None); raises TargetError when it could not start, ran out of time, or left the results file as it was. The coverage file is read only if the
    run wrote it: when it is as it was, it is not used and the note says so."""
    kinds = project.target_commands()[name]
    argv = split_command(kinds['run'])
    results = os.path.join(project.root, kinds['results'])
    lcov = os.path.join(project.root, kinds['lcov']) if 'lcov' in kinds else None
    before, before_lcov = stamp(results), lcov and stamp(lcov)
    say(f'running {name}: {kinds["run"]}')
    group = {'start_new_session': True} if os.name == 'posix' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    try:
        proc = subprocess.Popen(argv, cwd=project.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors='replace', **group)   # no shell
    except FileNotFoundError:
        raise TargetError(f'{name}: cannot start {argv[0]}: no such program')
    except PermissionError:
        raise TargetError(f'{name}: cannot start {argv[0]}: not allowed to run it')
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(proc)
        raise TargetError(f'{name}: the run took more than {timeout} s and was stopped')
    except BaseException:   # Ctrl-C too: the group is not the terminal's any more, so the signal would not reach it
        stop(proc)
        raise
    output = (stdout or '') + (stderr or '')
    if stamp(results) in (None, before):
        said = f'{kinds["results"]} is as it was before the run' if before else f'{kinds["results"]} was not written'
        raise TargetError(f'{name}: the command exited with {proc.returncode}, and {said}; a results file the run did not write is never read'
                          + (f'. Its last lines:\n{tail(output)}' if output.strip() else ''))
    note = None
    if lcov and stamp(lcov) in (None, before_lcov):
        note = f'{name}: {kinds["lcov"]} {"is as it was before the run" if before_lcov else "was not written"}: no line coverage'
        lcov = None
    return results, lcov, output, proc.returncode, note


def number(text):
    """Whether text is digits that int() reads: str.isdigit() is also true for '\u00b2' and the digits of other scripts that int() refuses."""
    return text.isascii() and text.isdigit()


def read_lcov(path, root):
    """{project-relative file: {line: hits}} from an lcov file: `SF:` names a file, `DA:line,hits` a line that can run. A file outside the project
    is left out."""
    out, current = {}, None
    with open(path, encoding='utf8', errors='replace') as fh:
        for raw in fh:
            record = raw.strip()
            if record.startswith('SF:'):
                name = record[3:].strip().replace('\\', '/')
                if os.path.isabs(name) or name.startswith('/') or (len(name) > 1 and name[0].isalpha() and name[1] == ':'):   # Python 3.13 on Windows calls `/x` rooted, not absolute
                    try:
                        name = os.path.relpath(name, root).replace(os.sep, '/')
                    except ValueError:   # another drive than the project's
                        name = '..'
                name = posixpath.normpath(name)
                current = out.setdefault(name, {}) if not name.startswith('..') else None
            elif record.startswith('DA:') and current is not None:
                fields = record[3:].split(',')
                if len(fields) >= 2 and number(fields[0]) and number(fields[1].lstrip('-')):
                    current[int(fields[0])] = max(current.get(int(fields[0]), 0), int(fields[1]))
            elif record == 'end_of_record':
                current = None
    return out


def line_coverage(project, scan, name, records):
    """(ran, total, {key: [ran, total]}) for the marked code of one target: the lines of its files that the coverage file has a record for, counted
    as the web run counts them (the lines inside a region, or the line of a line marker)."""
    by_key, ran, total = {}, 0, 0
    for r in scan.regions:
        if project.target_of(r.file) != name or r.file not in records:
            continue
        for n in ([r.start] if r.kind == 'line' else range(r.start + 1, (r.end or r.start))):
            if n not in records[r.file]:
                continue
            total += 1
            ran += records[r.file][n] > 0
            for k in r.keys:
                c = by_key.setdefault(k, [0, 0])
                c[0] += records[r.file][n] > 0
                c[1] += 1
    return ran, total, dict(sorted(by_key.items()))


def clause_coverage(project, name, results):
    """(percent or None, [the Rules and `gives` items that apply to the target and no passing test of its run proves]): SPEC §8 for one target. What
    the part of another target says about itself does not apply to this one."""
    def of_another(item):
        pieces = item.part.id.split('/')
        return pieces[0] == 'targets' and len(pieces) > 1 and pieces[1] != name
    universe = sorted(i.id for i in project.all_items()
                      if (i.section == 'Rules' or i.kind == 'gives') and name in project.targets_applying_to(i.id) and not of_another(i))
    proven = set()
    for key, row in results.items():
        item = project.items.get(key.partition('@')[0])
        if row.get('target') == name and row['status'] == 'pass' and isinstance(item, Item):
            proven |= project.proves(item)
    proven = testrun.with_refinements(project, proven)
    unproven = [i for i in universe if i not in proven]
    return (100 * (len(universe) - len(unproven)) / len(universe) if universe else None), unproven


def read_results(path, name):
    """{key: 'pass' | 'fail'} from the file a run wrote."""
    try:
        with open(path, encoding='utf8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise TargetError(f'{name}: cannot read the results of the run ({e})')
    if not isinstance(data, dict):
        raise TargetError(f'{name}: the results are {{"part/test:name": "pass"}}, one entry for each test')
    return data


def run(project, names, only=None, provides=None, everything=False, say=print, timeout=TIMEOUT):
    """({key: {'status', 'message', 'target'}}, [notes], {target: coverage}) for the tests of the named targets; the coverage of a target is its clause
    coverage and, when its rules give an `lcov:` file that the run wrote, its line coverage per clause. A key is the test, or `test@language` for a test with
    test code in some languages (a plain id in the file of a run stands for the language of that run). A test with test code in the language that the
    run did not report is `skipped`, and one that says `runs on:` is `deferred` as for the web tests."""
    scan = Scan(project)
    snap = lockfile.snapshot(project, scan)
    results, notes, covered = {}, [], {}
    for name in names:
        path, lcov, output, code, note = run_command(project, name, say, timeout)
        if note:
            notes.append(note)
        given = read_results(path, name)
        reported = set()
        for key, status in sorted(given.items()):
            base, _, wanted = key.partition('@')
            item = project.items.get(base)
            if not (isinstance(item, Item) and item.is_test):
                notes.append(f'{name} reported {key}, which is no test: ignored')
                continue
            if status not in ('pass', 'fail'):
                continue   # skipped, xfail and the like: no result
            if wanted and wanted != name:
                notes.append(f'{name} reported {key}: a run reports its own language only: ignored')
                continue
            language, why = lockfile.result_language(key, sorted((snap.get(base) or {}).get('targets') or {}), bare=name)
            if why:
                notes.append(f'{name}: {why.replace("results: ", "", 1)}: ignored')
                continue
            if only and not testrun.selects(project, item, only):
                continue
            row = f'{base}@{language}' if language else base
            reported.add(row)
            if lockfile.is_manual(item):
                continue
            reason = testrun.deferral(item, only, provides, everything)
            results[row] = ({'status': 'deferred', 'message': reason, 'target': name} if reason
                            else {'status': status, 'message': '', 'target': name})
        for item in project.all_items():
            line = ((snap.get(item.id) or {}).get('targets') or {}).get(name)
            row = f'{item.id}@{name}'
            if item.is_test and line is not None and 'result' in line and row not in reported and (not only or testrun.selects(project, item, only)):
                results[row] = {'status': 'skipped', 'message': f'the run of {name} did not report it', 'target': name}
        if code:
            notes.append(f'{name}: the command exited with {code}' + (f'. Its last lines:\n{tail(output)}' if output.strip() else ''))
        fc, unproven = clause_coverage(project, name, results)
        ran, total, by_clause = line_coverage(project, scan, name, read_lcov(lcov, project.root)) if lcov else (0, 0, {})
        covered[name] = {'clause_coverage': fc, 'unproven': unproven, 'line_coverage': 100 * ran / total if total else None,
                         'lines': (ran, total), 'by_clause': by_clause}
    return dict(sorted(results.items())), notes, covered
