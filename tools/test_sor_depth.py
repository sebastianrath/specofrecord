"""Tests for how wide a part may get (SPEC §13): the note for a part with too many child parts, and `sor parts --tree`.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, no browser.
"""
import json
import os
import re
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import lint                            # noqa: E402
from sorlib.model import Project                   # noqa: E402

doc = base.doc


def small(title='Part'):
    return doc(title, f'{title} exists.', rules=['- **r** - A rule.'], tests=['- **r** - ok.', '  manual: by hand'])


def children(parent, n):
    """n small parts directly under `parent` ('' for the top level)."""
    prefix = f'{parent}/' if parent else ''
    return {f'{prefix}c{i:02}': small(f'Child {i}') for i in range(1, n + 1)}


class Wide(base.Case):
    def wide(self, parts, *args):
        """The 'too wide' notes `sor check` prints for these parts, as (where, text) pairs."""
        self.project(parts)
        code, out, _ = base.run_sor(self.dir, 'check', *args)
        return code, [m.groups() for m in (re.match(r'\s*too wide\s+(\S+)\s+(.*)$', line) for line in out.splitlines()) if m]


class TestAPartWithTooManyChildren(Wide):
    LIMIT = lint.LIMIT_CHILDREN

    def test_the_limit_itself_is_fine_and_one_more_is_a_note_on_the_parent(self):
        _, notes = self.wide({'big': small('Big'), **children('big', self.LIMIT)})
        self.assertEqual(notes, [])
        _, notes = self.wide({'big': small('Big'), **children('big', self.LIMIT + 1)})
        self.assertEqual(len(notes), 1, notes)
        self.assertEqual(notes[0][0], 'big.md:1')
        self.assertIn(f'{self.LIMIT + 1} parts sit directly under `big` (at most {self.LIMIT})', notes[0][1])
        self.assertIn('`big/<group>/<name>`', notes[0][1])

    def test_it_is_a_note_not_a_problem(self):
        code, notes = self.wide({'big': small('Big'), **children('big', self.LIMIT + 1)})
        self.assertEqual((code, len(notes)), (0, 1))
        self.assertEqual(base.run_sor(self.dir, 'check', '--strict')[0], 2)   # --strict makes any note fail

    def test_the_top_level_parts_are_counted_for_the_root(self):
        _, notes = self.wide(children('', self.LIMIT + 1))
        self.assertEqual([n[0] for n in notes], ['SPECOFRECORD.md:1'])
        self.assertIn('directly under the root', notes[0][1])
        self.assertIn('`<group>/<name>`', notes[0][1])

    def test_only_the_parts_directly_under_one_part_are_counted(self):
        grand = {f'big/mid/g{i:02}': small(f'G{i}') for i in range(1, self.LIMIT + 1)}   # a full level two levels down
        _, notes = self.wide({'big': small('Big'), 'big/mid': small('Mid'), **grand})
        self.assertEqual(notes, [])

    def test_a_folder_that_only_groups_parts_is_no_part_and_gets_no_note(self):
        _, notes = self.wide(children('group', self.LIMIT + 5))   # sor/group/ has no group.md
        self.assertEqual(notes, [])

    def test_a_check_for_one_part_shows_the_note_of_that_part_only(self):
        parts = {'big': small('Big'), **children('big', self.LIMIT + 1), 'calm': small('Calm')}
        _, mine = self.wide(parts, 'big')
        self.assertEqual(len(mine), 1)
        _, theirs = self.wide(parts, 'calm')
        self.assertEqual(theirs, [])

    def test_the_real_projects_have_no_such_note(self):
        repo = os.path.dirname(HERE)
        for rel in ('examples/solar-system', 'editors/vscode'):
            project = Project(os.path.join(repo, rel))
            self.assertEqual([n for n in lint.notes(project) if n.kind == 'too wide'], [], rel)


class TestThePartsTree(base.Case):
    def setUp(self):
        super().setUp()
        # `a-b` sorts before `a/c` as text: a tree must still keep `a` and its children together
        self.project({'a': small('A'), 'a/c': small('C'), 'a/c/d': small('D'), 'a/e': small('E'), 'a-b': small('AB'), 'z': small('Z')})

    def labels(self, *args):
        """The name column of each part: every part takes two lines, and the last line counts them."""
        lines = base.run_sor(self.dir, 'parts', *args)[1].splitlines()
        return [re.match(r'(\s*\S+(?: \(\d+\))?)', line).group(1) for line in lines[:-1:2]]

    def test_each_part_comes_right_after_its_parent_and_is_indented_by_depth(self):
        self.assertEqual(self.labels('--tree'), ['ROOT (3)', 'a (2)', '  c (1)', '    d', '  e', 'a-b', 'z'])

    def test_the_flat_index_is_what_it_was(self):
        self.assertEqual(self.labels(), ['ROOT', 'a', 'a-b', 'a/c', 'a/c/d', 'a/e', 'z'])

    def test_json_has_the_same_parts_in_tree_order_with_the_flag(self):
        plain = json.loads(base.run_sor(self.dir, 'parts', '--json')[1])
        tree = json.loads(base.run_sor(self.dir, 'parts', '--tree', '--json')[1])
        self.assertEqual([p['id'] for p in plain], ['ROOT', 'a', 'a-b', 'a/c', 'a/c/d', 'a/e', 'z'])
        self.assertEqual([p['id'] for p in tree], ['ROOT', 'a', 'a/c', 'a/c/d', 'a/e', 'a-b', 'z'])


if __name__ == '__main__':
    unittest.main()
