"""Tests for how spec files are read and what `sor check` says about them: the plain format, the problems about `needs`
and `proves:`, the index's alias references, `sor new` when it cannot write, and the coverage a `sor test --coverage`
prints.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, no browser.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import cli, testrun, views            # noqa: E402
from sorlib.model import Project                  # noqa: E402

doc, write, read = base.doc, base.write, base.read


class TestThePlainFormat(base.Case):
    """People may write plain sentences without the strict sections (SPEC §15); the tool reads them by meaning."""

    def test_a_heading_the_tool_does_not_know_is_read_as_rules(self):
        self.project({'moon': '# Moon\nWhy: the moon.\n\n## Whatever you like\n- **orbit** - It circles.\n'})
        self.assertEqual(Project(self.dir).items['moon/orbit'].section, 'Rules')

    def test_bullets_right_under_the_title_are_rules(self):
        self.project({'moon': '# Moon\nIt is the moon.\n\n- **orbit** - It circles.\n'})
        project = Project(self.dir)
        self.assertEqual(project.items['moon/orbit'].section, 'Rules')
        self.assertEqual(project.parts['moon'].header['Why'], 'It is the moon.')

    def test_a_table_right_under_a_bullet_belongs_to_the_bullet(self):
        self.project({'moon': '# Moon\nWhy: the moon.\n- **phases** - The phases:\n| Phase | Day |\n|---|---|\n| New | 0 |\n'})
        item = Project(self.dir).items['moon/phases']
        self.assertEqual(list(item.rows), ['New'])

    def test_known_words_for_the_four_sections_are_read_by_meaning(self):
        self.project({'moon': '# Moon\nWhy: the moon.\n\n## Must\n- **a** - A.\n\n## How it works\n- **b** - B.\n\n'
                              '## Interface\n- gives **c** - C.\n\n## Checks\n- **a** - ok.\n  expect: ok\n'})
        project = Project(self.dir)
        self.assertEqual([project.items[i].section for i in ('moon/a', 'moon/b', 'moon/c', 'moon/test:a')],
                         ['Rules', 'Approach', 'Contract', 'Tests'])


class TestWhatCheckReports(base.Case):
    def kinds(self, **parts):
        self.project(parts)
        return [(p.kind, p.text) for p in Project(self.dir).check()]

    def test_a_needs_line_must_name_a_gives_item_that_exists(self):
        found = self.kinds(a=doc('A', 'First.', rules=['- **x** - X.'], contract=['- needs {b/y}']),
                           b=doc('B', 'Second.', rules=['- **y** - Y.']))
        self.assertTrue(any(k == 'needs' and t.startswith('{b/y} is not a `gives` item') for k, t in found), found)

    def test_a_part_and_an_item_may_not_share_a_name(self):
        found = self.kinds(a=doc('A', 'First.', rules=['- **b** - Same name as the part below.']), **{'a/b': doc('B', 'Second.', rules=['- **y** - Y.'])})
        self.assertTrue(any(k == 'collision' and '"a/b" names both' in t for k, t in found), found)

    def test_proves_may_not_name_a_needs_line(self):
        found = self.kinds(a=doc('A', 'First.', rules=['- **x** - X.'], contract=['- needs {b/y}'],
                                 tests=['- **other** - a split test.', '  proves: {a/needs}', '  expect: ok']),
                           b=doc('B', 'Second.', contract=['- gives **y** - Y.'], rules=['- **z** - Z.']))
        self.assertTrue(any(k == 'proves' and 'not a clause a test can prove' in t for k, t in found), found)


class TestTheIndex(base.Case):
    def test_an_alias_value_is_a_reference_with_its_place_in_the_line(self):
        self.project({'cam': doc('Camera', 'It looks.', rules=['- **zoom** - Zoom goes to {max: 6x}.', '- **pinch** - As far: {far: = zoom.max}.'])})
        code, out, _ = base.run_sor(self.dir, 'markers', '--json')
        self.assertEqual(code, 0)
        refs = [r for r in json.loads(out)['refs'] if r['text'] == 'zoom.max']
        self.assertEqual(len(refs), 1)
        line = [t for _, t in Project(self.dir).items['cam/pinch'].lines][0]
        self.assertEqual(line[refs[0]['col']:refs[0]['col'] + len('zoom.max')], 'zoom.max')


class TestNewWhenItCannotWrite(base.Case):
    def setUp(self):
        super().setUp()
        self.project({})

    def new(self, *args):
        return base.run_sor(self.dir, 'new', *args)

    def test_the_spec_folder_itself_may_be_given_as_the_project(self):
        code, out, _ = base.run_sor(os.path.join(self.dir, 'sor'), 'new', 'render')
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, 'sor', 'render.md')))

    def test_a_file_that_appears_while_it_writes_is_not_overwritten(self):
        real = open

        def appears(path, mode='r', *a, **k):   # only the exclusive create fails: someone else wrote the file first
            if mode == 'x':
                raise FileExistsError
            return real(path, mode, *a, **k)

        with mock.patch('builtins.open', appears):
            code, out, err = self.new('render')
        self.assertEqual(code, 2)
        self.assertIn('already exists: nothing written', out + err)

    def test_a_folder_it_cannot_write_to_is_said_not_raised(self):
        with mock.patch.object(views.os, 'makedirs', side_effect=OSError(13, 'Permission denied')):
            code, out, err = self.new('render')
        self.assertEqual(code, 2)
        self.assertIn('cannot write sor/render.md: Permission denied', out + err)


class TestWhatSorTestCoveragePrints(base.Case):
    """`sor test --coverage` lists what no passing test proves and the line coverage per clause. The page is replaced."""

    def setUp(self):
        super().setUp()
        web = doc('Web', 'The page.', rules=['- **path** - The page is {path: out/index.html}.'],
                  contract=['- gives **probes** - members of window.__probe.', '  read: errors', '  do: step(seconds)'])
        self.project({'targets/web': web, 'lim': doc('Limits', 'How many.', rules=['- **limit** - At most {max: 5}.', '- **other** - Nothing.'],
                                                    tests=['- **limit** - the cap.', '  expect: count(errors) = 0'])})
        write(self.dir, 'out/index.html', '<!-- @clause lim/limit -->\n<html></html>\n<!-- @clause end -->\n')

    def test_it_lists_the_clauses_no_passing_test_proves_and_the_lines_that_ran_per_clause(self):
        lines = {2: True}
        with mock.patch.object(testrun, 'run_page', lambda t, s, ids, timeout: ([{'id': i, 'status': 'pass'} for i in ids], lines)):
            code, out, _ = base.run_sor(self.dir, 'test', '--coverage')
        self.assertEqual(code, 0, out)
        self.assertIn('not proven by a passing test:\n  lim/other', out)
        self.assertIn('line coverage per clause (lowest first):', out)
        self.assertRegex(out, r'\d+%\s+\d+/\d+\s+lim/limit')


if __name__ == '__main__':
    unittest.main()
