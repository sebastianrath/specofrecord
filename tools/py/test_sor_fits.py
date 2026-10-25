"""Tests for `sor lock --already-fits` (SPEC §9, §11): a language whose code was checked against a changed clause and needs no change is
cleared without a code edit, the lock says so on the language's line (lock format 3), and `sor status` keeps a note.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

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
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
NOTE = 'note: confirmed to fit the clause and not rebuilt (`--already-fits`)'


class TestConfirmingALanguage(targeted.Targeted):
    def setUp(self):
        super().setUp()
        self.lock_all()
        self.change_clause()                                                # the clause changes, Python is rebuilt, TypeScript is not
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))

    def line(self, target='ts', key='greet/hello'):
        return self.raw()[f'{key}@{target}']

    def test_it_clears_the_language_with_no_code_edit_and_the_lock_says_so_on_its_line(self):
        code, out, _ = self.sor('lock', 'greet/hello', '--already-fits', 'ts')
        self.assertEqual(code, 0, out)
        self.assertIn('confirmed to fit the clause, not rebuilt: greet/hello in ts', out)
        self.assertTrue(flows.lock_bytes(self.dir).startswith(flows.LOCK_HEAD))
        self.assertIn(b'"kind": "code"', flows.lock_bytes(self.dir))      # lines per target
        text = self.raw()['greet/hello']['text']
        ts = self.line('ts')
        self.assertEqual((ts['fits'], ts['built']), (True, text))
        self.assertEqual(ts['code'], lockfile.read(Project(self.dir))['greet/hello']['targets']['ts']['code'])   # its code did not change
        self.assertNotIn('fits', self.line('py'))
        self.assertEqual(self.findings(), [])

    def test_status_is_clean_and_keeps_a_note_that_is_neither_pending_nor_in_the_json(self):
        self.assertEqual(self.sor('lock', 'greet/hello', '--already-fits', 'ts')[0], 0)
        code, out, _ = self.sor('status')
        self.assertEqual(code, 0, out)
        self.assertIn('clauses, code and lock agree', out)
        self.assertIn(f'{NOTE}: greet/hello in ts (not a pending change)', out)
        code, js, _ = self.sor('status', '--json')
        self.assertEqual(sorted(json.loads(js)), ['claims', 'findings', 'locked', 'problems', 'tests_deferred', 'tests_not_passed', 'tests_pending'])

    def test_both_languages_can_be_confirmed_after_a_change_that_concerns_no_code(self):
        write(self.dir, 'src_py/greet.py', self.PY)                         # Python as it was
        code, out, _ = self.sor('lock', 'greet/hello', '--already-fits', 'py,ts')
        self.assertEqual(code, 0, out)
        self.assertEqual((self.line('py')['fits'], self.line('ts')['fits']), (True, True))

    def test_without_the_flag_the_lock_still_refuses(self):
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('behind  greet/hello  its code in ts', out)

    def test_the_flag_and_allow_behind_cannot_both_name_a_language(self):
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/hello', '--already-fits', 'ts', '--allow-behind', 'ts')
        self.assertEqual(code, 2, out)
        self.assertIn('ts is named by --allow-behind and by --already-fits', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_it_refuses_when_nothing_is_behind_there_and_for_a_name_that_is_no_target(self):
        code, out, _ = self.sor('lock', 'greet/hello', '--already-fits', 'py')          # Python was rebuilt
        self.assertEqual(code, 2, out)
        self.assertIn('nothing to confirm', out)
        code, out, _ = self.sor('lock', 'greet/hello', '--already-fits', 'rust')
        self.assertEqual(code, 2, out)
        self.assertIn('rust, which is no target', out)

    def test_it_does_not_allow_a_language_with_no_code(self):
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        code, out, _ = self.sor('lock', 'greet/bye', '--already-fits', 'ts')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/bye', out)                           # that is --allow-behind's job

    def test_a_project_that_keeps_no_code_per_language_has_nothing_to_confirm(self):
        self.build(targets=None)
        code, out, _ = self.sor('lock', '--all', '--already-fits', 'ts')
        self.assertEqual(code, 2, out)
        self.assertIn('needs a project that says its targets', out)

    def test_a_lock_of_everything_with_nothing_changed_keeps_the_confirmation(self):
        # an unscoped lock works every line out again from the files, and carries what a line says besides its code
        self.assertEqual(self.sor('lock', 'greet/hello', '--already-fits', 'ts')[0], 0)
        self.lock_all()
        self.assertTrue(self.line('ts')['fits'])
        self.assertEqual(self.line('ts')['built'], self.raw()['greet/hello']['text'])

    def test_a_confirmation_whose_text_is_not_the_clauses_is_not_named(self):
        # a lock mended by hand after a merge of two branches can hold a line from one next to a clause from the other
        self.assertEqual(self.sor('lock', 'greet/hello', '--already-fits', 'ts')[0], 0)
        lock = lockfile.read(Project(self.dir))
        self.assertEqual(lockfile.confirmed_fits(Project(self.dir), lock), [('greet/hello', ['ts'])])
        lock['greet/hello']['text'] = 'another-text'
        self.assertEqual(lockfile.confirmed_fits(Project(self.dir), lock), [])

    def test_a_lock_of_another_clause_keeps_the_confirmation_and_stays_format_3(self):
        self.assertEqual(self.sor('lock', 'greet/hello', '--already-fits', 'ts')[0], 0)
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        self.assertEqual(self.sor('lock', 'greet/bye')[0], 0)
        self.assertTrue(self.line('ts')['fits'])
        self.assertTrue(flows.lock_bytes(self.dir).startswith(flows.LOCK_HEAD))
        self.assertIn(b'"kind": "code"', flows.lock_bytes(self.dir))      # lines per target


class TestWhenTheConfirmationNoLongerHolds(targeted.Targeted):
    def setUp(self):
        super().setUp()
        self.lock_all()
        self.change_clause()
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.assertEqual(self.sor('lock', 'greet/hello', '--already-fits', 'ts')[0], 0)

    def test_rebuilding_the_language_after_the_next_change_drops_it_and_the_lock_goes_back_to_format_2(self):
        flows.replace_in(self.spec_file, 'The greeting is "Hi".', 'The greeting is "Howdy".')
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Howdy'))
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Howdy'))
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)
        self.assertNotIn('fits', self.raw()['greet/hello@ts'])
        self.assertTrue(flows.lock_bytes(self.dir).startswith(flows.LOCK_HEAD))
        self.assertIn(b'"kind": "code"', flows.lock_bytes(self.dir))      # lines per target
        self.assertNotIn('note: confirmed', self.sor('status')[1])

    def test_a_change_to_the_clause_makes_the_language_behind_again_and_the_old_confirmation_says_nothing(self):
        flows.replace_in(self.spec_file, 'The greeting is "Hi".', 'The greeting is "Howdy".')
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Howdy'))
        self.assertEqual([f['status'] for f in self.findings()], ['changed'])
        self.assertNotIn('note: confirmed', self.sor('status')[1])
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('behind  greet/hello  its code in ts', out)
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'ts')[0], 0)
        self.assertNotIn('fits', self.raw()['greet/hello@ts'])             # confirmed for the text before; it is behind, not confirmed
        self.assertNotIn('note: confirmed', self.sor('status')[1])


class TestTheFormatFollowsTheLines(targeted.Targeted):
    def test_a_targeted_project_nobody_confirmed_anything_in_stays_format_2(self):
        self.lock_all()
        self.assertTrue(flows.lock_bytes(self.dir).startswith(flows.LOCK_HEAD))
        self.assertIn(b'"kind": "code"', flows.lock_bytes(self.dir))      # lines per target

    def test_an_older_tool_refuses_a_lock_with_a_confirmation_instead_of_dropping_it(self):
        self.lock_all()
        self.change_clause()
        self.assertEqual(self.sor('lock', 'greet/hello', '--already-fits', 'py,ts')[0], 0)
        text = read(os.path.join(self.spec, 'sor-lock.json'))
        self.assertIn('"fits": true', text)
        from unittest import mock
        with mock.patch.object(lockfile, 'FORMAT', 2):                     # a tool that knows formats 1 and 2
            with self.assertRaises(lockfile.LockFormatError):
                lockfile.read(Project(self.dir))


if __name__ == '__main__':
    unittest.main()
