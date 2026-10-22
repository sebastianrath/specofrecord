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
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                          # noqa: E402
import test_sor_flows as flows                   # noqa: E402
from sorlib import hook                         # noqa: E402
from sorlib import lock as lockfile              # noqa: E402
from sorlib import markers                       # noqa: E402
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

    def test_the_c_family_is_listed_with_the_multi_line_strings_it_has(self):
        for rel, style in (('a.c', 'c'), ('a.h', 'c'), ('a.cpp', 'c'), ('a.mm', 'c'), ('a.rs', 'c'), ('a.php', 'c'), ('a.html', 'c'),
                           ('a.css', 'c'), ('a.json', 'c'), ('a.ts', 'c+tick'), ('a.tsx', 'c+tick'), ('a.js', 'c+tick'), ('a.mjs', 'c+tick'),
                           ('a.go', 'c+rawtick'), ('a.java', 'c+triple'), ('a.kt', 'c+triple'), ('a.swift', 'c+triple'), ('a.cs', 'c+triple'),
                           ('a.dart', 'c+triple+triple1'), ('a.scala', 'c-keep+triple')):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), style)

    def test_types_where_indentation_is_meaning_keep_it(self):
        for rel, style in (('a.hs', 'dash-keep'), ('a.elm', 'dash-keep'), ('a.nim', 'hash-keep'), ('a.coffee', 'hash-keep'),
                           ('a.fs', 'c-keep'), ('a.yml', 'safe'), ('a.yaml', 'safe'), ('Makefile', 'safe'), ('a.pyx', 'python'),
                           ('rules.bzl', 'python'), ('BUILD', 'python'), ('pkg/WORKSPACE', 'python')):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), style)

    def test_a_file_known_by_its_name(self):
        for rel, style in (('Dockerfile', 'hash'), ('dir/dockerfile', 'hash'), ('Rakefile', 'hash'), ('CMakeLists.txt', 'hash')):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), style)

    def test_a_script_called_build_is_not_bazel(self):
        for rel in ('scripts/build', 'build', 'Build', 'workspace', 'dir/Workspace'):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), 'safe')

    def test_everything_not_listed_is_safe(self):
        for rel in ('a.erl', 'a.unknown', 'noext', 'dir.py/file', 'a.b/c', 'a.txt', 'a.xyz'):
            with self.subTest(rel):
                self.assertEqual(style_of(rel), 'safe')

    def test_an_unknown_style_is_refused_and_not_guessed(self):
        with self.assertRaises(ValueError):
            normalized(['x'], 'cc')

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


class TestPythonStrings(unittest.TestCase):
    """What the scanner keeps open from one line to the next decides which later lines count as statements."""

    def test_a_string_continued_by_a_backslash_does_not_blind_the_lines_after_it(self):
        # the second line is text, so its bracket opens nothing and the statements after it still carry their depth
        lines = ["x = 'a\\", "(b'", 'for i in y:', '    f(i)', '    return t']
        moved = lines[:-1] + ['        return t']
        self.assertEqual(normalized(lines, 'python').split('\n')[-1], '1:return t')
        self.assertNotEqual(normalized(lines, 'python'), normalized(moved, 'python'))

    def test_a_hash_line_inside_a_string_continued_by_a_backslash_is_text(self):
        lines = ["x = 'a\\", '# b\'', 'y = 1']
        self.assertIn('# b', normalized(lines, 'python'))
        self.assertNotEqual(normalized(lines, 'python'), normalized(lines[:1] + ["# c'"] + lines[2:], 'python'))

    def test_an_escaped_backslash_at_the_end_of_a_string_continues_nothing(self):
        lines = ["x = 'a\\\\'", '# note', 'y = 1']
        self.assertEqual(normalized(lines, 'python'), "0:x = 'a\\\\'\n0:y = 1")

    def test_a_multi_line_string_ends_at_its_own_three_quotes_not_at_any_three_characters(self):
        for quote in ('"', "'"):
            with self.subTest(quote):
                lines = [f'x = {quote * 3}a {quote * 2}b{quote * 3}', '# a comment', 'y = 1']
                self.assertEqual(normalized(lines, 'python'), f'0:x = {quote * 3}a {quote * 2}b{quote * 3}\n0:y = 1')

    def test_a_triple_quoted_string_that_holds_the_other_triple_goes_on(self):
        lines = ["x = \'\'\'", '"""', '# text', "\'\'\'", 'y = 1']
        self.assertIn('# text', normalized(lines, 'python'))
        self.assertIn('0:y = 1', normalized(lines, 'python'))

    def test_a_coding_cookie_is_code(self):
        self.assertNotEqual(py('# -*- coding: utf-8 -*-\nx = 1\n'), py('# -*- coding: latin-1 -*-\nx = 1\n'))
        self.assertEqual(py('# about x\nx = 1\n'), py('# about y\nx = 1\n'))


class TestPythonFStrings(unittest.TestCase):
    """An f-string has parts of code in it. Since Python 3.12 those may reuse the quote of the f-string and span lines, so the end of
    the string is not the next quote. The text is only scanned, so these run on every Python."""

    def levels(self, lines):
        return normalized(lines, 'python')

    def test_a_reused_quote_with_a_bracket_in_it_does_not_hide_the_nesting_after_it(self):
        lines = ['def clean(s):', '    t = f"{s.replace("(", "")}"', '    if t:', '        return t', '    return None']
        self.assertEqual(self.levels(lines),
                         '0:def clean(s):\n1:t = f"{s.replace("(", "")}"\n1:if t:\n2:return t\n1:return None')
        moved = lines[:-1] + ['        return None']
        self.assertNotEqual(self.levels(lines), self.levels(moved))

    def test_a_hash_in_a_reused_quote_is_not_a_comment(self):
        lines = ['t = f"{d["#"]}"', 'if t:', '    pass']
        self.assertEqual(self.levels(lines), '0:t = f"{d["#"]}"\n0:if t:\n1:pass')

    def test_a_field_may_span_lines_even_in_a_one_quote_f_string(self):
        lines = ['x = f"{', '    a +', '    b', '}"', 'if x:', '    pass']
        self.assertEqual(self.levels(lines), '0:x = f"{\na +\nb\n}"\n0:if x:\n1:pass')

    def test_a_comment_in_a_field_is_text_and_ends_with_its_line(self):
        lines = ['x = f"{', '    a  # a ) and a "', '}"', 'y = 1']
        self.assertEqual(self.levels(lines), '0:x = f"{\na # a ) and a "\n}"\n0:y = 1')

    def test_a_triple_quoted_f_string_keeps_its_lines_whatever_they_start_with(self):
        lines = ['s = f"""', '# heading {x}', '{y:>{w}}', '"""', 'z = 2']
        self.assertEqual(self.levels(lines), '0:s = f"""\n# heading {x}\n{y:>{w}}\n"""\n0:z = 2')

    def test_nested_fields_in_a_format_spec_and_nested_f_strings_close_where_they_should(self):
        lines = ['x = f"{a:{w}.{p}}" + f"{b!r:>{w}}" + f"{f"{c}"}"', 'if x:', '    pass']
        self.assertEqual(self.levels(lines), '0:x = f"{a:{w}.{p}}" + f"{b!r:>{w}}" + f"{f"{c}"}"\n0:if x:\n1:pass')

    def test_doubled_braces_and_named_escapes_are_text(self):
        for first in ('x = f"{{(}}"', 'x = f"\\N{BULLET} ("', 'x = rf"\\{a}("'):
            with self.subTest(first):
                self.assertEqual(self.levels([first, 'if x:', '    pass']), f'0:{first}\n0:if x:\n1:pass')

    def test_a_dict_or_a_lambda_in_a_field_does_not_end_it_early(self):
        lines = ['x = f"{ {"a": 1}["a"] } {(lambda y: y)(2)}"', 'if x:', '    pass']
        self.assertEqual(self.levels(lines), '0:x = f"{ {"a": 1}["a"] } {(lambda y: y)(2)}"\n0:if x:\n1:pass')

    def test_a_name_that_ends_in_f_or_t_is_not_a_prefix(self):
        for first in ('y = [1 if"(" else 2]', 'y = [not"(" and 2]'):
            with self.subTest(first):
                self.assertEqual(self.levels([first, 'z = 1']), f'0:{first}\n0:z = 1')

    def test_a_template_string_is_read_like_an_f_string(self):
        # Python 3.14, PEP 750: t, T, rt and tr prefixes, with the grammar of PEP 701
        for prefix in ('t', 'T', 'rt', 'tR', 'Tr'):
            with self.subTest(prefix):
                lines = ['def clean(s):', f'    x = {prefix}"{{s.replace("(", "")}}"', '    if x:', '        return x', '    return None']
                self.assertEqual(self.levels(lines), f'0:def clean(s):\n1:x = {prefix}"{{s.replace("(", "")}}"\n1:if x:\n2:return x\n1:return None')

    def test_f_strings_that_python_3_9_reads_are_read_as_before(self):
        lines = ["x = f'{d[\"a\"]} it\\'s' + f\"{n:>{w}}\"", 'if x:', '    pass']
        self.assertEqual(self.levels(lines), "0:x = f'{d[\"a\"]} it\\'s' + f\"{n:>{w}}\"\n0:if x:\n1:pass")


class TestTheSafeStyle(unittest.TestCase):
    """A type that is not listed: nothing is hidden except blank lines and trailing spaces. Comments are code, indentation counts."""

    def test_comments_and_spacing_inside_a_line_are_kept(self):
        self.assertEqual(py('% about it\nf()  ->  ok.\n', 'safe'), '0:% about it\n0:f()  ->  ok.')

    def test_blank_lines_and_trailing_spaces_go(self):
        self.assertEqual(py('a   \n\n   \nb\t\n', 'safe'), '0:a\n0:b')

    def test_a_piece_moved_to_other_columns_is_the_same_and_a_line_moved_inside_it_is_not(self):
        a = ['f(x) ->', '    g(x),', '    h(x).']
        self.assertEqual(normalized(a, 'safe'), normalized(['  ' + l for l in a], 'safe'))
        self.assertEqual(normalized(a, 'safe'), '0:f(x) ->\n4:g(x),\n4:h(x).')
        self.assertNotEqual(normalized(a, 'safe'), normalized(['f(x) ->', 'g(x),', '    h(x).'], 'safe'))

    def test_the_smallest_indentation_of_the_kept_lines_is_the_base(self):
        self.assertEqual(normalized(['    a', '  b', '      c'], 'safe'), '2:a\n0:b\n4:c')

    def test_tabs_count_as_eight_columns(self):
        self.assertEqual(normalized(['a', '\tb'], 'safe'), '0:a\n8:b')


class TestTheStylesThatKeepIndentation(unittest.TestCase):
    def test_a_haskell_line_moved_out_of_a_do_block_is_a_change(self):
        a = ['main = do', '  putStrLn "a"', '  putStrLn "b"']
        b = ['main = do', '  putStrLn "a"', 'putStrLn "b"']
        self.assertNotEqual(normalized(a, 'dash-keep'), normalized(b, 'dash-keep'))
        self.assertEqual(normalized(a, 'dash-keep'), '0:main = do\n2:putStrLn "a"\n2:putStrLn "b"')

    def test_their_comment_lines_still_go_and_a_comment_does_not_shift_the_columns(self):
        self.assertEqual(normalized(['      -- about it', 'main = do', '  f'], 'dash-keep'), '0:main = do\n2:f')

    def test_yaml_comments_are_code_because_a_hash_line_in_a_block_scalar_is_text(self):
        a = ['key: |', '  # not a comment', '  text']
        self.assertEqual(normalized(a, 'safe'), '0:key: |\n2:# not a comment\n2:text')

    def test_a_nim_hash_line_is_a_comment_and_its_nesting_counts(self):
        self.assertEqual(normalized(['# about', 'proc f() =', '  echo 1'], 'hash-keep'), '0:proc f() =\n2:echo 1')
        self.assertNotEqual(normalized(['proc f() =', '  echo 1'], 'hash-keep'), normalized(['proc f() =', 'echo 1'], 'hash-keep'))

    def test_a_scala_block_and_an_fsharp_block_keep_their_columns(self):
        self.assertEqual(normalized(['// c', 'def f =', '  g'], 'c-keep'), '0:def f =\n2:g')


class TestMultiLineStrings(unittest.TestCase):
    """A line inside a multi-line string is text, whatever it looks like. Only that changes: blank lines, indentation and runs of
    spaces inside such a string are not seen, as in a Python docstring."""

    def test_a_comment_looking_line_in_a_template_literal_is_part_of_the_hash(self):
        a = ['const sql = `', '// the query', 'SELECT 1', '`;']
        self.assertEqual(normalized(a, 'c+tick'), 'const sql = `\n// the query\nSELECT 1\n`;')
        self.assertNotEqual(normalized(a, 'c+tick'), normalized(['const sql = `', '// the other query', 'SELECT 1', '`;'], 'c+tick'))
        self.assertEqual(normalized(a, 'c'), 'const sql = `\nSELECT 1\n`;')          # the old rule, for a style without strings

    def test_html_comments_and_block_comments_inside_a_string_are_text_too(self):
        for line in ('<!-- hello -->', '/* text */'):
            with self.subTest(line):
                a = ['q := `', line, 'x', '`']
                b = ['q := `', line.replace('hello', 'bye').replace('text', 'other'), 'x', '`']
                self.assertNotEqual(normalized(a, 'c+tick'), normalized(b, 'c+tick'))

    def test_after_the_string_a_comment_is_a_comment_again(self):
        lines = ['const a = `x', '// text', '`;', '// a comment', 'const b = 1;']
        self.assertEqual(normalized(lines, 'c+tick'), 'const a = `x\n// text\n`;\nconst b = 1;')

    def test_a_string_that_closes_on_its_line_is_no_multi_line_string(self):
        lines = ['const a = `x ${b} y`;', '// a comment', 'const c = 1;']
        self.assertEqual(normalized(lines, 'c+tick'), 'const a = `x ${b} y`;\nconst c = 1;')

    def test_triple_quotes_for_java_kotlin_swift_scala_and_csharp(self):
        a = ['String s = """', '    // not a comment', '    """;', '// a comment']
        self.assertEqual(normalized(a, 'c+triple'), 'String s = """\n// not a comment\n""";')

    def test_dart_has_triple_single_quotes_as_well(self):
        a = ["var s = \'\'\'", '// not a comment', "\'\'\';"]
        self.assertEqual(normalized(a, 'c+triple+triple1'), "var s = \'\'\'\n// not a comment\n\'\'\';")
        self.assertEqual(normalized(a, 'c+triple'), "var s = \'\'\'\n\'\'\';")      # a style without them does not see it

    def test_a_backslash_makes_the_next_quote_no_closer(self):
        # a double-quoted string with an escaped quote and a backtick in it, then a template literal with an escaped backtick
        a = ['const s = "a \\" ` b";', '// a comment', 'const t = 1;']
        self.assertEqual(normalized(a, 'c+tick'), 'const s = "a \\" ` b";\nconst t = 1;')
        b = ['const p = `a \\` b`;', '// a comment', 'const t = 1;']
        self.assertEqual(normalized(b, 'c+tick'), 'const p = `a \\` b`;\nconst t = 1;')
        c = ["const q = 'it\\'s `';", '// a comment', 'const t = 1;']
        self.assertEqual(normalized(c, 'c+tick'), "const q = 'it\\'s `';\nconst t = 1;")

    def test_in_a_go_raw_string_a_backslash_is_just_a_backslash(self):
        lines = ['p := `C:\\`', 'q := `', '// x', '`', '// a comment', 'r := 1']
        self.assertEqual(normalized(lines, 'c+rawtick'), 'p := `C:\\`\nq := `\n// x\n`\nr := 1')
        # in a template literal the same backslash escapes the backtick, so that string goes on
        self.assertEqual(normalized(['const p = `C:\\`;', '// a comment', 'const r = 1;'], 'c+tick'), 'const p = `C:\\`;\n// a comment\nconst r = 1;')

    def test_a_backtick_in_a_comment_does_not_open_a_string(self):
        # editors/vscode/src/extension.js has a trailing comment `// inside a ``` block: ...`
        lines = ['let fence = false;   // inside a ``` block: shaded', '// a comment', 'const x = 1;']
        self.assertEqual(normalized(lines, 'c+tick'), 'let fence = false; // inside a ``` block: shaded\nconst x = 1;')

    def test_a_backtick_in_a_block_comment_or_in_another_string_does_not_open_one(self):
        lines = ['/* a ` in a block', '   comment */', 'const s = "a `";', '// a comment', 'const t = 1;']
        self.assertEqual(normalized(lines, 'c+tick'), '/* a ` in a block\ncomment */\nconst s = "a `";\nconst t = 1;')

    def test_a_backtick_on_a_later_line_of_a_block_comment_opens_nothing(self):
        lines = ['/* a block', '   with a ` in it */', '// a comment', 'const t = 1;']
        self.assertEqual(normalized(lines, 'c+tick'), '/* a block\nwith a ` in it */\nconst t = 1;')

    def test_an_apostrophe_is_no_string(self):
        lines = ["let a = x; // it's", "// a comment", "const t = 1;"]
        self.assertEqual(normalized(lines, 'c+tick'), "let a = x; // it's\nconst t = 1;")
        lines = ["fn f<'a>(x: &'a str) {}", '// a comment', 'let b = 1;']
        self.assertEqual(normalized(lines, 'c+tick'), "fn f<'a>(x: &'a str) {}\nlet b = 1;")

    def test_blank_lines_and_runs_of_spaces_inside_the_string_are_not_seen(self):
        a = ['const a = `x', '', '   y    z', '`;']
        self.assertEqual(normalized(a, 'c+tick'), 'const a = `x\ny z\n`;')

    def test_a_style_without_strings_gives_the_same_text_as_before_for_code_without_any(self):
        code = ['  // note', 'export const total = (items: number[]) => {', '    return items.reduce((a, b) => a + b, 0);   ', '};', '/* block */']
        for style in ('c+tick', 'c+triple', 'c+triple+triple1'):
            with self.subTest(style):
                self.assertEqual(normalized(code, style), normalized(code, 'c'))
        self.assertEqual(hashed(code, 'c+tick'), '5502253e7c35')


class TestAPieceThatDipsBelowItsFirstLine(unittest.TestCase):
    """A region is often part of a block: it starts inside a method and goes on with a line of the class around it."""
    PIECE = ['        a = 1', '    b = 2', '        c = 3']

    def test_the_lines_are_counted_from_the_first_and_may_be_below_it(self):
        self.assertEqual(normalized(self.PIECE, 'python'), '0:a = 1\n-1:b = 2\n0:c = 3')

    def test_moving_the_first_line_out_one_level_is_a_change(self):
        out = ['    a = 1', '    b = 2', '        c = 3']
        self.assertNotEqual(normalized(self.PIECE, 'python'), normalized(out, 'python'))

    def test_moving_the_last_line_out_is_a_change(self):
        self.assertNotEqual(normalized(self.PIECE, 'python'), normalized(self.PIECE[:2] + ['    c = 3'], 'python'))

    def test_the_same_piece_in_other_columns_is_not_a_change(self):
        for extra in (' ', '    ', '\t'):
            with self.subTest(repr(extra)):
                self.assertEqual(normalized(self.PIECE, 'python'), normalized([extra + l for l in self.PIECE], 'python'))
        self.assertEqual(normalized(self.PIECE, 'python'), normalized([l.replace('    ', '  ') for l in self.PIECE], 'python'))


class TestFilesWithHashComments(unittest.TestCase):
    def test_a_hash_line_inside_a_here_document_is_text_and_the_comments_after_it_are_comments_again(self):
        a = 'cat <<EOF\n# not a comment\n  text\nEOF\n# a comment\necho hi\n'
        self.assertIn('# not a comment', py(a, 'hash'))
        self.assertNotEqual(py(a, 'hash'), py(a.replace('# not a comment', '# other'), 'hash'))
        self.assertEqual(py(a, 'hash'), py(a.replace('# a comment', '# another'), 'hash'))

    def test_quoted_and_indented_here_document_words_end_where_their_word_is(self):
        for opener, closer in (('<<"EOF"', 'EOF'), ("<<'EOF'", 'EOF'), ('<<-EOF', '\tEOF'), ('<<~EOS', 'EOS')):
            with self.subTest(opener):
                a = f'cat {opener}\n# text\n{closer}\n# comment\nls\n'
                self.assertIn('# text', py(a, 'hash'))
                self.assertNotIn('# comment', py(a, 'hash'))

    def test_a_here_string_opens_no_here_document(self):
        self.assertNotIn('# c', py('cat <<<"x"\n# c\necho 1\n', 'hash'))

    def test_a_hash_line_in_a_string_that_goes_over_several_lines_is_text(self):
        a = 'echo "a\n# inside\nb"\n# outside\nls\n'
        self.assertIn('# inside', py(a, 'hash'))
        self.assertNotIn('# outside', py(a, 'hash'))

    def test_a_toml_multi_line_string_keeps_its_hash_lines(self):
        a = 'text = """\n# a line\n"""\n# a comment\nn = 1\n'
        self.assertIn('# a line', py(a, 'hash'))
        self.assertNotIn('# a comment', py(a, 'hash'))

    def test_a_ruby_interpolation_line_in_a_here_document_is_text(self):
        a = 'puts <<~TEXT\n  #{name}\n  # not a comment\nTEXT\nputs 1\n'
        self.assertIn('#{name}', py(a, 'hash'))
        self.assertIn('# not a comment', py(a, 'hash'))

    def test_an_apostrophe_in_a_comment_opens_nothing(self):
        a = "# don't\nls  # it's here\n# isn't\nwc\n"
        self.assertEqual(py(a, 'hash'), 'ls # it\'s here\nwc')

    def test_a_hash_inside_a_word_is_not_a_comment(self):
        self.assertEqual(py('echo ${#list}\n# c\nls\n', 'hash'), 'echo ${#list}\nls')

    def test_a_quote_nobody_closes_keeps_the_lines_after_it_as_code_rather_than_hide_them(self):
        self.assertEqual(py("echo 'x\n# c\n", 'hash'), "echo 'x\n# c")

    def test_a_magic_comment_is_code(self):
        self.assertNotEqual(py('# frozen_string_literal: true\nx = 1\n', 'hash'), py('# frozen_string_literal: false\nx = 1\n', 'hash'))

    def test_other_c_family_comment_forms_are_code_in_a_hash_language(self):
        self.assertIn('// a', py('// a\nx\n', 'hash'))


class TestFilesWithDashComments(unittest.TestCase):
    def test_the_comment_forms_the_old_rule_dropped_are_still_dropped(self):
        # SQL: a one-line /* */ comment was never a change before the rule followed the file type
        self.assertEqual(py('/* about */\nselect 1;\n', 'dash'), py('select 1;\n', 'dash'))
        self.assertEqual(py('-- about\nselect 1;\n', 'dash'), py('select 1;\n', 'dash'))
        self.assertEqual(py('---- Section ----\nselect 1;\n', 'dash'), py('select 1;\n', 'dash'))

    def test_a_line_that_starts_with_a_comment_and_goes_on_with_code_is_code(self):
        self.assertNotEqual(py('/* a */ select 1; /* b */\n', 'dash'), py('', 'dash'))
        self.assertNotEqual(py('/* a */ select 1; /* b */\n', 'dash'), py('/* a */ select 2; /* b */\n', 'dash'))

    def test_a_haskell_operator_that_starts_with_two_dashes_is_code(self):
        self.assertIn('--> g', py('f\n  --> g\n', 'dash'))
        self.assertIn('--| h', py('f\n  --| h\n', 'dash'))

    def test_a_haskell_pragma_is_code_and_a_block_comment_is_not(self):
        self.assertIn('{-# LANGUAGE Strict #-}', py('{-# LANGUAGE Strict #-}\n{- about -}\nx = 1\n', 'dash'))
        self.assertNotIn('about', py('{- about -}\nx = 1\n', 'dash'))

    def test_double_slash_is_not_a_comment_there(self):
        self.assertIn('// [(1, 2)]', py('arr\n  // [(1, 2)]\n', 'dash'))   # Haskell's array update


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
        self.assertEqual(scan.code_hashes(), scan.code_hashes(legacy=True))     # no multi-line string: the same hash as the old rule
        self.assertEqual(lockfile.old_rule_keys(lockfile.snapshot(project, scan), scan), {})


class TestHashesAreWorkedOutOnce(Project1):
    def test_a_scan_normalizes_its_code_once_however_often_it_is_asked(self):
        scan = Scan(Project(self.dir))
        with mock.patch.object(markers, 'normalized', wraps=normalized) as spy:
            first = scan.code_hashes()
            calls = spy.call_count
            self.assertEqual(scan.code_hashes(), first)
        self.assertGreater(calls, 0)
        self.assertEqual(spy.call_count, calls)
        first['calc/sum'] = 'changed by the caller'
        self.assertNotEqual(scan.code_hashes()['calc/sum'], 'changed by the caller')

    def test_the_old_rule_is_not_worked_out_while_every_hash_agrees(self):
        self.sor('lock', '--all')
        project = Project(self.dir)
        scan = Scan(project)
        with mock.patch.object(scan, 'code_hashes', wraps=scan.code_hashes) as spy:
            self.assertEqual(lockfile.old_rule_keys(lockfile.read(project), scan), {})
        self.assertEqual([c.kwargs for c in spy.call_args_list], [{}])


class TestAScopedLockOfSharedCodeOnAnOldLock(flows.Flow):
    CODE = '# @clause calc/sum calc/avg\ndef total(items):\n    t = 0\n    for i in items:\n        t += i\n    return t\n# @clause end\n'

    def setUp(self):
        super().setUp()
        self.project({'calc': doc('Calc', 'Adds numbers.', rules=['- **sum** - The total adds every item.',
                                                                  '- **avg** - The mean divides the total.'],
                                  tests=['- **sum** - adds.', '  manual: look', '- **avg** - divides.', '  manual: look'])})
        write(self.dir, 'src/calc.py', self.CODE)
        project = Project(self.dir)
        scan = Scan(project)
        entries = lockfile.snapshot(project, scan)
        for key, h in scan.code_hashes(legacy=True).items():   # a lock made before the rule followed the file type
            entries[key]['code'] = h
        lockfile.write(project, entries)

    def test_a_clause_that_shares_the_code_and_has_no_change_of_its_own_is_not_dragged_in(self):
        flows.replace_in(os.path.join(self.spec, 'calc.md'), 'adds every item', 'adds every item, and only items')
        code, out, _ = self.sor('lock', 'calc/sum')
        self.assertEqual(code, 0, out)
        self.assertNotIn('locking with them', out)
        self.assertEqual(json.loads(flows.lock_bytes(self.dir))['calc/avg']['code'],
                         Scan(Project(self.dir)).code_hashes(legacy=True)['calc/avg'])   # still the hash it had

    def test_rehash_without_a_lock_says_there_is_none(self):
        os.remove(os.path.join(self.spec, 'sor-lock.json'))
        code, out, _ = self.sor('lock', '--rehash')
        self.assertEqual(code, 0, out)
        self.assertIn('no sor-lock.json yet', out)
        self.assertNotIn('follows the rule', out)


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

    def test_a_manual_check_a_person_confirmed_survives_the_upgrade(self):
        self.assertEqual(self.sor('lock', '--all', '--confirm', 'calc/test:sum')[0], 0)
        self.assertEqual(self.entries()['calc/test:sum']['result'], 'checked')
        entries = self.entries()
        for key, h in self.hashes(legacy=True).items():
            entries[key]['code'] = h
        lockfile.write(Project(self.dir), entries)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.assertEqual(self.entries()['calc/test:sum']['result'], 'checked')

    def test_the_edit_guard_reads_an_old_lock_as_status_does_and_changes_with_the_rewrite(self):
        self.old_lock()
        comment = lambda: flows.reason(hook.pre_edit(flows.edit(self.code, '    t = 0', '    # start at zero\n    t = 0')))
        moved = lambda: flows.reason(hook.pre_edit(flows.edit(self.code, '    return t', '        return t')))
        # until the rewrite it sees what the old tool saw: a comment edit is a change, a line moved into a loop is not (SPEC §11)
        self.assertIn('Clauses come first', comment())
        self.assertIsNone(moved())
        self.assertEqual(self.sor('lock', '--rehash')[0], 0)
        self.assertIsNone(comment())
        self.assertIn('Clauses come first', moved())

    def test_a_clause_with_python_and_typescript_code_is_upgraded_as_one_and_still_sees_both_sides(self):
        ts = write(self.dir, 'src/calc.ts', '// @clause calc/sum\nexport const total = 1;\n// @clause end\n')
        self.old_lock()
        code, out, _ = self.sor('status')
        self.assertEqual(code, 0, out)
        self.assertIn('1 locked code hash(es)', out)
        flows.replace_in(ts, 'total = 1', 'total = 2')
        self.assertEqual(self.sor('status')[0], 2)                      # the TypeScript side moved
        flows.replace_in(ts, 'total = 2', 'total = 1')
        self.assertEqual(self.sor('lock', '--rehash')[0], 0)
        self.assertEqual(self.entries()['calc/sum']['code'], self.hashes()['calc/sum'])
        flows.replace_in(self.code, '    return t', '        return t')
        self.assertEqual(self.sor('status')[0], 2)                      # and the Python side now counts its nesting

    def test_a_file_that_gained_a_string_rule_migrates_like_python_did(self):
        write(self.dir, 'src/calc.py', '')
        q = '// @clause calc/sum\nconst q = `\n// the query\nSELECT 1\n`;\n// @clause end\n'
        write(self.dir, 'src/q.ts', q)
        self.old_lock()
        code, out, _ = self.sor('status')
        self.assertEqual(code, 0, out)                      # the old rule did not see the line, so it is no change
        self.assertIn('1 locked code hash(es)', out)
        self.assertEqual(self.sor('lock', '--rehash')[0], 0)
        self.assertEqual(self.sor('status')[0], 0)
        write(self.dir, 'src/q.ts', q.replace('the query', 'the other query'))
        self.assertEqual(self.sor('status')[0], 2)          # and now it is one

    def test_a_file_that_moved_to_the_safe_style_migrates_and_then_sees_its_nesting(self):
        write(self.dir, 'src/calc.py', '')
        y = '# @clause calc/sum\nkey:\n  child: 1\n  other: 2\n# @clause end\n'
        write(self.dir, 'src/c.yml', y)
        self.old_lock()
        self.assertEqual(self.sor('status')[0], 0)
        self.assertEqual(self.sor('lock', '--rehash')[0], 0)
        write(self.dir, 'src/c.yml', y.replace('  other: 2', 'other: 2'))
        self.assertEqual(self.sor('status')[0], 2)          # moved out of the block: the old rule could not see it

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
