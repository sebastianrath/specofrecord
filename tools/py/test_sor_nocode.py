"""Tests for the notes that make two silent gaps visible: a clause that is new or changed and has no code anywhere
(`no code`), and a clause text that says where its code is while the markers say otherwise (`code location`).

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

PAIR = doc('Pair', 'Two clauses.', rules=['- **a** - The page says {text: A}.', '- **b** - The page says {text: B}.'],
           tests=['- **a** - says a.', '  expect: ok', '- **b** - says b.', '  expect: ok'])
PAIR_APP = '// @clause pair/a\nconsole.log("A");\n// @clause end\n// @clause pair/b\nconsole.log("B");\n// @clause end\n'


def with_rule(text, name, body):
    return text.replace('- **b** - The page says {text: B}.', f'- **b** - The page says {{text: B}}.\n- **{name}** - {body}', 1)


class TestNoCodeYet(Flow):
    def pair_project(self):
        self.project({'pair': PAIR})
        write(self.dir, 'out/app.js', PAIR_APP)
        return accepted(self.dir)

    def notes(self):
        return [n for n in lint.notes(Project(self.dir)) if n.kind == 'no code']

    def test_a_locked_project_with_every_clause_built_has_no_such_note(self):
        self.pair_project()
        self.assertEqual(self.notes(), [])

    def test_a_new_clause_with_no_code_gets_one_note_naming_it(self):
        self.pair_project()
        write(self.dir, 'sor/pair.md', with_rule(read(os.path.join(self.dir, 'sor', 'pair.md')), 'c', 'The page says {text: C}.'))
        found = self.notes()
        self.assertEqual(len(found), 1)
        self.assertIn('pair/c', found[0].text)
        self.assertIn('no code in any target', found[0].text)
        self.assertEqual(found[0].where, 'pair.md:' + str(Project(self.dir).items['pair/c'].lineno))

    def test_it_is_a_note_never_a_problem_and_strict_makes_it_fail(self):
        self.pair_project()
        write(self.dir, 'sor/pair.md', with_rule(read(os.path.join(self.dir, 'sor', 'pair.md')), 'c', 'The page says {text: C}.'))
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertIn('no code', out)
        self.assertIn('0 problem(s)', out)
        self.assertEqual(self.sor('check', '--strict')[0], 2)

    def test_status_prints_the_same_note_as_a_line_and_json_is_unchanged(self):
        self.pair_project()
        write(self.dir, 'sor/pair.md', with_rule(read(os.path.join(self.dir, 'sor', 'pair.md')), 'c', 'The page says {text: C}.'))
        code, out, _ = self.sor('status')
        self.assertIn('note: 1 clause(s) are new or changed and have no code in any target: pair/c', out)
        data = __import__('json').loads(self.sor('status', '--json')[1])
        self.assertNotIn('notes', data)

    def test_a_changed_clause_whose_code_is_missing_is_noted_but_a_changed_one_with_code_is_not(self):
        self.pair_project()
        text = read(os.path.join(self.dir, 'sor', 'pair.md')).replace('{text: A}', '{text: Hi}', 1)
        write(self.dir, 'sor/pair.md', text)
        self.assertEqual(self.notes(), [])   # pair/a changed but has code
        write(self.dir, 'out/app.js', 'console.log("B");\n')   # now it has none
        # code outside any region is a problem of its own; the clause pair/a has no code now
        found = self.notes()
        self.assertTrue(any('pair/a' in n.text for n in found), [n.text for n in found])

    def test_locking_the_clause_without_code_acknowledges_it_and_the_note_goes(self):
        self.pair_project()
        write(self.dir, 'sor/pair.md', with_rule(read(os.path.join(self.dir, 'sor', 'pair.md')), 'c', 'The page says {text: C}.'))
        self.assertEqual(len(self.notes()), 1)
        code, out, _ = self.sor('lock', 'pair/c', '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.notes(), [])

    def test_a_project_with_no_lock_yet_gets_no_note_for_all_its_clauses(self):
        self.project({'pair': PAIR})   # nothing is locked: every clause is new
        self.assertEqual(self.notes(), [])

    def test_a_test_a_draft_and_a_clause_whose_rows_have_the_code_are_not_noted(self):
        table = doc('Bodies', 'The sky.', rules=['- **planets** - The planets:', '', '| Planet | Size |', '|---|---|', '| Mars | 5 |'],
                    tests=['- **planets** - there.', '  expect: ok'])
        self.project({'pair': PAIR, 'bodies': table})
        write(self.dir, 'out/app.js', PAIR_APP + '// @clause bodies/planets.Mars\nconst mars = 5;\n// @clause end\n')
        accepted(self.dir)
        text = read(os.path.join(self.dir, 'sor', 'bodies.md')).replace('| Mars | 5 |', '| Mars | 6 |')
        write(self.dir, 'sor/bodies.md', text)
        self.assertEqual(self.notes(), [])   # the changed clause has code in its row


class TestCodeLocationSentence(Flow):
    def notes(self):
        return [n for n in lint.notes(Project(self.dir)) if n.kind == 'code location']

    def build(self, sentence, app=PAIR_APP):
        text = PAIR.replace('- **a** - The page says {text: A}.', f'- **a** - The page says {{text: A}}. {sentence}', 1)
        self.project({'pair': text})
        write(self.dir, 'out/app.js', app)
        write(self.dir, 'out/other.js', '// @clause pair/b\nconsole.log("other");\n// @clause end\n')

    def test_a_sentence_naming_a_file_where_the_clause_has_no_marker_is_noted(self):
        self.build('Its code is in `out/other.js`.')
        found = self.notes()
        self.assertEqual(len(found), 1, [n.text for n in found])
        self.assertIn('pair/a', found[0].text)
        self.assertIn('out/other.js', found[0].text)
        self.assertIn('sor show', found[0].text)

    def test_a_sentence_naming_the_right_file_is_not_noted(self):
        self.build('Its code is in `out/app.js`.')
        self.assertEqual(self.notes(), [])

    def test_the_stock_phrases_are_found_and_other_sentences_are_not(self):
        for sentence, expected in (('The code is `out/other.js`.', 1), ('Their code is marked in `out/other.js`.', 1),
                                   ('It reads `out/other.js` for its input.', 0), ('See `out/other.js`.', 0)):
            with self.subTest(sentence=sentence):
                self.build(sentence)
                self.assertEqual(len(self.notes()), expected)

    def test_a_file_without_any_region_or_a_name_that_is_no_file_is_not_noted(self):
        self.build('Its code is in `engine/nowhere.cpp` and `a.b`.')
        self.assertEqual(self.notes(), [])

    def test_the_sentence_ends_at_a_full_stop_so_a_later_sentence_is_not_read(self):
        self.build('Its code is in `out/app.js`. A fixture lives in `out/other.js`.')
        self.assertEqual(self.notes(), [])

    def test_e_g_does_not_end_the_sentence(self):
        self.build('Its code is in `out/app.js`, e.g. `out/other.js`.')
        self.assertEqual(self.notes(), [])   # the sentence names a file that has the code, and the other after e.g.

    def test_it_is_a_note_and_never_a_problem(self):
        self.build('Its code is in `out/other.js`.')
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertIn('code location', out)
        self.assertEqual(self.sor('check', '--strict')[0], 2)

    def test_a_test_item_is_not_read(self):
        text = PAIR.replace('- **a** - says a.', '- **a** - says a. Its code is in `out/other.js`.', 1)
        self.project({'pair': text})
        write(self.dir, 'out/app.js', PAIR_APP)
        write(self.dir, 'out/other.js', '// @clause pair/b\nconsole.log("other");\n// @clause end\n')
        self.assertEqual(self.notes(), [])


if __name__ == '__main__':
    unittest.main()
