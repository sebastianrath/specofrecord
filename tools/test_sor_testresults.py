"""Tests for a test that keeps one result for each language it has test code in (SPEC §8, §11): `--results` with `id@py`, a plain id when only one
language has test code, what the lock refuses and names, and that every reader of a test's `result` goes on reading one.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
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
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
TEST = 'greet/test:hello'
PY_TEST = '# @clause test greet/hello\ndef test_hello():\n    assert HELLO\n# @clause end\n'
TS_TEST = '// @clause test greet/hello\ntest("hello", () => expect(HELLO));\n// @clause end\n'
OWN = ['- **hello** - says hello.', '  expect: ok']


class Tested(targeted.Targeted):
    """greet/hello with test code in Python and in TypeScript, a test that needs a result from the project's own framework."""

    def setUp(self):
        super().setUp()
        self.build(tests=OWN)
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        write(self.dir, 'src_py/test_greet.py', PY_TEST)
        write(self.dir, 'src_ts/greet.test.ts', TS_TEST)

    def results(self, **given):
        path = write(self.dir, 'results.json', json.dumps(given))
        return path

    def lock_with(self, given, *args):
        return self.sor('lock', '--all', '--results', self.results(**given), *args)

    def line(self, target, key=TEST):
        return self.raw()[f'{key}@{target}']


class TestOneResultForEachLanguage(Tested):
    def test_a_result_for_each_language_locks_and_is_written_on_its_line(self):
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'})
        self.assertEqual(code, 0, out)
        raw = self.raw()
        self.assertNotIn('result', raw[TEST])                                  # derived when the lock is read
        self.assertEqual((self.line('py')['result'], self.line('ts')['result']), ('pass', 'pass'))
        self.assertTrue(flows.lock_bytes(self.dir).startswith(b'{\n"*format": 3,\n'))
        self.assertEqual(lockfile.read(Project(self.dir))[TEST]['result'], 'pass')
        self.assertEqual(self.sor('status')[0], 0)

    def test_a_language_with_no_result_is_named_and_nothing_is_written(self):
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass'})
        self.assertEqual(code, 2, out)
        self.assertIn(f'1 test(s) did not pass (0 failed, 1 not run): {TEST}@ts', out)
        self.assertIn(f'"{TEST}@ts": "pass"', out)                             # the way out is shown with the line to give
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))

    def test_a_failed_language_is_named_and_allow_incomplete_locks_it_as_not_passed(self):
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'fail'})
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@ts (failed)', out)
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'fail'}, '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertEqual(lockfile.read(Project(self.dir))[TEST]['result'], 'fail')
        self.assertEqual(json.loads(self.sor('status', '--json')[1])['tests_not_passed'], [TEST])

    def test_a_plain_id_is_refused_when_two_languages_have_test_code_and_the_lines_are_named(self):
        code, out, _ = self.lock_with({TEST: 'pass'})
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST} has test code in py, ts: give a result for each, {TEST}@py, {TEST}@ts', out)

    def test_a_language_with_no_test_code_for_it_is_refused(self):
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass', f'{TEST}@go': 'pass'})
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@go: the test code of {TEST} is in py, ts, not in go', out)

    def test_a_result_that_names_no_test_is_refused_as_before(self):
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass', 'greet/nothing@py': 'pass'})
        self.assertEqual(code, 2, out)
        self.assertIn('results: greet/nothing@py is not a test', out)


    def test_the_results_of_tests_outside_a_scoped_lock_are_left_alone(self):
        path = self.results(**{f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'})
        code, out, _ = self.sor('lock', 'greet/bye', '--results', path)
        self.assertEqual(code, 0, out)
        self.assertNotIn(TEST, self.raw())                                     # hello's test is not part of this lock

    def test_a_language_is_refused_for_a_test_with_no_test_code_per_language(self):
        os.remove(os.path.join(self.dir, 'src_py', 'test_greet.py'))
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass'})
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@py: greet/test:hello has no test code per language, so it has one result: {TEST}', out)
        self.assertEqual(self.lock_with({TEST: 'pass'})[0], 0)                 # the plain id is its result, as for any test


    def test_status_names_the_lines_and_its_example_is_a_line_the_lock_accepts(self):
        code, out, _ = self.sor('status')
        self.assertIn(f'tests (1) — no passing result yet, so locking them is refused: {TEST}@py, {TEST}@ts', out)
        self.assertIn(f'{{"{TEST}@py": "pass"}}', out)
        example = json.loads('{"%s@py": "pass", "%s@ts": "pass"}' % (TEST, TEST))
        self.assertEqual(self.lock_with(example)[0], 0)
        self.assertNotIn('tests (', self.sor('status')[1])


class TestAChangedTestIsBehindLikeAClause(Tested):
    """A test with test code per language has lines like a clause, so when its text changes and its code does not, each language is behind it."""
    GIVEN = {f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'}

    def setUp(self):
        super().setUp()
        self.assertEqual(self.lock_with(self.GIVEN)[0], 0)
        flows.replace_in(self.spec_file, 'says hello.', 'says hello twice.')

    def test_status_says_the_code_of_both_languages_is_not_updated_yet(self):
        code, out, _ = self.sor('status')
        self.assertEqual(code, 1, out)
        self.assertIn(f'changed      {TEST}  code not updated yet in py, ts', out)

    def test_the_lock_refuses_until_they_are_rebuilt(self):
        code, out, _ = self.lock_with(self.GIVEN)
        self.assertEqual(code, 2, out)
        self.assertIn(f'behind  {TEST}  its code in py, ts', out)

    def test_already_fits_clears_a_test_line_and_the_result_is_given_as_usual(self):
        code, out, _ = self.lock_with(self.GIVEN, '--already-fits', 'py,ts')
        self.assertEqual(code, 0, out)
        self.assertEqual((self.line('py')['fits'], self.line('py')['result']), (True, 'pass'))
        self.assertEqual(lockfile.read(Project(self.dir))[TEST]['result'], 'pass')

    def test_allow_behind_locks_it_and_leaves_it_listed(self):
        code, out, _ = self.lock_with(self.GIVEN, '--allow-behind', 'py,ts')
        self.assertEqual(code, 0, out)
        self.assertIn(f'behind       {TEST}  py, ts', self.sor('status')[1])


class TestNothingWaitsWithoutAllowBehind(Tested):
    def test_a_lock_without_the_option_does_not_work_out_what_is_behind_for_the_results(self):
        from unittest import mock
        project = Project(self.dir)
        scan = Scan(project)
        given = {f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'}

        def calls(allow):
            with mock.patch.object(lockfile, 'bases', wraps=lockfile.bases) as bases:
                lockfile.accept(project, scan, given, False, [], {}, [], None, allow, ())
            return bases.call_count
        self.assertEqual(calls(('ts',)), calls(()) + 1)          # the extra one is the work for results that may wait

    def test_a_language_named_by_the_option_that_is_not_behind_still_needs_its_result(self):
        code, out, _ = self.lock_with({f'{TEST}@py': 'pass'}, '--allow-behind', 'ts')
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@ts', out)


class TestOneLanguageHasTestCode(Tested):
    def setUp(self):
        super().setUp()
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))

    def test_a_plain_id_is_that_languages_result_and_the_other_needs_none(self):
        code, out, _ = self.lock_with({TEST: 'pass'})
        self.assertEqual(code, 0, out)
        self.assertEqual(self.line('py')['result'], 'pass')
        self.assertNotIn(f'{TEST}@ts', self.raw())

    def test_the_line_of_that_language_works_too_and_the_other_is_refused(self):
        self.assertEqual(self.lock_with({f'{TEST}@py': 'pass'})[0], 0)
        code, out, _ = self.lock_with({f'{TEST}@ts': 'pass'})
        self.assertEqual(code, 2, out)
        self.assertIn('is in py, not in ts', out)


class TestWhatKeepsOneResult(Tested):
    def test_a_manual_test_and_a_test_left_to_ci_keep_their_result_on_the_entry(self):
        self.build(tests=['- **hello** - looks right.', '  manual: look at it'])
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        write(self.dir, 'src_py/test_greet.py', PY_TEST)
        write(self.dir, 'src_ts/greet.test.ts', TS_TEST)
        self.lock_all()
        self.assertEqual(self.raw()[TEST]['result'], 'manual')
        self.assertNotIn('result', self.raw()[f'{TEST}@py'])                   # its lines have code and built, so the lock stays format 2
        self.assertTrue(flows.lock_bytes(self.dir).startswith(b'{\n"*format": 2,\n'))

    def test_a_result_is_not_carried_to_the_next_lock(self):
        self.assertEqual(self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'})[0], 0)
        code, out, _ = self.sor('lock', '--all')                              # results come with each lock, as before
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@py', out)

    def test_a_project_that_adds_its_targets_does_not_find_every_test_changed(self):
        self.build(targets=None, tests=OWN)
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        write(self.dir, 'src_py/test_greet.py', PY_TEST)
        write(self.dir, 'src_ts/greet.test.ts', TS_TEST)
        path = write(self.dir, 'results.json', json.dumps({TEST: 'pass'}))
        self.assertEqual(self.sor('lock', '--all', '--results', path)[0], 0)
        old = read(os.path.join(self.spec, 'sor-lock.json'))
        self.build(targets='py, ts', tests=OWN)
        write(self.dir, 'sor/sor-lock.json', old)
        self.assertEqual([(f['status'], f['key']) for f in self.findings()], [('changed', 'ROOT')])


class TestEveryOtherReaderStillReadsOneResult(Tested):
    def test_the_hook_status_and_evidence_see_a_result_for_the_test(self):
        self.assertEqual(self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'fail'}, '--allow-incomplete')[0], 0)
        entry = lockfile.read(Project(self.dir))[TEST]
        self.assertEqual(entry['result'], 'fail')
        self.assertEqual(sorted(entry['targets']), ['py', 'ts'])
        code, out, _ = self.sor('status')
        self.assertIn('had not passed at the last lock', out)


if __name__ == '__main__':
    unittest.main()
