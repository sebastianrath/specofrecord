"""The JavaScript copy of the hashing rules (tools/js) against the Python tool, which is the reference.

A lock written by one of the two has to read as unchanged by the other (SPEC §11), so both answer the same questions:

* every row of vectors/hashing.json, which `node tools/js/test/vectors.js` runs;
* the code of this repository, read as every style, plain and with characters put in at random places (a quote, a backslash, a
  no-break space, a character from outside the first plane): the same normalized text, so the same hash;
* lines with markers in them, scanned as every kind of file: the same regions, problems and unmarked lines;
* locks with keys of every kind: the same text;
* projects in the states the reading commands tell apart (`markers --json`, `status --json`, `parts --json`): the same JSON.

The rows only cover what somebody thought of; the others are what notices a rule that changes in one copy only. They
are skipped when there is no `node` (it is named in the output), and nothing in the tool itself needs it.

    SOR_COMPARE_JS=1 python3 -m unittest discover -s tools -p 'test_*.py'

runs the whole suite and, before and after every command a test gives `test_sor.run_sor`, puts the project through both tools and
compares the three JSON answers. It takes minutes, and it is how the JavaScript reader meets every state the suite builds.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Node 16 or later.
"""
import ast
import contextlib
import hashlib
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from sorlib import anchors                   # noqa: E402
from sorlib import cli                       # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib import markers                   # noqa: E402
from sorlib.model import split_lines         # noqa: E402

NODE = shutil.which('node')
JS = os.path.join(HERE, 'js')
STYLES = ['c', 'c+tick', 'c+rawtick', 'c+triple', 'c+triple+triple1', 'c-keep', 'c-keep+triple', 'hash', 'hash-keep', 'dash', 'dash-keep',
          'python', 'safe']
# Files of this repository in several languages. A file that is missing is left out, and the test insists on enough of them.
CORPUS = ['tools/sorlib/markers.py', 'tools/sorlib/lock.py', 'tools/sorlib/model.py', 'tools/sorlib/cli.py', 'tools/sorlib/hook.py',
          'tools/js/sorlib/markers.js', 'tools/js/sorlib/lock.js', 'tools/js/sorlib/pytext.js', 'tools/js/test/vectors.js',
          'editors/vscode/src/extension.js', 'editors/vscode/test/suite.js', 'plugins/sync-tools.sh', 'tools/coverage.sh',
          'index.html', 'vectors/make_hashing.py', 'examples/solar-system/sor/SPECOFRECORD.md', 'SPEC.md']
MAX_LINES = 400
# What is put into a line, at random: quotes, brackets, comment starters, a here-document, escapes, and characters Python and
# JavaScript treat differently (whitespace, a line separator, a letter outside ASCII, a character from beyond the first plane).
INSERTS = ['"', "'", '`', '"""', "'''", '\\', '{', '}', '(', ')', '[', ']', '#', '//', '/*', '*/', '<<EOF', '<<-"X"', '<<<', '\t', ' ',
           '\u0085', ' ', '\x1c', '﻿', '\U0001F600', 'f"', "rf'", 'F"""', 't"', '--', '{-', '-}', ':', '!', '#!', '\\N{', '{{',
           '}}', ' ', '  ', 'é', '\U0001D431', '　', '\x0b', '\x0c', "\\'", '\\"']
MARKS = ['@clause a/b', '@clause a/b c/d', '@clause end', '@clause glue', '@clause test a/b', '@clause file a/b', '@clause', '@clauses x',
         '@clauseé x', '@clause a/b */', '@clause a/b -->', '@clause a/b *)', '@clause a/b c', '@clause a/b c']
STARTS = ['//', '///', '#', '##', '/*', '/**', '<!--', '--', '---', ';', ';;', '%', '%%', '!', "'", '(*', 'rem', 'REM', '::', '||', '　//', '//\u0085']
PATHS = ['a.js', 'a.py', 'a.sql', 'a.erl', 'a.f90', 'a.vb', 'a.bat', 'a.ml', 'a.pas', 'a.m', 'a.fs', 'a.xyz', 'x/Dockerfile', 'x/BUILD', 'a.hs']
KEYS = ['a', 'a/b', 'a/b@py', 'é', '～', '\U0001F600', 'ROOT', '__proto__', 'constructor', 'toString', '1', '10', '2', 'a b', 'z z',
        'q"q', 'b\\b', 'tab\there', '\x01']

# Python source in the shapes an anchor has to get right: what `ast` makes of them is the reference.
PY_SNIPPETS = [
    '@one\n# a comment between\n@two(\n    1,\n)\ndef f():\n    return 1\n\n\nclass A:\n    """doc\nless indented\n"""\n    def m(self): return 2\n    x = 3\n    @property\n    def p(self):\n        pass\n    @p.setter\n    def p(self, v):\n        pass\n',
    'class A: pass\nclass B(A): x = 1; y = 2\ndef g(): return 1\nasync def h():\n    await g()\nz = 1; w = 2\n',
    'a = b = 1\nx: int\ny: int = 2\n(z) = 3\np, q = 1, 2\nn = 0\nn += 1\nw = x == y\nt = a if b else a\nu = lambda: 0\nd = {\n    "k": 1,\n    "j": [1, 2],\n}\ne: dict = {"a": 1}\nv = (yield_ := 3)\n',
    'def f():\n    pass\n\n\ndef f():\n    return 2\n\n\nclass K:\n    def f(self): pass\n    def f(self): return 3\n    class In:\n        def g(self): pass\n',
    'def f():\n\treturn 1\n\n\nclass T:\n\tdef m(self):\n\t\treturn 2\n\tv = 4\n',
    'def f():\r\n    return 1\r\n\r\nx = 5\r\n',
    'def f():\r    return 1\rx = 5\r',
    'x = """a\n#not a comment = 1\n"""\ny = "it\'s # not a comment"\ndef f():\n    s = \'\'\'\nnot indented\n\'\'\'\n    return s\nz = f"{x!r:>{y}}"\n',
    'x = 1 + \\\n    2\ndef f(a,\n      b):\n    return (a +\n            b)\nq = [1,\n 2]\n',
    'if True:\n    def inside(): pass\n    c = 1\nelse:\n    def inside(): return 2\ntry:\n    import os\nexcept ImportError:\n    pass\nwith open("f") as fh:\n    d = 2\n',
    'def f(x=lambda: 1, *a: int, y: "A:B" = {1: 2}) -> dict[str, int]:\n    return {1: 2}\nclass C(Base, metaclass=M): v = 1\nfor i in range(3): j = i\nwhile False: k = 1\n',
    'def été():\n    return 1\nπ = 3\nclass Ünï:\n    def mé(self): pass\n',
    'def f():\n    return 1\n\x0c\ndef g():\n    return 2\n',
    'def f():\n    x = "open\n    return 1\n',
    'def f():\n    return (1,\n',
    'def f():\n    return 1)\n',
    'def f():\n        return 1\n    y = 2\n',
    '  x = 1\ndef f(): pass\n',
    'def f():\nreturn 1\n',
    'def f():\n    """never closed\n    return 1\n',
    'x = 1 \\',
    'def f():\n    return 1  # trailing\n    # comment inside\n# comment outside\n\n\n\ny = 3\n',
    'class A:\n    pass\n\n    # a comment at the end of the class\n\nclass B:\n    pass\n',
    'def f(): pass; z = 3\nclass Q:\n    a = 1; b = 2\n    def m(self): c = 3; return c\n',
    'x: "str" = "a"\nx = 7\ny = z = w\nglobal_ = 1\n__all__ = ["f"]\n',
    'class A:\n    def f(self): pass\nclass B:\n    def f(self): pass\n    def g(self): pass\n',
    'x = 1\ny = )(\ndef g(): pass\n',
    'x = 1\ndef f():\n    return (1,\n',
    'x = 1\ny = (1,\n',
    'match = re.compile("x")\ncase: int = 4\nmatch.flags = 1\nmatch2 = 3\nmatch, case = 1, 2\ndef f(): pass\n',
    'x = 1\ny = 2 \\\n',
    'x = 1\ny = """abc\n',
    'x = 1\ny = "abc\\\n',
    'if (lambda: 1)():\n    y = 1\ndef g(): pass\nw = 2\n',
    'type_ = 1\nprint = 2\nlambda_ = 3\nif_ = 4\nelse_: int = 5\n',
]
PY_NAMES = ['match', 'case', 'match2', 'f', 'g', 'h', 'A', 'B', 'C', 'K', 'T', 'A.f', 'A.g', 'B.f', 'B.g', 'A.m', 'A.x', 'A.p', 'K.f', 'K.In', 'K.In.g', 'B.a', 'Q.a', 'Q.b', 'Q.m', 'x', 'y', 'z', 'w', 'a', 'b',
            'p', 'q', 'n', 'u', 'd', 'e', 'v', 't', 'c', 'j', 'k', 'été', 'π', 'Ünï.mé', 'inside', 'os', 'fh', 'print', 'lambda_', 'else_', '__all__',
            'missing', 'A.missing', 'f.inner', '']
PY_FILES = ['tools/sorlib/anchors.py', 'tools/sorlib/hook.py', 'tools/sorlib/blame.py', 'vectors/make_hashing.py']

# Code in the languages whose anchors are found by declaration patterns and brace matching.
BRACE_SNIPPETS = [
    'package main\n\nfunc (s *Server) Serve(addr string) error {\n\tif s == nil { return nil }\n\treturn nil\n}\n\ntype Point struct {\n\tX, Y int\n}\n\nfunc main() {}\nconst Max = 10\nvar total = 0\n',
    'pub struct Config { pub a: u32 }\nimpl Config {\n    pub fn new() -> Self { Config { a: 1 } }\n    fn helper(&self) -> u32 { self.a }\n}\npub enum Mode { A, B }\nfn main() { println!("{}", "}"); }\ntrait Run { fn run(&self); }\n',
    'namespace App {\n  public class Widget {\n    private int size;\n    public Widget(int size) { this.size = size; }\n    public int Grow(int by) {\n      return size + by; // }\n    }\n    static void Main(string[] args) { }\n  }\n  interface IThing { void Do(); }\n}\n',
    'class Widget {\n  constructor(size) { this.size = size; }\n  grow(by) {\n    return this.size + by;\n  }\n  static make() { return new Widget(1); }\n  async load() { await fetch("}"); }\n}\nexport default class Other {}\nexport function plain(a, b) { return a + b; }\nexport const arrow = (x) => { return x; };\nlet count = 0;\nconst obj = {\n  method() { return 1; },\n  other: function () { return 2; },\n  third: async function () {},\n};\n',
    'int q() { /* x *// y */ }\nint r() {\n  /*/\n  } */\n  return 1;\n}\nint add(int a, int b) {\n  return a + b;\n}\nstatic inline int sub(int a, int b) { return a - b; }\nstruct Node {\n  int v;\n  struct Node *next;\n};\nenum Color { RED, GREEN };\nvoid Widget::grow(int by) {\n  /* { */ size += by;\n}\nclass Foo {\n public:\n  int bar() const { return 1; }\n};\ntypedef struct { int x; } Pt;\nconst int LIMIT = 4;\n',
    'public class Main {\n    public static void main(String[] args) {\n        System.out.println("a { b");\n    }\n    private <T> List<T> items(Class<T> c) throws Exception {\n        return null;\n    }\n    interface Listener { void on(); }\n    enum Kind { A, B }\n}\n',
    '<html><body>\n<script>\nfunction positions(t) {\n  return [t];\n}\nconst startAngles = {\n  a: 1,\n};\n</script>\n<script type="module">\nclass Hud { show() { return `}`; } }\n</script>\n</body></html>\n',
    'type Id = string;\ninterface Shape { area(): number }\nexport class Sq implements Shape {\n  area(): number { return 1; }\n}\nexport const make = (n: number): Sq => new Sq();\nenum E { A = 1 }\nfunction* gen() { yield 1; }\n',
    'def not_braces():\n    return {"a": 1}\nfoo() {\n  echo "}"\n}\nfunction bar {\n  :\n}\n',
    'fn one() {}\nfn two()\n{\n}\nfn three(\n    a: i32,\n    b: i32,\n) -> i32 {\n    a + b\n}\nconst A: i32 = 1;\nconst B: &str = "unterminated {\nfn after() {}\nconst D: &str = \'open {\nfn after3() {}\n',
]
BRACE_NAMES = ['Serve', 'Server.Serve', 'Point', 'main', 'Max', 'total', 'Config', 'Config.new', 'Config.helper', 'Mode', 'Run', 'Widget', 'Widget.grow',
               'Widget.Grow', 'Widget.constructor', 'Widget.make', 'Widget.load', 'Other', 'plain', 'arrow', 'count', 'obj', 'obj.method', 'obj.other',
               'obj.third', 'add', 'sub', 'Node', 'Color', 'Foo', 'Foo.bar', 'Pt', 'LIMIT', 'Main', 'Main.main', 'Main.items', 'Listener', 'Kind', 'positions',
               'startAngles', 'Hud', 'Hud.show', 'Id', 'Shape', 'Sq', 'Sq.area', 'make', 'E', 'gen', 'foo', 'bar', 'one', 'two', 'three', 'A', 'B', 'after',
               'App', 'App.Widget', 'App.Widget.Grow', 'App.Widget.Widget', 'IThing', 'q', 'r', 'D', 'after3', 'missing', 'Widget.missing', 'Widget::grow', 'Widget::missing']
BRACE_PATHS = ['x.go', 'x.rs', 'x.cs', 'x.js', 'x.c', 'x.java', 'x.html', 'x.ts', 'x.sh', 'x.rs']
BRACE_FILES = ['tools/js/sorlib/views.js', 'tools/js/sorlib/anchors.js', 'examples/solar-system/out/index.html']


def sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()[:12]


def corpus():
    out = []
    for rel in CORPUS:
        path = os.path.join(REPO, *rel.split('/'))
        if os.path.isfile(path):
            with open(path, encoding='utf8') as fh:
                out.append((rel, split_lines(fh.read())[:MAX_LINES]))
    return out


def corrupted(lines, rng):
    out = list(lines)
    for _ in range(max(1, len(out) // 10)):
        i = rng.randrange(len(out))
        p = rng.randint(0, len(out[i]))
        out[i] = out[i][:p] + rng.choice(INSERTS) + out[i][p:]
    return out


def python_scan(path, text, starters):
    regions, problems, unmarked = markers.scan_text(path, text, starters)
    return {'regions': [[r.kind, r.ids, r.start, r.end, r.lines] for r in regions],
            'problems': [[p.kind, p.where, p.text] for p in problems], 'unmarked': unmarked}


def python_render(entries, fmt):
    try:
        return lockfile.render(json.loads(json.dumps(entries)), fmt)
    except (ValueError, lockfile.LockWriteError):
        return 'error'


def ask_node(jobs):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'jobs.json')
        with open(path, 'w', encoding='utf8') as fh:
            json.dump(jobs, fh, ensure_ascii=False)
        done = subprocess.run([NODE, os.path.join(JS, 'test', 'crosscheck.js'), path], capture_output=True, text=True, encoding='utf8')
    if done.returncode != 0:
        raise AssertionError(f'node failed:\n{done.stderr[-1500:]}')
    return json.loads(done.stdout)


READING = (('markers', '--json'), ('status', '--json'), ('parts', '--json'))
SESSION_VARIABLES = ('CLAUDE_CODE_SESSION_ID', 'SOR_AGENT', 'SOR_ENFORCE_CLAIMS')


def python_json(project, args, fresh=False):
    """The JSON the Python tool prints for a reading command, or None when it prints none (a project it refuses). `fresh`: in a program of
    its own, so that nothing the tests have put in place in this process (a patched function that counts calls) sees the question. Whoever runs
    the tests, the Python tool is asked as nobody's session: it marks the claims of a Claude Code session that calls it as alive, which the
    JavaScript tool, a reader, never does."""
    env = {k: v for k, v in os.environ.items() if k not in SESSION_VARIABLES}
    if fresh:
        done = subprocess.run([sys.executable, os.path.join(HERE, 'sor.py'), '-C', project, *args], capture_output=True, text=True, encoding='utf8',
                              env=dict(env, PYTHONDONTWRITEBYTECODE='1', NO_COLOR='1'))
        text = done.stdout
    else:
        out = io.StringIO()
        saved = {k: os.environ.pop(k) for k in SESSION_VARIABLES if k in os.environ}
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                cli.main(['-C', project, *args])
        except (SystemExit, OSError, ValueError, lockfile.LockFormatError):
            return None
        finally:
            os.environ.update(saved)
        text = out.getvalue()
    try:
        return json.loads(text)
    except ValueError:
        return None


def javascript_json(project, commands):
    """[(exit code, parsed JSON or None)] of the JavaScript tool for these command lines, in one program."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'jobs.json')
        with open(path, 'w', encoding='utf8') as fh:
            json.dump([['-C', project, *args] for args in commands], fh, ensure_ascii=False)
        done = subprocess.run([NODE, os.path.join(JS, 'test', 'readall.js'), path], capture_output=True, text=True, encoding='utf8')
    if done.returncode != 0:
        raise AssertionError(f'node failed:\n{done.stderr[-1500:]}')
    out = []
    for answer in json.loads(done.stdout):
        try:
            out.append((answer['code'], json.loads(answer['out'])))
        except ValueError:
            out.append((answer['code'], None))
    return out


def unlike(a, b, path=''):
    """What differs between two parsed JSON values, in order; an integer and the same float are one number, as in JavaScript."""
    if isinstance(a, float) and a == int(a):
        a = int(a)
    if isinstance(b, float) and b == int(b):
        b = int(b)
    if type(a) is not type(b):
        return [f'{path}: {a!r} is not {b!r}']
    if isinstance(a, dict):
        out = [f'{path}: keys {list(a)} are not {list(b)}'] if list(a) != list(b) else []
        for k in a:
            out += unlike(a[k], b[k], f'{path}.{k}') if k in b else []
        return out
    if isinstance(a, list):
        out = [f'{path}: {len(a)} entries are not {len(b)}'] if len(a) != len(b) else []
        for i, (x, y) in enumerate(zip(a, b)):
            out += unlike(x, y, f'{path}[{i}]')
        return out
    return [] if a == b else [f'{path}: {a!r} is not {b!r}']


def compare_with_javascript(project, extra=(), fresh=False):
    """What differs between the two tools' answers for the reading commands on a project: [] when they agree. The JavaScript status has
    no `problems` and the claims differ in the times of the clock only, so those are left out; `extra` are more `markers` targets."""
    out = []
    commands = [list(a) for a in READING] + [['markers', '--json', t] for t in extra]
    for args, (code, got) in zip(commands, javascript_json(project, commands)):
        want = python_json(project, args, fresh)
        if want is None:
            if code == 0:
                out.append(f'{" ".join(args)}: the Python tool prints no JSON and the JavaScript tool succeeds')
            continue
        if args[0] == 'status':
            want.pop('problems', None)
        if got is None:
            out.append(f'{" ".join(args)}: the JavaScript tool prints no JSON (exit {code})')
            continue
        out += [f'{" ".join(args)}{d}' for d in unlike(want, got)[:6]]
    return out


@unittest.skipUnless(NODE, 'node is not installed, so the JavaScript copy of the hashing rules (tools/js) was not run')
class TestTheJavaScriptCopy(unittest.TestCase):
    def test_it_gives_the_answer_of_every_row_of_the_vectors(self):
        done = subprocess.run([NODE, os.path.join(JS, 'test', 'vectors.js')], capture_output=True, text=True, encoding='utf8')
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-1500:])
        self.assertRegex(done.stdout, r'Ran \d+ checks, 0 failed')

    def test_it_normalizes_the_code_of_this_repository_to_the_text_the_python_tool_does(self):
        rng = random.Random(20261021)
        cases = []
        for rel, lines in corpus():
            cases.append((rel, 'plain', lines))
            cases.append((rel, 'corrupted', corrupted(lines, rng)))
            if len(lines) > 60:
                a = rng.randrange(len(lines) // 2)
                cases.append((rel, 'a piece', lines[a:a + rng.randint(5, 40)]))
        self.assertGreater(len({rel for rel, _, _ in cases}), 10, 'the corpus is the code of this repository: too few files found')
        jobs = [{'lines': lines, 'style': style} for _, _, lines in cases for style in STYLES]
        expected = [sha(markers.normalized(j['lines'], j['style'])) for j in jobs]
        got = ask_node({'normalize': jobs})['normalize']
        self.assertEqual(len(got), len(expected))
        different = [(cases[i // len(STYLES)][0], cases[i // len(STYLES)][1], STYLES[i % len(STYLES)])
                     for i in range(len(expected)) if expected[i] != got[i]]
        self.assertEqual(different, [], 'file, variant and style where the two copies hash the same code differently')

    def test_it_finds_the_lines_of_a_python_anchor_as_the_python_parser_does(self):
        rng = random.Random(20261024)
        texts = list(PY_SNIPPETS)
        for rel in PY_FILES:
            path = os.path.join(REPO, *rel.split('/'))
            if os.path.isfile(path):
                with open(path, encoding='utf8') as fh:
                    texts.append(fh.read())
        # The same texts with a line taken out or a character put in, which is how most of the odd shapes come about. Python's parser refuses a
        # whole file for a mistake anywhere (a bad operator, a character that is not allowed) and the JavaScript copy reads statements, not the
        # grammar, so only the variants that still parse count; the hand-made texts above include the mistakes a tokenizer does see.
        for text in list(texts):
            lines = text.split('\n')
            for _ in range(3):
                broken = list(lines)
                i = rng.randrange(len(broken))
                if rng.random() < 0.5:
                    del broken[i]
                else:
                    p = rng.randint(0, len(broken[i]))
                    broken[i] = broken[i][:p] + rng.choice(INSERTS + ['    ', '\t', ':', '=', '(', ')']) + broken[i][p:]
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore')
                        ast.parse('\n'.join(broken))
                    texts.append('\n'.join(broken))
                except (SyntaxError, ValueError):
                    pass
        jobs, parsed = [], 0
        for text in texts:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')   # an escape that Python does not know in a string is a warning, not a mistake
                    names = [n.name for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                parsed += 1
            except (SyntaxError, ValueError):
                names = []
            jobs.append({'path': 'x.py', 'text': text, 'names': (names[:40] + PY_NAMES)})
        self.assertGreater(parsed, len(PY_SNIPPETS), 'most of the texts should parse, or the test shows little')
        want = [[anchors.find(j['text'], j['path'], n) for n in j['names']] for j in jobs]
        self.assertTrue(any(w is not None for ws in want for w in ws) and any(w is None for ws in want for w in ws))
        got = ask_node({'anchor': jobs})['anchor']
        wrong = [(i, j['names'][k], w, g) for i, (j, ws, gs) in enumerate(zip(jobs, want, got)) for k, (w, g) in enumerate(zip(ws, gs))
                 if (list(w) if w else None) != g]
        self.assertEqual(wrong[:8], [], 'text number, name, the Python tool\'s lines, the JavaScript copy\'s')

    def test_it_finds_the_lines_of_an_anchor_in_other_languages_as_the_python_tool_does(self):
        import re
        rng = random.Random(20261025)
        texts = [(path, text) for path, text in zip(BRACE_PATHS, BRACE_SNIPPETS)]
        harvested = []
        for rel in BRACE_FILES:
            path = os.path.join(REPO, *rel.split('/'))
            if os.path.isfile(path):
                with open(path, encoding='utf8') as fh:
                    text = fh.read()
                texts.append((rel, text))
                found = re.findall(r'(?:function\*?|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)|^\s+(?:static\s+|async\s+|get\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{', text, re.M)
                harvested.append([a or b for a, b in found][:30])
        # a piece of every text with a character put in: brace matching reads any text, so the answers have to agree on all of it
        for path, text in list(texts):
            lines = text.split('\n')
            for _ in range(2):
                broken = list(lines)
                i = rng.randrange(len(broken))
                p = rng.randint(0, len(broken[i]))
                broken[i] = broken[i][:p] + rng.choice(['{', '}', '"', "'", '`', '/*', '*/', '//', ';', '(', ')', '\\']) + broken[i][p:]
                texts.append((path, '\n'.join(broken)))
        jobs = []
        for i, (path, text) in enumerate(texts):
            names = BRACE_NAMES + (harvested[(i % len(harvested))] if harvested else [])
            jobs.append({'path': path, 'text': text, 'names': names})
        want = [[anchors.find(j['text'], j['path'], n) for n in j['names']] for j in jobs]
        self.assertTrue(any(w is not None for ws in want for w in ws) and any(w is None for ws in want for w in ws))
        got = ask_node({'anchor': jobs})['anchor']
        wrong = [(i, jobs[i]['path'], jobs[i]['names'][k], w, g) for i, (ws, gs) in enumerate(zip(want, got)) for k, (w, g) in enumerate(zip(ws, gs))
                 if (list(w) if w else None) != g]
        self.assertEqual(wrong[:8], [], 'text number, path, name, the Python tool\'s lines, the JavaScript copy\'s')

    def test_it_reads_markers_and_scans_files_as_the_python_tool_does(self):
        rng = random.Random(20261022)
        lines = []
        for _ in range(1200):
            start, mark = rng.choice(STARTS), rng.choice(MARKS)
            gap = rng.choice(['', ' ', '  ', '\t', ' ', '\u0085'])
            before = rng.choice(['', '', 'x = 1;', 'f()  ', '  ', 'a '])
            lines.append(before + start + gap + mark)
        marker_jobs = [{'path': rng.choice(PATHS), 'line': line, 'starters': rng.choice([[], [], ['%'], ['||'], ['%', '!']])} for line in lines]
        expected = []
        for j in marker_jobs:
            got = markers.parse_marker(j['path'], j['line'], j['starters'])
            expected.append(None if got is None else [got[0], got[1]])
        self.assertTrue(any(e is None for e in expected) and any(e is not None for e in expected) and any(e and e[0] for e in expected))
        answers = ask_node({'marker': marker_jobs})['marker']
        self.assertEqual([(j, a) for j, a, e in zip(marker_jobs, answers, expected) if a != e], [])
        scan_jobs = []
        for _ in range(60):
            body = []
            for _ in range(rng.randint(3, 25)):
                body.append(rng.choice(lines + ['code();', '', '   ', 'more  code', ' ']))
            scan_jobs.append({'path': rng.choice(PATHS), 'text': rng.choice(['\n', '\r\n', '\r']).join(body) + rng.choice(['', '\n']),
                              'starters': rng.choice([[], ['%']])})
        want = [python_scan(j['path'], j['text'], j['starters']) for j in scan_jobs]
        for part in ('regions', 'problems', 'unmarked'):
            self.assertTrue(any(w[part] for w in want), f'the scans should include some {part}')
        got = ask_node({'scan': scan_jobs})['scan']
        self.assertEqual([(j, g) for j, g, w in zip(scan_jobs, got, want) if g != w], [])

    def test_it_writes_the_lock_the_python_tool_does_for_keys_of_every_kind(self):
        rng = random.Random(20261023)
        jobs = []
        for _ in range(150):
            entries = {}
            for key in rng.sample(KEYS, rng.randint(1, 8)):
                entry = {'kind': rng.choice(['item', 'part', 'row', 'test']), 'text': rng.choice(['x', 'café', '\U0001F600', 'a\nb', '"q"', ''])}
                if rng.random() < 0.5:
                    entry['code'] = 'c' * 12
                if rng.random() < 0.3:
                    entry['refs'] = {rng.choice(KEYS): 'r1', rng.choice(KEYS): 'r2'}
                if rng.random() < 0.3:
                    entry['targets'] = {t: {'code': 'a' * 12, 'built': 'b'} for t in rng.sample(['py', 'ts', '*', '\U0001F600', '～', 'go'], rng.randint(1, 3))}
                    for line in entry['targets'].values():
                        if rng.random() < 0.3:
                            line.update(rng.choice([{'fits': True}, {'later': '\u00fc'}, {'fits': True, 'note': 'a\nb'}]))
                        if entry['kind'] == 'test' and rng.random() < 0.6:
                            line['result'] = rng.choice(['pass', 'fail', 'none'])
                if entry['kind'] == 'test':
                    entry['result'] = rng.choice(['pass', 'fail', 'none', 'manual'])
                entries[key] = entry
            jobs.append({'entries': entries, 'fmt': rng.choice([None, None, 1, 2, 3])})
        want = [python_render(j['entries'], j['fmt']) for j in jobs]
        self.assertTrue(any(w == 'error' for w in want) and any(w != 'error' for w in want), 'the jobs should include refusals and lock texts')
        got = ask_node({'render': jobs})['render']
        self.assertEqual([(j, g) for j, g, w in zip(jobs, got, want) if g != w], [])


if __name__ == '__main__':
    unittest.main()
