"""Tests for `sor lock greet/hello@py`, the lock of one language of a clause (SPEC §16): it writes that language's line (and the line of the
clause's own test, and the glue of that language's files) and nothing else, it never rewrites the clause's own line, and it does not step on
a lock of another language of the same clause.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps. Every project lives in a temporary folder.
"""
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import cli, hook                 # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
AGAIN = 'run it again'
TEST = 'greet/test:hello'
OWN = ['- **hello** - says hello.', '  expect: ok', '- **bye** - looks right.', '  manual: look']


def hello(language, word='Hi', more='', head=''):
    """The code of greet/hello in one language, `more` inside its region and `head` before it."""
    if language == 'py':
        return f'{head}# @clause greet/hello\nHELLO = "{word}"\n{more}# @clause end\n'
    return f'{head}// @clause greet/hello\nexport const HELLO = "{word}";\n{more}// @clause end\n'


def test_code(language, more=False):
    """The test code of greet/hello in one language; `more` adds a second test, which is a change to the code."""
    if language == 'py':
        return ('# @clause test greet/hello\ndef test_hello():\n    assert HELLO\n'
                + ('def test_again():\n    assert HELLO\n' if more else '') + '# @clause end\n')
    return ('// @clause test greet/hello\ntest("hello", () => expect(HELLO));\n'
            + ('test("again", () => expect(HELLO));\n' if more else '') + '// @clause end\n')


class Locked(targeted.Targeted):
    """greet/hello with code in Python and TypeScript, greet/bye with code in Python only, all locked (bye's TypeScript is left for later)."""

    def setUp(self):
        super().setUp()
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        self.lock_all('--allow-behind', 'ts')

    def rebuild(self, language, **kwargs):
        write(self.dir, f'src_{language}/greet.{language}', hello(language, **kwargs))

    def hello_hi_in_py_only(self):
        """The clause says "Hi", Python is rebuilt and locked with the clause, TypeScript is behind."""
        self.change_clause()
        self.rebuild('py')
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'ts')[0], 0)

    def lines(self, key='greet/hello'):
        return {k: v for k, v in self.raw().items() if k.startswith(key + '@')}

    def snapshot(self):
        project = Project(self.dir)
        return lockfile.snapshot(project, Scan(project))


class TestWhatItWrites(Locked):
    def test_it_writes_the_line_of_that_language_and_nothing_else(self):
        self.hello_hi_in_py_only()
        self.rebuild('ts')
        before = self.raw()
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('locked greet/hello@ts in sor/sor-lock.json', out)
        after = self.raw()
        self.assertEqual(sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)), ['greet/hello@ts'])
        self.assertEqual(after['greet/hello@ts']['built'], after['greet/hello']['text'])
        self.assertEqual(self.sor('status')[0], 0)

    def test_the_other_language_may_have_moved_on_and_is_left_as_the_lock_had_it(self):
        self.hello_hi_in_py_only()
        self.rebuild('py', more='EXTRA = 1\n')                              # py moves on and nobody locks it
        self.rebuild('ts')
        py_line = self.lines()['greet/hello@py']
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.lines()['greet/hello@py'], py_line)
        self.assertEqual([f['status'] for f in self.findings()], ['drift'])    # py's change is still the drift it was

    def test_a_second_run_has_nothing_to_do_and_writes_nothing(self):
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to lock for greet/hello@py', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_it_locks_the_first_code_of_a_language_the_clause_was_locked_without(self):
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        self.assertEqual([(f['status'], f['key'], f['detail']) for f in self.findings()], [('behind', 'greet/bye', 'ts (first code)')])   # not drift
        code, out, _ = self.sor('lock', 'greet/bye@ts')
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(self.lines('greet/bye')), ['greet/bye@py', 'greet/bye@ts'])
        self.assertEqual(self.lines('greet/bye')['greet/bye@ts']['built'], self.raw()['greet/bye']['text'])
        self.assertEqual(self.findings(), [])

    def test_a_clause_locked_without_any_code_gets_its_first_line(self):
        flows.replace_in(self.spec_file, '- **bye** - The farewell is "Bye".', '- **bye** - The farewell is "Bye".\n- **extra** - The extra is "X".')
        self.assertEqual(self.sor('lock', '--all', '--allow-behind', 'ts')[0], 0)
        write(self.dir, 'src_ts/extra.ts', '// @clause greet/extra\nexport const EXTRA = "X";\n// @clause end\n')
        code, out, _ = self.sor('lock', 'greet/extra@ts')
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(self.lines('greet/extra')), ['greet/extra@ts'])
        self.assertEqual(self.findings(), [])


class TestWhatItRefuses(Locked):
    def test_a_clause_that_changed_is_locked_first(self):
        self.change_clause()
        self.rebuild('py')
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('changed  greet/hello@py  greet/hello is not locked as it reads now', out)
        self.assertIn('sor lock greet/hello', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_clause_never_locked_is_locked_first(self):
        flows.replace_in(self.spec_file, '- **bye** - The farewell is "Bye".', '- **bye** - The farewell is "Bye".\n- **extra** - The extra is "X".')
        write(self.dir, 'src_py/extra.py', '# @clause greet/extra\nEXTRA = "X"\n# @clause end\n')
        code, out, _ = self.sor('lock', 'greet/extra@py')
        self.assertEqual(code, 2, out)
        self.assertIn('greet/extra is not locked as it reads now', out)

    def test_a_clause_locked_before_the_project_said_its_targets_is_locked_first(self):
        self.build(targets=None)
        self.lock_all()                                                     # one joined hash of the code of each clause
        root = os.path.join(self.spec, 'SPECOFRECORD.md')
        write(self.dir, 'sor/SPECOFRECORD.md', read(root).replace('Why: A project the tests use.', 'Why: A project the tests use.\nTargets: py, ts', 1))
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('greet/hello is not locked as it reads now', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_language_with_no_code_for_the_clause_is_refused_and_says_to_write_it(self):
        code, out, _ = self.sor('lock', 'greet/bye@ts')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/bye@ts  greet/bye has no code in ts', out)

    def test_an_id_that_names_no_language_of_the_clause_says_why(self):
        for ident, why in (('greet/bye@fr', 'fr is not a language of greet/bye (it has py, ts)'),
                           ('greet/nope@ts', 'greet/nope is no clause'),
                           ('greet@ts', 'greet is no clause')):
            with self.subTest(ident):
                code, out, _ = self.sor('lock', ident)
                self.assertEqual(code, 2, out)
                self.assertIn(why, out)

    def test_changed_code_with_no_change_to_the_clause_is_drift(self):
        self.rebuild('py', word='Howdy')
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('drift  greet/hello@py', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_code_that_is_behind_and_has_not_changed_needs_the_word_of_the_user(self):
        self.hello_hi_in_py_only()
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 2, out)
        self.assertIn('behind  greet/hello@ts', out)
        self.assertIn('--already-fits ts', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_the_options_for_whole_clauses_are_not_for_one_language(self):
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--allow-behind', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('leaves out every other language by itself', out)
        code, out, _ = self.sor('lock', 'greet/hello', 'greet/bye@py', '--already-fits', 'ts')
        self.assertEqual(code, 2, out)
        self.assertIn('two commands', out)

    def test_a_language_the_project_does_not_have_is_refused_by_the_flag(self):
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--already-fits', 'zz')
        self.assertEqual(code, 2, out)
        self.assertIn('names zz, which is no target', out)

    def test_in_a_project_without_targets_an_id_with_an_at_sign_names_no_language(self):
        self.build(targets=None)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('keeps no code per language', out)


class TestAlreadyFits(Locked):
    def test_it_confirms_the_language_without_a_code_change_and_records_that(self):
        self.hello_hi_in_py_only()
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--already-fits', 'ts')
        self.assertEqual(code, 0, out)
        self.assertIn('confirmed to fit the clause, not rebuilt: greet/hello in ts', out)
        line = self.lines()['greet/hello@ts']
        self.assertEqual((line['fits'], line['built']), (True, self.raw()['greet/hello']['text']))
        self.assertTrue(flows.lock_bytes(self.dir).startswith(b'{\n"*format": 3,\n'))
        self.assertEqual(self.findings(), [])

    def test_it_is_refused_when_the_language_is_not_behind(self):
        code, out, _ = self.sor('lock', 'greet/hello@py', '--already-fits', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('nothing to confirm', out)

    def test_it_is_refused_for_a_language_other_than_the_one_being_locked(self):
        self.hello_hi_in_py_only()
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--already-fits', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('--already-fits ts', out)         # the way out names the language that is behind


class Tested(Locked):
    """greet/hello has test code in Python and TypeScript, and needs a result from the project's own framework for each."""

    def setUp(self):
        super().setUp()
        self.build(tests=OWN)
        self.rebuild('py', word='Hello')
        self.rebuild('ts', word='Hello')
        write(self.dir, 'src_py/test_greet.py', test_code('py'))
        write(self.dir, 'src_ts/greet.test.ts', test_code('ts'))
        self.lock_with({f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'}, '--allow-behind', 'ts')

    def lock_with(self, given, *args):
        path = write(self.dir, 'results.json', json.dumps(given))
        code, out, _ = self.sor('lock', '--all', '--results', path, *args)
        self.assertEqual(code, 0, out)

    def results(self, **given):
        return write(self.dir, 'results.json', json.dumps(given))

    def line_of(self, language):
        return self.lines('greet/test:hello')[f'{TEST}@{language}']

    def clause_changed_and_both_languages_rebuilt(self):
        """hello says "Hi" and is locked with both languages behind, then both are rebuilt."""
        self.change_clause()
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')[0], 0)    # nothing is rebuilt: no result to give yet
        self.rebuild('py')
        self.rebuild('ts')


class TestTestsPerLanguage(Tested):
    def test_the_line_of_the_test_in_that_language_is_locked_with_a_result_of_its_own(self):
        self.clause_changed_and_both_languages_rebuilt()
        py_line = self.line_of('py')
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', self.results(**{f'{TEST}@ts': 'pass'}))
        self.assertEqual(code, 0, out)
        self.assertIn(f'locked greet/hello@ts, {TEST}@ts', out)
        self.assertEqual(self.line_of('ts')['result'], 'pass')
        self.assertEqual(self.line_of('ts')['built'], self.raw()[TEST]['text'])
        self.assertEqual(self.line_of('py'), py_line)

    def test_a_language_without_a_result_for_its_test_is_named_and_nothing_is_written(self):
        self.clause_changed_and_both_languages_rebuilt()
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 2, out)
        self.assertIn(f'1 test(s) did not pass (0 failed, 1 not run): {TEST}@ts', out)
        self.assertIn(f'"{TEST}@ts": "pass"', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_failed_test_is_named_and_allow_incomplete_records_it_as_failed_for_that_language_only(self):
        self.clause_changed_and_both_languages_rebuilt()
        failed = self.results(**{f'{TEST}@ts': 'fail'})
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', failed)
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@ts (failed)', out)
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', failed, '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertIn(f'recorded as not passed: {TEST}@ts', out)
        self.assertEqual((self.line_of('py')['result'], self.line_of('ts')['result']), ('none', 'fail'))   # py waits for its own lock
        self.assertEqual(lockfile.read(Project(self.dir))[TEST]['result'], 'fail')

    def test_a_test_that_did_not_pass_is_asked_for_again_whatever_the_code_does(self):
        self.clause_changed_and_both_languages_rebuilt()
        self.assertEqual(self.sor('lock', 'greet/hello@ts', '--results', self.results(**{f'{TEST}@ts': 'fail'}), '--allow-incomplete')[0], 0)
        code, out, _ = self.sor('lock', 'greet/hello@ts')                  # the code is what the lock has, but its test failed
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST}@ts', out)
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', self.results(**{f'{TEST}@ts': 'pass'}))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.line_of('ts')['result'], 'pass')

    def test_the_order_in_the_reference_file_works_without_a_made_up_result(self):
        self.change_clause()
        self.rebuild('py')
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-behind', 'ts', '--results', self.results(**{f'{TEST}@py': 'pass'}))
        self.assertEqual(code, 0, out)                                      # the TypeScript test waits: its code is not rebuilt yet
        self.assertIn(f'{TEST}@ts', self.sor('status')[1])                  # and `sor status` keeps listing it
        self.rebuild('ts')
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 2, out)                                      # the lock of the language asks for it
        self.assertIn(f'{TEST}@ts', out)
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', self.results(**{f'{TEST}@ts': 'pass'}))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.findings(), [])
        self.assertNotIn('tests (', self.sor('status')[1])

    def test_allow_behind_leaves_no_result_for_a_language_that_is_not_behind(self):
        write(self.dir, 'src_ts/greet.test.ts', test_code('ts', more=True))
        self.change_clause()
        self.rebuild('py')
        self.rebuild('ts')
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-behind', 'ts', '--results', self.results(**{f'{TEST}@py': 'pass'}))
        self.assertEqual(code, 2, out)                                      # ts is rebuilt, so its test has to pass like any other
        self.assertIn(f'{TEST}@ts', out)

    def test_a_plain_result_is_ambiguous_with_test_code_in_two_languages(self):
        self.clause_changed_and_both_languages_rebuilt()
        code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', self.results(**{TEST: 'pass'}))
        self.assertEqual(code, 2, out)
        self.assertIn(f'{TEST} has test code in py, ts: give a result for each', out)

    def test_the_result_of_the_other_language_is_not_asked_for(self):
        self.clause_changed_and_both_languages_rebuilt()
        ts_line = self.line_of('ts')
        code, out, _ = self.sor('lock', 'greet/hello@py', '--results', self.results(**{f'{TEST}@py': 'pass'}))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.line_of('ts'), ts_line)

    def test_a_test_that_stands_as_it_was_needs_no_result_while_the_code_it_proves_is_not_locked(self):
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to lock', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)


class TestSharedCode(Locked):
    """In Python a first region is the code of greet/hello and greet/bye, and a second is greet/hello's alone."""
    SHARED = '# @clause greet/hello greet/bye\nBYE = "{}"\n# @clause end\n# @clause greet/hello\nHELLO = "{}"\n# @clause end\n'

    def setUp(self):
        super().setUp()
        self.build()                                               # a fresh spec and lock: the shared region is there from the start
        os.remove(os.path.join(self.dir, 'src_py/bye.py'))
        write(self.dir, 'src_py/greet.py', self.SHARED.format('Bye', 'Hello'))
        self.lock_all('--allow-behind', 'ts')
        self.change_clause()
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')[0], 0)    # hello says "Hi"; no language is rebuilt yet

    def test_two_clauses_that_share_code_in_a_language_are_locked_together(self):
        write(self.dir, 'src_py/greet.py', self.SHARED.format('Bye now', 'Hi'))
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('is also the code of greet/bye', out)
        self.assertIn('sor lock greet/hello@py greet/bye@py', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_naming_both_locks_them_both(self):
        write(self.dir, 'src_py/greet.py', self.SHARED.format('Bye now', 'Hi'))
        code, out, _ = self.sor('lock', 'greet/hello@py', 'greet/bye@py')
        self.assertEqual(code, 0, out)
        self.assertIn('locked greet/bye@py, greet/hello@py', out)
        now = self.snapshot()
        for clause in ('greet/bye', 'greet/hello'):
            self.assertEqual(self.lines(clause)[f'{clause}@py']['code'], now[clause]['targets']['py']['code'])

    def test_a_clause_that_shares_code_but_has_nothing_new_there_is_left_alone(self):
        write(self.dir, 'src_py/greet.py', self.SHARED.format('Bye', 'Hi'))
        before = self.lines('greet/bye')
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.lines('greet/bye'), before)


class TestGlue(Locked):
    def test_the_glue_of_that_languages_files_goes_with_the_lock_and_the_other_language_keeps_its_own(self):
        write(self.dir, 'src_py/greet.py', hello('py', word='Hello', head='# @clause glue\nimport os\n# @clause end\n'))
        write(self.dir, 'src_ts/greet.ts', hello('ts', word='Hello', head='// @clause glue\nimport "x";\n// @clause end\n'))
        self.assertEqual({f['key'] for f in self.findings('new')}, {'glue:src_py/greet.py', 'glue:src_ts/greet.ts'})
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertIn('glue of src_py/greet.py', out)
        self.assertEqual({f['key'] for f in self.findings('new')}, {'glue:src_ts/greet.ts'})
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to lock for greet/hello@py', out)             # the glue it took is locked, and nothing else is new

    def test_the_glue_of_a_file_that_holds_other_clauses_only_is_left_to_them(self):
        write(self.dir, 'src_py/greet.py', hello('py', word='Hello', head='# @clause glue\nimport os\n# @clause end\n'))
        write(self.dir, 'src_py/bye.py', '# @clause glue\nimport sys\n# @clause end\n# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        self.assertEqual({f['key'] for f in self.findings('new')}, {'glue:src_py/greet.py', 'glue:src_py/bye.py'})
        self.assertEqual(self.sor('lock', 'greet/hello@py')[0], 0)
        self.assertEqual({f['key'] for f in self.findings('new')}, {'glue:src_py/bye.py'})


class TestProblemsInTheFiles(Locked):
    def setUp(self):
        super().setUp()
        self.hello_hi_in_py_only()
        self.rebuild('ts')

    def test_a_problem_in_a_file_of_the_other_language_that_holds_the_clause_does_not_stop_this_lock(self):
        write(self.dir, 'src_py/greet.py', hello('py') + 'UNMARKED = 1\n')
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('1 problem(s) in other files do not block this lock', out)

    def test_a_problem_in_a_file_of_this_language_that_holds_the_clause_does(self):
        write(self.dir, 'src_ts/greet.ts', hello('ts') + 'export const UNMARKED = 1;\n')
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 2, out)
        self.assertIn('unmarked  src_ts/greet.ts', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_problem_in_the_spec_file_of_the_clause_does(self):
        flows.replace_in(self.spec_file, 'Says hello.', 'Says hello. <fill in: more>')
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 2, out)
        self.assertIn('placeholder', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_problem_in_another_item_of_the_spec_file_does_not(self):
        flows.replace_in(self.spec_file, '- **bye** - The farewell is "Bye".', '- **bye** - The farewell is "Bye". {nowhere}')
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('1 problem(s) in other items of these files do not block this lock', out)


class TestClaims(Locked):
    def setUp(self):
        super().setUp()
        self.hello_hi_in_py_only()
        self.rebuild('ts')

    def lock_as(self, agent, session, *args):
        return self.sor('lock', '--as', agent, *args, CLAUDE_CODE_SESSION_ID=session)

    def test_a_claim_of_the_whole_clause_by_someone_else_is_in_the_way(self):
        self.assertTrue(self.claim(['greet/hello'], 'alice', session='A')[0])
        code, out, _ = self.lock_as('bob', 'B', 'greet/hello@ts')
        self.assertEqual(code, 2, out)
        self.assertIn('claimed  alice', out)
        self.assertIn('wait for them, or ask them to release', out)

    def test_a_claim_of_the_same_language_by_someone_else_is_in_the_way(self):
        self.assertTrue(self.claim(['greet/hello@ts'], 'alice', session='A')[0])
        code, out, _ = self.lock_as('bob', 'B', 'greet/hello@ts')
        self.assertEqual(code, 2, out)
        self.assertIn('claimed  alice', out)

    def test_a_claim_of_another_language_is_not(self):
        self.assertTrue(self.claim(['greet/hello@py'], 'alice', session='A')[0])
        code, out, _ = self.lock_as('bob', 'B', 'greet/hello@ts')
        self.assertEqual(code, 0, out)

    def test_your_own_claim_is_not_in_the_way_and_a_lock_with_no_ids_locks_what_you_claimed(self):
        self.assertTrue(self.claim(['greet/hello@ts'], 'bob', session='B')[0])
        code, out, _ = self.lock_as('bob', 'B')
        self.assertEqual(code, 0, out)
        self.assertIn('locking what you claimed: greet/hello@ts', out)
        self.assertIn('locked greet/hello@ts', out)


class TestInTheSameCommandAsOtherIds(Locked):
    def test_a_whole_clause_and_the_language_of_another_are_two_locks_in_one(self):
        self.hello_hi_in_py_only()
        self.rebuild('ts')
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        code, out, _ = self.sor('lock', 'greet/hello', 'greet/bye@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('locked greet/bye@ts', out)
        self.assertEqual(sorted(self.lines('greet/bye')), ['greet/bye@py', 'greet/bye@ts'])
        self.assertEqual(self.findings(), [])

    def test_a_language_of_a_clause_that_is_locked_whole_in_the_same_command_is_part_of_it(self):
        self.change_clause()
        self.rebuild('py')
        self.rebuild('ts')
        code, out, _ = self.sor('lock', 'greet/hello', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('greet/hello@ts is locked with the whole clause, not on its own', out)
        self.assertEqual(self.findings(), [])

    def test_two_clauses_in_one_language(self):
        self.hello_hi_in_py_only()
        self.rebuild('ts')
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        code, out, _ = self.sor('lock', 'greet/bye@ts', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('locked greet/bye@ts, greet/hello@ts', out)
        self.assertEqual(self.findings(), [])


class TestWhatIsLeftInTheOtherLanguages(Locked):
    def test_a_language_that_is_behind_is_said_with_the_way_to_finish_it(self):
        self.change_clause()
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')[0], 0)
        self.rebuild('py')
        code, out, _ = self.sor('lock', 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertIn('greet/hello is not finished in every language: ts is behind the clause', out)
        self.assertIn('sor claim greet/hello@ts', out)
        self.assertIn('sor lock greet/hello@ts', out)

    def test_a_language_with_no_code_yet_is_said_too(self):
        flows.replace_in(self.spec_file, 'The farewell is "Bye".', 'The farewell is "Bye now".')
        self.assertEqual(self.sor('lock', 'greet/bye', '--allow-behind', 'py,ts')[0], 0)
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye now"\n# @clause end\n')
        code, out, _ = self.sor('lock', 'greet/bye@py')
        self.assertEqual(code, 0, out)
        self.assertIn('greet/bye is not finished in every language: ts has no code yet', out)

    def test_nothing_is_said_when_every_language_is_done(self):
        self.hello_hi_in_py_only()
        self.rebuild('ts')
        code, out, _ = self.sor('lock', 'greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertNotIn('not finished', out)


class TestReleasingALanguage(Locked):
    def setUp(self):
        super().setUp()
        self.hello_hi_in_py_only()
        self.rebuild('ts')

    def release(self, *ids):
        return self.sor('release', '--as', 'bob', *ids, CLAUDE_CODE_SESSION_ID='B')

    def test_code_that_is_not_locked_is_said_when_the_language_is_released(self):
        self.assertTrue(self.claim(['greet/hello@ts'], 'bob', session='B')[0])
        code, out, _ = self.release('greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('released greet/hello@ts', out)
        self.assertIn('note: greet/hello@ts has code that is not locked yet: lock it (sor lock greet/hello@ts)', out)

    def test_a_language_with_nothing_open_is_released_without_a_word(self):
        self.assertTrue(self.claim(['greet/hello@py'], 'bob', session='B')[0])
        code, out, _ = self.release('greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertNotIn('note:', out)

    def test_a_language_that_is_behind_is_said_even_when_its_code_did_not_change(self):
        write(self.dir, 'src_ts/greet.ts', self.TS)                      # back to the code that was accepted for the old text
        self.assertTrue(self.claim(['greet/hello@ts'], 'bob', session='B')[0])
        code, out, _ = self.release('greet/hello@ts')
        self.assertIn('greet/hello@ts has code that is not locked yet', out)

    def test_a_whole_clause_and_a_language_in_one_release(self):
        self.assertTrue(self.claim(['greet/bye', 'greet/hello@ts'], 'bob', session='B')[0])
        code, out, _ = self.release('--all')
        self.assertEqual(code, 0, out)
        self.assertIn('note: greet/hello@ts has code that is not locked yet', out)
        self.assertNotIn('greet/bye has', out)

    def test_releasing_whole_clauses_does_not_read_the_project(self):
        self.assertTrue(self.claim(['greet/hello'], 'bob', session='B')[0])
        with mock.patch.object(cli, 'Scan', side_effect=AssertionError('the project was scanned')):
            code, out, _ = self.release('greet/hello')
        self.assertEqual(code, 0, out)

    def test_a_lock_this_copy_cannot_read_is_no_reason_to_refuse_a_release(self):
        self.assertTrue(self.claim(['greet/hello@ts'], 'bob', session='B')[0])
        lock = os.path.join(self.spec, 'sor-lock.json')
        write(self.dir, 'sor/sor-lock.json', re.sub(r'"\*format": \d+', '"*format": 99', read(lock), count=1))
        code, out, _ = self.release('greet/hello@ts')
        self.assertEqual(code, 0, out)
        self.assertIn('released greet/hello@ts', out)
        self.assertNotIn('note:', out)

    def test_a_whole_clause_is_released_without_that_note(self):
        self.assertTrue(self.claim(['greet/hello'], 'bob', session='B')[0])
        code, out, _ = self.release('greet/hello')
        self.assertEqual(code, 0, out)
        self.assertNotIn('note:', out)

    def test_two_languages_are_named_together(self):
        self.rebuild('py', more='EXTRA = 1\n')                              # py moved on after it was locked
        self.assertTrue(self.claim(['greet/hello@py', 'greet/hello@ts'], 'bob', session='B')[0])
        code, out, _ = self.release('--all')
        self.assertIn('greet/hello@py, greet/hello@ts have code that is not locked yet: lock them (sor lock greet/hello@py greet/hello@ts)', out)


class TestTheEditHookAllowsTheCodeThatIsToCome(Locked):
    """The edit hook lets code change only for a clause that has a change pending. The first code of a language the clause was locked without,
    and the rebuilding of a language that is behind, are such changes."""

    def write_tool(self, path, text):
        return hook.pre_edit({'tool_name': 'Write', 'tool_input': {'file_path': path, 'content': text}})

    def test_the_first_code_of_a_language_is_let_through(self):
        path = os.path.join(self.dir, 'src_ts', 'bye.ts')
        self.assertIsNone(self.write_tool(path, '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n'))

    def test_changed_code_of_a_language_that_was_built_is_not_while_the_clause_stands(self):
        path = os.path.join(self.dir, 'src_py', 'bye.py')
        said = flows.reason(self.write_tool(path, '# @clause greet/bye\nBYE = "Goodbye"\n# @clause end\n'))
        self.assertIn('Clauses come first', said)

    def test_rebuilding_a_language_that_is_behind_is_let_through(self):
        self.hello_hi_in_py_only()
        path = os.path.join(self.dir, 'src_ts', 'greet.ts')
        self.assertIsNone(self.write_tool(path, hello('ts')))


class LocksWhile:
    """A lock of one language runs and, after it has worked out what to write, `meanwhile` happens."""

    def lock_while(self, meanwhile, *args):
        original = lockfile.accept_language

        def accept(*a, **k):
            result = original(*a, **k)
            with mock.patch.object(lockfile, 'accept_language', original):   # what happens meanwhile may be a lock of its own
                meanwhile()
            return result

        with mock.patch.object(lockfile, 'accept_language', accept):
            return self.sor('lock', *args)


class Meanwhile(LocksWhile, Locked):
    """hello says "Hi" and is locked with both languages behind, then both are rebuilt."""

    def setUp(self):
        super().setUp()
        self.change_clause()
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')[0], 0)
        self.rebuild('py')
        self.rebuild('ts')

    def append_to(self, language):
        return lambda: self.rebuild(language, more='MORE = 1\n' if language == 'py' else 'export const MORE = 1;\n')


class TestAnotherLanguageLandsMeanwhile(Meanwhile):
    def test_both_lines_survive_when_the_other_language_is_locked_while_this_one_is_worked_out(self):
        def ts_lands():
            self.assertEqual(self.sor('lock', 'greet/hello@ts')[0], 0)
        code, out, _ = self.lock_while(ts_lands, 'greet/hello@py')
        self.assertEqual(code, 0, out)
        text = self.raw()['greet/hello']['text']
        lines = self.lines()
        self.assertEqual((lines['greet/hello@py']['built'], lines['greet/hello@ts']['built']), (text, text))
        now = self.snapshot()['greet/hello']['targets']
        self.assertEqual((lines['greet/hello@py']['code'], lines['greet/hello@ts']['code']), (now['py']['code'], now['ts']['code']))
        self.assertEqual(self.findings(), [])

    def test_the_other_languages_file_changing_meanwhile_is_not_this_locks_business(self):
        ts_line = self.lines()['greet/hello@ts']
        code, out, _ = self.lock_while(self.append_to('ts'), 'greet/hello@py')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.lines()['greet/hello@ts'], ts_line)                      # ts is as it was, still to lock


class TestATestResultLandsMeanwhile(LocksWhile, Tested):
    def test_the_result_the_other_language_gives_meanwhile_is_not_a_change_to_what_this_lock_read(self):
        self.clause_changed_and_both_languages_rebuilt()

        def ts_lands_failed():
            code, out, _ = self.sor('lock', 'greet/hello@ts', '--results', self.results(**{f'{TEST}@ts': 'fail'}), '--allow-incomplete')
            self.assertEqual(code, 0, out)
        code, out, _ = self.lock_while(ts_lands_failed, 'greet/hello@py', '--results', self.results(**{f'{TEST}@py': 'pass'}))
        self.assertEqual(code, 0, out)
        self.assertEqual((self.line_of('py')['result'], self.line_of('ts')['result']), ('pass', 'fail'))


class TestThisLanguageChangesMeanwhile(Meanwhile):
    def test_a_file_of_this_language_changing_stops_the_lock(self):
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.lock_while(self.append_to('py'), 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('src_py/greet.py changed while this one was being worked out', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_the_clause_being_locked_meanwhile_stops_the_lock(self):
        def clause_locked():
            project = Project(self.dir)
            entries = lockfile.read(project)
            entries['greet/hello'] = dict(entries['greet/hello'], text='another')
            lockfile.write(project, entries)
        code, out, _ = self.lock_while(clause_locked, 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('the lock changed while this one was being worked out', out)
        self.assertIn(AGAIN, out)
        self.assertEqual(lockfile.read(Project(self.dir))['greet/hello']['text'], 'another')

    def test_the_same_line_being_locked_meanwhile_stops_the_lock(self):
        def same_line_locked():
            project = Project(self.dir)
            entries = lockfile.read(project)
            entries['greet/hello']['targets']['py'] = dict(entries['greet/hello']['targets']['py'], code='another')
            lockfile.write(project, entries)
        code, out, _ = self.lock_while(same_line_locked, 'greet/hello@py')
        self.assertEqual(code, 2, out)
        self.assertIn('the lock changed while this one was being worked out', out)
        self.assertIn(AGAIN, out)


if __name__ == '__main__':
    unittest.main()
