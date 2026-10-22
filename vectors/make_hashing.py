"""Writes vectors/hashing.json, the rows any implementation of the tool runs (see README.md).

    python3 vectors/make_hashing.py           write the file
    python3 vectors/make_hashing.py --check   exit 1 when the file is not what this script writes

The expected texts are written here by hand, and every hash is computed with hashlib alone, never with the tool, so those rows say what
the rule is and do not just repeat what the tool does. The rows that list the table of types (a row for every extension in it) come from
the tool's own table: they cannot prove the table right, they stop it changing without the file changing.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from sorlib import markers as _tool   # noqa: E402  (only for the table of types)

def sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()[:12]

def norm(name, style, lines, expected, note=None):
    row = {'name': name, 'style': style, 'lines': lines, 'normalized': expected}
    if note:
        row['note'] = note
    return row

N = []
# --- C family: the default; indentation never counts
N.append(norm('c: the TypeScript row whose hash was pinned before the rule followed the file type', 'c',
    ['  // note', 'export const total = (items: number[]) => {', '    return items.reduce((a, b) => a + b, 0);   ', '};', '', '/* block */'],
    'export const total = (items: number[]) => {\nreturn items.reduce((a, b) => a + b, 0);\n};'))
N.append(norm('c: `#include` and `#define` are code in C', 'c',
    ['#include <stdio.h>', '#define N 3', '  int main(void) {', '      return  N;', '  }'],
    '#include <stdio.h>\n#define N 3\nint main(void) {\nreturn N;\n}'))
N.append(norm('c: html keeps the spaces inside quotes and drops a comment line', 'c',
    ['<!-- c -->', '<p   class="a  b">hi   there</p>'], '<p class="a  b">hi there</p>'))
N.append(norm('c: spaces inside quotes stay as written, outside they collapse', 'c', ['x  =  "a   b"  +  \'c  d\''], 'x = "a   b" + \'c  d\''))
N.append(norm('c: a comment after code is part of its line', 'c', ['a();  // note'], 'a(); // note'))
N.append(norm('c: a line that starts with /* and ends with */ is a comment even when code sits between', 'c',
    ['/* a */ b(); /* c */', 'd();'], 'd();', 'known limit, pinned because locks depend on it'))
N.append(norm('c: blank lines and tabs go, lines keep their order', 'c', ['\tone();', '', '\t\ttwo();', '   '], 'one();\ntwo();'))
# --- Python: nesting counts, in levels
loop = ['def total(items):', '    t = 0', '    for i in items:', '        t += i', '    return t']
loop_n = '0:def total(items):\n1:t = 0\n1:for i in items:\n2:t += i\n1:return t'
N.append(norm('python: every statement carries its depth in levels', 'python', loop, loop_n))
N.append(norm('python: two spaces instead of four is the same', 'python', [l.replace('    ', '  ') for l in loop], loop_n))
N.append(norm('python: eight spaces instead of four is the same', 'python', [l.replace('    ', '        ') for l in loop], loop_n))
N.append(norm('python: tabs count as eight columns and a level each', 'python', ['def f():', '\treturn 1'], '0:def f():\n1:return 1'))
N.append(norm('python: a line moved into the loop is a different text', 'python',
    ['def total(items):', '    t = 0', '    for i in items:', '        t += i', '        return t'],
    '0:def total(items):\n1:t = 0\n1:for i in items:\n2:t += i\n2:return t'))
N.append(norm('python: comment-only and blank lines go, a comment after code stays', 'python',
    ['# about it', '', 'x = 1  # one', '    # indented comment', 'y = 2'], '0:x = 1 # one\n0:y = 2'))
N.append(norm('python: else and elif sit at the level of their if', 'python',
    ['if x:', '    a()', 'elif y:', '    b()', 'else:', '    c()'], '0:if x:\n1:a()\n0:elif y:\n1:b()\n0:else:\n1:c()'))
N.append(norm('python: lines inside brackets carry no depth and a comment line there goes', 'python',
    ['x = foo(', '        1,   ', '   # between', '    2,', ')', 'y = 3'], '0:x = foo(\n1,\n2,\n)\n0:y = 3'))
N.append(norm('python: a backslash continuation carries no depth', 'python',
    ['total = a + \\', '        b', 'next = 1'], '0:total = a + \\\nb\n0:next = 1'))
N.append(norm('python: brackets and hashes inside strings are text', 'python',
    ['x = "(" + \'#\'', 'y = 1'], '0:x = "(" + \'#\'\n0:y = 1'))
N.append(norm('python: a # line inside a multi-line string is text', 'python',
    ['DOC = """', '# Heading', 'text', '"""', 'run()'], '0:DOC = """\n# Heading\ntext\n"""\n0:run()'))
N.append(norm('python: a string a backslash continues does not blind the lines after it', 'python',
    ['def f(items):', '    for item in items:', "        x = 'a\\", "(b'", '        y = 1', '        z = 2', '    return 3'],
    "0:def f(items):\n1:for item in items:\n2:x = 'a\\\n(b'\n2:y = 1\n2:z = 2\n1:return 3"))
N.append(norm('python: an escaped backslash at the end of a string continues nothing', 'python',
    ["x = 'a\\\\'", '# note', 'y = 1'], "0:x = 'a\\\\'\n0:y = 1"))
N.append(norm('python: a tab goes to the next multiple of eight columns, also after spaces', 'python',
    ['if x:', '  \ty', '          z'], '0:if x:\n1:y\n2:z'))
N.append(norm('python: a piece that dips below its first line counts a level below it', 'python',
    ['        a = 1', '    b = 2', '        c = 3'], '0:a = 1\n-1:b = 2\n0:c = 3'))
N.append(norm('python: the same piece in other columns is the same', 'python',
    ['  a = 1', 'b = 2', '  c = 3'], '0:a = 1\n-1:b = 2\n0:c = 3'))
N.append(norm('python: a shebang and a coding cookie are code', 'python',
    ['#!/usr/bin/env python3', '# -*- coding: latin-1 -*-', '# plain', 'x = 1'],
    '0:#!/usr/bin/env python3\n0:# -*- coding: latin-1 -*-\n0:x = 1'))
N.append(norm('python: an f-string that reuses its quote in a field, with a bracket in it, does not hide the nesting after it', 'python',
    ['def clean(s):', '    t = f"{s.replace("(", "")}"', '    if t:', '        return t', '    return None'],
    '0:def clean(s):\n1:t = f"{s.replace("(", "")}"\n1:if t:\n2:return t\n1:return None'))
N.append(norm('python: a field of an f-string may span lines, and its lines carry no depth', 'python',
    ['x = f"{', '    a +', '    b', '}"', 'if x:', '    pass'], '0:x = f"{\na +\nb\n}"\n0:if x:\n1:pass'))
N.append(norm('python: fields nested in a format spec close where they should', 'python',
    ['x = f"{a:{w}.{p}}"', 'if x:', '    pass'], '0:x = f"{a:{w}.{p}}"\n0:if x:\n1:pass'))
N.append(norm('python: a # in a format spec is text, not a comment', 'python',
    ['x = f"{n:#x}"', 'if x:', '    pass'], '0:x = f"{n:#x}"\n0:if x:\n1:pass'))
N.append(norm('python: a quote in a format spec is text, not a string', 'python',
    ['x = f"{n:\'>10}"', 'if x:', '    pass'], '0:x = f"{n:\'>10}"\n0:if x:\n1:pass'))
N.append(norm('python: in a raw f-string a backslash before a brace does not hide the field', 'python',
    ['x = rf"\\{d["("]}"', 'if x:', '    pass'], '0:x = rf"\\{d["("]}"\n0:if x:\n1:pass'))
N.append(norm('python: in an f-string that is not raw a backslash before a brace is text and the brace opens a field', 'python',
    ['x = f"\\{d["("]}"', 'if x:', '    pass'], '0:x = f"\\{d["("]}"\n0:if x:\n1:pass'))
N.append(norm('python: a backslash at the end of the text of an f-string goes on to the next line', 'python',
    ['x = f"ab\\', '# still text {y}"', 'z = 1'], '0:x = f"ab\\\n# still text {y}"\n0:z = 1'))
N.append(norm('python: \\N{ in an f-string reads a name up to the next }', 'python',
    ['x = f"\\N{ab', 'y = 1'], '0:x = f"\\N{ab\n0:y = 1'))
N.append(norm('python: a string nobody closes ends with its line', 'python', ['x = "abc', '# a note', 'y = 1'], '0:x = "abc\n0:y = 1'))
N.append(norm('python: a triple-quoted f-string keeps its lines, whatever they start with', 'python',
    ['s = f"""', '# heading {x}', '{y:>{w}}', '"""', 'z = 2'], '0:s = f"""\n# heading {x}\n{y:>{w}}\n"""\n0:z = 2'))
N.append(norm('python: a name that ends in f is not a string prefix', 'python',
    ['y = [1 if"(" else 2]', 'z = 1'], '0:y = [1 if"(" else 2]\n0:z = 1'))
N.append(norm('python: a name that ends in f is not a string prefix, also when the string has a brace', 'python',
    ['y = [1 if"{" else 2]', 'z = 1'], '0:y = [1 if"{" else 2]\n0:z = 1'))
N.append(norm('python: a template string (Python 3.14) is read like an f-string', 'python',
    ['def clean(s):', '    x = t"{s.replace("(", "")}"', '    if x:', '        return x', '    return None'],
    '0:def clean(s):\n1:x = t"{s.replace("(", "")}"\n1:if x:\n2:return x\n1:return None'))
# --- hash types: `#` lines are comments, indentation does not count
N.append(norm('hash: a shebang is code, a comment line is not', 'hash', ['#!/bin/sh', '# a comment', 'ls'], '#!/bin/sh\nls'))
N.append(norm('hash: indentation does not count', 'hash', ['if true; then', '        echo there', 'fi'], 'if true; then\necho there\nfi'))
N.append(norm('hash: a # line inside a here-document is text, and the comments after it are comments again', 'hash',
    ['cat <<EOF', '# not a comment', '  text', 'EOF', '# a comment', 'echo hi'], 'cat <<EOF\n# not a comment\ntext\nEOF\necho hi'))
N.append(norm('hash: a here-string opens no here-document', 'hash', ['cat <<<"x"', '# c', 'echo 1'], 'cat <<<"x"\necho 1'))
N.append(norm('hash: a # line inside a string over several lines is text', 'hash',
    ['echo "a', '# inside', 'b"', '# outside', 'ls'], 'echo "a\n# inside\nb"\nls'))
N.append(norm('hash: a toml multi-line string keeps its # lines', 'hash',
    ['text = """', '# a line', '"""', '# a comment', 'n = 1'], 'text = """\n# a line\n"""\nn = 1'))
N.append(norm('hash: a Ruby interpolation line in a here-document is text', 'hash',
    ['puts <<~TEXT', '  #{name}', '  # not a comment', 'TEXT', 'puts 1'], 'puts <<~TEXT\n#{name}\n# not a comment\nTEXT\nputs 1'))
N.append(norm('hash: an apostrophe in a comment opens nothing', 'hash',
    ["# don't", "ls  # it's here", "# isn't", 'wc'], "ls # it's here\nwc"))
N.append(norm('hash: a # inside a word is not a comment', 'hash', ['echo ${#list}', '# c', 'ls'], 'echo ${#list}\nls'))
N.append(norm('hash: a quote nobody closes keeps the lines after it as code', 'hash', ["echo 'x", '# c'], "echo 'x\n# c"))
N.append(norm('hash: a magic comment is code', 'hash', ['# frozen_string_literal: true', 'x = 1'], '# frozen_string_literal: true\nx = 1'))
N.append(norm('hash: other comment forms are code', 'hash', ['// a', 'x'], '// a\nx'))
# --- dash types
N.append(norm('dash: -- lines, one-line block comments and a row of dashes are comments', 'dash',
    ['-- one', '/* about */', '---- Section ----', 'select 1;', '  -- two'], 'select 1;'))
N.append(norm('dash: a block comment that goes on with code is code', 'dash', ['/* a */ select 1; /* b */'], '/* a */ select 1; /* b */'))
N.append(norm('dash: --> and --| are Haskell operators, so code', 'dash', ['f', '  --> g', '  --| h'], 'f\n--> g\n--| h'))
N.append(norm('dash: a Haskell pragma is code and a one-line block comment is not', 'dash',
    ['{-# LANGUAGE Strict #-}', '{- about -}', 'x = 1'], '{-# LANGUAGE Strict #-}\nx = 1'))
N.append(norm('dash: // is code', 'dash', ['arr', '  // [(1, 2)]'], 'arr\n// [(1, 2)]'))
# --- safe, and the styles that keep indentation
N.append(norm('safe: comments are code and spaces inside a line stay', 'safe', ['% about it', 'f()  ->  ok.'], '0:% about it\n0:f()  ->  ok.'))
N.append(norm('safe: blank lines and trailing spaces go', 'safe', ['a   ', '', '   ', 'b\t'], '0:a\n0:b'))
N.append(norm('safe: columns are counted from the smallest indentation of the lines kept', 'safe', ['    a', '  b', '      c'], '2:a\n0:b\n4:c'))
N.append(norm('safe: a tab is its own indentation and never eight spaces', 'safe', ['a', '\tb'], '0:a\n\\u0009:b'))
N.append(norm('safe: the start every kept line has in common is dropped, tabs too', 'safe', ['\ta', '\t\tb'], '0:a\n\\u0009:b'))
N.append(norm('safe: another whitespace character in the indentation is written out', 'safe', ['\u00a0a', 'b'], '\\u00a0:a\n0:b'))
N.append(norm('c: whitespace at the ends of a line is what Python strips: no-break space, form feed, U+001C', 'c',
    ['\u00a0a\u00a0', '\x0cb\x0c', '\x1cc\x1c'], 'a\nb\nc', 'a port has to strip the same characters'))
N.append(norm('c: U+0085 and U+001F are whitespace too, and a byte order mark is not', 'c',
    ['\x85d\x85', '\x1fe\x1f', '\ufeffa', '\ufeff// x'], 'd\ne\n\ufeffa\n\ufeff// x',
    'whitespace is what Python strips, which is not what a regular expression or trim() of another language strips'))
N.append(norm('c: a Unicode line separator inside a comment line or a string is just a character', 'c',
    ['// a\u2028b', '/* a\u2028b */', 'x(1);', 'y  =  "a  \\\u2028  b"  ;'], 'x(1);\ny = "a  \\\u2028  b" ;',
    'a dot matches everything but a line feed'))
N.append(norm('dash: a Unicode line separator inside a comment line is just a character', 'dash', ['-- a\u2028b', 'select 1'], 'select 1'))
N.append(norm('hash: a Unicode line separator inside a comment line is just a character', 'hash', ['# a\u2028b', 'ls'], 'ls'))
N.append(norm('hash: a # in the middle of a word is no comment, so the quote after it opens a string', 'hash',
    ["echo a#b '", '# inside the string', "'", 'ls'], "echo a#b '\n# inside the string\n'\nls"))
N.append(norm('safe: moving the whole piece is not a change', 'safe', ['  f(x) ->', '      g(x).'], '0:f(x) ->\n4:g(x).'))
N.append(norm('dash-keep: a line moved out of a haskell do block is a different text', 'dash-keep',
    ['main = do', '  putStrLn "a"', 'putStrLn "b"'], '0:main = do\n2:putStrLn "a"\n0:putStrLn "b"'))
N.append(norm('dash-keep: a comment line goes and does not shift the columns', 'dash-keep',
    ['      -- about it', 'main = do', '  f'], '0:main = do\n2:f'))
N.append(norm('hash-keep: a hash line goes and the nesting counts', 'hash-keep', ['# about', 'proc f() =', '  echo 1'], '0:proc f() =\n2:echo 1'))
N.append(norm('c-keep: a comment line goes and the nesting counts', 'c-keep', ['// c', 'def f =', '  g'], '0:def f =\n2:g'))
# --- multi-line strings of the c family
N.append(norm('c+tick: a line that looks like a comment inside a template literal is text', 'c+tick',
    ['const sql = `', '// the query', 'SELECT 1', '`;'], 'const sql = `\n// the query\nSELECT 1\n`;'))
N.append(norm('c: without the string kind the same lines lose the comment-looking one', 'c',
    ['const sql = `', '// the query', 'SELECT 1', '`;'], 'const sql = `\nSELECT 1\n`;'))
N.append(norm('c+tick: after the string a comment is a comment again', 'c+tick',
    ['const a = `x', '// text', '`;', '// a comment', 'const b = 1;'], 'const a = `x\n// text\n`;\nconst b = 1;'))
N.append(norm('c+tick: a string that closes on its line is not a multi-line string', 'c+tick',
    ['const a = `x ${b} y`;', '// a comment', 'const c = 1;'], 'const a = `x ${b} y`;\nconst c = 1;'))
N.append(norm('c+triple: a text block keeps a comment-looking line', 'c+triple',
    ['String s = """', '    // not a comment', '    """;', '// a comment'], 'String s = """\n// not a comment\n""";'))
N.append(norm('c+triple+triple1: dart has triple single quotes', 'c+triple+triple1',
    ["var s = \'\'\'", '// not a comment', "\'\'\';"], "var s = \'\'\'\n// not a comment\n\'\'\';"))
N.append(norm('c+tick: a region that ends inside a string has lost its place, so none of its lines is dropped', 'c+tick',
    ['const a = <p>use ` here</p>;', 'const q = `', '// the query', '`;', 'const z = 1;'],
    'const a = <p>use ` here</p>;\nconst q = `\n// the query\n`;\nconst z = 1;'))
N.append(norm('c+rawtick: a backslash does not escape the backtick, so a raw string can end in one', 'c+rawtick',
    ['p := `C:\\`', 'q := `', '// x', '`', '// a comment', 'r := 1'], 'p := `C:\\`\nq := `\n// x\n`\nr := 1'))
N.append(norm('c+tick: backticks in a trailing comment open nothing', 'c+tick',
    ['let fence = false;   // inside a ``` block: shaded', '// a comment', 'const x = 1;'], 'let fence = false; // inside a ``` block: shaded\nconst x = 1;'))
N.append(norm('c+tick: a backtick in a block comment or in another string opens nothing', 'c+tick',
    ['/* a ` in a block', '   comment */', 'const s = "a `";', '// a comment', 'const t = 1;'], '/* a ` in a block\ncomment */\nconst s = "a `";\nconst t = 1;'))
N.append(norm('c+tick: an apostrophe is not a string', 'c+tick',
    ["fn f<'a>(x: &'a str) {}", '// a comment', 'let b = 1;'], "fn f<'a>(x: &'a str) {}\nlet b = 1;"))
N.append(norm('c+tick: blank lines and runs of spaces inside the string are not seen', 'c+tick',
    ['const a = `x', '', '   y    z', '`;'], 'const a = `x\ny z\n`;', 'a limit, said in the SPEC'))
for row in N:
    row['hash'] = sha(row['normalized'])

STYLE = []
for name, path, style in [
    ('python by extension', 'src/a.py', 'python'), ('python, in capitals', 'src_py/pkg/a.PY', 'python'), ('python stubs', 'x.pyi', 'python'),
    ('python for windows', 'x.pyw', 'python'), ('cython', 'x.pyx', 'python'), ('starlark', 'rules.bzl', 'python'),
    ('bazel build files are known by their name, as written', 'pkg/BUILD', 'python'), ('a script called build is not bazel', 'scripts/build', 'safe'),
    ('nor is a file called workspace', 'workspace', 'safe'),
    ('shell', 'run.sh', 'hash'), ('bash', 'run.bash', 'hash'), ('zsh', 'run.zsh', 'hash'),
    ('ruby', 'a.rb', 'hash'), ('perl', 'a.pl', 'hash'), ('r', 'a.r', 'hash'), ('toml', 'conf.toml', 'hash'), ('elixir', 'a.ex', 'hash'),
    ('a Dockerfile is known by its name', 'Dockerfile', 'hash'), ('in any case, in a folder', 'ci/dockerfile', 'hash'),
    ('sql', 'q.sql', 'dash'), ('lua', 'a.lua', 'dash'),
    ('haskell keeps its indentation', 'a.hs', 'dash-keep'), ('elm', 'a.elm', 'dash-keep'),
    ('nim', 'a.nim', 'hash-keep'), ('coffeescript', 'a.coffee', 'hash-keep'),
    ('javascript has template literals', 'a.js', 'c+tick'), ('typescript', 'a.ts', 'c+tick'), ('typescript with jsx', 'a.tsx', 'c+tick'),
    ('go has raw strings with backticks, where a backslash is just a backslash', 'a.go', 'c+rawtick'),
    ('java has text blocks', 'a.java', 'c+triple'), ('kotlin', 'a.kt', 'c+triple'), ('swift', 'a.swift', 'c+triple'), ('c sharp', 'a.cs', 'c+triple'),
    ('dart has both kinds of triple quotes', 'a.dart', 'c+triple+triple1'),
    ('scala keeps its indentation, since scala 3 may leave out braces', 'a.scala', 'c-keep+triple'), ('f sharp', 'a.fs', 'c-keep'),
    ('c', 'a.c', 'c'), ('c plus plus', 'a.cpp', 'c'), ('a header', 'a.h', 'c'), ('objective c plus plus', 'a.mm', 'c'), ('rust', 'a.rs', 'c'),
    ('php', 'a.php', 'c'), ('html', 'a.html', 'c'), ('css', 'a.css', 'c'), ('json', 'a.json', 'c'),
    ('yaml is safe: a # line in a block scalar is text', 'a.yml', 'safe'), ('a makefile is known by its name and is safe', 'Makefile', 'safe'),
    ('erlang is not listed for hashing', 'a.erl', 'safe'),
    ('no extension', 'LICENSE', 'safe'), ('a dot only in the folder', 'dir.py/file', 'safe'), ('a dot in a folder of another file', 'a.b/c', 'safe'),
    ('an unlisted extension', 'a.unknown', 'safe'), ('the last dot counts', 'a.py.txt', 'safe'), ('a name that is only an extension', '.py', 'python')]:
    STYLE.append({'name': name, 'path': path, 'style': style})

for ext, (style, _starters) in sorted(_tool.STYLES.items()):
    STYLE.append({'name': f'the table: .{ext}', 'path': f'a.{ext}', 'style': style})
for name, style in sorted(_tool.LANGUAGES_BY_NAME.items()):
    STYLE.append({'name': f'the table, by name: {name}', 'path': f'x/{name}', 'style': style})
for name, style in sorted(_tool.LANGUAGES_BY_EXACT_NAME.items()):
    STYLE.append({'name': f'the table, by exact name: {name}', 'path': f'x/{name}', 'style': style})

SPLIT = []
for name, text, lines in [
    ('line feed, and no empty line after the last', 'a\nb\n', ['a', 'b']), ('carriage return and line feed', 'a\r\nb', ['a', 'b']),
    ('a lone carriage return', 'a\rb', ['a', 'b']), ('a form feed is not a line break', 'a\fb\nc', ['a\fb', 'c']),
    ('a vertical tab is not a line break', 'a\u000bb', ['a\u000bb']), ('a Unicode line separator is not a line break', 'a\u2028b\nc', ['a\u2028b', 'c']),
    ('an empty text has no lines', '', []), ('one line feed is one empty line', '\n', ['']), ('a blank line in the middle and at the end', 'a\n\n', ['a', '']),
    ('no line feed at the end', 'a', ['a'])]:
    SPLIT.append({'name': name, 'text': text, 'lines': lines})

def region(file, start, lines, style_lines=None):
    return {'file': file, 'start': start, 'lines': lines}

by_name = {r['name']: r for r in N}
loop_text = by_name['python: every statement carries its depth in levels']['normalized']
CODE = []
def join(parts):
    return '\n\x00\n'.join(parts)
CODE.append({'name': 'one region', 'regions': [region('src/a.ts', 1, ['  one();', '  two();'])], 'hash': sha('one();\ntwo();')})
CODE.append({'name': 'two regions of a file are joined in line order, whatever order they are given in',
             'regions': [region('src/a.ts', 20, ['two();']), region('src/a.ts', 3, ['one();'])], 'hash': sha(join(['one();', 'two();']))})
CODE.append({'name': 'regions of several files are joined in file order, each by the rule of its type',
             'regions': [region('src_ts/a.ts', 1, ['export const A = 1;']), region('src_py/a.py', 1, loop)],
             'hash': sha(join([loop_text, 'export const A = 1;']))})
CODE.append({'name': 'the same text in one region or two gives different hashes (the join counts)',
             'regions': [region('src/a.ts', 1, ['one();']), region('src/a.ts', 5, ['two();'])], 'hash': sha(join(['one();', 'two();']))})
CODE.append({'name': 'files are ordered by code point, so a file named with an astral character comes after one named with U+FF5E',
             'regions': [region('src/\U0001F600.ts', 1, ['two();']), region('src/\uff5e.ts', 1, ['one();'])], 'hash': sha(join(['one();', 'two();']))})
CODE.append({'name': 'no regions is the hash of an empty text', 'regions': [], 'hash': sha('')})
CODE.append({'name': 'a region of only comments and blanks is the hash of an empty text',
             'regions': [region('src/a.ts', 1, ['// only', ''])], 'hash': sha('')})
CODE.append({'name': 'a shell and a Python file of one clause', 'regions': [region('a/run.sh', 1, ['# c', 'ls']), region('b/x.py', 1, ['x = 1'])],
             'hash': sha(join(['ls', '0:x = 1']))})

TEXT = [{'name': n, 'input': t, 'hash': sha(t)} for n, t in [
    ('the empty text', ''), ('ascii', 'abc'), ('non-ascii is read as UTF-8', 'é'), ('a line feed counts', 'a\n'),
    ('a part face with a value', 'Camera\nWhy: it moves')]]

def entry(d):
    return json.dumps(d, sort_keys=True, separators=(', ', ': '), ensure_ascii=False)
LOCK = []
LOCK.append({'name': 'sorted keys, one entry per line, entry keys sorted', 'fmt': 1,
             'entries': {'b/item': {'kind': 'item', 'text': 'x', 'code': 'c'}, 'a': {'kind': 'part', 'text': 'y'}},
             'text': '{\n"a": {"kind": "part", "text": "y"},\n"b/item": {"code": "c", "kind": "item", "text": "x"}\n}\n'})
LOCK.append({'name': 'non-ascii is written as it is', 'fmt': 1, 'entries': {'é': {'kind': 'part', 'text': 'ü'}},
             'text': '{\n"é": {"kind": "part", "text": "ü"}\n}\n'})
LOCK.append({'name': 'keys are ordered by code point, so an astral key comes after U+FF5E', 'fmt': 1,
             'entries': {'\U0001F600': {'kind': 'part', 'text': 'y'}, '\uff5e': {'kind': 'part', 'text': 'z'}},
             'text': '{\n"\uff5e": {"kind": "part", "text": "z"},\n"\U0001F600": {"kind": "part", "text": "y"}\n}\n'})
LOCK.append({'name': 'a test entry with a result', 'fmt': 1,
             'entries': {'a/test:x': {'kind': 'test', 'result': 'pass', 'text': 't'}},
             'text': '{\n"a/test:x": {"kind": "test", "result": "pass", "text": "t"}\n}\n'})
LOCK.append({'name': 'no entries is an empty line between the braces', 'fmt': 1, 'entries': {}, 'text': '{\n\n}\n'})
LOCK.append({'name': 'a later format opens with its marker, then the entries as before', 'fmt': 2,
             'entries': {'a': {'kind': 'part', 'text': 'y'}}, 'text': '{\n"*format": 2,\n"a": {"kind": "part", "text": "y"}\n}\n'})

PY_C, TS_C, ALL_C = 'a1b2c3d4e5f6', '0f1e2d3c4b5a', '123456789abc'
DIGEST = [
    {'name': 'one target', 'targets': {'py': {'code': PY_C}}, 'digest': sha(f'py:{PY_C}')},
    {'name': 'targets in the order of their names, whatever order they come in', 'targets': {'ts': {'code': TS_C}, 'py': {'code': PY_C}},
     'digest': sha(f'py:{PY_C}\nts:{TS_C}')},
    {'name': 'targets are ordered by code point, so an astral name comes after U+FF5E', 'targets': {'\U0001F600': {'code': TS_C}, '\uff5e': {'code': PY_C}},
     'digest': sha(f'\uff5e:{PY_C}\n\U0001F600:{TS_C}')},
    {'name': 'code in no target is the target `*`', 'targets': {'*': {'code': ALL_C}, 'py': {'code': PY_C}},
     'digest': sha(f'*:{ALL_C}\npy:{PY_C}')},
]
clause = {'kind': 'item', 'refs': {'x': 'r1'}, 'text': 'text1'}
FOLD = [
    {'name': 'a line goes into its clause and the clause gets the digest of its targets as its code',
     'file': {'g/h': clause, 'g/h@py': {'kind': 'code', 'of': 'g/h', 'target': 'py', 'code': PY_C, 'built': 'text1'},
              'g/h@ts': {'kind': 'code', 'of': 'g/h', 'target': 'ts', 'code': TS_C, 'built': 'text0'}},
     'entries': {'g/h': dict(clause, code=sha(f'py:{PY_C}\nts:{TS_C}'), targets={'py': {'code': PY_C, 'built': 'text1'}, 'ts': {'code': TS_C, 'built': 'text0'}})}},
    {'name': 'a clause that keeps one joined code is left as it is', 'file': {'g/h': dict(clause, code=ALL_C)},
     'entries': {'g/h': dict(clause, code=ALL_C)}},
    {'name': 'a line whose clause is not in the file is dropped',
     'file': {'g/h': clause, 'g/x@py': {'kind': 'code', 'of': 'g/x', 'target': 'py', 'code': PY_C, 'built': 'text1'}},
     'entries': {'g/h': clause}},
]
LOCK.append({'name': 'a clause with code per target: its own line without code, then a line for each target', 'fmt': None,
             'entries': {'g/h': dict(clause, code='ignored', targets={'ts': {'code': TS_C, 'built': 'text0'}, 'py': {'code': PY_C, 'built': 'text1'}}),
                         'g/b': {'kind': 'item', 'text': 't2', 'code': ALL_C}},
             'text': '{\n"*format": 2,\n"g/b": {"code": "%s", "kind": "item", "text": "t2"},\n"g/h": {"kind": "item", "refs": {"x": "r1"}, "text": "text1"},\n'
                     '"g/h@py": {"built": "text1", "code": "%s", "kind": "code", "of": "g/h", "target": "py"},\n'
                     '"g/h@ts": {"built": "text0", "code": "%s", "kind": "code", "of": "g/h", "target": "ts"}\n}\n' % (ALL_C, PY_C, TS_C)})
LOCK.append({'name': 'the format follows the entries: none with a line is format 1 with no marker', 'fmt': None,
             'entries': {'g/b': {'kind': 'item', 'text': 't2', 'code': ALL_C}},
             'text': '{\n"g/b": {"code": "%s", "kind": "item", "text": "t2"}\n}\n' % ALL_C})

MARK = []
for name, path, line, starters, expected in [
    ('a line comment', 'a.js', '// @clause a/b', [], ['', ['a/b']]),
    ('a hash', 'a.py', '# @clause a/b c/d', [], ['', ['a/b', 'c/d']]),
    ('a doubled starter is the whole marker', 'a.clj', ';; @clause a/b', [], ['', ['a/b']]),
    ('three slashes', 'a.rs', '/// @clause a/b', [], ['', ['a/b']]),
    ('a doc block opener', 'a.js', '/** @clause a/b */', [], ['', ['a/b']]),
    ('three dashes', 'a.sql', '--- @clause a/b', [], ['', ['a/b']]),
    ('an html comment', 'a.html', '<!-- @clause a/b -->', [], ['', ['a/b']]),
    ('code before the marker makes it a line marker', 'a.js', 'x = 1;  // @clause a/b', [], ['x = 1;', ['a/b']]),
    ('a marker with no id', 'a.js', '// @clause', [], ['', []]),
    ('the end of a region', 'a.js', '// @clause end', [], ['', ['end']]),
    ('a word that only starts with clause is not the marker', 'a.js', '// @clauses a/b', [], None),
    ('a letter of another alphabet after clause makes it another word', 'a.js', '// @clause\u00e9 a/b', [], None),
    ('a Unicode line separator in the words separates them', 'a.js', '// @clause a/b\u2028c', [], ['', ['a/b', 'c']]),
    ('words are separated by whatever Python takes for whitespace', 'a.js', '// @clause a/b\u00a0c\u0085d', [], ['', ['a/b', 'c', 'd']]),
    ('whitespace between the starter and the word is whatever Python takes for whitespace', 'a.js', '//\u0085@clause a/b', [], ['', ['a/b']]),
    ('a quote before the word is not a starter in a javascript file', 'a.js', "assert(!x, '@clause end has no lens');", [], None),
    ('erlang percent', 'a.erl', '% @clause a/b', [], ['', ['a/b']]),
    ('erlang double percent', 'a.erl', '%% @clause a/b', [], ['', ['a/b']]),
    ('erlang line marker', 'a.erl', 'f() -> ok.  % @clause a/b', [], ['f() -> ok.', ['a/b']]),
    ('fortran bang', 'a.f90', '! @clause a/b', [], ['', ['a/b']]),
    ('visual basic quote', 'a.vb', "' @clause a/b", [], ['', ['a/b']]),
    ('batch rem, in any case', 'a.bat', 'Rem @clause a/b', [], ['', ['a/b']]),
    ('batch colons', 'a.cmd', ':: @clause a/b', [], ['', ['a/b']]),
    ('batch rem only at the start of a line', 'a.bat', 'echo REM @clause a/b', [], None),
    ('ocaml comment: the closing star paren is not an id', 'a.ml', '(* @clause a/b *)', [], ['', ['a/b']]),
    ('percent in a type that does not list it', 'a.js', '% @clause a/b', [], None),
    ('percent in a type nobody listed', 'a.xyz', '% @clause a/b', [], None),
    ('a starter the target declares', 'a.xyz', '% @clause a/b', ['%'], ['', ['a/b']]),
    ('a declared starter is a run', 'a.xyz', '%% @clause a/b', ['%'], ['', ['a/b']]),
    ('a declared starter of two characters', 'a.xyz', '|| @clause a/b', ['||'], ['', ['a/b']]),
    ('a declared starter adds and takes nothing away', 'a.xyz', '// @clause a/b', ['%'], ['', ['a/b']]),
]:
    MARK.append({'name': name, 'path': path, 'line': line, 'starters': starters,
                 'marker': None if expected is None else {'code': expected[0], 'words': expected[1]}})

STARTERS = []
for ext, (_style, starters) in sorted(_tool.STYLES.items()):
    STARTERS.append({'name': f'the starters of .{ext}', 'path': f'a.{ext}', 'starters': starters.split()})
STARTERS.append({'name': 'a file nobody listed', 'path': 'LICENSE', 'starters': []})

doc = {
    'about': 'Rows of input and expected output for how Spec of Record hashes code and writes the lock (SPEC section 11). Any implementation '
             'of the tool runs every row. The expected texts are written by hand and the hashes are computed with SHA-256 alone, never with the tool. '
             'A line in a row is one string; a text is one string. Run them with tools/test_sor_vectors.py.',
    'format': 2,
    'style_of': {'how': 'style_of(path) -> style: the style of the lower-cased file name if it is one of the known names, else of the text after its last dot if the name has a dot, else "safe". A style is family[-keep][+kinds]; see SPEC section 11.', 'rows': STYLE},
    'split_lines': {'how': 'split_lines(text) -> lines: a line ends at LF, CRLF or CR and nowhere else; no empty last line for a final break.', 'rows': SPLIT},
    'normalize': {'how': 'normalized(lines, style) -> text: the code as the lock sees it.', 'rows': N},
    'code_hash': {'how': 'code_hash(regions) -> hash: regions sorted by (file, start), each normalized by style_of(file), joined with "\\n\\u0000\\n", SHA-256 of the UTF-8, first 12 hex digits.', 'rows': CODE},
    'text_hash': {'how': 'text_hash(text) -> hash: SHA-256 of the UTF-8, first 12 hex digits (lock.h).', 'rows': TEXT},
    'targets_digest': {'how': 'digest(targets) -> hash: text_hash of the lines "<target>:<code>" in the order of the target names, joined by LF. It is the `code` of a clause that keeps its code per target.', 'rows': DIGEST},
    'fold': {'how': 'fold(file entries) -> entries: a line of kind "code" goes into the entry named by its `of` as targets[<target>] = {code, built}, and that entry gets code = digest(targets); a line without its clause is dropped.', 'rows': FOLD},
    **({'marker': {'how': 'parse_marker(path, line, starters) -> null | {code, words}: a marker is `@clause` after a comment starter, the whole line or after code (a line marker). Every file has the starters // # /* <!-- -- ; as runs (// and ///, ; and ;;), its type adds more (SPEC section 10), and `starters` are those its target declares, which add and never take away. Words are what follows `@clause` without a closing */ --> or *); REM and :: count only at the start of a line.', 'rows': MARK}}),
    **({'starters_of': {'how': 'starters_of(path) -> [starter]: the comment starters, besides // # /* <!-- -- ; (SPEC section 10), that a marker may follow in a file of that type: the `starters` column of the table, in order. A row for every extension in it.', 'rows': STARTERS}}),
    'lock_render': {'how': 'render(entries, fmt) -> text of the lock file (fmt null: the format the entries need, 2 when a clause has `targets`, else 1): a clause with `targets` loses `targets` and `code` and gets a line `<clause>@<target>` of kind "code" per target; keys sorted, one entry per line, entry keys sorted, separators ", " and ": ", non-ASCII as written; a fmt above 1 opens with its marker line.', 'rows': LOCK},
}
names = [r['name'] for k in doc if isinstance(doc[k], dict) and 'rows' in doc[k] for r in doc[k]['rows']]
assert len(names) == len(set(names)), 'duplicate row names'


def render():
    return json.dumps(doc, indent=1, ensure_ascii=False) + '\n'


if __name__ == '__main__':
    path = os.path.join(ROOT, 'vectors', 'hashing.json')
    if '--check' in sys.argv[1:]:
        with open(path, encoding='utf8', newline='') as fh:
            same = fh.read() == render()
        print('vectors/hashing.json is' + ('' if same else ' NOT') + ' what the generator writes')
        sys.exit(0 if same else 1)
    with open(path, 'w', encoding='utf8', newline='\n') as fh:
        fh.write(render())
    print(len(names), 'rows')
