"""Runs vectors/hashing.json: rows of input and expected output for how the tool hashes code and writes the lock (SPEC §11).

Any implementation of the tool, in any language, has to give the same answer for every row, or a lock written by one would show
as drift in the other. The expected texts were written by hand and the hashes computed with SHA-256 alone, so a row says what the
rule is and not only what this tool happens to do.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only.
"""
import hashlib
import json
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from sorlib import lock as lockfile          # noqa: E402
from sorlib import markers                   # noqa: E402
from sorlib.model import split_lines         # noqa: E402

PATH = os.path.join(REPO, 'vectors', 'hashing.json')
with open(PATH, encoding='utf8') as fh:
    VECTORS = json.load(fh)
CATEGORIES = ('style_of', 'split_lines', 'normalize', 'code_hash', 'text_hash', 'targets_digest', 'fold', 'marker', 'lock_render')


def rows(category):
    return VECTORS[category]['rows']


def sha(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()[:12]


class TestTheFile(unittest.TestCase):
    def test_it_has_every_category_with_rows_and_a_name_for_each_row(self):
        self.assertEqual(VECTORS['format'], 2)
        for category in CATEGORIES:
            with self.subTest(category):
                self.assertTrue(VECTORS[category]['how'])
                self.assertTrue(rows(category))
                self.assertTrue(all(r['name'] for r in rows(category)))
        names = [r['name'] for c in CATEGORIES for r in rows(c)]
        self.assertEqual(len(names), len(set(names)), 'a failing row must be found by its name')

    def test_every_type_the_tool_knows_has_a_row_so_that_a_port_cannot_map_one_differently(self):
        paths = {r['path'] for r in rows('style_of')}
        missing = [f'.{e}' for e in markers.STYLES if f'a.{e}' not in paths]
        missing += [n for n in list(markers.LANGUAGES_BY_NAME) + list(markers.LANGUAGES_BY_EXACT_NAME) if f'x/{n}' not in paths]
        self.assertEqual(missing, [], 'a type without a row: add it to the file')

    def test_the_hashes_in_the_file_are_sha256_of_its_own_texts(self):
        for r in rows('normalize'):
            self.assertEqual(r['hash'], sha(r['normalized']), r['name'])
        for r in rows('text_hash'):
            self.assertEqual(r['hash'], sha(r['input']), r['name'])
        for r in rows('targets_digest'):
            self.assertEqual(r['digest'], sha('\n'.join(f'{t}:{r["targets"][t]["code"]}' for t in sorted(r['targets']))), r['name'])

    def test_the_hashes_the_tool_pinned_before_the_rule_followed_the_file_type_are_rows(self):
        pinned = {r['hash'] for r in rows('normalize') if r['style'] == 'c'}
        self.assertLessEqual({'5502253e7c35', '03f73544624d', 'a10cf9686abb'}, pinned)


class TestEveryRow(unittest.TestCase):
    def test_style_of(self):
        for r in rows('style_of'):
            with self.subTest(r['name']):
                self.assertEqual(markers.style_of(r['path']), r['style'])

    def test_split_lines(self):
        for r in rows('split_lines'):
            with self.subTest(r['name']):
                self.assertEqual(split_lines(r['text']), r['lines'])

    def test_normalize(self):
        for r in rows('normalize'):
            with self.subTest(r['name']):
                got = markers.normalized(r['lines'], r['style'])
                self.assertEqual(got, r['normalized'])
                self.assertEqual(sha(got), r['hash'])

    def test_code_hash(self):
        for r in rows('code_hash'):
            with self.subTest(r['name']):
                regions = []
                for g in r['regions']:
                    region = markers.Region(g['file'], g['start'], 'code', ['x'])
                    region.lines = g['lines']
                    regions.append(region)
                self.assertEqual(markers.code_hash(regions), r['hash'])

    def test_text_hash(self):
        for r in rows('text_hash'):
            with self.subTest(r['name']):
                self.assertEqual(lockfile.h(r['input']), r['hash'])

    def test_marker(self):
        for r in rows('marker'):
            with self.subTest(r['name']):
                got = markers.parse_marker(r['path'], r['line'], r['starters'])
                self.assertEqual(None if got is None else {'code': got[0], 'words': got[1]}, r['marker'])

    def test_targets_digest(self):
        for r in rows('targets_digest'):
            with self.subTest(r['name']):
                self.assertEqual(lockfile.digest(r['targets']), r['digest'])

    def test_fold(self):
        for r in rows('fold'):
            with self.subTest(r['name']):
                self.assertEqual(lockfile.fold(json.loads(json.dumps(r['file']))), r['entries'])

    def test_lock_render(self):
        for r in rows('lock_render'):
            with self.subTest(r['name']), mock.patch.object(lockfile, 'FORMAT', max(lockfile.FORMAT, r['fmt'] or 1)):
                self.assertEqual(lockfile.render(json.loads(json.dumps(r['entries'])), r['fmt']), r['text'])


if __name__ == '__main__':
    unittest.main()
