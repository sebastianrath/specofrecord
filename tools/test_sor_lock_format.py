"""Tests for the lock's format number (SPEC §11): format 1 has no marker and keeps its bytes, a number this tool does not know is
refused by everything that reads or rewrites the lock, and nothing is changed when it refuses.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. No format above 1 exists yet, so a later one is made by hand, or by moving `FORMAT` in the test.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import hook, testrun            # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read


class Locked(flows.Flow):
    """greet/hello and greet/bye, locked."""

    def setUp(self):
        super().setUp()
        self.project({'greet': flows.GREET})
        write(self.dir, 'out/app.js', flows.APP)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        self.path = os.path.join(self.spec, 'sor-lock.json')

    def mark(self, value):
        """The lock file with a format marker as its first entry, as a later format would write it."""
        text = read(self.path)
        with open(self.path, 'w', encoding='utf8', newline='\n') as fh:
            fh.write(text.replace('{\n', '{\n' + json.dumps(lockfile.FORMAT_KEY) + ': ' + json.dumps(value) + ',\n', 1))
        return read(self.path)


class TestFormatOne(Locked):
    def test_a_lock_has_no_marker_and_keeps_the_same_bytes(self):
        before = flows.lock_bytes(self.dir)
        self.assertNotIn(lockfile.FORMAT_KEY.encode(), before)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_the_locks_of_the_two_real_projects_are_what_this_tool_would_write(self):
        for rel in ('examples/solar-system', 'editors/vscode'):
            with self.subTest(rel):
                project = Project(os.path.join(REPO, rel))
                with open(project.lock_path, encoding='utf8', newline='') as fh:
                    self.assertEqual(lockfile.render(lockfile.read(project)), fh.read())

    def test_a_marker_that_says_1_is_read_as_format_1_and_not_kept(self):
        self.mark(1)
        self.assertEqual(self.sor('status')[0], 0)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        self.assertNotIn(lockfile.FORMAT_KEY, read(self.path))

    def test_no_key_can_start_with_the_marker_character(self):
        # item names stop at `*`, and every other key has a prefix of its own
        self.project({'greet': flows.GREET.replace('- **bye**', '- **\\*format** - starts with the marker character.\n- **bye**')})
        self.assertFalse([k for k in lockfile.snapshot(Project(self.dir), Scan(Project(self.dir))) if k.startswith('*')])
        for rel in ('examples/solar-system', 'editors/vscode'):
            project = Project(os.path.join(REPO, rel))
            self.assertFalse([k for k in lockfile.snapshot(project, Scan(project)) if k.startswith('*')], rel)


class TestAFormatThisToolDoesNotRead(Locked):
    def test_everything_that_reads_the_lock_refuses_and_changes_nothing(self):
        before = self.mark(lockfile.FORMAT + 1)
        for args in (('status',), ('status', '--json'), ('lock', '--all'), ('lock', 'greet/hello'), ('lock', '--rehash'),
                     ('changes',)):
            with self.subTest(args):
                code, out, err = self.sor(*args)
                self.assertEqual(code, 2, (out, err))
                self.assertIn(f'is in lock format {lockfile.FORMAT + 1}', err)
                self.assertIn(f'reads format {lockfile.FORMAT} at most', err)
                self.assertIn('Update sor', err)
                self.assertNotIn('Traceback', err + out)
                self.assertEqual(read(self.path), before)

    def test_what_does_not_read_the_lock_still_works(self):
        self.mark(lockfile.FORMAT + 1)
        for args in (('check',), ('parts',), ('needs',), ('show', 'greet/hello'), ('test', '--list')):
            with self.subTest(args):
                self.assertEqual(self.sor(*args)[0], 0)

    def test_a_marker_that_is_no_whole_number_from_1_up_is_refused_as_damage(self):
        for value in ('2', 0, -1, 2.5, True, None, [2], {'version': 2}):
            with self.subTest(value):
                self.mark(value)
                code, out, err = self.sor('status')
                self.assertEqual(code, 2, (out, err))
                self.assertIn('not a lock format number', err)
                self.assertNotIn('Traceback', err)
                write(self.dir, 'sor/sor-lock.json', self.original)

    def setUp(self):
        super().setUp()
        self.original = read(self.path)

    def test_a_write_refuses_to_replace_a_lock_a_newer_sor_wrote_since_it_was_read(self):
        project = Project(self.dir)
        entries = lockfile.read(project)
        newer = self.mark(lockfile.FORMAT + 1)
        with self.assertRaises(lockfile.LockFormatError):
            lockfile.write(project, entries)
        self.assertEqual(read(self.path), newer)

    def test_a_lock_that_cannot_be_read_at_all_is_still_replaced_as_it_always_was(self):
        project = Project(self.dir)
        entries = lockfile.read(project)
        write(self.dir, 'sor/sor-lock.json', '{ not json')
        lockfile.write(project, entries)
        self.assertEqual(lockfile.read(project), entries)

    def test_this_tool_refuses_to_write_a_format_it_does_not_know(self):
        with self.assertRaises(ValueError):
            lockfile.write(Project(self.dir), {}, fmt=lockfile.FORMAT + 1)


class TestWhatTheWriterRefuses(unittest.TestCase):
    """Code per target is format 2, and a line `clause@target` is the lock's own: nothing else may be called that."""
    ENTRY = {'kind': 'item', 'text': 'abc', 'targets': {'py': {'code': 'aaa', 'built': 'abc'}}}

    def test_entries_with_code_per_target_cannot_be_written_as_format_1(self):
        self.assertTrue(lockfile.render({'a/b': self.ENTRY}).startswith('{\n"*format": 2,\n'))
        self.assertTrue(lockfile.render({'a/b': self.ENTRY}, lockfile.FORMAT).startswith('{\n"*format": 2,\n'))
        with self.assertRaises(ValueError) as caught:
            lockfile.render({'a/b': self.ENTRY}, 1)
        self.assertIn('need lock format 2, not 1', str(caught.exception))

    def test_a_clause_named_like_the_line_for_the_code_of_another_is_refused_at_the_write(self):
        entries = {'a/b': self.ENTRY, 'a/b@py': {'kind': 'item', 'text': 'x'}}
        with self.assertRaises(lockfile.LockWriteError) as caught:
            lockfile.render(entries)
        self.assertIn('a/b@py is a clause of its own', str(caught.exception))


class TestALaterFormatRoundTrip(Locked):
    """A later tool, made here by moving FORMAT one up: it writes its marker first, and a tool with the real FORMAT refuses it."""
    LATER = lockfile.FORMAT + 1

    def test_the_marker_is_the_first_line_and_the_entries_come_back_without_it(self):
        project = Project(self.dir)
        entries = lockfile.read(project)
        with mock.patch.object(lockfile, 'FORMAT', self.LATER):
            lockfile.write(project, entries, fmt=self.LATER)
            self.assertEqual(read(self.path).split('\n')[1], f'"*format": {self.LATER},')
            self.assertEqual(lockfile.read(project), entries)
        with self.assertRaises(lockfile.LockFormatError):
            lockfile.read(project)
        self.assertEqual(self.sor('status')[0], 2)

    def test_the_marker_does_not_move_the_other_lines(self):
        entries = lockfile.read(Project(self.dir))
        with mock.patch.object(lockfile, 'FORMAT', self.LATER):
            self.assertEqual(lockfile.render(entries, self.LATER).split('\n', 2)[2], lockfile.render(entries).split('\n', 1)[1])


class TestRunningTestsOnALockItCannotRead(flows.Flow):
    def test_sor_test_refuses_before_it_asks_the_browser(self):
        self.project({'targets/web': flows.TARGET, 'lim': base.doc('Limits', 'How many errors.', rules=['- **limit** - At most {max: 5} errors.'],
                                                                   tests=['- **limit** - the cap holds.', '  expect: count(errors) = {limit.max}'])})
        write(self.dir, 'out/index.html', flows.PAGE)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        path = os.path.join(self.spec, 'sor-lock.json')
        write(self.dir, 'sor/sor-lock.json', read(path).replace('{\n', '{\n"*format": 99,\n', 1))
        asked = []

        def page(target, script, ids, timeout):
            asked.extend(ids)
            return [{'id': i, 'status': 'pass'} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            code, out, err = self.sor('test')
        self.assertEqual((code, asked), (2, []))
        self.assertIn('is in lock format 99', err)


class TestTheEditGuardOnALockItCannotRead(Locked):
    def test_an_edit_to_code_is_refused_with_the_reason_and_an_edit_to_a_clause_is_not(self):
        self.mark(lockfile.FORMAT + 1)
        said = flows.reason(hook.pre_edit(flows.edit(self.app, '"Hello"', '"Hi"')))
        self.assertIn(f'lock format {lockfile.FORMAT + 1}', said)
        self.assertIn('Update sor', said)
        self.assertIn('edits to code are refused', said)
        self.assertIsNone(flows.reason(hook.pre_edit(flows.edit(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}'))))

    def test_reading_code_still_answers_and_says_nothing_about_pending_changes(self):
        self.mark(lockfile.FORMAT + 1)
        out = hook.post_read({'tool_input': {'file_path': self.app}})
        self.assertIsNotNone(out)
        self.assertNotIn('Clauses changed since the last lock', json.dumps(out))


if __name__ == '__main__':
    unittest.main()
