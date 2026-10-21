"""Tests for how code is normalized before it is hashed (SPEC §11): the rule follows the type of the file, so Python indentation is
meaning, `#` comments are comments where they are, and every other type is hashed exactly as before; and for the migration of a
lock written under the old rule (`sor lock --rehash`).

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
"""
import hashlib
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                          # noqa: E402
import test_sor_flows as flows                   # noqa: E402
from sorlib import lock as lockfile              # noqa: E402
from sorlib.markers import Scan, normalized, style_of   # noqa: E402
from sorlib.model import Project                 # noqa: E402

doc, write, read = base.doc, base.write, base.read


def hashed(lines, style='c'):
    return hashlib.sha256(normalized(lines, style).encode('utf8')).hexdigest()[:12]


def py(text, style='python'):
    return normalized(text.strip('\n').splitlines(), style)


class TestTheStyleOfAFile(unittest.TestCase):
    def test_a_type_with_its_own_rule_is_found_by_its_extension_in_any_case(self):
        for rel, style in (('a.py', 'python'), ('src_py/pkg/a.PY', 'python'), ('x.pyi', 'python'), ('run.sh', 'hash'),
                           ('a.rb', 'hash'), ('conf.toml', 'hash'), ('q.sql', 'dash'), ('a.lua', 'dash')):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), style)

    def test_everything_else_is_c_family_as_it_was_before(self):
        for rel in ('a.ts', 'a.js', 'a.c', 'a.h', 'a.cpp', 'a.mm', 'a.go', 'a.rs', 'a.java', 'a.html', 'a.css', 'a.json', 'Makefile',
                    'Dockerfile', 'a.unknown', 'noext', 'dir.py/file', 'a.b/c'):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), 'c')

    def test_c_family_hashes_are_byte_for_byte_what_they_were(self):
        # hashes made by the rule before it followed the file type; a drift here would rewrite every locked project
        ts = ['  // note', 'export const total = (items: number[]) => {', '    return items.reduce((a, b) => a + b, 0);   ',
              '};', '', '/* block */']
        c = ['#include <stdio.h>', '#define N 3', '  int main(void) {', '      return  N;', '  }']
        html = ['<!-- c -->', '<p   class="a  b">hi   there</p>']
        self.assertEqual(hashed(ts), '5502253e7c35')
        self.assertEqual(hashed(c), '03f73544624d')       # `#include` and `#define` are code in C
        self.assertEqual(hashed(html), 'a10cf9686abb')


class TestPythonKeepsItsNesting(unittest.TestCase):
    LOOP = '''
def total(items):
    t = 0
    for i in items:
        t += i
    return t
'''

    def test_moving_a_line_into_a_loop_is_a_change(self):
        into = self.LOOP.replace('    return t', '        return t')
        self.assertNotEqual(py(self.LOOP), py(into))

    def test_moving_a_line_out_of_a_block_is_a_change(self):
        out = self.LOOP.replace('        t += i', '    t += i')
        self.assertNotEqual(py(self.LOOP), py(out))

    def test_the_same_nesting_in_other_columns_is_not_a_change(self):
        two = self.LOOP.replace('    ', '  ')
        eight = self.LOOP.replace('    ', '        ')
        self.assertEqual(py(self.LOOP), py(two))
        self.assertEqual(py(self.LOOP), py(eight))

    def test_a_changed_word_is_a_change(self):
        self.assertNotEqual(py(self.LOOP), py(self.LOOP.replace('t += i', 't -= i')))

    def test_comment_only_and_blank_lines_are_no_change(self):
        noisy = '# about the total\n\ndef total(items):\n    # start at zero\n    t = 0\n\n    for i in items:\n        t += i\n    # done\n    return t\n'
        self.assertEqual(py(self.LOOP), py(noisy))

    def test_a_comment_after_code_is_part_of_its_line_as_in_every_other_type(self):
        self.assertNotEqual(py(self.LOOP), py(self.LOOP.replace('t = 0', 't = 0  # start')))

    def test_else_and_elif_sit_at_the_level_of_their_if(self):
        a = 'if x:\n    a()\nelif y:\n    b()\nelse:\n    c()\n'
        b = a.replace('else:\n    c()', 'else:\n    c()\nd()')
        self.assertIn('0:else:', py(a))
        self.assertIn('1:c()', py(a))
        self.assertNotEqual(py(a), py(b))

    def test_a_statement_that_goes_on_inside_brackets_carries_no_depth_and_may_be_re_indented(self):
        a = 'x = foo(\n    1,\n    2,\n)\ny = 3\n'
        b = 'x = foo(\n            1,\n  2,\n)\ny = 3\n'
        self.assertEqual(py(a), py(b))
        self.assertIn('0:y = 3', py(a))

    def test_a_backslash_continuation_carries_no_depth(self):
        a = 'total = a + \\\n    b\nnext = 1\n'
        b = 'total = a + \\\n            b\nnext = 1\n'
        self.assertEqual(py(a), py(b))
        self.assertIn('0:next = 1', py(a))

    def test_brackets_and_hashes_inside_strings_are_text(self):
        src = 'x = "(" + \'#\'\ny = 1\n'
        self.assertIn('0:x = "(" + \'#\'', py(src))      # the line is kept: the `#` is inside quotes, not a comment
        self.assertIn('0:y = 1', py(src))                # and the open bracket inside the string does not swallow the next line

    def test_a_line_starting_with_a_hash_inside_a_multi_line_string_is_text(self):
        a = 'DOC = """\n# Heading\ntext\n"""\nrun()\n'
        b = a.replace('# Heading', '# Other heading')
        self.assertNotEqual(py(a), py(b))                 # the docstring changed, whatever its lines start with
        self.assertIn('0:run()', py(a))                   # and the string ends where its quotes do

    def test_a_fragment_that_starts_inside_a_class_is_counted_from_its_first_line(self):
        method = '    def area(self):\n        return self.w * self.h\n'
        self.assertEqual(py(method), py(method.replace('    ', '  ')))
        self.assertIn('1:return self.w * self.h', py(method))

    def test_tabs_count_as_a_level_like_the_spaces_they_stand_for(self):
        self.assertEqual(py(self.LOOP), py(self.LOOP.replace('    ', '\t')))

    def test_a_shebang_names_the_interpreter_and_is_code(self):
        self.assertNotEqual(py('#!/usr/bin/env python3\nx = 1\n'), py('#!/usr/bin/env python2\nx = 1\n'))


class TestTheOtherTypes(unittest.TestCase):
    def test_hash_types_drop_hash_comments_and_still_ignore_indentation(self):
        a = 'echo hi\nif true; then\n  echo there\nfi\n'
        b = '# a comment\necho  hi\nif true; then\n        echo there\n    # another\nfi\n'
        self.assertEqual(py(a, 'hash'), py(b, 'hash'))
        self.assertNotEqual(py('#!/bin/sh\nx\n', 'hash'), py('#!/bin/bash\nx\n', 'hash'))

    def test_dash_types_drop_dash_comments(self):
        self.assertEqual(py('select 1;\n', 'dash'), py('-- one\nselect 1;\n  -- two\n', 'dash'))

    def test_c_family_keeps_a_hash_line_as_code_and_keeps_ignoring_indentation(self):
        self.assertNotEqual(py('#define N 3\n', 'c'), py('#define N 4\n', 'c'))
        self.assertEqual(py('a();\n  b();\n', 'c'), py('a();\nb();\n', 'c'))


class Project1(flows.Flow):
    """A Python project: one clause, one file of code."""
    CODE = '# @clause calc/sum\ndef total(items):\n    t = 0\n    for i in items:\n        t += i\n    return t\n# @clause end\n'

    def setUp(self):
        super().setUp()
        self.project({'calc': doc('Calc', 'Adds numbers.', rules=['- **sum** - The total adds every item.'],
                                  tests=['- **sum** - adds.', '  manual: look'])})
        self.code = write(self.dir, 'src/calc.py', self.CODE)

    def entries(self):
        return json.loads(flows.lock_bytes(self.dir))

    def hashes(self, legacy=False):
        project = Project(self.dir)
        return Scan(project).code_hashes(legacy=legacy)


class TestALockOfPythonCode(Project1):
    def test_a_line_moved_into_a_loop_is_drift_and_a_comment_edit_is_not(self):
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.assertIn('agree', self.sor('status')[1])
        write(self.dir, 'src/calc.py', self.CODE.replace('    return t', '        return t'))
        code, out, _ = self.sor('status')
        self.assertEqual(code, 2)
        self.assertIn('drift', out)
        write(self.dir, 'src/calc.py', self.CODE.replace('    t = 0', '    # start at zero\n    t = 0'))
        code, out, _ = self.sor('status')
        self.assertEqual(code, 0, out)
        self.assertIn('agree', out)

    def test_re_indenting_the_whole_function_is_not_drift(self):
        self.sor('lock', '--all')
        write(self.dir, 'src/calc.py', self.CODE.replace('    ', '  '))
        self.assertEqual(self.sor('status')[0], 0)

    def test_a_project_without_a_type_of_its_own_hashes_as_before(self):
        write(self.dir, 'src/calc.py', '')
        write(self.dir, 'src/calc.ts', '// @clause calc/sum\nexport const total = (a: number[]) => a.reduce((x, y) => x + y, 0);\n// @clause end\n')
        project = Project(self.dir)
        scan = Scan(project)
        self.assertFalse(scan.has_own_rules())
        self.assertEqual(scan.code_hashes(), scan.code_hashes(legacy=True))
        self.assertEqual(lockfile.old_rule_keys(lockfile.snapshot(project, scan), scan), {})


class TestALockMadeUnderTheOldRule(Project1):
    def old_lock(self):
        """The lock the tool wrote before the rule followed the file type: code hashes made with one rule for every file."""
        project = Project(self.dir)
        scan = Scan(project)
        entries = lockfile.snapshot(project, scan)
        for key, h in scan.code_hashes(legacy=True).items():
            entries[key]['code'] = h
        lockfile.write(project, entries)
        return entries

    def test_it_is_not_drift_and_status_says_what_to_do(self):
        self.old_lock()
        code, out, _ = self.sor('status')
        self.assertEqual(code, 0, out)
        self.assertIn('agree', out)
        self.assertIn('1 locked code hash(es)', out)
        self.assertIn('sor lock --rehash', out)

    def test_rehash_rewrites_only_the_code_hash_and_accepts_nothing(self):
        before = self.old_lock()
        code, out, _ = self.sor('lock', '--rehash')
        self.assertEqual(code, 0, out)
        self.assertIn('rewrote 1 code hash(es)', out)
        after = self.entries()
        self.assertEqual({k: {f: v for f, v in e.items() if f != 'code'} for k, e in after.items()},
                         {k: {f: v for f, v in e.items() if f != 'code'} for k, e in before.items()})
        self.assertEqual(after['calc/sum']['code'], self.hashes()['calc/sum'])
        self.assertNotEqual(after['calc/sum']['code'], before['calc/sum']['code'])
        self.assertNotIn('locked code hash', self.sor('status')[1])
        self.assertIn('nothing to rewrite', self.sor('lock', '--rehash')[1])

    def test_after_the_rewrite_a_line_moved_into_a_loop_is_seen(self):
        self.old_lock()
        self.sor('lock', '--rehash')
        write(self.dir, 'src/calc.py', self.CODE.replace('    return t', '        return t'))
        self.assertEqual(self.sor('status')[0], 2)

    def test_a_change_the_old_rule_also_saw_stays_a_change_and_is_not_rewritten(self):
        self.old_lock()
        write(self.dir, 'src/calc.py', self.CODE.replace('t += i', 't -= i'))
        code, out, _ = self.sor('status')
        self.assertEqual(code, 2, out)
        self.assertIn('drift', out)
        before = flows.lock_bytes(self.dir)
        self.assertIn('nothing to rewrite', self.sor('lock', '--rehash')[1])
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_until_the_rewrite_a_change_only_the_old_rule_ignores_is_not_seen(self):
        # the cost of the migration, said in the status note: the old hash cannot tell the dedent from the original
        self.old_lock()
        write(self.dir, 'src/calc.py', self.CODE.replace('    return t', '        return t'))
        self.assertEqual(self.sor('status')[0], 0)

    def test_rehash_takes_nothing_else(self):
        self.old_lock()
        for extra in (['calc'], ['--all'], ['--run-tests'], ['--allow-incomplete']):
            with self.subTest(extra):
                code, out, _ = self.sor('lock', '--rehash', *extra)
                self.assertEqual(code, 2, out)
                self.assertIn('takes nothing else', out)

    def test_a_scoped_lock_on_an_old_lock_writes_the_new_hash_for_what_it_locks(self):
        self.old_lock()
        flows.replace_in(os.path.join(self.spec, 'calc.md'), 'adds every item', 'adds every item and nothing else')
        write(self.dir, 'src/calc.py', self.CODE)
        self.assertEqual(self.sor('lock', 'calc/sum')[0], 0)
        self.assertEqual(self.entries()['calc/sum']['code'], self.hashes()['calc/sum'])

    def test_a_project_of_other_types_has_nothing_to_rewrite_and_its_lock_stays_the_same_bytes(self):
        write(self.dir, 'src/calc.py', '')
        write(self.dir, 'src/calc.ts', '// @clause calc/sum\nexport const total = 1;\n// @clause end\n')
        self.sor('lock', '--all')
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', '--rehash')
        self.assertEqual(code, 0)
        self.assertIn('nothing to rewrite', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)


if __name__ == '__main__':
    unittest.main()
