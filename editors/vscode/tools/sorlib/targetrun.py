"""Running the tests of a target in its own framework (SPEC §9).

A target says how in the Rules of its part: `{run: python3 -m pytest -q}` is the command, `{results: out/results-py.json}` the file the
command writes `{"part/test:name": "pass"}` to, as `sor test --out` does (the tool reads no pytest or jest output), and `{lcov: out/lcov-py.info}`
the coverage it writes, in the lcov format that coverage.py, c8, nyc and istanbul all produce.

`sor test --targets py` runs that command from the project root, with no shell, when the call names the target and never otherwise: the command is
text in a spec file, so what a call runs is written in the call. A results file the run did not write (it is as it was before) is never read.
"""
import json
import os
import shlex
import subprocess

from . import lock as lockfile
from . import testrun   # the web runner: which tests a call selects, and which it leaves to CI
from .markers import Scan
from .model import Item

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


def run_command(project, name, say=print, timeout=TIMEOUT):
    """Runs the command of a target. Returns (the results file, what the command printed, its exit code); raises TargetError when it could not
    start, ran out of time, or left the results file as it was."""
    kinds = project.target_commands()[name]
    argv = shlex.split(kinds['run'])
    results = os.path.join(project.root, kinds['results'])
    before = stamp(results)
    say(f'running {name}: {kinds["run"]}')
    try:
        done = subprocess.run(argv, cwd=project.root, capture_output=True, text=True, errors='replace', timeout=timeout)   # no shell
    except FileNotFoundError:
        raise TargetError(f'{name}: cannot start {argv[0]}: no such program')
    except PermissionError:
        raise TargetError(f'{name}: cannot start {argv[0]}: not allowed to run it')
    except subprocess.TimeoutExpired:
        raise TargetError(f'{name}: the run took more than {timeout} s and was stopped')
    output = (done.stdout or '') + (done.stderr or '')
    if stamp(results) in (None, before):
        said = f'{kinds["results"]} is as it was before the run' if before else f'{kinds["results"]} was not written'
        raise TargetError(f'{name}: the command exited with {done.returncode}, and {said}; a results file the run did not write is never read'
                          + (f'. Its last lines:\n{tail(output)}' if output.strip() else ''))
    return results, output, done.returncode


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
    """({key: {'status', 'message', 'target'}}, [notes]) for the tests of the named targets. A key is the test, or `test@language` for a test with
    test code in some languages (a plain id in the file of a run stands for the language of that run). A test with test code in the language that the
    run did not report is `skipped`, and one that says `runs on:` is `deferred` as for the web tests."""
    snap = lockfile.snapshot(project, Scan(project))
    results, notes = {}, []
    for name in names:
        path, output, code = run_command(project, name, say, timeout)
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
    return dict(sorted(results.items())), notes
