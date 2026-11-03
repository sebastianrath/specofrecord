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
        self.assertIn('note: 1 clause(s) of pair are new or changed and have no code in any target: pair/c', out)
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


class TestNoCodeInOtherShapes(Flow):
    OTHER = doc('Other', 'Another part.', rules=['- **x** - The page says {text: X}.'], tests=['- **x** - says x.', '  expect: ok'])

    def notes(self, *args):
        return [n for n in lint.notes(Project(self.dir)) if n.kind == 'no code']

    def two_parts(self):
        self.project({'pair': PAIR, 'other': self.OTHER})
        write(self.dir, 'out/app.js', PAIR_APP + '// @clause other/x\nconsole.log("X");\n// @clause end\n')
        accepted(self.dir)
        for name, last, rule, value in (('pair', 'b', 'c', 'C'), ('other', 'x', 'y', 'Y')):
            path = os.path.join(self.dir, 'sor', name + '.md')
            old = f'- **{last}** - The page says {{text: {last.upper()}}}.'
            write(self.dir, f'sor/{name}.md', read(path).replace(old, old + f'\n- **{rule}** - The page says {{text: {value}}}.', 1))

    def test_the_note_is_one_per_part_and_the_part_filter_of_sor_check_shows_each_under_its_own_part(self):
        self.two_parts()
        found = self.notes()
        self.assertEqual(sorted(n.text.split(' of ')[1].split(' ')[0] for n in found), ['other', 'pair'])
        for part, other in (('pair', 'other/y'), ('other', 'pair/c')):
            with self.subTest(part=part):
                out = self.sor('check', part)[1]
                self.assertIn(f'{part}/', out)
                self.assertNotIn(other, out)

    def test_a_code_line_that_resolves_counts_as_code_and_one_that_does_not_is_noted(self):
        rules = ['- **run** - It runs.', '  code: src/a.js#run']
        self.project({'hand': doc('Hand', 'By hand.', header=['Source: code at src/'], rules=rules)})
        write(self.dir, 'src/a.js', 'function run() {\n  return 1;\n}\n')
        accepted(self.dir)
        self.assertEqual(self.notes(), [])   # the line that resolves is code
        rules += ['- **gone** - It is gone.', '  code: src/a.js#missing', '- **fresh** - It runs too.', '  code: src/a.js#run']
        write(self.dir, 'sor/hand.md', doc('Hand', 'By hand.', header=['Source: code at src/'], rules=rules))
        ids = ' '.join(n.text for n in self.notes())
        self.assertIn('hand/gone', ids)   # its line does not resolve: no code
        self.assertNotIn('hand/fresh', ids)   # a new clause whose line resolves has code
        self.assertNotIn('hand/run', ids)

    def test_a_locked_clause_whose_code_is_deleted_is_drift_and_not_a_no_code_note(self):
        self.project({'pair': PAIR})
        write(self.dir, 'out/app.js', PAIR_APP)
        accepted(self.dir)
        write(self.dir, 'out/app.js', '// @clause pair/b\nconsole.log("B");\n// @clause end\n')
        self.assertEqual(self.notes(), [])
        out = self.sor('status')[1]
        self.assertIn('drift', out)
        self.assertIn('pair/a', out)


class TestNoCodeWithTwoTargets(Flow):
    def target(self, name, path):
        return doc(name.title(), 'Where the code of one language lives.', rules=[f'- **code0** - The code is under {{path: {path}}}.'])

    def test_a_new_clause_without_code_in_any_target_is_noted_and_one_with_code_in_a_target_is_not(self):
        greet = doc('Greet', 'Says hello.', rules=['- **hello** - The greeting is "Hello".'])
        self.project({'targets/py': self.target('py', 'src_py/'), 'targets/ts': self.target('ts', 'src_ts/'), 'greet': greet})
        write(self.dir, 'src_py/greet.py', '# @clause greet/hello\nHELLO = "Hello"\n# @clause end\n')
        write(self.dir, 'src_ts/greet.ts', '// @clause greet/hello\nexport const HELLO = "Hello";\n// @clause end\n')
        accepted(self.dir)
        path = os.path.join(self.dir, 'sor', 'greet.md')
        write(self.dir, 'sor/greet.md', read(path).replace('- **hello** - The greeting is "Hello".',
                                                           '- **hello** - The greeting is "Hello".\n- **bye** - The farewell is "Bye".', 1))
        found = [n for n in lint.notes(Project(self.dir)) if n.kind == 'no code']
        self.assertEqual(len(found), 1, [n.text for n in found])
        self.assertIn('greet/bye', found[0].text)
        self.assertNotIn('greet/hello', found[0].text)


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

    def test_e_g_and_i_e_do_not_end_the_sentence(self):
        for sentence in ('Its code is in `out/app.js`, e.g. `out/other.js`.', 'Its code is in `out/app.js`, i.e. `out/other.js`.'):
            with self.subTest(sentence=sentence):
                self.build(sentence)
                found = self.notes()
                self.assertEqual(len(found), 1, [n.text for n in found])   # the file after the abbreviation is read, and it is wrong
                self.assertIn('out/other.js', found[0].text)
                self.assertNotIn('out/app.js', found[0].text)

    def test_a_sentence_that_wraps_onto_the_next_line_is_read_whole(self):
        text = PAIR.replace('- **a** - The page says {text: A}.',
                            '- **a** - The page says {text: A}. Its code is in `out/app.js` and\n  `out/other.js`, in one place.', 1)
        self.project({'pair': text})
        write(self.dir, 'out/app.js', PAIR_APP)
        write(self.dir, 'out/other.js', '// @clause pair/b\nconsole.log("other");\n// @clause end\n')
        found = self.notes()
        self.assertEqual(len(found), 1, [n.text for n in found])
        self.assertIn('out/other.js', found[0].text)
        self.assertEqual(found[0].where, 'pair.md:' + str(Project(self.dir).items['pair/a'].lineno))

    def test_a_dot_slash_prefix_is_removed_as_a_prefix_not_as_a_set_of_characters(self):
        self.build('Its code is in `./out/other.js`.')
        found = self.notes()
        self.assertEqual(len(found), 1, [n.text for n in found])
        self.assertIn('out/other.js', found[0].text)

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
