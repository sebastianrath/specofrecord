"""Tests for where the result of a test came from (SPEC §11, `via`): a result that `sor lock` ran is labeled `run`, one it read from a results
file is labeled `file`, a lock made before the labels has none and is not called run, and `sor status` and `sor lock` say so next to the count
of passed tests, and count the manual tests next to it.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder; the browser is replaced, as in test_sor_flows.
"""
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
import test_sor_testresults as perlanguage   # noqa: E402
import test_sor_targetrun as bycommand       # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
LIMIT, LOOSE = 'lim/test:limit', 'lim/test:loose'
THREE = {LIMIT: 'pass', LOOSE: 'pass', 'targets/web/test:path': 'pass'}


class Labeled(flows.Flow):
    """A web project with a test sor runs itself (limit, path) and one in the project's own framework (loose) whose result comes from a file."""

    def setUp(self):
        super().setUp()
        self.build(flows.TARGET_WITH_TEST_CODE, flows.TEST_CODE)

    DIRECT = flows.TestExternalTests.DIRECT
    LOOSE = flows.TestExternalTests.LOOSE
    build = flows.TestExternalTests.build
    ask = flows.TestExternalTests.ask
    results = flows.TestExternalTests.results

    def entries(self):
        return json.loads(flows.lock_bytes(self.dir))

    def status(self):
        return self.sor('status')[1]


class TestARunAndAFileAreLabeledEachItsOwnWay(Labeled):
    def lock(self):
        return self.ask('lock', '--all', '--run-tests', '--results', self.results({LOOSE: 'pass'}))

    def test_the_tests_sor_ran_say_run_and_the_one_from_the_file_says_file(self):
        code, out, _ = self.lock()
        self.assertEqual(code, 0, out)
        entries = self.entries()
        self.assertEqual((entries[LIMIT]['via'], entries['targets/web/test:path']['via'], entries[LOOSE]['via']), ('run', 'run', 'file'))
        self.assertIn('tests: 3 passed (2 ran when locked, 1 from a results file)', out)

    def test_status_says_so_next_to_agree(self):
        self.lock()
        code, out, _ = self.sor('status')
        self.assertEqual(code, 0, out)
        self.assertIn('tests locked: 3 passed (2 ran when locked, 1 from a results file)', out)
        self.assertIn('clauses, code and lock agree', out)

    def test_a_lock_that_is_asked_again_changes_nothing(self):
        self.lock()
        first = flows.lock_bytes(self.dir)
        self.assertEqual(self.lock()[0], 0)
        self.assertEqual(flows.lock_bytes(self.dir), first)
        self.assertEqual(self.sor('status')[0], 0)          # nothing turned pending because of a label


class TestAResultsFileWithoutARun(Labeled):
    def test_every_result_is_from_the_file(self):
        code, out, _ = self.sor('lock', '--all', '--results', self.results(THREE))
        self.assertEqual(code, 0, out)
        self.assertEqual({k: e['via'] for k, e in self.entries().items() if e.get('kind') == 'test'},
                         {LIMIT: 'file', LOOSE: 'file', 'targets/web/test:path': 'file'})
        self.assertIn('tests locked: 3 passed (3 from a results file)', self.status())

    def test_a_failure_is_labeled_too_and_a_test_with_no_result_is_not(self):
        code, out, _ = self.sor('lock', '--all', '--results', self.results({LIMIT: 'fail', LOOSE: 'pass'}), '--allow-incomplete')
        self.assertEqual(code, 0, out)
        entries = self.entries()
        self.assertEqual((entries[LIMIT]['result'], entries[LIMIT]['via']), ('fail', 'file'))
        self.assertEqual(entries['targets/web/test:path']['result'], 'none')
        self.assertNotIn('via', entries['targets/web/test:path'])


class TestALockMadeBeforeTheLabels(Labeled):
    def setUp(self):
        super().setUp()
        flows.accepted(self.dir)                              # passes written the way an older sor wrote them: no `via`

    def test_nothing_is_called_run_and_status_adds_nothing(self):
        lock = lockfile.read(Project(self.dir))
        by = lockfile.passed_by(lock)
        self.assertEqual((by['run'], by['file'], by['unlabeled'] > 0), (0, 0, True))
        self.assertNotIn('tests locked', self.status())

    def test_a_pass_that_was_labeled_since_is_set_apart_from_those_that_were_not(self):
        lock = lockfile.read(Project(self.dir))
        lock[LIMIT]['via'] = 'run'
        lockfile.write(Project(self.dir), lock)
        out = self.status()
        self.assertRegex(out, r'tests locked: \d+ passed \(1 ran when locked, \d+ locked before results were labeled\)')


class TestManualTestsAreCounted(Labeled):
    def setUp(self):
        super().setUp()
        flows.replace_in(os.path.join(self.spec, 'lim.md'), '  proves: {limit}\n', '  proves: {limit}\n  manual: by eye\n')

    def test_status_counts_a_manual_test_that_nobody_checked_and_one_that_somebody_did(self):
        self.assertEqual(self.ask('lock', '--all', '--run-tests')[0], 0)
        self.assertIn('tests locked: 2 passed, 1 manual and not yet checked by a person', self.status())
        self.assertEqual(self.ask('lock', '--all', '--run-tests', '--confirm', LOOSE)[0], 0)
        out = self.status()
        self.assertIn('tests locked: 2 passed, 1 manual and checked by a person', out)
        self.assertNotIn('not yet checked', out)

    def test_a_lock_of_tests_that_were_all_run_adds_no_line(self):
        flows.replace_in(os.path.join(self.spec, 'lim.md'), '- **loose** - test that errors stay below the cap.\n  proves: {limit}\n  manual: by eye\n', '')
        os.remove(os.path.join(self.dir, 'test', 'limit.test.js'))
        code, out, _ = self.ask('lock', '--all', '--run-tests')
        self.assertEqual(code, 0, out)
        self.assertIn('tests: 2 passed, 0 manual checks confirmed', out)       # no brackets: nothing to tell
        self.assertNotIn('tests locked', self.status())


class TestALabelDoesNotOutliveItsResult(perlanguage.Tested):
    def test_a_language_with_no_new_result_keeps_no_label(self):
        test = perlanguage.TEST
        self.assertEqual(self.lock_with({f'{test}@py': 'pass', f'{test}@ts': 'pass'})[0], 0)
        self.assertEqual((self.line('py')['via'], self.line('ts')['via']), ('file', 'file'))
        code, out, _ = self.lock_with({f'{test}@py': 'pass'}, '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertEqual((self.line('ts')['result'], 'via' in self.line('ts')), ('none', False), out)
        self.assertEqual((self.line('py')['result'], self.line('py')['via']), ('pass', 'file'))


    def test_a_language_that_stands_as_it_was_needs_no_new_result_because_of_its_label(self):
        test = perlanguage.TEST
        self.assertEqual(self.lock_with({f'{test}@py': 'pass', f'{test}@ts': 'pass'})[0], 0)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to lock', out)


class TestACommandThatWroteTheResultsSaysCommand(bycommand.Runs):
    """The pass of a target comes from a file that a command of the spec wrote. sor ran the command and did not judge the test, so the lock says
    `command` and not `run`, whatever the command exited with."""

    def lock_py(self):
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)
        return self.out('lock', 'greet/hello@py', '--run-tests', '--targets', 'py')

    def test_the_line_of_a_language_whose_test_a_target_run_passed_says_command(self):
        self.plan('py', {bycommand.TEST: 'pass'})
        code, out = self.lock_py()
        self.assertEqual(code, 0, out)
        line = self.raw()[f'{bycommand.TEST}@py']
        self.assertEqual((line['result'], line['via']), ('pass', 'command'))
        self.assertNotIn('via', self.raw()[f'{bycommand.TEST}@ts'])           # not run, so it has no source either

    def test_a_command_that_crashed_after_writing_pass_is_still_only_a_command(self):
        self.plan('py', {bycommand.TEST: 'pass'})
        write(self.dir, 'exit-py.txt', '1')
        code, out = self.lock_py()
        self.assertIn('the command exited with 1', out)                       # the note it always had
        self.assertEqual(self.raw()[f'{bycommand.TEST}@py']['via'], 'command')

    def test_status_says_the_pass_stands_on_a_command(self):
        self.plan('py', {bycommand.TEST: 'pass'})
        self.plan('ts', {f'{bycommand.TEST}@ts': 'pass'})
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--allow-behind', 'py,ts')[0], 0)
        code, out = self.out('lock', 'greet/hello@py', 'greet/hello@ts', '--run-tests', '--targets', 'py,ts')
        self.assertEqual(code, 0, out)
        self.assertIn('tests locked: 1 passed (1 from a target command)', self.sor('status')[1])


class TestAResultNobodyVouchesFor(unittest.TestCase):
    """What `settle` and the counts do with a result whose source is not said."""

    def test_a_result_with_no_source_gets_no_label(self):
        for sources in ({}, {'a': 'cloud'}, {'b': 'run'}):
            with self.subTest(sources=sources):
                entry = {'kind': 'test', 'result': 'none'}
                lockfile.settle(entry, 'pass', 'a', sources)
                self.assertEqual(entry, {'kind': 'test', 'result': 'pass'})

    def test_a_label_is_set_with_the_result_and_dropped_with_it(self):
        for source in lockfile.VIA:
            entry = {'kind': 'test'}
            lockfile.settle(entry, 'fail', 'a', {'a': source})
            self.assertEqual((entry['result'], entry['via']), ('fail', source))
            lockfile.settle(entry, None, 'a', {'a': source})
            self.assertEqual(entry, {'kind': 'test', 'result': 'none'})
            lockfile.settle(entry, 'pass', 'a', {})                            # the old label does not stay on a new result
            self.assertEqual(entry, {'kind': 'test', 'result': 'pass'})

    def test_a_label_that_is_not_one_of_the_known_ones_counts_as_unlabeled(self):
        lock = {'t1': {'kind': 'test', 'result': 'pass', 'via': 'cloud'}, 't2': {'kind': 'test', 'result': 'pass', 'via': 'command'},
                't3': {'kind': 'test', 'result': 'pass', 'via': 'run'}, 't4': {'kind': 'test', 'result': 'pass'},
                't5': {'kind': 'test', 'result': 'pass', 'targets': {'py': {'result': 'pass', 'via': 'run'}, 'ts': {'result': 'pass', 'via': 'command'}}}}
        self.assertEqual(lockfile.passed_by(lock), {'run': 1, 'command': 2, 'file': 0, 'unlabeled': 2})
        self.assertEqual(lockfile.passed_text(lockfile.passed_by(lock)),
                         '5 passed (1 ran when locked, 2 from a target command, 2 locked before results were labeled)')


class TestAcceptWithoutSources(flows.Flow):
    def test_hand_fed_results_with_no_sources_are_labeled_nothing(self):
        self.greet_project(lock=False)
        project = Project(self.dir)
        entries, _ = lockfile.accept(project, Scan(project), {'greet/test:hello': 'pass'}, True)
        tests = [e for e in entries.values() if e.get('kind') == 'test']
        self.assertTrue(tests)
        self.assertEqual([e for e in tests if 'via' in e], [])

    def test_the_same_results_with_a_source_are_labeled_with_it(self):
        self.greet_project(lock=False)
        project = Project(self.dir)
        given = {'greet/test:hello': 'pass'}
        entries, _ = lockfile.accept(project, Scan(project), given, True, sources={k: 'file' for k in given})
        self.assertEqual(entries['greet/test:hello']['via'], 'file')


if __name__ == '__main__':
    unittest.main()
