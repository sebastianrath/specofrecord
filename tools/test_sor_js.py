"""The JavaScript copy of the hashing rules (tools/js) against the Python tool, which is the reference.

A lock written by one of the two has to read as unchanged by the other (SPEC §11), so both answer the same questions:

* every row of vectors/hashing.json, which `node tools/js/test/vectors.js` runs;
* the code of this repository, read as every style, plain and with characters put in at random places (a quote, a backslash, a
  no-break space, a character from outside the first plane): the same normalized text, so the same hash;
* lines with markers in them, scanned as every kind of file: the same regions, problems and unmarked lines;
* locks with keys of every kind: the same text.

The rows only cover what somebody thought of; the second and third are what notices a rule that changes in one copy only. They
are skipped when there is no `node` (it is named in the output), and nothing in the tool itself needs it.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Node 16 or later.
"""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

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
