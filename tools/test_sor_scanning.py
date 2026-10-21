"""Tests for how the tool reads code and history: the marker scanner and its problems, `code: path#name` anchors in
Python, in brace languages and with nested names, alias values in the lock, and `git blame` for drifted lines.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only. The blame tests need `git` and skip themselves without it.
"""
import datetime
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                           # noqa: E402  (its helpers only)
from sorlib import anchors, blame, markers       # noqa: E402
from sorlib import lock as lockfile              # noqa: E402
from sorlib.markers import Scan                  # noqa: E402
from sorlib.model import Project                 # noqa: E402

doc, write = base.doc, base.write


class TestScanText(unittest.TestCase):
    """The marker scanner on one file's text (SPEC §10): the regions it finds and the problems it names."""

    def scan(self, text, rel='a.js'):
        regions, problems, unmarked = markers.scan_text(rel, text)
        return regions, [(p.kind, p.text) for p in problems], unmarked

    def test_a_region_that_is_never_closed_is_a_problem_and_runs_to_the_end_of_the_file(self):
        regions, problems, _ = self.scan('// @clause a/b\none();\ntwo();\n')
        self.assertEqual(problems, [('marker', 'region is never closed with @clause end')])
        self.assertEqual((regions[0].start, regions[0].end, regions[0].where), (1, 3, 'a.js:1-3'))

    def test_a_line_ends_at_a_line_feed_or_a_carriage_return_and_nowhere_else(self):
        # editors number lines that way; a form feed or a Unicode separator inside a line must not shift every number after it
        regions, _, unmarked = self.scan('// @clause a/b\none();\x0c\ntwo();\u2028three();\x0bfour();\n// @clause end\nfive();\n')
        self.assertEqual((regions[0].start, regions[0].end, len(regions[0].lines)), (1, 4, 2))
        self.assertEqual(unmarked, [5])
        regions, _, _ = self.scan('// @clause a/b\r\none();\r// @clause end\r')
        self.assertEqual((regions[0].start, regions[0].end), (1, 3))

    def test_end_without_an_open_region_is_a_problem(self):
        self.assertEqual(self.scan('one();\n// @clause end\n')[1], [('marker', '@clause end without an open region')])

    def test_a_marker_with_no_id_is_a_problem(self):
        regions, problems, _ = self.scan('// @clause\none();\n// @clause end\n')
        self.assertEqual(problems, [('marker', '@clause needs at least one id')])
        self.assertEqual(len(regions), 1)

    def test_a_region_opened_inside_another_closes_the_first_and_says_so(self):
        regions, problems, _ = self.scan('// @clause a\none();\n// @clause b\ntwo();\n// @clause end\n')
        self.assertEqual(problems, [('marker', 'regions never nest: the region at line 1 is still open')])
        self.assertEqual([(r.ids, r.start, r.end) for r in regions], [(['a'], 1, 2), (['b'], 3, 5)])

    def test_a_line_marker_belongs_to_its_own_line_and_must_name_an_id(self):
        regions, problems, _ = self.scan('{ name: 1 },  // @clause bodies/mars\n')
        self.assertEqual((problems, regions[0].kind, regions[0].ids, regions[0].lines), ([], 'line', ['bodies/mars'], ['{ name: 1 },']))
        for tail in ('// @clause', '// @clause end', '// @clause glue', '// @clause test', '// @clause file'):
            with self.subTest(tail=tail):
                self.assertEqual(self.scan('x = 1;  ' + tail + '\n')[1],
                                 [('marker', 'a line marker names the ids its line serves')])

    def test_glue_test_and_code_regions_have_their_kinds(self):
        regions, problems, _ = self.scan('// @clause glue\n"use strict";\n// @clause end\n'
                                         '// @clause test a/b\nit();\n// @clause end\n'
                                         '// @clause a/c\ncode();\n// @clause end\n')
        self.assertEqual(problems, [])
        self.assertEqual([(r.kind, r.ids) for r in regions], [('glue', []), ('test', ['a/b']), ('code', ['a/c'])])

    def test_a_file_marker_makes_the_whole_file_one_region_without_its_marker_lines(self):
        regions, problems, unmarked = self.scan('# @clause file physics/solver\nimport math\n\ndef f(): pass\n', 'solver.py')
        self.assertEqual(problems, [])
        self.assertEqual((regions[0].kind, regions[0].ids, regions[0].start, regions[0].end), ('file', ['physics/solver'], 1, 4))
        self.assertEqual(regions[0].lines, ['import math', '', 'def f(): pass'])
        self.assertEqual(unmarked, [])

    def test_lines_outside_any_region_are_unmarked_and_blank_ones_are_not(self):
        self.assertEqual(self.scan('one();\n\n// @clause a\ntwo();\n// @clause end\nthree();\n')[2], [1, 6])

    def test_every_comment_style_opens_a_marker_and_a_closing_comment_is_not_an_id(self):
        for text in ('# @clause a\n', '-- @clause a\n', '; @clause a\n', '/* @clause a */\n', '<!-- @clause a -->\n', '// @clause a\n'):
            with self.subTest(text=text):
                regions, problems, _ = self.scan(text + 'x\n// @clause end\n')
                self.assertEqual((regions[0].ids, [p for p in problems if 'never' in p[1]]), (['a'], []))


class TestScanOfAProject(base.Case):
    """The scanner against a project's clauses: ids that do not exist, code that is not marked, whole files."""

    def setUp(self):
        super().setUp()
        self.project({'bodies': doc('Bodies', 'The sky.', rules=['- **sun** - Size {size: 28}.'], tests=['- **sun** - it is there.', '  expect: ok'])})

    def problems(self):
        return [(p.kind, p.text) for p in Scan(Project(self.dir)).problems]

    def test_a_file_marker_is_only_for_a_part_whose_code_is_written_by_hand(self):
        write(self.dir, 'out/app.js', '// @clause file bodies\nconsole.log(1);\n')
        self.assertIn(('marker', '@clause file is only for `Source: code` parts'), self.problems())

    def test_code_in_a_by_hand_part_needs_no_markers_and_may_be_one_file_region(self):
        self.project({'bodies': doc('Bodies', 'The sky.', rules=['- **sun** - Size {size: 28}.'], header=['Source: code at src/'])})
        write(self.dir, 'src/sun.js', '// @clause file bodies\nconsole.log(1);\n')
        write(self.dir, 'src/helper.js', 'console.log(2);\n')
        self.assertEqual(self.problems(), [])

    def test_a_marker_naming_something_that_does_not_exist_or_a_test_is_a_problem(self):
        write(self.dir, 'out/app.js', '// @clause bodies/moon\na();\n// @clause end\n// @clause bodies/test:sun\nb();\n// @clause end\n')
        found = self.problems()
        self.assertIn(('marker', 'bodies/moon is no item, row or part'), found)
        self.assertIn(('marker', 'bodies/test:sun is a test: mark test code with @clause test'), found)

    def test_test_code_must_name_a_test_that_exists(self):
        write(self.dir, 'out/app.js', '// @clause test bodies/moon\na();\n// @clause end\n')
        self.assertIn(('marker', 'bodies/moon has no test'), self.problems())

    def test_a_code_anchor_naming_a_missing_file_or_a_missing_name_is_a_problem(self):
        self.project({'bodies': doc('Bodies', 'The sky.', rules=['- **sun** - Size {size: 28}.', '  code: src/sun.py#glow',
                                                                  '- **moon** - Size {size: 2}.', '  code: src/none.py#x'])})
        write(self.dir, 'src/sun.py', 'def shine():\n    return 1\n')
        found = self.problems()
        self.assertIn(('anchor', 'code: src/sun.py#glow: no "glow" in src/sun.py'), found)
        self.assertIn(('anchor', 'code: src/none.py#x: no such file'), found)

    def test_a_code_anchor_gives_the_item_the_lines_of_the_symbol(self):
        self.project({'bodies': doc('Bodies', 'The sky.', rules=['- **sun** - Size {size: 28}.', '  code: src/sun.py#Sun.glow'])})
        write(self.dir, 'src/sun.py', 'class Sun:\n    def shine(self):\n        pass\n\n    def glow(self):\n        return 1\n')
        scan = Scan(Project(self.dir))
        self.assertEqual(scan.problems, [])
        region = scan.regions_for('bodies/sun')[0]
        self.assertEqual((region.kind, region.start, region.end, region.target), ('anchor', 5, 6, 'src/sun.py#Sun.glow'))

    def test_a_file_that_cannot_be_read_as_text_is_skipped(self):
        with open(os.path.join(self.dir, 'out.bin'), 'wb') as fh:
            fh.write(b'\xff\xfe\x00 // @clause bodies/sun\n')
        self.assertEqual([p for p in Scan(Project(self.dir)).problems if 'out.bin' in p.where], [])

    def test_a_file_over_the_size_limit_is_skipped(self):
        write(self.dir, 'big.js', '// @clause bodies/nothing\n' + 'a();\n' * 10)
        self.assertTrue([p for p in Scan(Project(self.dir)).problems if 'big.js' in p.where])
        with mock.patch.object(markers, 'MAX_BYTES', 10):
            self.assertEqual([p for p in Scan(Project(self.dir)).problems if 'big.js' in p.where], [])

    def test_a_file_that_two_code_roots_both_reach_is_read_once(self):
        self.project({'bodies': doc('Bodies', 'The sky.', rules=['- **sun** - Size {size: 28}.'], header=['Source: code at src/']),
                      'targets/web': doc('Web', 'The page.', rules=['- **path** - The page is {path: src/index.html}.'])})
        write(self.dir, 'src/index.html', '<!-- @clause bodies/sun -->\n<p></p>\n<!-- @clause end -->\n')
        scan = Scan(Project(self.dir))
        self.assertEqual(len(scan.regions_for('bodies/sun')), 1)

    def test_text_that_is_not_on_disk_yet_is_read_as_if_it_were(self):
        scan = Scan(Project(self.dir), {os.path.join(self.dir, 'out', 'new.js'): '// @clause bodies/sun\nx();\n// @clause end\n'})
        self.assertEqual([r.file for r in scan.regions_for('bodies/sun')], ['out/new.js'])


class TestAnchors(unittest.TestCase):
    """`code: path#name` (SPEC §10): where a named symbol starts and ends, in Python and in the brace languages."""

    PY = ('import os\n'            # 1
          'LIMIT = 5\n'            # 2
          'SIZE: int = 3\n'        # 3
          '\n'                     # 4
          '@decorate\n'            # 5
          'def solve(x):\n'        # 6
          '    return x\n'         # 7
          '\n'                     # 8
          'class World:\n'         # 9
          '    def step(self):\n'  # 10
          '        pass\n'         # 11
          '\n'                     # 12
          '    async def tick(self):\n'  # 13
          '        pass\n')        # 14

    def test_python_is_read_with_its_own_parser(self):
        cases = {'LIMIT': (2, 2), 'SIZE': (3, 3), 'solve': (5, 7), 'World': (9, 14), 'World.step': (10, 11), 'World.tick': (13, 14)}
        for name, span in cases.items():
            with self.subTest(name=name):
                self.assertEqual(anchors.find(self.PY, 'm.py', name), span)

    def test_python_without_the_name_or_with_a_syntax_error_has_no_symbol(self):
        self.assertIsNone(anchors.find(self.PY, 'm.py', 'nothing'))
        self.assertIsNone(anchors.find(self.PY, 'm.py', 'World.nothing'))
        self.assertIsNone(anchors.find('def broken(:\n', 'm.py', 'broken'))

    def test_without_a_name_the_whole_file_is_meant(self):
        self.assertEqual(anchors.find(self.PY, 'm.py', ''), (1, 14))
        self.assertEqual(anchors.find('', 'm.py', ''), (1, 1))

    JS = ('const LIMIT = 5;\n'                          # 1
          'function solve(x) {\n'                       # 2
          '  const s = "}";  // }\n'                    # 3
          '  /* } { */\n'                               # 4
          '  return x;\n'                               # 5
          '}\n'                                         # 6
          'class World {\n'                             # 7
          '  step(dt) {\n'                              # 8
          '    return `{${dt}}`;\n'                     # 9
          '  }\n'                                       # 10
          '  async tick() {\n'                          # 11
          '    return 1;\n'                             # 12
          '  }\n'                                       # 13
          '}\n')                                        # 14

    def test_a_form_feed_in_the_file_does_not_move_the_lines_after_it(self):
        text = 'a();\x0c\nfunction f() {\n  x;\n}\ny();\n'
        self.assertEqual(anchors.find(text, 'm.js', 'f'), (2, 4))
        self.assertEqual(anchors.find(text, 'm.js', ''), (1, 5))

    def test_braces_in_strings_and_comments_do_not_end_a_block(self):
        self.assertEqual(anchors.find(self.JS, 'm.js', 'solve'), (2, 6))
        self.assertEqual(anchors.find(self.JS, 'm.js', 'LIMIT'), (1, 1))

    def test_a_method_is_found_inside_its_class_by_a_dotted_name(self):
        self.assertEqual(anchors.find(self.JS, 'm.js', 'World'), (7, 14))
        self.assertEqual(anchors.find(self.JS, 'm.js', 'World.step'), (8, 10))
        self.assertEqual(anchors.find(self.JS, 'm.js', 'World.tick'), (11, 13))
        self.assertIsNone(anchors.find(self.JS, 'm.js', 'World.nothing'))

    def test_a_cplusplus_method_outside_its_class_is_written_owner_double_colon_name(self):
        cpp = 'int World::step(int dt) {\n  return dt;\n}\n\nint other() { return 0; }\n'
        self.assertEqual(anchors.find(cpp, 'm.cpp', 'World::step'), (1, 3))
        self.assertEqual(anchors.find(cpp, 'm.cpp', 'World.step'), (1, 3))

    def test_other_declarations_are_found_by_their_keywords(self):
        text = ('pub fn solve() {\n  1\n}\n'
                'type Id = u32;\n'
                'export default function* gen() {\n  yield 1;\n}\n'
                'struct Point {\n  x: i32,\n}\n')
        self.assertEqual(anchors.find(text, 'm.rs', 'solve'), (1, 3))
        self.assertEqual(anchors.find(text, 'm.rs', 'Id'), (4, 4))
        self.assertEqual(anchors.find(text, 'm.js', 'gen'), (5, 7))
        self.assertEqual(anchors.find(text, 'm.rs', 'Point'), (8, 10))

    def test_a_declaration_that_opens_no_block_ends_where_it_ends_not_at_the_next_brace(self):
        text = 'type Id = u32;\n\n\n\n\nfn other() {\n}\n'
        self.assertEqual(anchors.find(text, 'm.rs', 'Id'), (1, 1))

    def test_a_block_comment_hides_braces_over_several_lines(self):
        text = 'function f() {\n  /* a }\n     } */\n  return 1;\n}\n'
        self.assertEqual(anchors.find(text, 'm.js', 'f'), (1, 5))

    def test_a_target_splits_at_the_hash(self):
        self.assertEqual(anchors.split('src/a.py#World.step'), ('src/a.py', 'World.step'))
        self.assertEqual(anchors.split('src/a.py'), ('src/a.py', ''))


class TestAliasValues(base.Case):
    """An alias value `{name: = other}` changes in the lock when the value it stands for changes (SPEC §4)."""

    RULES = ['- **zoom** - Zoom goes to {max: 6x}.', '- **pinch** - Pinch goes as far: {far: = zoom.max}.']

    def snapshot(self, zoom_max):
        self.project({'cam': doc('Camera', 'It looks.', rules=[self.RULES[0].replace('6x', zoom_max), self.RULES[1]])})
        project = Project(self.dir)
        return lockfile.snapshot(project, Scan(project))

    def test_the_alias_changes_when_its_target_changes_and_not_otherwise(self):
        before, same, after = self.snapshot('6x'), self.snapshot('6x'), self.snapshot('8x')
        self.assertEqual(before['cam/pinch.far'], same['cam/pinch.far'])
        self.assertNotEqual(before['cam/pinch.far']['text'], after['cam/pinch.far']['text'])

    def test_a_plain_value_does_not_follow_another_one(self):
        self.project({'cam': doc('Camera', 'It looks.', rules=['- **zoom** - Zoom goes to {max: 6x}.', '- **pinch** - Pinch goes as far: {far: 6x}.'])})
        project = Project(self.dir)
        first = lockfile.snapshot(project, Scan(project))['cam/pinch.far']
        self.project({'cam': doc('Camera', 'It looks.', rules=['- **zoom** - Zoom goes to {max: 8x}.', '- **pinch** - Pinch goes as far: {far: 6x}.'])})
        project = Project(self.dir)
        self.assertEqual(first, lockfile.snapshot(project, Scan(project))['cam/pinch.far'])

    def test_an_alias_of_itself_does_not_loop(self):
        self.project({'cam': doc('Camera', 'It looks.', rules=['- **zoom** - Zoom goes to {max: = zoom.max}.'])})
        project = Project(self.dir)
        self.assertIn('cam/zoom.max', lockfile.snapshot(project, Scan(project)))

    def test_an_alias_refers_to_what_it_stands_for_and_the_lock_records_it(self):
        self.snapshot('6x')
        project = Project(self.dir)
        entry = lockfile.snapshot(project, Scan(project))['cam/pinch']
        self.assertIn('cam/zoom.max', entry['refs'])


@unittest.skipUnless(shutil.which('git'), 'git is not installed')
class TestBlame(base.Case):
    """`git blame` on the lines of drifted code: who changed them and when, or nothing (SPEC §11)."""

    def git(self, *args):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_DATE='2026-10-17T12:00:00',
                   GIT_COMMITTER_DATE='2026-10-17T12:00:00')
        subprocess.run(['git', '-c', 'user.name=Ada Lovelace', '-c', 'user.email=ada@example.com', *args],
                       cwd=self.dir, env=env, check=True, capture_output=True)

    def repo(self):
        write(self.dir, 'out/app.js', 'one();\ntwo();\nthree();\n')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'first')

    def test_a_committed_line_says_who_changed_it_in_which_commit_and_when(self):
        self.repo()
        said = blame.describe(self.dir, 'out/app.js:1-2')
        self.assertRegex(said, r'^changed by Ada Lovelace in [0-9a-f]{7} \(2026-10-1[67]\)$')

    def test_a_line_that_is_not_committed_says_so(self):
        self.repo()
        write(self.dir, 'out/app.js', 'one();\ntwo();\nthree();\nfour();\n')
        self.assertEqual(blame.describe(self.dir, 'out/app.js:4'), 'not committed yet')

    def test_several_places_are_asked_together_and_the_newest_change_wins(self):
        self.repo()
        write(self.dir, 'out/app.js', 'one();\ntwo();\nthree();\n')
        write(self.dir, 'out/b.js', 'x();\n')
        self.git('add', '.')
        self.git('commit', '-q', '-m', 'second')
        self.assertTrue(blame.describe(self.dir, 'out/app.js:1, out/b.js:1').startswith('changed by Ada Lovelace'))

    def test_outside_a_repository_or_for_a_place_that_is_not_there_nothing_is_said(self):
        write(self.dir, 'out/app.js', 'one();\n')
        self.assertEqual(blame.describe(self.dir, 'out/app.js:1'), '')
        self.repo()
        self.assertEqual(blame.describe(self.dir, 'out/missing.js:1'), '')
        self.assertEqual(blame.describe(self.dir, 'not a place'), '')

    def test_without_git_on_the_path_nothing_is_said(self):
        self.repo()
        with mock.patch.object(blame.subprocess, 'run', side_effect=OSError('no git')):
            self.assertEqual(blame.describe(self.dir, 'out/app.js:1'), '')

    def test_only_drifted_lines_are_asked_and_only_so_many(self):
        self.repo()

        class Found:
            def __init__(self, status, where):
                self.status, self.where, self.by = status, where, None

        findings = [Found('drift', 'out/app.js:1'), Found('changed', 'out/app.js:1'), Found('code-changed', 'out/app.js:2')]
        blame.annotate(type('P', (), {'root': self.dir}), findings)
        self.assertTrue(findings[0].by.startswith('changed by Ada'))
        self.assertIsNone(findings[1].by)
        self.assertTrue(findings[2].by.startswith('changed by Ada'))
        many = [Found('drift', 'out/app.js:1') for _ in range(5)]
        blame.annotate(type('P', (), {'root': self.dir}), many, most=2)
        self.assertEqual([f.by is not None for f in many], [True, True, False, False, False])


if __name__ == '__main__':
    unittest.main()
