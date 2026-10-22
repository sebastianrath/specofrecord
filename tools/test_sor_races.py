"""Tests for what `sor lock` does when something else happens while it works: another lock lands, a file it read changes, a claim appears.
Between reading the lock and the files and writing, a lock can take a while (it may run tests), and the lock is worked out from what it read, so
it writes nothing that it did not read: it stops and says to run it again.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps: "something else happens" is a function that runs right after the lock has worked out what to write.
"""
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import claims                    # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
AGAIN = 'run it again'


class Meanwhile(targeted.Targeted):
    """greet/hello in both languages, locked; greet/bye in Python, not locked. Then `lock` runs and, after it has worked out what to write,
    `meanwhile` happens."""

    def setUp(self):
        super().setUp()
        self.lock_all()
        self.bye = write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        self.change_clause()                                                                  # hello changes in both languages
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Hi'))

    def lock_while(self, meanwhile, *args):
        original = lockfile.accept

        def accept(*a, **k):
            result = original(*a, **k)
            meanwhile()
            return result

        with mock.patch.object(lockfile, 'accept', accept):
            return self.sor('lock', *args)

    def another_lock_lands(self, key, **changes):
        def do():
            project = Project(self.dir)
            entries = lockfile.read(project)
            entries[key] = dict(entries[key], **changes)
            lockfile.write(project, entries)
        return do


class TestAnotherLockLands(Meanwhile):
    def test_a_lock_of_the_whole_project_stops_when_the_lock_is_not_what_it_read(self):
        code, out, _ = self.lock_while(self.another_lock_lands('greet/bye', text='another'), '--all')
        self.assertEqual(code, 2, out)
        self.assertIn('the lock changed while this one was being worked out', out)
        self.assertIn(AGAIN, out)
        self.assertEqual(lockfile.read(Project(self.dir))['greet/bye']['text'], 'another')     # what the other lock wrote is still there
        self.assertIn('greet/hello', [f['key'] for f in self.findings()])                       # and this lock's own work was not written

    def test_a_scoped_lock_keeps_what_another_lock_wrote_for_other_clauses(self):
        code, out, _ = self.lock_while(self.another_lock_lands('greet/bye', text='another'), 'greet/hello')
        self.assertEqual(code, 0, out)
        entries = lockfile.read(Project(self.dir))
        self.assertEqual(entries['greet/bye']['text'], 'another')
        self.assertEqual([f for f in self.findings() if f['key'] == 'greet/hello'], [])        # and hello is locked

    def test_a_scoped_lock_stops_when_another_lock_wrote_one_of_its_clauses(self):
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.lock_while(self.another_lock_lands('greet/hello', text='another'), 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('the lock changed while this one was being worked out', out)
        self.assertNotEqual(flows.lock_bytes(self.dir), before)                                 # the other lock's, not this one's
        self.assertEqual(lockfile.read(Project(self.dir))['greet/hello']['text'], 'another')

    def test_a_line_of_a_language_counts_as_part_of_its_clause(self):
        def other_language_lands():
            project = Project(self.dir)
            entries = lockfile.read(project)
            entries['greet/hello']['targets']['ts'] = dict(entries['greet/hello']['targets']['ts'], built='another')
            lockfile.write(project, entries)
        code, out, _ = self.lock_while(other_language_lands, 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('the lock changed', out)


class TestAFileChanges(Meanwhile):
    def edit(self, path, extra='\n// edited meanwhile\n'):
        def do():
            with open(path, 'a', encoding='utf8') as fh:
                fh.write(extra)
        return do

    def test_a_code_file_of_the_clauses_being_locked_stops_the_lock(self):
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.lock_while(self.edit(os.path.join(self.dir, 'src_ts', 'greet.ts')), 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('src_ts/greet.ts changed while this one was being worked out', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_code_file_of_another_clause_does_not(self):
        code, out, _ = self.lock_while(self.edit(self.bye), 'greet/hello')
        self.assertEqual(code, 0, out)

    def test_a_lock_of_the_whole_project_stops_for_any_code_file_it_read(self):
        code, out, _ = self.lock_while(self.edit(self.bye), '--all', '--allow-incomplete')
        self.assertEqual(code, 2, out)
        self.assertIn('src_py/bye.py changed while this one was being worked out', out)

    def test_a_spec_file_stops_it_whatever_the_scope(self):
        code, out, _ = self.lock_while(self.edit(self.spec_file, '\n'), 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('sor/greet.md changed while this one was being worked out', out)

    def test_a_file_that_is_no_part_of_the_project_does_not(self):
        code, out, _ = self.lock_while(self.edit(os.path.join(self.dir, 'notes.txt'), 'x'), 'greet/hello')
        self.assertEqual(code, 0, out)


class TestTheStamps(Meanwhile):
    def test_a_path_that_cannot_be_examined_is_left_out_not_an_error(self):
        from sorlib.markers import file_stamps
        link = os.path.join(self.dir, 'src_py', 'dangling.py')
        try:
            os.symlink(os.path.join(self.dir, 'nowhere.py'), link)       # listed by the folder, but there is nothing behind it
        except (OSError, NotImplementedError):
            self.skipTest('no symbolic links here')
        stamps = file_stamps(Project(self.dir))
        self.assertNotIn(link, stamps)
        self.assertIn(os.path.join(self.dir, 'src_py', 'greet.py'), stamps)
        self.assertTrue(all(isinstance(v, tuple) and len(v) == 2 for v in stamps.values()))


class TestAClaimAppears(Meanwhile):
    def test_a_lock_of_the_whole_project_stops_when_another_agent_claimed_meanwhile(self):
        def bob_claims():
            self.claim(['greet/bye'], 'bob', session='B')
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.lock_while(bob_claims, '--all', '--allow-incomplete')
        self.assertEqual(code, 2, out)
        self.assertIn('claimed  bob: greet/bye', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_claim_of_the_same_session_does_not(self):
        def alice_claims():
            self.claim(['greet/bye'], 'alice', session='')
        code, out, _ = self.lock_while(alice_claims, '--all', '--allow-incomplete', '--as', 'alice')
        self.assertEqual(code, 0, out)


if __name__ == '__main__':
    unittest.main()
