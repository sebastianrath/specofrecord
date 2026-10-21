"""Symbol anchors: a clause names the code it is about with an indented line

    - **step** — advances the world by one fixed tick.
      code: src/physics/solver.cpp#World.step

`path#name` is a function, class, method (`Class.method`), struct, type or constant in that
file; `path` alone is the whole file. Python files are read with Python's own parser. Every
other language is read by declaration patterns and brace matching, which covers C, C++, C#,
Java, JavaScript, TypeScript, Go, Rust, Zig and the scripts inside HTML files.
"""
import ast
import os
import re

ANCHOR = re.compile(r'^\s+code:\s*(\S+)\s*$')


def split(target):
    path, _, name = target.partition('#')
    return path, name


def find(text, path, name):
    """(first line, last line), 1-based, of `name` in a file's text; the whole file without a
    name; None when it is not there."""
    lines = text.splitlines()
    if not name:
        return (1, max(1, len(lines)))
    if path.endswith('.py'):
        return _python(text, name)
    names = re.split(r'\.|::', name)
    if len(names) > 1:   # C++ writes a method outside its class as Owner::name
        span = _braces(lines, ['::'.join(names)])
        if span:
            return span
    return _braces(lines, names)


def _python(text, name):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    body = tree.body
    found = None
    for part in name.split('.'):
        found = None
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == part:
                found = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and t.id == part for t in targets):
                    found = node
        if found is None:
            return None
        body = getattr(found, 'body', [])
    first = min([found.lineno] + [d.lineno for d in getattr(found, 'decorator_list', [])])
    return (first, found.end_lineno)


KEYWORDS = r'(?:export\s+)?(?:default\s+)?(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:static\s+)?'


def _decl_patterns(name):
    n = re.escape(name)
    return [
        re.compile(KEYWORDS + r'(?:function\s*\*?|class|struct|interface|enum|union|trait|impl|type|'
                   r'fn|func(?:\s*\([^)]*\))?|def|namespace|module|record)\s+' + n + r'\b'),
        re.compile(KEYWORDS + r'(?:const|let|var|val)\s+' + n + r'\b'),
        re.compile(r'^\s*(?:[\w$<>\[\],:*&~]+\s+)+(?:[\w$<>]+::)*' + n + r'\s*\([^;]*$'),   # C, C++, Java, C#
        re.compile(r'^\s*' + KEYWORDS + n + r'\s*\([^;]*\)\s*\{?\s*$'),      # object or class method
        re.compile(r'^\s*' + n + r'\s*:\s*(?:async\s+)?function\b'),
    ]


def _braces(lines, names, lo=0, hi=None):
    hi = len(lines) if hi is None else hi
    patterns = _decl_patterns(names[0])
    for i in range(lo, hi):
        if any(p.search(lines[i]) for p in patterns):
            end = _block_end(lines, i, hi)
            if len(names) == 1:
                return (i + 1, end + 1)
            inner = _braces(lines, names[1:], i + 1, end)
            if inner:
                return inner
    return None


def _block_end(lines, start, hi):
    """Last line of the declaration starting at `start`: through its matching `}`, or through the
    `;` that ends it when it opens no block."""
    depth, opened, quote = 0, False, None
    block_comment = False
    for i in range(start, hi):
        line = lines[i]
        j = 0
        while j < len(line):
            c = line[j]
            two = line[j:j + 2]
            if block_comment:
                if two == '*/':
                    block_comment, j = False, j + 1
            elif quote:
                if c == '\\':
                    j += 1
                elif c == quote:
                    quote = None
            elif two == '//':
                break
            elif two == '/*':
                block_comment, j = True, j + 1
            elif c in '"\'`':
                quote = c
            elif c == '{':
                depth, opened = depth + 1, True
            elif c == '}':
                depth -= 1
                if opened and depth == 0:
                    return i
            elif c == ';' and not opened and depth == 0:
                return i
            j += 1
        if quote in ('"', "'"):
            quote = None   # strings do not run past the end of a line
        if not opened and i - start >= 3:
            return start   # no block opened within a few lines: a one-line declaration
    return hi - 1 if opened else start
