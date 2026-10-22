"""Tests for what the session-start note says about pending work: the clauses changed since the last lock, a language behind, drift and the
claims in force, so that a session that did not start the work still knows of it.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
"""
import os
import re
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import hook                      # noqa: E402
from sorlib import lock as lockfile          # noqa: E402

doc, write, read = base.doc, base.write, base.read


def note(root):
    out = hook.session_start({'cwd': root})
    return out['hookSpecificOutput']['additionalContext']


def pending_lines(root):
    return [l for l in note(root).splitlines() if l.startswith(('Pending since', 'Claims in force'))]


class TestWhatTheStartNoteSaysIsPending(flows.Flow):
    def setUp(self):
        super().setUp()
        self.greet_project()                      # locked, in agreement
        self.spec_file = os.path.join(self.spec, 'greet.md')

    def test_a_project_in_agreement_gets_the_note_it_always_got(self):
        self.assertEqual(pending_lines(self.dir), [])

    def test_a_clause_changed_since_the_last_lock_is_named(self):
        flows.replace_in(self.spec_file, '{text: Hello}', '{text: Hi}')
        line, = pending_lines(self.dir)
        self.assertTrue(line.startswith('Pending since the last lock: greet/hello changed'), line)
        self.assertIn(f'`{hook.CMD} status` has the detail', line)

    def test_drift_is_named_too(self):
        flows.replace_in(self.app, '"Hello"', '"Hi"')
        line, = pending_lines(self.dir)
        self.assertIn('greet/hello drift', line)

    def test_a_claim_in_force_is_named_with_who_holds_it(self):
        self.claim(['greet/bye'], 'alice')
        line, = pending_lines(self.dir)
        self.assertTrue(line.startswith('Claims in force: alice: greet/bye'), line)

    def test_a_project_with_no_lock_yet_says_nothing_of_it(self):
        os.remove(os.path.join(self.spec, 'sor-lock.json'))
        self.assertEqual(pending_lines(self.dir), [])

    def test_a_lock_this_copy_cannot_read_leaves_the_plain_note(self):
        lock = os.path.join(self.spec, 'sor-lock.json')
        write(self.dir, 'sor/sor-lock.json', read(lock).replace('{\n', '{\n"*format": 99,\n', 1))
        text = note(self.dir)
        self.assertIn('This project keeps its specification as clauses in sor/', text)
        self.assertEqual(pending_lines(self.dir), [])

    def test_a_failure_while_working_it_out_never_costs_the_note(self):
        flows.replace_in(self.spec_file, '{text: Hello}', '{text: Hi}')
        with mock.patch.object(lockfile, 'status', side_effect=RuntimeError('broken')):
            text = note(self.dir)
        self.assertIn('This project keeps its specification as clauses in sor/', text)
        self.assertNotIn('Pending since', text)

    def test_run_as_a_program_the_note_carries_the_pending_line(self):
        flows.replace_in(self.spec_file, '{text: Hello}', '{text: Hi}')
        code, out, err = flows.run_hook('session-start', {'cwd': self.dir})
        self.assertEqual(code, 0, err)
        self.assertIn('Pending since the last lock: greet/hello changed', out)


class TestTheLineIsCapped(flows.Flow):
    def test_a_lot_of_pending_clauses_end_in_a_count_and_stay_under_the_limit(self):
        rules = [f'- **item-{i:03d}-with-a-rather-long-name** - Says number {i}.' for i in range(80)]
        self.project({'many': doc('Many', 'Lots of clauses.', rules=rules)})
        flows.accepted(self.dir)
        flows.replace_in(os.path.join(self.spec, 'many.md'), 'Says number', 'Tells number')
        line, = pending_lines(self.dir)
        self.assertLessEqual(len(line), hook.PENDING_MAX)
        self.assertRegex(line, r'; \.\.\. and \d+ more \(`' + re.escape(hook.CMD) + r' status` has the detail\)\.$')
        shown = line.count(' changed')
        self.assertTrue(0 < shown < 80, shown)
        self.assertIn(f'and {80 - shown} more', line)


class TestALanguageThatIsBehind(targeted.Targeted):
    def test_it_is_named_with_the_language(self):
        self.lock_all()
        self.change_clause()
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'ts')[0], 0)
        line, = pending_lines(self.dir)
        self.assertIn('greet/hello behind (ts)', line)


if __name__ == '__main__':
    unittest.main()
