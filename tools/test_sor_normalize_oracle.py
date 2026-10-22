"""Python's own tokenizer as the judge of how code is normalized before it is hashed (SPEC §11).

The normalization of Python (`sorlib.markers`) reads lines with a small scanner of its own, so it is compared with `tokenize` on real
code, the standard library of the Python that runs the tests:

* an edit that cannot change what a file means (every indent made narrower, comment and blank lines before a statement) leaves the
  normalized text alone;
* an edit of one statement's indentation that still compiles and changes the tokenizer's INDENT and DEDENT structure changes it.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. The files are a fixed sample (sorted, every n-th), so a run is repeatable.
"""
import io
import os
import re
import sys
import sysconfig
import tokenize
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sorlib.markers import normalized   # noqa: E402
from sorlib.model import split_lines     # noqa: E402

LAYOUT = {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER}
FSTRING_MIDDLE = getattr(tokenize, 'FSTRING_MIDDLE', None)   # Python 3.12 tokenizes the text of an f-string as pieces of its own
SAMPLE = 25

# Small programs with what the scanner has to get right: a string a backslash continues, strings with the other quote inside, `#` in
# strings and brackets, statements that go on over lines, and blocks that end in several ways. Every one is judged as the sample is.
TRICKY = [
    "def f(items):\n    for item in items:\n        x = 'a\\\n(b'\n        y = 1\n        z = 2\n    return 3\n",
    "def f(items):\n    for item in items:\n        x = \"a \\\"quoted\\\" \\\n  (word\"\n        y = 1\n        z = 2\n    return 3\n",
    "def f():\n    s = \"\"\"A doc\n# not a comment\n  it's \"quoted\" 'twice'\n\"\"\"\n    if s:\n        s = s.strip()\n    return s\n",
    "def f(a, b):\n    x = [\n        a,   # first\n        # between\n        b,\n    ]\n    if x:\n        return {'k': '#', \"j\": \"(\"}\n    return None\n",
    "def f(a):\n    total = a + \\\n        1\n    while total:\n        total -= 1\n        if total > 5:\n            continue\n    return total\n",
    "class A:\n    @property\n    def x(self):\n        try:\n            return 1\n        except KeyError:\n            return 2\n"
    "        finally:\n            pass\n\n    def y(self):\n        with open('f') as f, open('g') as g:\n            return f, g\n",
    "def f(a):\n    if a:\n        b = 1; c = 2\n    elif a is None:\n        b = 3\n    else:\n        b = 4\n    for i in range(b):\n        c += i\n    else:\n        c = 0\n    return c\n",
]

# Python 3.12 and later: an f-string may reuse its own quote in a field, span lines in a field, and have a comment there. The scanner
# reads them on every Python, but only these Pythons can say what the tokenizer thinks of them.
TRICKY_312 = [
    "def clean(s):\n    t = f\"{s.replace(\"(\", \"\")}\"\n    if t:\n        return t\n    return None\n",
    "def f(d, w):\n    x = f\"{d[\"#\"]:>{w}}\" + f\"{f\"{w}\"}\"\n    if x:\n        return x\n    return None\n",
    "def f(a, b):\n    x = f\"{\n        a +  # a comment with ) and \"\n        b\n    }\"\n    if x:\n        return x\n    return None\n",
    "def f(a):\n    s = f\"\"\"\n# not a comment {a}\n{a!r:>{len(a)}}\n\"\"\"\n    for i in s:\n        print(i)\n    return s\n",
    "def f(a):\n    s = f\"ab\\\n# still text {a}\"\n    if s:\n        return s\n    return None\n",
]


def tokens(text):
    return list(tokenize.generate_tokens(io.StringIO(text).readline))


def signature(toks):
    """The token structure without layout: types and strings, INDENT and DEDENT without their widths, string bodies without the
    indentation of their lines."""
    out = []
    for tok in toks:
        if tok.type in LAYOUT:
            continue
        text = tok.type == tokenize.STRING or (FSTRING_MIDDLE is not None and tok.type == FSTRING_MIDDLE)
        s = '' if tok.type == tokenize.INDENT else re.sub(r'\n[ \t]+', '\n', tok.string) if text else tok.string
        out.append((tok.type, s))
    return out


def statement_starts(toks):
    """1-based numbers of the lines on which a statement starts: the first token after a NEWLINE (or the first of the file)."""
    starts, fresh = [], True
    for tok in toks:
        if tok.type in LAYOUT or tok.type in (tokenize.INDENT, tokenize.DEDENT):
            continue
        if fresh and tok.type != tokenize.NEWLINE:
            starts.append(tok.start[0])
        fresh = tok.type == tokenize.NEWLINE
    return starts


def norm(text):
    return normalized(split_lines(text), 'python')


def sample_files():
    lib = sysconfig.get_paths()['stdlib']
    files = []
    for dirpath, dirs, names in os.walk(lib):
        dirs[:] = sorted(d for d in dirs if d not in ('test', 'tests', 'site-packages', 'idlelib', 'lib2to3', '__pycache__'))
        files += [os.path.join(dirpath, n) for n in sorted(names) if n.endswith('.py')]
    return files[::max(1, len(files) // SAMPLE)]


def thin(path, starts, n):
    """All the statement starts of a small program, about n of a long file's."""
    return starts if path.startswith('TRICKY') else starts[::max(1, len(starts) // n)]


class TestTheNormalizationAgreesWithTheTokenizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checked = []
        for n, text in enumerate(TRICKY + (TRICKY_312 if sys.version_info >= (3, 12) else [])):
            toks = tokens(text)
            cls.checked.append((f'TRICKY[{n}]', text, signature(toks), statement_starts(toks)))
        for path in sample_files():
            try:
                with open(path, encoding='utf8') as fh:
                    text = fh.read()
                compile(text, path, 'exec')
                toks = tokens(text)
            except (OSError, SyntaxError, ValueError, tokenize.TokenError, UnicodeDecodeError):
                continue
            cls.checked.append((path, text, signature(toks), statement_starts(toks)))

    def edits_that_compile(self, text, path, lines):
        new = '\n'.join(lines) + '\n'
        try:
            compile(new, path, 'exec')
            return new, signature(tokens(new))
        except (SyntaxError, ValueError, tokenize.TokenError):
            return None, None

    def test_there_is_something_to_compare(self):
        self.assertGreater(len(self.checked), 10)
        self.assertTrue(all(compile(t, n, 'exec') for n, t, _, _ in self.checked if n.startswith('TRICKY')))   # the small programs are Python

    def test_narrower_indents_everywhere_are_no_change(self):
        compared = 0
        for path, text, sig, _ in self.checked:
            lines = split_lines(text)
            two = '\n'.join(re.sub(r'^((?:    )+)', lambda m: '  ' * (len(m.group(1)) // 4), l) for l in lines) + '\n'
            try:
                if signature(tokens(two)) != sig:
                    continue
            except (tokenize.TokenError, SyntaxError, ValueError):
                continue
            compared += 1
            with self.subTest(path):
                self.assertEqual(norm(two), norm(text))
        self.assertGreater(compared, 8)

    def test_comment_and_blank_lines_before_a_statement_are_no_change(self):
        compared = 0
        for path, text, sig, starts in self.checked:
            lines = split_lines(text)
            for start in thin(path, starts, 4):
                indent = re.match(r'[ \t]*', lines[start - 1]).group(0)
                new, new_sig = self.edits_that_compile(text, path, lines[:start - 1] + [indent + '# a new comment', ''] + lines[start - 1:])
                if new is None or new_sig != sig:     # a comment inside a string or after a backslash is no such edit
                    continue
                compared += 1
                with self.subTest(f'{path}:{start}'):
                    self.assertEqual(norm(new), norm(text))
        self.assertGreater(compared, 25)

    def test_moving_a_statement_in_or_out_by_one_level_that_still_compiles_is_a_change(self):
        compared = 0
        for path, text, sig, starts in self.checked:
            lines = split_lines(text)
            for start in thin(path, starts, 6):
                line = lines[start - 1]
                for new_line in ('    ' + line, line[4:] if line.startswith('    ') else None):
                    if new_line is None:
                        continue
                    new, new_sig = self.edits_that_compile(text, path, lines[:start - 1] + [new_line] + lines[start:])
                    if new is None or new_sig == sig:
                        continue
                    compared += 1
                    with self.subTest(f'{path}:{start}'):
                        self.assertNotEqual(norm(new), norm(text))
        self.assertGreater(compared, 15)


if __name__ == '__main__':
    unittest.main()
