"""Tests for the claim of one language of a clause, `greet/hello@py` (SPEC §16): what it holds, what it conflicts with, what the edit hook
refuses because of it, and how it is released.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import claims, hook              # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read


class Claimed(targeted.Targeted):
    """greet/hello with code in Python and TypeScript, greet/bye with code in Python only, locked."""

    def setUp(self):
        super().setUp()
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        self.lock_all('--allow-behind', 'ts')

    def take(self, *ids, agent, session):
        ok, res = self.claim(list(ids), agent, session=session)
        return ok

    def held_by(self, agent):
        return [c for c in self.claims_file() if c['agent'] == agent]


class TestWhatALanguageClaimConflictsWith(Claimed):
    def test_a_clause_as_a_whole_conflicts_with_a_whole_claim(self):
        self.assertTrue(self.take('greet/hello', agent='a', session='A'))
        self.assertFalse(self.take('greet/hello', agent='b', session='B'))

    def test_a_clause_as_a_whole_conflicts_with_one_of_its_languages_and_the_other_way_round(self):
        self.assertTrue(self.take('greet/hello', agent='a', session='A'))
        self.assertFalse(self.take('greet/hello@py', agent='b', session='B'))
        self.assertFalse(self.take('greet/hello@ts', agent='b', session='B'))
        self.claim_released = self.run_release('a', 'A')
        self.assertTrue(self.take('greet/hello@py', agent='b', session='B'))
        self.assertFalse(self.take('greet/hello', agent='a', session='A'))

    def test_it_conflicts_also_when_the_language_has_no_code_yet(self):
        self.assertTrue(self.take('greet/bye@ts', agent='a', session='A'))           # bye has code in Python only
        self.assertFalse(self.take('greet/bye', agent='b', session='B'))
        self.assertFalse(self.take('greet/bye@ts', agent='b', session='B'))

    def test_two_languages_of_one_clause_do_not_conflict_but_one_language_twice_does(self):
        self.assertTrue(self.take('greet/hello@py', agent='a', session='A'))
        self.assertTrue(self.take('greet/hello@ts', agent='b', session='B'))
        self.assertFalse(self.take('greet/hello@py', agent='c', session='C'))
        self.assertFalse(self.take('greet/hello@ts', agent='c', session='C'))

    def test_a_language_of_another_clause_is_free(self):
        self.assertTrue(self.take('greet/hello@py', agent='a', session='A'))
        self.assertTrue(self.take('greet/bye@py', agent='b', session='B'))

    def test_a_part_holds_the_languages_of_its_clauses(self):
        self.assertTrue(self.take('greet', agent='a', session='A'))
        self.assertFalse(self.take('greet/hello@ts', agent='b', session='B'))

    def run_release(self, agent, session):
        with mock.patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': session}):
            return claims.release(Project(self.dir), [], agent, everything=True)


class TestWhatALanguageClaimHolds(Claimed):
    def test_it_holds_its_line_the_line_of_the_clauses_own_test_and_the_code_of_that_language_only(self):
        self.build(tests=['- **hello** - says hello.', '  manual: look'])
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        self.assertTrue(self.take('greet/hello@py', agent='a', session='A'))
        (c,) = self.held_by('a')
        self.assertEqual(c['keys'], ['greet/hello@py', 'greet/test:hello@py'])
        self.assertEqual(c['pins'], ['greet/hello'])
        self.assertEqual(c['regions'], [['src_py/greet.py', ['greet/hello']]])

    def test_a_clause_as_a_whole_holds_a_line_for_each_language_and_pins_nothing(self):
        self.assertTrue(self.take('greet/hello', agent='a', session='A'))
        (c,) = self.held_by('a')
        self.assertIn('greet/hello@py', c['keys'])
        self.assertIn('greet/hello@ts', c['keys'])
        self.assertNotIn('pins', c)

    def test_the_status_and_a_refusal_show_the_language(self):
        self.take('greet/hello@py', agent='a', session='A')
        self.assertIn('greet/hello@py', self.sor('status')[1])
        ok, res = self.claim(['greet/hello@py'], 'b', session='B')
        self.assertFalse(ok)
        self.assertIn('greet/hello@py', claims.describe(res['holders'][0]))


class TestWhichIdsAreALanguage(Claimed):
    def refused(self, ident):
        code, out, err = self.run_as_a('claim', ident)
        self.assertEqual(code, 2, out + err)
        return err + out

    def run_as_a(self, *args):
        return self.sor(*args, CLAUDE_CODE_SESSION_ID='A')

    def test_a_language_the_clause_does_not_have_is_refused_naming_the_ones_it_has(self):
        self.assertIn('greet/hello@rust: rust is not a language of greet/hello (it has py, ts)', self.refused('greet/hello@rust'))

    def test_a_language_of_something_that_is_no_clause_is_refused(self):
        self.assertIn('greet/nothing@py: greet/nothing is no clause', self.refused('greet/nothing@py'))
        self.assertIn('greet@py: greet is no clause', self.refused('greet@py'))

    def test_a_language_of_a_part_that_limits_its_languages_is_refused(self):
        self.build(part_targets='py')
        write(self.dir, 'src_py/greet.py', self.PY)
        self.assertIn('ts is not a language of greet/hello (it has py)', self.refused('greet/hello@ts'))

    def test_a_project_that_keeps_no_code_per_language_has_only_the_clause(self):
        self.build(targets=None)
        self.assertIn('this project keeps no code per language', self.refused('greet/hello@py'))

    def test_a_claim_of_a_language_takes_all_its_ids_or_none(self):
        self.assertTrue(self.take('greet/hello@py', agent='a', session='A'))
        code, out, _ = self.run_as_a('claim', 'greet/bye', 'greet/hello@py', '--as', 'b')
        self.assertEqual(code, 3, out)
        self.assertEqual(self.held_by('b'), [])


class TestTheEditHookAndALanguageClaim(Claimed):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertTrue(self.take('greet/hello@py', agent='a', session='A'))
        flows.replace_in(self.spec_file, 'The greeting is "Hello".', 'The greeting is "Hi".')   # a person changed the clause: code may follow

    def edit(self, path, old, new, session='B'):
        return hook.pre_edit(dict(flows.edit(path, old, new), session_id=session))

    def said(self, result):
        return flows.reason(result) or ''

    def test_another_session_cannot_edit_the_text_of_the_clause(self):
        result = self.edit(self.spec_file, 'The greeting is "Hi".', 'The greeting is "Hey".')
        self.assertIn('Someone else is working on this', self.said(result))
        self.assertIn('greet/hello@py', self.said(result))

    def test_another_session_cannot_edit_the_code_of_that_language(self):
        result = self.edit(os.path.join(self.dir, 'src_py', 'greet.py'), '"Hello"', '"Hi"')
        self.assertIn('Someone else is working on this', self.said(result))

    def test_another_session_can_edit_the_code_of_the_other_language(self):
        self.assertIsNone(self.edit(os.path.join(self.dir, 'src_ts', 'greet.ts'), '"Hello"', '"Hi"'))

    def test_the_holder_can_edit_the_code_of_its_language(self):
        self.assertIsNone(self.edit(os.path.join(self.dir, 'src_py', 'greet.py'), '"Hello"', '"Hi"', session='A'))

    def test_another_session_can_edit_another_clause(self):
        flows.replace_in(self.spec_file, 'The farewell is "Bye".', 'The farewell is "Goodbye".')
        self.assertIsNone(self.edit(os.path.join(self.dir, 'src_py', 'bye.py'), '"Bye"', '"Goodbye"'))


class TestAnExpiredClaimOfALanguage(Claimed):
    def test_it_is_no_news_once_the_whole_clause_is_claimed_again(self):
        self.take('greet/hello@py', agent='a', session='A')
        self.expire()
        self.assertEqual([c['asked'] for c in claims.lost(Project(self.dir), 'a', [], session='A')], [['greet/hello@py']])
        self.assertEqual(claims.lost(Project(self.dir), 'a', ['greet/hello'], session='A'), [])
        self.take('greet/hello', agent='a', session='A')
        self.assertEqual([c['asked'] for c in self.claims_file()], [['greet/hello']])      # the spent claim of its language went


class TestReleasingALanguage(Claimed):
    def test_a_language_is_released_by_its_id_and_the_others_stay(self):
        self.take('greet/hello@py', agent='a', session='A')
        self.take('greet/hello@ts', agent='a', session='A')
        code, out, _ = self.sor('release', 'greet/hello@py', '--as', 'a', CLAUDE_CODE_SESSION_ID='A')
        self.assertEqual(code, 0, out)
        self.assertEqual([c['asked'] for c in self.claims_file()], [['greet/hello@ts']])

    def test_releasing_the_clause_frees_its_languages_too(self):
        self.take('greet/hello@py', agent='a', session='A')
        code, out, _ = self.sor('release', 'greet/hello', '--as', 'a', CLAUDE_CODE_SESSION_ID='A')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.claims_file(), [])


class TestAProjectWithoutLanguagesIsAsBefore(flows.Flow):
    def test_an_id_with_an_at_in_it_is_just_an_unknown_id(self):
        self.greet_project()
        code, out, err = self.sor('claim', 'greet/hello@py', '--as', 'a')
        self.assertEqual(code, 2, out + err)
        self.assertIn('this project keeps no code per language', err + out)
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'a')[0], 0)
        (c,) = self.claims_file()
        self.assertNotIn('pins', c)
        self.assertEqual([k for k in c['keys'] if '@' in k], [])


if __name__ == '__main__':
    unittest.main()
