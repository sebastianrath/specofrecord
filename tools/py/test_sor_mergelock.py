"""Tests for the lock file when a merge touched it: conflict markers, a key written twice, a file that is no JSON, and the commands, the check and the hooks
that meet it (SPEC §16). A lock in that state is named, with what to do, by every command that reads it; the edit
guard goes on letting edits through, because those are the edits that resolve the merge; nothing is rewritten.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import hook                      # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read


def conflicted(text):
    """The lock text a merge leaves when two branches changed neighbouring lines: both versions, between markers."""
    lines = text.split('\n')
    i = next(n for n, line in enumerate(lines) if line.startswith('"greet/hello"'))
    return '\n'.join(lines[:i] + ['<<<<<<< HEAD'] + [lines[i]] + ['======='] + [lines[i].replace('"text": "', '"text": "x')] + ['>>>>>>> b'] + lines[i + 1:])


class Conflicted(flows.Flow):
    def setUp(self):
        super().setUp()
        self.greet_project()
        self.lock_path = os.path.join(self.spec, 'sor-lock.json')
        self.good = read(self.lock_path)

    def spoil(self, text):
        write(self.dir, 'sor/sor-lock.json', text)
        self.spoiled = read(self.lock_path)

    def said(self, *args):
        code, out, err = self.sor(*args)
        return code, out + err


class TestAConflictedLock(Conflicted):
    def setUp(self):
        super().setUp()
        self.spoil(conflicted(self.good))

    def test_every_command_that_reads_the_lock_names_the_conflict_and_changes_nothing(self):
        for args in (('status',), ('lock', 'greet/hello'), ('lock', '--all')):
            code, said = self.said(*args)
            self.assertEqual(code, 2, (args, said))
            self.assertIn('merge conflict markers (line ', said, args)
            self.assertIn('Restore either side', said, args)
            self.assertNotIn('Traceback', said, args)
            self.assertEqual(read(self.lock_path), self.spoiled, args)      # not rewritten, not replaced

    def test_check_reports_it_as_a_problem(self):
        code, said = self.said('check')
        self.assertEqual(code, 2, said)
        self.assertRegex(said, r'lock +sor/sor-lock\.json +sor/sor-lock\.json has merge conflict markers')
        self.assertIn('1 problem(s)', said)

    def test_check_of_a_good_lock_has_no_lock_problem(self):
        self.spoil(self.good)
        code, said = self.said('check')
        self.assertEqual(code, 0, said)
        self.assertNotRegex(said, r'(?m)^ *lock +sor/')      # no problem of kind lock

    def test_the_edit_guard_lets_the_edits_that_resolve_the_merge_through_and_says_why(self):
        body = hook.pre_edit(flows.edit(self.app, '"Hello"', '"Hi"'))['hookSpecificOutput']
        self.assertNotIn('permissionDecision', body)      # an answer with no decision: the edit goes ahead
        self.assertIn('merge conflict markers', body['additionalContext'])
        self.assertIsNone(hook.pre_edit(flows.edit(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')))      # clauses were always free to change

    def test_the_edit_guard_still_refuses_to_write_the_lock_itself(self):
        said = flows.reason(hook.pre_edit(flows.edit(self.lock_path, '"greet/hello"', '"x"')))
        self.assertIn('written only by `sor lock`', said)

    def test_the_session_note_is_still_written(self):
        out = hook.session_start({'cwd': self.dir})
        self.assertIn('Spec of Record', out['hookSpecificOutput']['additionalContext'])

    def test_restoring_one_side_and_locking_the_other_sides_clauses_is_the_way_out(self):
        self.spoil(self.good)
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        flows.replace_in(self.app, '"Hello"', '"Hi"')
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass'}))
        code, said = self.said('lock', 'greet/hello', '--results', results)
        self.assertEqual(code, 0, said)
        self.assertEqual(self.said('status')[0], 0)


class TestADamagedLock(Conflicted):
    def test_a_key_written_twice_is_named_and_is_a_problem(self):
        line = next(l for l in self.good.split('\n') if l.startswith('"greet/hello"'))
        self.spoil(self.good.replace(line, line + '\n' + line.replace('"text": "', '"text": "x'), 1))
        code, said = self.said('status')
        self.assertEqual(code, 2, said)
        self.assertIn('has the key greet/hello twice', said)
        self.assertNotIn('Traceback', said)
        self.assertIn('has the key greet/hello twice', self.said('check')[1])
        self.assertEqual(read(self.lock_path), self.spoiled)

    def test_a_file_that_is_no_json_is_named(self):
        self.spoil(self.good[:60])
        code, said = self.said('status')
        self.assertEqual(code, 2, said)
        self.assertIn('is not the JSON that', said)
        self.assertNotIn('Traceback', said)
        self.assertIn('is not the JSON', self.said('check')[1])

    def test_the_guard_does_not_refuse_edits_for_a_damaged_lock_either(self):
        self.spoil(self.good[:60])
        out = hook.pre_edit(flows.edit(self.app, '"Hello"', '"Hi"'))
        self.assertNotIn('permissionDecision', out['hookSpecificOutput'])
        self.assertIn('not the JSON', out['hookSpecificOutput']['additionalContext'])

    def test_a_lock_in_a_newer_format_is_still_refused_as_before(self):
        self.spoil(re.sub(r'"\*format": \d+', '"*format": 99', self.good, 1))
        code, said = self.said('status')
        self.assertEqual(code, 2, said)
        self.assertIn('lock format 99', said)
        self.assertIn('0 problem(s)', self.said('check')[1])      # not a damaged file: it is refused when it is used


class TestAResultsFile(Conflicted):
    def test_a_results_file_that_is_no_json_is_named_and_nothing_is_locked(self):
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        flows.replace_in(self.app, '"Hello"', '"Hi"')
        before = read(self.lock_path)
        results = write(self.dir, 'results.json', 'this is not json')
        code, said = self.said('lock', 'greet/hello', '--results', results)
        self.assertEqual(code, 2, said)
        self.assertIn('is not JSON', said)
        self.assertNotIn('Traceback', said)
        self.assertEqual(read(self.lock_path), before)

    def test_a_missing_results_file_and_a_list_are_named(self):
        code, said = self.said('lock', '--all', '--results', os.path.join(self.dir, 'nope.json'))
        self.assertEqual(code, 2, said)
        self.assertIn('cannot read', said)
        results = write(self.dir, 'results.json', json.dumps(['greet/test:hello']))
        code, said = self.said('lock', '--all', '--results', results)
        self.assertEqual(code, 2, said)
        self.assertIn('holds {"part/test:name": "pass"}', said)


PAGE = base.doc('Greet', 'Says hello.',
                rules=['- **hello** - The page says {text: Hello}.', '', '- **bye** - The page says {text: Bye}.', '', '- **thanks** - The page says {text: Thanks}.'],
                tests=['- **hello** - says hello.', '  manual: a person looks'])
CODE = ('// @clause glue\n"use strict";\n// @clause end\n// @clause greet/hello\nconsole.log("Hello");\n// @clause end\n'
        '// @clause greet/bye\nconsole.log("Bye");\n// @clause end\n// @clause greet/thanks\nconsole.log("Thanks");\n// @clause end\n')


@unittest.skipUnless(shutil.which('git'), 'git is not installed')
class TestTwoBranchesLockNeighbouringClauses(flows.Flow):
    """What the blank line between lock entries is for (SPEC §11), with git: two branches lock clauses whose entries sit next to each other in the file."""

    def git(self, *args, check=True):
        done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'core.hooksPath=/dev/null', *args], cwd=self.dir, capture_output=True,
                              text=True)
        if check:
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def setUp(self):
        super().setUp()
        self.project({'greet': PAGE})
        write(self.dir, 'out/app.js', CODE)
        self.lock_path = os.path.join(self.spec, 'sor-lock.json')
        self.git('init', '-q', '-b', 'main')
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.commit('base')

    def said(self, *args):
        code, out, err = self.sor(*args)
        return code, out + err

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def change_and_lock(self, branch, name, old, new, older_tool=False):
        """On a branch of its own: change the clause `name`, lock it, commit. `older_tool`: the lock is written as a tool from before the blank lines would."""
        self.git('checkout', '-q', 'main')
        self.git('checkout', '-q', '-b', branch)
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: %s}' % old, '{text: %s}' % new)
        flows.replace_in(self.app, '"%s"' % old, '"%s"' % new)
        self.assertEqual(self.sor('lock', f'greet/{name}')[0], 0)
        if older_tool:
            write(self.dir, 'sor/sor-lock.json', lockfile.render(lockfile.read(Project(self.dir)), 3))
        self.commit(branch)

    def merge_both(self):
        self.git('checkout', '-q', 'main')
        self.git('merge', '-q', '-m', 'a', 'a')
        return self.git('merge', '-m', 'b', 'b', check=False)

    def test_neighbouring_entries_merge_without_a_conflict_and_the_merge_is_in_agreement(self):
        # greet/bye.text and greet/hello are neighbours in the sorted lock
        self.change_and_lock('a', 'hello', 'Hello', 'Hi')
        self.change_and_lock('b', 'bye', 'Bye', 'Cya')
        merged = self.merge_both()
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        code, said = self.said('status')
        self.assertEqual(code, 0, said)
        self.assertIn('clauses, code and lock agree', said)
        entries = lockfile.read(Project(self.dir))
        self.assertEqual(entries['greet/hello']['code'], lockfile.read(Project(self.dir))['greet/hello']['code'])
        self.assertTrue(read(self.lock_path).startswith('{\n"*format": 4,\n\n'))

    def test_control_the_same_merge_with_the_lock_written_without_blank_lines_conflicts(self):
        self.change_and_lock('a', 'hello', 'Hello', 'Hi', older_tool=True)
        self.change_and_lock('b', 'bye', 'Bye', 'Cya', older_tool=True)
        merged = self.merge_both()
        self.assertNotEqual(merged.returncode, 0)
        self.assertEqual(self.git('diff', '--name-only', '--diff-filter=U').stdout.split(), ['sor/sor-lock.json'])      # only the lock; the spec and the code merged
        code, said = self.said('status')
        self.assertEqual(code, 2, said)
        self.assertIn('merge conflict markers', said)

    def test_the_way_out_of_such_a_conflict_gives_the_lock_a_correct_hand_merge_gives(self):
        self.change_and_lock('a', 'hello', 'Hello', 'Hi', older_tool=True)
        self.change_and_lock('b', 'bye', 'Bye', 'Cya', older_tool=True)
        self.assertNotEqual(self.merge_both().returncode, 0)
        self.git('checkout', '--ours', '--', 'sor/sor-lock.json')      # restore one side's version, as the message says
        self.assertEqual(self.sor('lock', 'greet/bye')[0], 0)         # then lock the clauses of the other side
        self.assertEqual(self.sor('status')[0], 0)
        recovered = flows.lock_bytes(self.dir)
        self.assertEqual(self.sor('lock', '--all')[0], 0)      # a lock of everything accepts nothing more: this is the lock a correct hand merge gives
        self.assertEqual(flows.lock_bytes(self.dir), recovered)

    def test_both_branches_locking_a_test_that_names_both_clauses_still_conflicts_there(self):
        both = PAGE.replace('says hello.', 'says {hello} and then {bye}.')
        write(self.dir, 'sor/greet.md', both)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.commit('a test that names two clauses')
        self.change_and_lock('a', 'hello', 'Hello', 'Hi')      # locking hello locks its own test too
        self.change_and_lock('b', 'bye', 'Bye', 'Cya')
        self.assertEqual(self.sor('lock', 'greet/test:hello')[0], 0)      # and b relocks that test, which names its clause too
        self.commit('b: relock the test')
        merged = self.merge_both()
        self.assertNotEqual(merged.returncode, 0)      # a conflict, where two people changed the same entry: somebody has to look
        self.assertIn('sor/sor-lock.json', self.git('diff', '--name-only', '--diff-filter=U').stdout.split())

    def test_a_clean_merge_does_not_hide_a_test_that_one_branch_left_stale(self):
        both = PAGE.replace('says hello.', 'says {hello} and then {bye}.')
        write(self.dir, 'sor/greet.md', both)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.commit('a test that names two clauses')
        self.change_and_lock('a', 'hello', 'Hello', 'Hi')      # a locks hello and its test (which names bye as it is on a)
        self.change_and_lock('b', 'bye', 'Bye', 'Cya')         # b locks bye only: the test is stale there
        merged = self.merge_both()
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        code, said = self.said('status')
        self.assertIn('greet/test:hello', said)      # listed for review, not agreed
        self.assertIn('stale', said)


if __name__ == '__main__':
    unittest.main()
