"""Tests for `Require: code` (SPEC §10): a part that says so makes `sor lock` refuse a clause that is new or changed and has no code,
unless the clause says `code: none`. A project that never writes the line is not asked anything.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, dummy projects only, no browser.
"""
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import lint                            # noqa: E402
from sorlib.model import Project                   # noqa: E402
from test_sor_flows import Flow, accepted          # noqa: E402

doc, write, read = base.doc, base.write, base.read

APP = '// @clause pair/a\nconsole.log("A");\n// @clause end\n'
A = '- **a** - The page says {text: A}.'
TESTS = ['- **a** - says a.', '  expect: ok']


def pair(header=(), extra=()):
    """A part `pair` with the clause a (and what `extra` adds); the tests are `a`'s."""
    return doc('Pair', 'Two clauses.', header=list(header), rules=[A, *extra], tests=TESTS)


class Required(Flow):
    def start(self, header=('Require: code',), extra=(), app=APP):
        """pair/a locked with its code; then `extra` rules are added, not locked."""
        self.project({'pair': pair(header)})
        write(self.dir, 'out/app.js', app)
        accepted(self.dir)
        if extra:
            write(self.dir, 'sor/pair.md', pair(header, extra))

    def lock(self, *ids):
        return self.sor('lock', *ids, '--allow-incomplete')

    def lock_bytes(self):
        return read(os.path.join(self.dir, 'sor', 'sor-lock.json'))


class TestTheRefusal(Required):
    NEW = ['- **c** - The page says {text: C}.']

    def test_a_new_clause_with_no_code_is_refused_and_the_lock_is_unchanged(self):
        self.start(extra=self.NEW)
        before = self.lock_bytes()
        code, out, _ = self.lock('pair/c')
        self.assertNotEqual(code, 0, out)
        self.assertIn('lock refused', out)
        self.assertIn('no code  pair/c', out)
        self.assertIn('Require: code', out)
        self.assertIn('code: none', out)
        self.assertEqual(self.lock_bytes(), before)

    def test_the_same_clause_with_its_code_marked_is_locked(self):
        self.start(extra=self.NEW)
        write(self.dir, 'out/app.js', APP + '// @clause pair/c\nconsole.log("C");\n// @clause end\n')
        code, out, _ = self.lock('pair/c')
        self.assertEqual(code, 0, out)

    def test_code_none_under_the_clause_is_the_way_out_and_it_is_in_the_clause_text(self):
        self.start(extra=self.NEW)
        before = read(os.path.join(self.dir, 'sor', 'pair.md'))
        write(self.dir, 'sor/pair.md', before.replace('{text: C}.', '{text: C}.\n  code: none'))
        code, out, _ = self.lock('pair/c')
        self.assertEqual(code, 0, out)
        self.assertIn('code: none', read(os.path.join(self.dir, 'sor', 'pair.md')))

    def test_the_flag_that_excuses_tests_does_not_excuse_it(self):
        self.start(extra=self.NEW)
        code, out, _ = self.sor('lock', 'pair/c', '--allow-incomplete')
        self.assertNotEqual(code, 0, out)
        self.assertIn('no code  pair/c', out)

    def test_lock_all_is_refused_too(self):
        self.start(extra=self.NEW)
        code, out, _ = self.sor('lock', '--all', '--allow-incomplete')
        self.assertNotEqual(code, 0, out)
        self.assertIn('no code  pair/c', out)

    def test_a_changed_clause_that_lost_its_code_is_refused(self):
        self.start()
        write(self.dir, 'sor/pair.md', read(os.path.join(self.dir, 'sor', 'pair.md')).replace('{text: A}', '{text: Hi}'))
        write(self.dir, 'out/app.js', '// @clause glue\nconsole.log("x");\n// @clause end\n')
        code, out, _ = self.lock('pair/a')
        self.assertNotEqual(code, 0, out)
        self.assertIn('no code  pair/a', out)

    def test_a_clause_locked_without_code_before_is_not_asked_again_until_it_changes(self):
        self.start(header=(), extra=self.NEW)   # the setting is not there yet
        self.assertEqual(self.lock('pair/c')[0], 0)   # locked with no code
        write(self.dir, 'sor/pair.md', pair(('Require: code',), self.NEW))   # now it is on
        self.assertEqual(self.sor('status')[0] in (0, 1), True)
        self.assertEqual(self.lock('pair/c')[0], 0)   # nothing changed: not refused
        write(self.dir, 'sor/pair.md', read(os.path.join(self.dir, 'sor', 'pair.md')).replace('{text: C}', '{text: Cc}'))
        code, out, _ = self.lock('pair/c')
        self.assertNotEqual(code, 0, out)   # changed: asked

    def test_tests_and_clauses_in_a_part_without_the_setting_are_never_asked(self):
        self.start(header=(), extra=self.NEW)
        self.assertEqual(self.lock('pair/c')[0], 0)
        self.start(extra=['- **d** - The page says {text: D}.'])
        write(self.dir, 'sor/pair.md', read(os.path.join(self.dir, 'sor', 'pair.md')).replace(
            '## Tests', '## Tests\n- **d** - says d.\n  expect: ok', 1))
        code, out, _ = self.lock('pair/test:d')
        self.assertEqual(code, 0, out)   # a test needs no code

    def test_locking_other_clauses_is_not_held_up_by_a_new_clause_outside_the_scope(self):
        self.start(extra=self.NEW)
        write(self.dir, 'sor/pair.md', read(os.path.join(self.dir, 'sor', 'pair.md')).replace('{text: A}', '{text: Ab}'))
        code, out, _ = self.lock('pair/a')
        self.assertEqual(code, 0, out)


class TestTheSettingAndTheLine(Required):
    def project_with(self, root_header=(), part_header=()):
        write(self.dir, 'sor/SPECOFRECORD.md', doc('Demo', 'A project the tests use.', header=list(root_header),
                                                   rules=['- **out-of-scope** - everything else.']))
        write(self.dir, 'sor/pair.md', pair(part_header, ['- **c** - The page says {text: C}.']))
        write(self.dir, 'out/app.js', APP)

    def test_the_root_line_applies_to_every_part_and_a_part_line_overrides_it(self):
        self.project_with(root_header=('Require: code',))
        project = Project(self.dir)
        self.assertTrue(project.requires_code(project.parts['pair']))
        self.project_with(root_header=('Require: code',), part_header=('Require:',))
        project = Project(self.dir)
        self.assertFalse(project.requires_code(project.parts['pair']))

    def test_a_part_line_does_not_reach_the_parts_beside_it(self):
        self.project({'pair': pair(('Require: code',)), 'other': doc('Other', 'Another part.', rules=['- **x** - X.'])})
        project = Project(self.dir)
        self.assertTrue(project.requires_code(project.parts['pair']))
        self.assertFalse(project.requires_code(project.parts['other']))

    def test_a_line_that_names_something_else_is_a_problem(self):
        for line in ('Require: tests', 'Require: code,', 'Require: code, tests'):
            with self.subTest(line=line):
                self.project({'pair': pair((line,))})
                write(self.dir, 'out/app.js', APP)
                code, out, _ = self.sor('check')
                self.assertEqual(code, 2, out)
                self.assertIn('require', out)

    def test_code_none_with_code_marked_is_a_problem_and_without_it_is_not(self):
        self.project({'pair': pair(('Require: code',), ['- **c** - The page says {text: C}.', '  code: none'])})
        write(self.dir, 'out/app.js', APP)
        self.assertEqual(self.sor('check')[0], 0)
        write(self.dir, 'out/app.js', APP + '// @clause pair/c\nconsole.log("C");\n// @clause end\n')
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2, out)
        self.assertIn('pair/c says `code: none` but code is marked for it', out)

    def test_code_none_is_no_anchor_and_the_no_code_note_leaves_the_clause_alone(self):
        self.project({'pair': pair((), ['- **c** - The page says {text: C}.', '  code: none'])})
        write(self.dir, 'out/app.js', APP)
        project = Project(self.dir)
        self.assertEqual(project.items['pair/c'].anchors, [])
        self.assertTrue(project.items['pair/c'].no_code)
        self.assertEqual([n for n in lint.notes(project) if n.kind == 'no code'], [])
        self.assertEqual(self.sor('check')[0], 0)

    def test_a_project_that_never_writes_the_line_is_not_asked_anything(self):
        self.project({'pair': pair((), ['- **c** - The page says {text: C}.'])})
        write(self.dir, 'out/app.js', APP)
        self.assertEqual(self.lock('--all')[0], 0)


class TestVerification(Required):
    def test_code_none_is_hashed_with_the_clause_so_adding_it_is_a_change(self):
        self.start(extra=['- **c** - The page says {text: C}.'])
        self.assertNotEqual(self.lock('pair/c')[0], 0)   # refused: no code
        accepted(self.dir)   # lock everything as it is, c without code
        self.assertEqual(self.sor('status')[1].strip(), 'clauses, code and lock agree')
        path = os.path.join(self.dir, 'sor', 'pair.md')
        write(self.dir, 'sor/pair.md', read(path).replace('{text: C}.', '{text: C}.\n  code: none'))
        out = self.sor('status')[1]
        self.assertIn('changed', out)
        self.assertIn('pair/c', out)

    def test_a_needs_line_is_no_clause_and_is_not_asked_for_code(self):
        self.project({'pair': doc('Pair', 'Two.', header=['Require: code'], rules=[A], tests=TESTS),
                      'user': doc('User', 'Uses.', header=['Require: code'], rules=['- **u** - Uses {pair/a}.'],
                                  contract=['- needs {pair/a}'], tests=['- **u** - ok.', '  expect: ok'])})
        write(self.dir, 'out/app.js', APP + '// @clause user/u\nconsole.log("U");\n// @clause end\n')
        out = self.sor('lock', '--all', '--allow-incomplete')[1]
        self.assertNotIn('no code  user/needs', out)
        self.assertEqual([n.text for n in lint.notes(Project(self.dir)) if n.kind == 'no code'], [])

    def test_each_code_none_exception_is_shown_once_as_a_note_when_it_is_made(self):
        self.start(extra=['- **c** - The page says {text: C}.', '  code: none'])
        found = [n for n in lint.notes(Project(self.dir)) if n.kind == 'code waived']
        self.assertEqual(len(found), 1, [n.text for n in found])
        self.assertIn('pair/c', found[0].text)
        self.assertIn('note: 1 clause(s) of pair are new or changed and say `code: none`: pair/c', self.sor('status')[1])
        self.assertEqual(self.lock('pair/c')[0], 0)
        self.assertEqual([n for n in lint.notes(Project(self.dir)) if n.kind == 'code waived'], [])   # locked: shown once


if __name__ == '__main__':
    unittest.main()
