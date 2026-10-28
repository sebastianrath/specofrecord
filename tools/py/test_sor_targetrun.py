"""Tests for running the tests of a target in its own framework (SPEC §9): what a target says (`{run: …}`, `{results: …}`, `{lcov: …}`), the
problems `sor check` finds in it, that a command runs only when a call names its target, how the results it writes are read, and `sor lock
--run-tests --targets`.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder; the "framework" is a small Python script that writes what the
test says it should.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import time
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import targetrun                 # noqa: E402
from sorlib.model import Project, split_command, unsafe_path   # noqa: E402

doc, write, read = base.doc, base.write, base.read
TEST = 'greet/test:hello'
PY_TEST = '# @clause test greet/hello\ndef test_hello():\n    assert HELLO\n# @clause end\n'
TS_TEST = '// @clause test greet/hello\ntest("hello", () => expect(HELLO));\n// @clause end\n'
TESTS = ['- **hello** - says hello.', '  expect: ok', '- **bye** - looks right.', '  manual: look']
# the "framework": writes the results in plan-<language>.json to out/results-<language>.json, the lcov in lcov-<language>.info to out/, and exits
# with the code in exit-<language>.txt
RUNNER = '''import json, os, sys
language = sys.argv[1]
os.makedirs('out', exist_ok=True)
open('ran-' + language + '.txt', 'a').write('x')
if os.path.exists('plan-' + language + '.json'):
    open('out/results-' + language + '.json', 'w').write(open('plan-' + language + '.json').read())
if os.path.exists('lcov-' + language + '.info'):
    open('out/lcov-' + language + '.info', 'w').write(open('lcov-' + language + '.info').read())
print('ran the tests of ' + language)
sys.exit(int(open('exit-' + language + '.txt').read()) if os.path.exists('exit-' + language + '.txt') else 0)
'''


def target_part(name, path, extra=''):
    """`extra`: the text of the rule about the tests, or a list of such texts (one rule each)."""
    texts = [extra] if isinstance(extra, str) and extra else list(extra or [])
    return doc(name.title(), 'Where the code of one language lives and how its tests run.',
               rules=[f'- **code** - The code is under {{path: {path}}}.'] + [f'- **tests{i or ""}** - {t}' for i, t in enumerate(texts)])


class Runs(targeted.Targeted):
    """greet/hello has code and test code in Python and TypeScript; both targets say how their tests run."""
    RUN = '"%s" run.py %s' % (sys.executable.replace('\\', '/'), '%s')

    def build(self, py_extra=None, ts_extra=None, parts=None, **more):
        shutil.rmtree(os.path.join(self.dir, 'sor'), ignore_errors=True)
        py_extra = py_extra if py_extra is not None else 'Run with {run: %s}, results in {results: out/results-py.json}, coverage in {lcov: out/lcov-py.info}.' % (self.RUN % 'py')
        ts_extra = ts_extra if ts_extra is not None else 'Run with {run: %s}, results in {results: out/results-ts.json}.' % (self.RUN % 'ts')
        self.project({'targets/py': target_part('py', 'src_py/', py_extra), 'targets/ts': target_part('ts', 'src_ts/', ts_extra),
                      'greet': doc('Greet', 'Says hello.', rules=['- **hello** - The greeting is "Hello".', '- **bye** - The farewell is "Bye".'],
                                   tests=more.get('tests') or TESTS), **(parts or {})})
        root = os.path.join(self.spec, 'SPECOFRECORD.md')
        write(self.dir, 'sor/SPECOFRECORD.md', read(root).replace('Why: A project the tests use.', 'Why: A project the tests use.\nTargets: py, ts', 1))

    def setUp(self):
        flows.Flow.setUp(self)
        self.build()
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        write(self.dir, 'src_py/test_greet.py', PY_TEST)
        write(self.dir, 'src_ts/greet.test.ts', TS_TEST)
        write(self.dir, 'run.py', RUNNER)
        self.spec_file = os.path.join(self.spec, 'greet.md')

    def plan(self, language, results, code=None):
        write(self.dir, f'plan-{language}.json', json.dumps(results))
        if code is not None:
            write(self.dir, f'exit-{language}.txt', str(code))

    def ran(self, language):
        path = os.path.join(self.dir, f'ran-{language}.txt')
        return len(read(path)) if os.path.exists(path) else 0

    def out(self, *args):
        code, out, err = self.sor(*args)
        return code, out + err


class TestWhatATargetSays(Runs):
    def test_the_values_are_read_from_the_rules_of_the_target(self):
        said = Project(self.dir).target_commands()
        self.assertEqual(sorted(said), ['py', 'ts'])
        self.assertTrue(said['py']['run'].endswith('run.py py'))
        self.assertEqual((said['py']['results'], said['py']['lcov']), ('out/results-py.json', 'out/lcov-py.info'))
        self.assertEqual(said['ts'], {'run': said['ts']['run'], 'results': 'out/results-ts.json'})

    def test_a_project_that_says_nothing_has_nothing(self):
        self.build(py_extra='', ts_extra='')
        self.assertEqual(Project(self.dir).target_commands(), {})
        self.assertEqual(self.out('check')[0], 0)

    def problems(self, **kwargs):
        self.build(**kwargs)
        code, out = self.out('check')
        return code, out

    def test_a_command_with_nowhere_to_read_its_results_is_a_problem(self):
        code, out = self.problems(py_extra='Run with {run: python3 run.py py}.')
        self.assertEqual(code, 2, out)
        self.assertIn('target py has a `run:` and no `results:`', out)

    def test_a_file_without_the_command_that_writes_it_is_a_problem(self):
        code, out = self.problems(py_extra='Results in {results: out/r.json}, coverage in {lcov: out/l.info}.')
        self.assertEqual(code, 2, out)
        self.assertIn('target py has a `results:` and no `run:`', out)
        self.assertIn('target py has a `lcov:` and no `run:`', out)

    def test_a_path_outside_the_project_or_in_the_spec_folder_is_a_problem(self):
        for path, why in (('/tmp/r.json', 'is not a path relative to the project'), ('../r.json', 'leaves the project'),
                          ('sor/r.json', 'is in sor/, which holds the spec'), ('C:/r.json', 'is not a path relative to the project'),
                          ('./sor/r.json', 'is in sor/, which holds the spec'), ('SOR/r.json', 'is in sor/, which holds the spec'),
                          ('out/../sor/r.json', 'leaves the project')):
            with self.subTest(path):
                code, out = self.problems(py_extra='Run with {run: python3 run.py py}, results in {results: %s}.' % path)
                self.assertEqual(code, 2, out)
                self.assertIn(f'`results: {path}` {why}', out)

    def test_a_path_that_only_looks_different_from_one_in_the_spec_folder_is_one(self):
        for path in ('./sor/r.json', '.\\sor\\r.json', 'sor//r.json', 'Sor/r.json', './/sor/r.json'):
            self.assertTrue(unsafe_path(path), path)
        for path in ('out/sor/r.json', 'sorry/r.json', './out/r.json', 'r.json', 'out//r.json'):
            self.assertEqual(unsafe_path(path), '', path)

    def test_a_command_that_cannot_be_split_into_words_is_a_problem(self):
        code, out = self.problems(py_extra='Run with {run: python3 "run.py}, results in {results: out/r.json}.')
        self.assertEqual(code, 2, out)
        self.assertIn('is not a command: words separated by spaces, quotes closed', out)

    def test_a_backslash_is_a_character_like_any_other_in_a_command_so_one_spec_gives_one_command(self):
        self.assertEqual(split_command(r'.venv\Scripts\python.exe -m pytest -q'), [r'.venv\Scripts\python.exe', '-m', 'pytest', '-q'])
        self.assertEqual(split_command(r'"C:\Program Files\Python\python.exe" a\b "c d" e'), [r'C:\Program Files\Python\python.exe', r'a\b', 'c d', 'e'])
        self.assertEqual(split_command("python3 -m pytest -k 'a b' \"c\\d\""), ['python3', '-m', 'pytest', '-k', 'a b', 'c\\d'])
        self.assertEqual(split_command('  '), [])
        with self.assertRaises(ValueError):
            split_command('python3 "run.py')
        code, out = self.problems(py_extra='Run with {run: .venv\\Scripts\\python.exe run.py py}, results in {results: out/r.json}.')
        self.assertNotIn('is not a command', out)

    def test_two_commands_for_one_target_are_a_problem(self):
        code, out = self.problems(py_extra=['Run with {run: python3 run.py py}, results in {results: out/r.json}.', 'Or with {run: pytest}.'])
        self.assertEqual(code, 2, out)
        self.assertIn('target py says `run:` twice', out)


class TestAWebTargetRunsItself(Runs):
    def test_a_web_target_with_a_command_is_a_problem(self):
        flows.replace_in(os.path.join(self.spec, 'targets', 'py.md'), '{path: src_py/}', '{path: out/page.html}')
        code, out = self.out('check')
        self.assertIn('target py is a web target: `sor test` runs its tests itself, so it has no `run:`', out)


class TestTheRowsOfTheWebRunAndOfATarget(Runs):
    def test_the_result_of_a_run_replaces_the_external_row_of_its_test(self):
        from unittest import mock
        from sorlib import cli, testrun
        self.plan('py', {TEST: 'pass'})
        external = ({TEST: {'status': 'external', 'message': 'your own run'}, 'greet/test:bye': {'status': 'manual', 'message': ''}}, None)
        with mock.patch.object(testrun, 'web_targets', return_value=[object()]), mock.patch.object(testrun, 'run', return_value=external), \
                contextlib.redirect_stdout(io.StringIO()):
            results, summary, notes, covered = cli.run_tests(Project(self.dir), ['py'])
        self.assertEqual(sorted(results), ['greet/test:bye', f'{TEST}@py'])
        self.assertEqual(results[f'{TEST}@py']['status'], 'pass')


    def merged(self, web, target):
        from unittest import mock
        from sorlib import cli, testrun
        rows = {TEST: {'status': target, 'message': '', 'target': 'py'}}
        with mock.patch.object(testrun, 'web_targets', return_value=[object()]), \
                mock.patch.object(testrun, 'run', return_value=({TEST: {'status': web, 'message': ''}}, None)), \
                mock.patch.object(targetrun, 'run', return_value=(rows, [], {})), contextlib.redirect_stdout(io.StringIO()):
            results, _, notes, _ = cli.run_tests(Project(self.dir), ['py'])
        return results[TEST]['status'], notes

    def test_a_failure_of_the_web_run_is_not_taken_back_by_the_run_of_a_target_and_the_collision_is_said(self):
        status, notes = self.merged('fail', 'pass')
        self.assertEqual(status, 'fail')
        self.assertEqual(notes, [f'{TEST}: the web run says fail and the run of py says pass: the failure stands'])

    def test_a_failure_of_the_run_of_a_target_replaces_a_pass_of_the_web_run(self):
        status, notes = self.merged('pass', 'fail')
        self.assertEqual(status, 'fail')
        self.assertEqual(notes, [f'{TEST}: the web run says pass and the run of py says fail: the failure stands'])

    def test_two_runs_that_agree_say_nothing_and_a_deferred_test_gives_way_to_the_run_that_has_a_result(self):
        self.assertEqual(self.merged('pass', 'pass'), ('pass', []))
        status, notes = self.merged('deferred', 'pass')
        self.assertEqual(status, 'pass')
        self.assertEqual(notes, [f'{TEST}: the web run says deferred and the run of py says pass: the result of py stands'])


class TestNamingTargets(Runs):
    def test_a_name_that_is_no_target_or_says_no_command_is_refused_with_the_reason(self):
        code, out = self.out('test', '--targets', 'go')
        self.assertEqual(code, 2, out)
        self.assertIn('--targets names go, which is no target (targets: py, ts)', out)
        self.build(ts_extra='')
        code, out = self.out('test', '--targets', 'ts')
        self.assertEqual(code, 2, out)
        self.assertIn('--targets names ts, which does not say how its tests run', out)

    def test_the_command_never_runs_when_the_call_does_not_name_its_target(self):
        for args in (('test',), ('test', '--list'), ('lock', '--all', '--allow-behind', 'py,ts', '--allow-incomplete'), ('status',), ('check',)):
            with self.subTest(args):
                try:
                    self.out(*args)
                except SystemExit:
                    pass
        self.assertEqual((self.ran('py'), self.ran('ts')), (0, 0))

    def test_a_test_with_no_web_target_to_run_says_so_and_how_to_run_a_target(self):
        code, out, err = self.sor('test')
        self.assertNotEqual(code, 0)
        self.assertIn('no web target', out + err)
        self.assertIn('sor test --targets py', out + err)

    def test_a_test_without_a_result_is_told_which_targets_can_run_it(self):
        """The tests block of `sor status` and the refusal of `sor lock` said `no web target`, as if nothing could run them, to a project whose
        targets say how their tests run."""
        for args in (('status',), ('lock', '--all')):
            code, out = self.out(*args)
            self.assertIn('`sor lock --run-tests --targets py,ts`', out, args)
            self.assertIn('`--results F`', out, args)
            self.assertIn('`manual:`', out, args)
            self.assertNotIn('has no web target', out, args)

    def test_only_a_target_that_says_how_its_tests_run_is_offered(self):
        self.build(ts_extra='Results in {results: out/results-ts.json}.')
        code, out = self.out('status')
        self.assertIn('`sor lock --run-tests --targets py`', out)
        self.assertNotIn('py,ts', out)

    def test_with_a_web_target_too_the_run_of_the_page_stays_and_the_targets_are_added(self):
        from unittest import mock
        from sorlib import lock as lockfile
        with mock.patch.object(Project, 'has_web_target', return_value=True):
            said = lockfile.how_to_pass(Project(self.dir), [TEST])
        self.assertIn('`sor lock --run-tests` runs the tests', said)
        self.assertIn('`sor lock --run-tests --targets py,ts`', said)
        self.assertIn('`@clause test <id>`', said)

    def test_the_targets_that_were_not_named_are_told_in_a_line(self):
        self.plan('py', {f'{TEST}': 'pass'})
        code, out = self.out('test', '--targets', 'py')
        self.assertIn('note: ts says how its tests run', out)
        self.assertIn('`sor test --targets ts` runs it', out)
        self.assertNotIn('py says how', out)

    def test_a_flag_for_the_lock_needs_run_tests(self):
        code, out = self.out('lock', '--all', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('--targets runs the tests of a target: add --run-tests', out)


class TestRunningATarget(Runs):
    def test_the_command_runs_and_its_results_are_the_rows_of_that_language(self):
        self.plan('py', {TEST: 'pass'})
        code, out = self.out('test', '--targets', 'py')
        self.assertEqual(code, 0, out)
        self.assertIn('running py:', out)
        self.assertRegex(out, rf'PASS\s+{TEST}@py')
        self.assertEqual(self.ran('py'), 1)
        self.assertEqual(self.ran('ts'), 0)

    def test_both_languages_give_a_row_each_and_a_failure_is_an_exit_code_of_1(self):
        self.plan('py', {TEST: 'pass'})
        self.plan('ts', {f'{TEST}@ts': 'fail'})
        out_file = os.path.join(self.dir, 'results.json')
        code, out = self.out('test', '--targets', 'py,ts', '--out', out_file)
        self.assertEqual(code, 1, out)
        self.assertEqual(json.loads(read(out_file)), {f'{TEST}@py': 'pass', f'{TEST}@ts': 'fail'})   # the file sor lock --results takes

    def test_a_test_with_test_code_in_the_language_that_the_run_did_not_report_is_skipped(self):
        self.plan('py', {})
        code, out = self.out('test', '--targets', 'py')
        self.assertRegex(out, rf'SKIP\s+{TEST}@py\s+the run of py did not report it')

    def test_what_a_run_reports_that_is_not_its_own_is_ignored_and_said(self):
        self.plan('py', {f'{TEST}@ts': 'pass', 'greet/test:nothing': 'pass', f'{TEST}': 'skipped'})
        code, out = self.out('test', '--targets', 'py')
        self.assertIn(f'py reported {TEST}@ts: a run reports its own language only: ignored', out)
        self.assertIn('py reported greet/test:nothing, which is no test: ignored', out)
        self.assertNotRegex(out, rf'PASS\s+{TEST}')
        self.assertRegex(out, rf'SKIP\s+{TEST}@py\s+the run of py did not report it')       # a skipped test gave no result, so it is missing

    def test_a_manual_test_takes_no_result(self):
        self.plan('py', {'greet/test:bye': 'pass', TEST: 'pass'})
        code, out = self.out('test', '--targets', 'py')
        self.assertEqual([l for l in out.splitlines() if 'PASS' in l and 'greet/test:bye' in l], [])      # nobody runs it: a person checks it

    def test_ids_choose_which_rows_are_shown_but_not_what_runs(self):
        self.plan('py', {TEST: 'pass', 'greet/test:bye': 'pass'})
        code, out = self.out('test', 'greet/hello', '--targets', 'py')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran('py'), 1)
        self.assertRegex(out, rf'PASS\s+{TEST}@py')

    def test_a_failing_command_with_fresh_results_is_a_failure_of_the_tests_and_its_output_is_shown(self):
        self.plan('py', {TEST: 'fail'}, code=3)
        code, out = self.out('test', '--targets', 'py')
        self.assertEqual(code, 1, out)
        self.assertIn('py: the command exited with 3. Its last lines:', out)
        self.assertIn('ran the tests of py', out)

    def test_a_deferred_test_is_deferred_here_too(self):
        self.build(tests=['- **hello** - says hello.', '  expect: ok', '  runs on: linux', '- **bye** - looks right.', '  manual: look'])
        self.plan('py', {TEST: 'pass'})
        code, out = self.out('test', '--targets', 'py')
        self.assertRegex(out, rf'DEFER\s+{TEST}@py')
        self.plan('py', {})
        code, out = self.out('test', '--targets', 'py')
        self.assertNotIn(f'{TEST}@py', out)                                           # left to CI, so a run that leaves it out misses nothing


class TestAResultsFileThatWasNotWritten(Runs):
    def test_a_file_the_run_left_as_it_was_is_never_read(self):
        write(self.dir, 'out/results-py.json', json.dumps({TEST: 'pass'}))          # from an earlier run
        code, out = self.out('test', '--targets', 'py')                              # the command writes nothing: there is no plan
        self.assertEqual(code, 2, out)
        self.assertIn('out/results-py.json is as it was before the run', out)
        self.assertNotIn('PASS', out)

    def test_a_file_that_is_not_there_after_the_run_is_said(self):
        code, out = self.out('test', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('out/results-py.json was not written', out)
        self.assertIn('ran the tests of py', out)                                    # what the command printed helps to see why

    def test_results_that_are_not_a_json_object_are_said(self):
        write(self.dir, 'plan-py.json', '[1, 2]')
        code, out = self.out('test', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('the results are {"part/test:name": "pass"}', out)
        write(self.dir, 'plan-py.json', 'not json')
        code, out = self.out('test', '--targets', 'py')
        self.assertIn('cannot read the results of the run', out)

    def test_a_program_that_is_not_there_is_said(self):
        self.build(py_extra='Run with {run: no-such-program-here}, results in {results: out/r.json}.')
        code, out = self.out('test', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('cannot start no-such-program-here: no such program', out)

    def test_a_run_that_takes_too_long_is_stopped(self):
        write(self.dir, 'slow.py', 'import time\ntime.sleep(5)\n')
        self.build(py_extra='Run with {run: "%s" slow.py}, results in {results: out/r.json}.' % sys.executable.replace('\\', '/'))
        project = Project(self.dir)
        with self.assertRaises(targetrun.TargetError) as caught:
            targetrun.run_command(project, 'py', say=lambda *_: None, timeout=1)
        self.assertIn('the run took more than 1 s and was stopped', str(caught.exception))


# the process-tree kill runs on every system: on Windows it is taskkill /T
class TestStoppingARunAndWhatItStarted(Runs):
    # a "framework" that starts a worker and waits; the worker adds a byte to beat.txt every 50 ms for at most 20 s and holds the pipes of the run like a
    # worker does. Whether it still runs is read from the file: a process that was killed can stay a zombie that kill(pid, 0) finds (in a container
    # whose first process reaps nothing), and a file does not care.
    WORKER = 'import time\nfor _ in range(400):\n    open("beat.txt", "a").write("x")\n    time.sleep(0.05)\n'
    SPAWN = ('import subprocess, sys, time\n'
             'subprocess.Popen([sys.executable, "-c", %r])\n'
             'time.sleep(60)\n') % WORKER

    def start(self):
        write(self.dir, 'spawn.py', self.SPAWN)
        self.build(py_extra='Run with {run: "%s" spawn.py}, results in {results: out/r.json}.' % sys.executable.replace('\\', '/'))
        return Project(self.dir)

    def beats(self):
        path = os.path.join(self.dir, 'beat.txt')
        return len(read(path)) if os.path.exists(path) else 0

    def running(self):
        """Waits for the worker to beat, so that the test knows it started."""
        end = time.time() + 5
        while self.beats() < 3:
            self.assertLess(time.time(), end, 'the worker did not start')
            time.sleep(0.05)

    def silent(self):
        """Whether the worker stopped beating (it has not written for twice the time between two beats and more)."""
        before = self.beats()
        time.sleep(0.6)
        return self.beats() == before

    def test_a_run_that_takes_too_long_is_stopped_with_the_programs_it_started(self):
        project = self.start()
        began = time.time()
        with self.assertRaises(targetrun.TargetError) as caught:
            targetrun.run_command(project, 'py', say=lambda *_: None, timeout=1)
        self.assertIn('the run took more than 1 s and was stopped', str(caught.exception))
        self.assertLess(time.time() - began, 10)
        self.assertGreaterEqual(self.beats(), 3, 'the worker never ran')
        self.assertTrue(self.silent(), 'the worker still runs')

    def test_ctrl_c_ends_the_run_and_what_it_started_and_goes_on_to_the_caller(self):
        from unittest import mock
        project = self.start()

        original = targetrun.subprocess.Popen.communicate

        def interrupted(proc, *args, **kwargs):
            if os.path.basename(str(proc.args[0])) == 'taskkill.exe' or proc.args[0] == 'taskkill':   # on Windows stopping the run is itself a program to run
                return original(proc, *args, **kwargs)
            self.running()
            raise KeyboardInterrupt
        with mock.patch.object(targetrun.subprocess.Popen, 'communicate', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                targetrun.run_command(project, 'py', say=lambda *_: None, timeout=30)
        self.assertTrue(self.silent(), 'the worker still runs')


class TestCoverageOfATarget(Runs):
    PY_LCOV = 'SF:src_py/greet.py\nDA:2,3\nend_of_record\n'

    def covered(self, *args):
        code, out = self.out('test', '--targets', 'py', '--coverage', *args)
        return code, out

    def test_the_lines_of_the_marked_code_that_ran_are_counted_for_the_target(self):
        self.plan('py', {TEST: 'pass'})
        write(self.dir, 'lcov-py.info', self.PY_LCOV)
        code, out = self.covered()
        self.assertEqual(code, 0, out)
        self.assertIn('line coverage py 100.0% (1 of 1 marked code lines ran)', out)
        self.assertIn('line coverage per clause in py (lowest first):', out)
        self.assertRegex(out, r'100%\s+1/1\s+greet/hello')

    def test_a_line_that_did_not_run_and_a_line_with_no_record_are_told_apart(self):
        self.plan('py', {TEST: 'pass'})
        write(self.dir, 'src_py/greet.py', '# @clause greet/hello\nHELLO = "Hello"\nOTHER = 1\nANOTHER = 2\n# @clause end\n')
        write(self.dir, 'lcov-py.info', 'SF:src_py/greet.py\nDA:2,1\nDA:3,0\nend_of_record\n')      # line 4 has no record: it cannot run
        code, out = self.covered()
        self.assertIn('line coverage py 50.0% (1 of 2 marked code lines ran)', out)

    def test_a_line_marker_counts_as_the_one_line_it_is(self):
        self.plan('py', {TEST: 'pass'})
        write(self.dir, 'src_py/greet.py', self.PY + 'X = 1  # @clause greet/hello\n')
        write(self.dir, 'lcov-py.info', 'SF:src_py/greet.py\nDA:2,1\nDA:4,0\nend_of_record\n')
        code, out = self.covered()
        self.assertIn('line coverage py 50.0% (1 of 2 marked code lines ran)', out)

    def test_a_file_of_another_target_is_not_counted_for_this_one(self):
        self.plan('py', {TEST: 'pass'})
        write(self.dir, 'lcov-py.info', self.PY_LCOV + 'SF:src_ts/greet.ts\nDA:2,0\nend_of_record\n')
        code, out = self.covered()
        self.assertIn('line coverage py 100.0% (1 of 1 marked code lines ran)', out)

    def test_a_coverage_file_the_run_did_not_write_is_not_read(self):
        self.plan('py', {TEST: 'pass'})
        write(self.dir, 'out/lcov-py.info', self.PY_LCOV)                          # from an earlier run
        code, out = self.covered()
        self.assertEqual(code, 0, out)
        self.assertIn('py: out/lcov-py.info is as it was before the run: no line coverage', out)
        self.assertNotIn('line coverage py', out)
        self.assertIn('clause coverage py', out)                                     # what the results give does not need it

    def test_a_target_that_says_no_lcov_has_clause_coverage_only(self):
        self.plan('ts', {TEST: 'pass'})
        code, out = self.out('test', '--targets', 'ts')
        self.assertIn('clause coverage ts 20.0% (4 rules and gives that apply to ts without a passing test of its run)', out)
        self.assertNotIn('line coverage ts', out)

    def test_the_clause_coverage_of_a_target_is_the_share_of_what_applies_to_it_that_its_run_proved(self):
        self.plan('py', {TEST: 'pass'})
        code, out = self.covered()
        self.assertIn('clause coverage py 20.0% (4 rules and gives that apply to py without a passing test of its run)', out)
        self.assertRegex(out, r'not proven in py by a passing test of its run:\n  greet/bye\n  out-of-scope\n  targets/py/code\n  targets/py/tests\n')
        self.assertNotIn('targets/ts', out)                                          # what the part of ts says about itself does not apply to py
        self.assertNotIn('clause coverage ts', out)                                  # ts was not run

    def test_the_rules_of_a_part_that_is_not_for_the_target_do_not_count_against_it(self):
        self.build(parts={'pyonly': doc('Py only', 'Only for Python.', rules=['- **pkg** - It packages.'], header=['Targets: py'])})
        write(self.dir, 'run.py', RUNNER)
        self.plan('ts', {TEST: 'pass'})
        code, out = self.out('test', '--targets', 'ts')
        self.assertIn('clause coverage ts 20.0% (4 rules and gives that apply to ts without', out)       # pkg is for Python only: it is not among the five
        self.plan('py', {TEST: 'pass'})
        code, out = self.out('test', '--targets', 'py')
        self.assertIn('clause coverage py 16.7% (5 rules and gives that apply to py without', out)

    def test_the_run_of_another_target_proves_nothing_for_this_one(self):
        self.plan('py', {TEST: 'pass'})
        self.plan('ts', {TEST: 'fail'})
        code, out = self.out('test', '--targets', 'py,ts')
        self.assertIn('clause coverage py 20.0% (4 rules', out)
        self.assertIn('clause coverage ts 0.0% (5 rules', out)                       # the pass of py is not a pass of ts

    def test_a_goal_refined_by_a_proven_rule_is_proven_too(self):
        self.build(tests=TESTS)
        flows.replace_in(self.spec_file, '- **bye** - The farewell is "Bye".', '- **bye** - The farewell is "Bye".\n- **goal** - It greets. Refined by {hello}.')
        self.plan('py', {TEST: 'pass'})
        code, out = self.covered()
        self.assertIn('clause coverage py 33.3% (4 rules', out)                      # hello, and the goal that is refined by it

    def test_a_failed_test_proves_nothing(self):
        self.plan('py', {TEST: 'fail'})
        code, out = self.covered()
        self.assertIn('clause coverage py 0.0% (5 rules', out)

    def test_the_lock_prints_it_too(self):
        self.plan('py', {TEST: 'pass'})
        write(self.dir, 'lcov-py.info', self.PY_LCOV)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)
        code, out = self.out('lock', 'greet/hello@py', '--run-tests', '--targets', 'py')
        self.assertIn('line coverage py 100.0%', out)


class TestReadingAnLcovFile(unittest.TestCase):
    def read(self, text):
        folder = self.tmp()
        path = write(folder, 'lcov.info', text)
        return targetrun.read_lcov(path, folder)

    def tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_files_and_lines_with_their_hits_and_the_other_records_ignored(self):
        got = self.read('TN:\nSF:a/b.py\nFN:1,f\nDA:1,2\nDA:2,0,abc123\nBRDA:1,0,0,1\nLF:2\nLH:1\nend_of_record\nSF:c.py\nDA:5,1\nend_of_record\n')
        self.assertEqual(got, {'a/b.py': {1: 2, 2: 0}, 'c.py': {5: 1}})

    def test_a_path_is_made_relative_to_the_project_and_one_outside_it_is_left_out(self):
        folder = self.tmp()
        path = write(folder, 'lcov.info', f'SF:{folder}/x/y.py\nDA:1,1\nend_of_record\nSF:./z.py\nDA:1,1\nend_of_record\nSF:/elsewhere/q.py\nDA:1,1\nend_of_record\n'
                                           'SF:..\\up.py\nDA:1,1\nend_of_record\nSF:w\\v.py\nDA:1,1\nend_of_record\n')
        got = targetrun.read_lcov(path, folder)
        self.assertEqual(sorted(got), ['w/v.py', 'x/y.py', 'z.py'])

    def test_a_line_seen_twice_keeps_the_larger_count_and_a_record_that_is_not_numbers_is_ignored(self):
        got = self.read('SF:a.py\nDA:1,4\nDA:1,0\nDA:x,1\nDA:2,-\nDA:3\nend_of_record\n')
        self.assertEqual(got, {'a.py': {1: 4}})

    def test_digits_of_other_scripts_are_not_numbers_to_it(self):
        got = self.read('SF:a.py\nDA:\u00b2,1\nDA:1,\u0663\nDA:2,3\nend_of_record\n')
        self.assertEqual(got, {'a.py': {2: 3}})

    def test_lines_outside_a_file_record_are_ignored(self):
        self.assertEqual(self.read('DA:1,1\nSF:a.py\nend_of_record\nDA:2,2\n'), {'a.py': {}})


class TestLockingWithTheResultsOfARun(Runs):
    def locked_with_ts_behind(self):
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)

    def test_the_lock_takes_the_results_of_the_named_target_and_writes_them_on_its_line(self):
        self.locked_with_ts_behind()
        self.plan('py', {TEST: 'pass'})
        self.plan('ts', {TEST: 'pass'})
        code, out = self.out('lock', 'greet/hello@py', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 0, out)
        self.assertIn('locked ', out)
        lines = {k: v for k, v in json.loads(flows.lock_bytes(self.dir)).items() if k.startswith(TEST + '@')}
        self.assertEqual({k: v['result'] for k, v in lines.items()}, {f'{TEST}@py': 'pass', f'{TEST}@ts': 'none'})
        self.assertEqual((self.ran('py'), self.ran('ts')), (1, 0))

    def test_a_failed_result_refuses_the_lock(self):
        self.locked_with_ts_behind()
        self.plan('py', {TEST: 'fail'})
        code, out = self.out('lock', 'greet/hello@py', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@py (failed)', out)

    def test_a_run_that_could_not_be_done_refuses_the_lock_and_writes_nothing(self):
        self.locked_with_ts_behind()
        before = flows.lock_bytes(self.dir)
        code, out = self.out('lock', 'greet/hello@py', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('lock refused', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)


class TestARefusalThatNoTestCanChange(Runs):
    """What `sor lock --run-tests --targets` refuses whatever the tests say is refused before any command starts: the command is text in a spec,
    so the person is asked before it runs, and it takes as long as the tests take, and no result of it can make the lock go through."""
    BYE_PY = '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n'

    def test_a_problem_in_the_code_is_refused_before_a_command_starts(self):
        loose = os.path.join(self.dir, 'src_py', 'loose.py')
        write(self.dir, 'src_py/loose.py', 'LOOSE = 1\n')                  # a line in no region: `sor check` says so at once
        self.plan('py', {TEST: 'pass'})
        code, out = self.out('lock', '--all', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('code outside any @clause region', out)
        self.assertIn('no test was run', out)
        self.assertNotIn('ran the tests of py', out)
        self.assertEqual((self.ran('py'), self.ran('ts')), (0, 0))
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'sor', 'sor-lock.json')))   # a refusal writes nothing
        os.remove(loose)
        self.out('lock', '--all', '--run-tests', '--targets', 'py')
        self.assertEqual(self.ran('py'), 1)                                   # without the fault the command starts, as it always did

    def test_a_clause_with_no_code_in_a_target_that_applies_is_refused_before_a_command_starts(self):
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)
        write(self.dir, 'src_py/bye.py', self.BYE_PY)                         # built in Python only
        self.plan('py', {TEST: 'pass'})
        code, out = self.out('lock', 'greet/bye', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/bye  it applies to ts', out)
        self.assertIn('no test was run', out)
        self.assertEqual(self.ran('py'), 0)

    def locked_with_everything_behind(self):
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)
        self.plan('py', {TEST: 'pass'})

    def lock_of_py(self, clause='greet/hello'):
        started = self.ran('py')
        code, out = self.out('lock', f'{clause}@py', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('no test was run', out)
        self.assertEqual(self.ran('py'), started)                                   # the command did not start again
        return out

    def test_a_lock_of_one_language_is_refused_before_a_command_starts_when_its_clause_changed(self):
        self.locked_with_everything_behind()
        flows.replace_in(self.spec_file, 'The greeting is "Hello".', 'The greeting is "Hi".')
        self.assertIn('lock it first', self.lock_of_py())

    def test_a_lock_of_one_language_is_refused_before_a_command_starts_when_its_code_drifted(self):
        self.plan('py', {TEST: 'pass'})
        self.plan('ts', {TEST: 'pass'})
        code, out = self.out('lock', '--all', '--run-tests', '--targets', 'py,ts')    # locked with a passing test in both languages
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran('py'), 1)
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hallo'))        # then its code changed and the clause did not
        self.assertIn('drift  greet/hello@py', self.lock_of_py())

    def test_a_lock_of_one_language_is_refused_before_a_command_starts_when_the_clause_has_no_code_there(self):
        self.locked_with_everything_behind()
        self.assertIn('no code  greet/bye@py', self.lock_of_py('greet/bye'))

    def test_a_refusal_that_needs_a_result_still_comes_after_the_run(self):
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)
        self.plan('py', {TEST: 'fail'})
        code, out = self.out('lock', 'greet/hello@py', '--run-tests', '--targets', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@py (failed)', out)
        self.assertNotIn('no test was run', out)
        self.assertEqual(self.ran('py'), 1)


class TestTheFiguresOfTheWebRunNextToThoseOfATarget(Runs):
    """A figure that stands next to those of a target says whose it is: `clause coverage 0.0%` beside 63 passing tests of a target reads as if
    nothing were covered, when it is the web run's, in which every test was left to CI."""
    SUMMARY = {'clause_coverage': 0.0, 'line_coverage': None, 'unproven': ['a', 'b'], 'lines': (0, 0), 'by_clause': {}}

    def web_target(self, name='web'):
        import types
        return [types.SimpleNamespace(part=types.SimpleNamespace(id=f'targets/{name}'))]

    def printed(self, name):
        from sorlib import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.print_coverage(self.SUMMARY, False, name)
        return out.getvalue()

    def test_a_web_run_that_is_alone_keeps_its_plain_line(self):
        self.assertEqual(self.printed(None), 'clause coverage 0.0% (2 rules and gives without a passing test)\n')

    def test_a_web_run_next_to_a_target_says_it_is_the_web_run(self):
        self.assertEqual(self.printed('web'), 'clause coverage web 0.0% (2 rules and gives without a passing test of its run)\n')

    def test_the_label_is_the_name_of_the_web_target_and_only_when_a_target_printed_its_figures(self):
        from unittest import mock
        from sorlib import cli, testrun
        project = Project(self.dir)
        with mock.patch.object(testrun, 'web_targets', return_value=self.web_target('browser')):
            self.assertEqual(cli.web_label(project, {'py': {}}), 'browser')
            self.assertIsNone(cli.web_label(project, {}))
        with mock.patch.object(testrun, 'web_targets', return_value=[]):
            self.assertIsNone(cli.web_label(project, {'py': {}}))

    def test_the_label_is_the_name_of_the_target_when_the_path_rule_is_in_a_part_inside_it(self):
        from unittest import mock
        from sorlib import cli, testrun
        with mock.patch.object(testrun, 'web_targets', return_value=self.web_target('web/page')):   # the part `targets/web/page` is the target `web`
            self.assertEqual(cli.web_label(Project(self.dir), {'py': {}}), 'web')

    def test_sor_test_labels_the_figures_of_the_web_run_when_a_target_runs_too(self):
        from unittest import mock
        from sorlib import testrun
        self.plan('py', {TEST: 'pass'})
        with mock.patch.object(testrun, 'web_targets', return_value=self.web_target()), \
                mock.patch.object(testrun, 'run', return_value=({}, dict(self.SUMMARY))):
            code, out = self.out('test', '--targets', 'py')
        self.assertIn('clause coverage web 0.0% (2 rules and gives without a passing test of its run)', out)
        self.assertIn('clause coverage py ', out)


if __name__ == '__main__':
    unittest.main()
