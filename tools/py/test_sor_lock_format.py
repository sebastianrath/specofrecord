"""Tests for the lock's format number (SPEC §11): the lock is written in the newest format, which opens with its marker and has a blank line between the
entries, the older formats (1 to 3) are still read, a number this tool does not know is refused by everything that reads or rewrites the lock, and nothing
is changed when it refuses.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. No format above the newest exists yet, so a later one is made by hand, or by moving `FORMAT` in the test.
"""
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
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
        """The lock file with another format marker as its first entry, as a later format would write it."""
        text = read(self.path)
        marker = json.dumps(lockfile.FORMAT_KEY) + ': '
        self.assertIn(marker + str(lockfile.FORMAT) + ',', text)      # a written lock always carries its marker
        with open(self.path, 'w', encoding='utf8', newline='\n') as fh:
            fh.write(text.replace(marker + str(lockfile.FORMAT) + ',', marker + json.dumps(value) + ',', 1))
        return read(self.path)

    def as_format(self, number):
        """The lock rewritten the way an older tool of that format number wrote it (no blank lines before 4, no marker in 1)."""
        project = Project(self.dir)
        entries = lockfile.read(project)
        with open(self.path, 'w', encoding='utf8', newline='\n') as fh:
            fh.write(lockfile.render(entries, number))
        return entries


class TestTheNewestFormat(Locked):
    def test_a_lock_opens_with_its_marker_has_a_blank_line_between_entries_and_keeps_the_same_bytes(self):
        before = flows.lock_bytes(self.dir)
        self.assertTrue(before.startswith(('{\n"*format": %d,\n\n"' % lockfile.FORMAT).encode()), before[:60])
        lines = before.decode().split('\n')[1:-2]
        self.assertTrue(all((n % 2 == 1) == (line == '') for n, line in enumerate(lines)), 'a blank line after every entry, and only there')
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_the_file_is_still_one_json_object_that_an_older_reader_parses_apart_from_the_marker(self):
        data = json.loads(read(self.path))
        self.assertEqual(data[lockfile.FORMAT_KEY], lockfile.FORMAT)
        self.assertIn('greet/hello', data)

    def test_the_locks_of_the_two_real_projects_are_what_this_tool_would_write(self):
        for rel in ('examples/solar-system', 'editors/vscode'):
            with self.subTest(rel):
                project = Project(os.path.join(REPO, rel))
                with open(project.lock_path, encoding='utf8', newline='') as fh:
                    self.assertEqual(lockfile.render(lockfile.read(project)), fh.read())

    def test_an_older_format_is_read_the_same_and_the_next_lock_writes_the_newest(self):
        for number in (1, 2, 3):
            with self.subTest(number):
                entries = self.as_format(number)
                self.assertEqual(lockfile.FORMAT_KEY in read(self.path), number > 1)
                self.assertNotIn('\n\n', read(self.path))      # no blank lines before format 4
                self.assertEqual(lockfile.read(Project(self.dir)), entries)
                self.assertEqual(self.sor('status')[0], 0)
                flows.replace_in(self.app, '"Hello"', '"Hi"')
                flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
                self.assertEqual(self.sor('lock', 'greet/hello', '--allow-incomplete')[0], 0)
                self.assertTrue(read(self.path).startswith('{\n"*format": %d,\n\n' % lockfile.FORMAT))
                flows.replace_in(self.app, '"Hi"', '"Hello"')
                flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hi}', '{text: Hello}')
                self.assertEqual(self.sor('lock', 'greet/hello', '--allow-incomplete')[0], 0)

    def test_rehash_rewrites_an_older_form_and_nothing_else(self):
        entries = self.as_format(2)
        code, out, err = self.sor('lock', '--rehash')
        self.assertEqual(code, 0, err)
        self.assertIn(f'in lock format {lockfile.FORMAT}', out)
        self.assertEqual(lockfile.read(Project(self.dir)), entries)
        self.assertTrue(read(self.path).startswith('{\n"*format": %d,\n\n' % lockfile.FORMAT))
        code, out, err = self.sor('lock', '--rehash')
        self.assertEqual(code, 0, err)
        self.assertIn('nothing to rewrite', out)

    def test_a_marker_that_says_1_is_read_as_format_1_and_not_kept(self):
        self.as_format(1)
        text = read(self.path)
        with open(self.path, 'w', encoding='utf8', newline='\n') as fh:
            fh.write(text.replace('{\n', '{\n"*format": 1,\n', 1))
        self.assertEqual(self.sor('status')[0], 0)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        self.assertNotIn('"*format": 1', read(self.path))

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
        self.assertTrue(lockfile.render({'a/b': self.ENTRY}).startswith('{\n"*format": 4,\n\n'))
        self.assertTrue(lockfile.render({'a/b': self.ENTRY}, 2).startswith('{\n"*format": 2,\n"'))      # no blank lines before format 4
        with self.assertRaises(ValueError) as caught:
            lockfile.render({'a/b': self.ENTRY}, 1)
        self.assertIn('need lock format 2, not 1', str(caught.exception))

    def test_a_line_that_says_more_than_code_and_built_is_format_3_and_cannot_be_written_as_format_2(self):
        fits = dict(self.ENTRY, targets={'py': {'code': 'aaa', 'built': 'abc'}, 'ts': {'code': 'bbb', 'built': 'abc', 'fits': True}})
        self.assertTrue(lockfile.render({'a/b': fits}, 3).startswith('{\n"*format": 3,\n"'))
        self.assertIn('"fits": true', lockfile.render({'a/b': fits}))
        with self.assertRaises(ValueError) as caught:
            lockfile.render({'a/b': fits}, 2)
        self.assertIn('need lock format 3, not 2', str(caught.exception))

    def test_every_field_of_a_line_goes_into_its_clause_and_comes_back(self):
        text = lockfile.render({'a/b': dict(self.ENTRY, targets={'ts': {'code': 'bbb', 'built': 'abc', 'fits': True, 'later': 'x'}})})
        data = json.loads(text)
        self.assertEqual(data.pop(lockfile.FORMAT_KEY), lockfile.FORMAT)
        entries = lockfile.fold(data)
        self.assertEqual(entries['a/b']['targets'], {'ts': {'code': 'bbb', 'built': 'abc', 'fits': True, 'later': 'x'}})
        self.assertEqual(lockfile.render(entries), text)

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
            self.assertEqual(lockfile.render(entries, self.LATER).split('\n', 2)[2], lockfile.render(entries).split('\n', 2)[2])


class TestRunningTestsOnALockItCannotRead(flows.Flow):
    def test_sor_test_refuses_before_it_asks_the_browser(self):
        self.project({'targets/web': flows.TARGET, 'lim': base.doc('Limits', 'How many errors.', rules=['- **limit** - At most {max: 5} errors.'],
                                                                   tests=['- **limit** - the cap holds.', '  expect: count(errors) = {limit.max}'])})
        write(self.dir, 'out/index.html', flows.PAGE)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        path = os.path.join(self.spec, 'sor-lock.json')
        write(self.dir, 'sor/sor-lock.json', re.sub(r'"\*format": \d+', '"*format": 99', read(path), 1))
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
