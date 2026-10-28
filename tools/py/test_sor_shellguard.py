"""Tests for the check after a shell command (`sor hook pre-bash` and `post-bash`, shellguard.py): that a command which changes code behind the edit
guard's back is told what the guard would have refused, and that it is told nothing else.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. Every project and the folder that the hooks keep their notes in are temporary; the commands are not run, a test changes
the files the way a `sed -i` would.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_guard as guard               # noqa: E402
from sorlib import claims, shellguard        # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

doc, write, read = base.doc, base.write, base.read
CODE = '# @clause greet/hello\nHELLO = "Hello"\n# @clause end\n# @clause greet/bye\nBYE = "Bye"\n# @clause end\n'
SED = "sed -i 's/Hello/Hi/' src/greet.py"


def build(folder):
    """A project with two clauses and their code, locked."""
    write(folder, 'sor/SPECOFRECORD.md', base.ROOT_DOC)
    write(folder, 'sor/greet.md', doc('Greet', 'Says hello.', rules=['- **hello** - The greeting is "Hello".', '- **bye** - The farewell is "Bye".'],
                                      tests=['- **hello** - looks right.', '  manual: look', '- **bye** - looks right.', '  manual: look']))
    write(folder, 'src/greet.py', CODE)
    code, out, err = base.run_sor(folder, 'lock', '--all')
    assert code == 0, (out, err)


def change(folder, rel, old, new):
    path = os.path.join(folder, *rel.split('/'))
    write(folder, rel, read(path).replace(old, new, 1))
    os.utime(path, ns=(time.time_ns() + 10 ** 9, time.time_ns() + 10 ** 9))   # a clock that is coarse would not show a change within one tick


def said(out):
    return out['hookSpecificOutput']['additionalContext'] if out else None


class Base(unittest.TestCase):
    def setUp(self):
        for name in ('SOR_ENFORCE_CLAIMS',):
            self.addCleanup(os.environ.pop, name, None)
        self.notes = tempfile.TemporaryDirectory()
        self.addCleanup(self.notes.cleanup)
        patch = mock.patch.object(tempfile, 'tempdir', self.notes.name)   # where the hooks keep what they note between two commands
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = os.path.realpath(self.tmp())
        build(self.dir)

    def tmp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, d, True)
        return d

    def payload(self, command, call='c1', cwd=None, **more):
        return dict({'session_id': 's1', 'tool_use_id': call, 'cwd': cwd or self.dir, 'tool_name': 'Bash', 'tool_input': {'command': command},
                     'hook_event_name': 'PostToolUse'}, **more)

    def run_command(self, command, changes, **more):
        """What the check says about a command whose effect `changes()` has on the files."""
        shellguard.before(self.payload(command, **more))
        changes()
        return said(shellguard.after(self.payload(command, **more)))

    def command_notes(self):
        """The notes of commands that were noted before and not yet read after (the other files are the lists of projects, of drift and of the sweep)."""
        found = (shellguard.read_json(p) or {} for p in glob.glob(os.path.join(self.notes.name, 'sor-shell-*')))
        return [f for f in found if f.get('projects')]


class TestWhichCommandsAreLeftOut(unittest.TestCase):
    LEFT_OUT = [
        'git status', 'git checkout main', 'git add -A && git commit -m "x"', 'git -C proj merge main', 'cd proj && git pull',
        'sor status', 'sor lock greet/bye', 'python3 tools/py/sor.py -C proj lock --all', 'cd editors/vscode && python3 ../../tools/py/sor.py lock',
        'py -3 tools/py/sor.py check', 'SOR_AGENT=bob sor claim greet/hello', 'git log 2>&1', 'git status > /dev/null', 'git diff 2>/dev/null',
        'cd x', 'export FOO=1', 'pushd x && popd', '', '  ', 'git status\nsor status',
        'git status&&git log', 'git add -A;git commit -m x', 'git apply < fix.diff', 'git commit -F - < message.txt',
    ]
    CHECKED = [
        'sed -i s/a/b/ f', "python3 - <<'EOF'\nopen('f','w').write('x')\nEOF", 'git show HEAD:f > src/greet.py', 'git status && sed -i s/a/b/ f',
        'cat > f <<EOF\nx\nEOF', 'sor status >> src/greet.py', 'cd x && prettier --write .', 'echo hi > f', 'perl -pi -e s/a/b/ f', 'npm run format',
        'bash -c "git status"', 'git status; rm f', 'git log &> f', 'echo "unclosed', 'python3 build.py', 'git status | tee f', 'git diff | head -5',
        'git status;sed -i s/a/b/ f', 'git add -A&&sed -i s/a/b/ f', 'git status >', 'git log >& out.txt', 'git log > 2', 'git log 2> err.txt',
    ]

    def test_a_line_of_git_and_sor_commands_is_left_out(self):
        for command in self.LEFT_OUT:
            with self.subTest(command=command):
                self.assertTrue(shellguard.analyse(command)[0])

    def test_everything_else_is_looked_at_also_when_git_is_in_the_line(self):
        for command in self.CHECKED:
            with self.subTest(command=command):
                self.assertFalse(shellguard.analyse(command)[0])

    def test_it_says_whether_the_line_has_a_git_or_sor_command(self):
        self.assertEqual([shellguard.analyse(c)[1] for c in ('sor lock && true', 'cd x && git status', 'sed -i s/a/b/ f', 'python3 tools/py/sor.py lock')],
                         [True, True, False, True])


class TestTheCheckAfterACommand(Base):
    def test_code_changed_behind_the_guard_whose_clause_did_not_change_is_said(self):
        out = self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi'))
        self.assertIn('files that the edit guard watches changed while this command ran', out)
        self.assertIn('Clauses come first: code changes only after the clause it serves has changed.', out)
        self.assertIn('src/greet.py:1-3 serves `greet/hello`: change **hello** in sor/greet.md first.', out)
        self.assertNotIn('greet/bye', out)
        self.assertNotIn(f'In {self.dir}:', out)   # one project: no need to name it
        self.assertIn('Use Edit on files the guard watches', out)
        self.assertIn('A person may have saved a file in the editor while the command ran: keep a change of theirs', out)
        self.assertNotIn('if it should not, revert the change', out)   # not a blanket instruction: a person\'s change is kept

    def test_it_says_it_with_the_name_of_the_event_it_was_called_for(self):
        shellguard.before(self.payload(SED))
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        out = shellguard.after(self.payload(SED, hook_event_name='PostToolUseFailure'))
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'PostToolUseFailure')

    def test_code_and_clause_changed_together_is_the_order_the_guard_wants_and_says_nothing(self):
        def both():
            change(self.dir, 'sor/greet.md', 'The greeting is "Hello"', 'The greeting is "Hi"')
            change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        self.assertIsNone(self.run_command(SED, both))

    def test_a_command_that_changed_nothing_says_nothing_and_leaves_no_note(self):
        self.assertIsNone(self.run_command('ls -la', lambda: None))
        self.assertEqual(self.command_notes(), [])

    def test_a_file_the_guard_does_not_watch_is_not_it(self):
        self.assertIsNone(self.run_command('echo x > notes.txt', lambda: write(self.dir, 'out/notes.txt', 'x')))
        self.assertIsNone(self.run_command('echo x > a', lambda: write(self.dir, 'sor/.sor-claims.json', '{}'), call='c2'))

    def test_the_lock_file_written_by_anything_but_sor_lock_is_said(self):
        out = self.run_command('python3 -c "open(\'sor/sor-lock.json\', \'a\').write(\' \')"',
                               lambda: change(self.dir, 'sor/sor-lock.json', '{', '{ '))
        self.assertIn('sor/sor-lock.json changed: it is written only by `python3 tools/py/sor.py lock`', out)

    def test_a_line_that_also_runs_sor_may_have_written_the_lock(self):
        self.assertIsNone(self.run_command('sor lock && true', lambda: change(self.dir, 'sor/sor-lock.json', '{', '{ ')))

    def test_a_line_of_git_and_sor_commands_is_not_looked_at_at_all(self):
        for command in ('git checkout main', 'cd proj && python3 tools/py/sor.py lock', 'sor status'):
            with self.subTest(command=command):
                self.assertIsNone(self.run_command(command, lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi')))
                self.assertEqual(self.command_notes(), [])
                change(self.dir, 'src/greet.py', 'Hi', 'Hello')

    def test_git_with_a_redirection_to_a_file_is_looked_at(self):
        out = self.run_command('git show HEAD:src/greet.py > src/greet.py', lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi'))
        self.assertIn('serves `greet/hello`', out)

    def test_drift_that_was_there_before_the_command_is_not_the_commands(self):
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')   # a person's change, before the command
        self.assertIsNone(self.run_command('echo >> src/greet.py', lambda: write(self.dir, 'src/greet.py', read(os.path.join(self.dir, 'src', 'greet.py')) + '\n')))
        out = self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Bye', 'Ciao'), call='c2')
        self.assertIn('serves `greet/bye`', out)
        self.assertNotIn('greet/hello', out)

    def test_two_commands_at_once_each_get_what_was_changed_while_it_ran(self):
        a, b = self.payload('sed one', call='a'), self.payload('sed two', call='b')
        shellguard.before(a)
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        shellguard.before(b)
        change(self.dir, 'src/greet.py', 'Bye', 'Ciao')
        out_b, out_a = said(shellguard.after(b)), said(shellguard.after(a))
        self.assertIn('greet/bye', out_b)
        self.assertNotIn('greet/hello', out_b)
        self.assertIn('greet/hello', out_a)
        self.assertIn('greet/bye', out_a)

    def test_two_calls_are_told_apart_by_their_id_then_their_session_and_then_their_command(self):
        a, b = self.payload(SED, call='a'), self.payload(SED, call='b')
        self.assertNotEqual(shellguard.call_id(a), shellguard.call_id(b))                              # the same command twice at once
        self.assertNotEqual(shellguard.call_id(a), shellguard.call_id(dict(a, session_id='s2')))       # the same id in two sessions
        no_id = dict(self.payload(SED), tool_use_id=None)
        self.assertEqual(shellguard.call_id(no_id), shellguard.call_id(dict(no_id)))                   # no id: the command pairs the two hooks
        self.assertNotEqual(shellguard.call_id(no_id), shellguard.call_id(dict(no_id, tool_input={'command': 'sed two'})))
        shellguard.before(no_id)
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        self.assertIn('greet/hello', said(shellguard.after(no_id)))

    def test_the_drift_of_a_project_is_worked_out_again_only_when_a_file_changed(self):
        with mock.patch.object(shellguard, 'drift_findings', wraps=shellguard.drift_findings) as worked_out:
            shellguard.before(self.payload('ls', call='1'))
            shellguard.before(self.payload('ls', call='2'))
            self.assertEqual(worked_out.call_count, 1)   # the second command found it kept for the same stamps
            change(self.dir, 'src/greet.py', 'Hello', 'Hi')
            shellguard.before(self.payload('ls', call='3'))
            self.assertEqual(worked_out.call_count, 2)

    def test_a_check_that_fails_for_one_project_does_not_break_the_hook(self):
        shellguard.before(self.payload(SED))
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        with mock.patch.object(shellguard, 'check_project', side_effect=RuntimeError('broken')):
            self.assertIsNone(shellguard.after(self.payload(SED)))

    def test_the_notes_are_swept_at_most_once_in_a_while(self):
        first, second = shellguard.tmp('stale-one'), shellguard.tmp('stale-two')
        for path in (first, second):
            write(self.notes.name, os.path.basename(path), '{}')
            os.utime(path, (time.time() - 3 * 86400, time.time() - 3 * 86400))
        shellguard.sweep()
        self.assertFalse(os.path.exists(first))
        write(self.notes.name, os.path.basename(first), '{}')
        os.utime(first, (time.time() - 3 * 86400, time.time() - 3 * 86400))
        shellguard.sweep()
        self.assertTrue(os.path.exists(first))   # swept a moment ago
        with mock.patch.object(shellguard, 'FOUND_TTL', -1):
            shellguard.sweep()
        self.assertFalse(os.path.exists(first))

    def test_the_note_of_a_command_is_gone_once_it_was_read(self):
        shellguard.before(self.payload(SED))
        self.assertTrue(os.path.exists(shellguard.tmp(shellguard.call_id(self.payload(SED)))))
        shellguard.after(self.payload(SED))
        self.assertFalse(os.path.exists(shellguard.tmp(shellguard.call_id(self.payload(SED)))))
        self.assertIsNone(shellguard.after(self.payload(SED)))   # nothing noted: nothing said

    def test_notes_of_commands_that_never_ended_are_removed_after_a_day(self):
        old = shellguard.tmp('stale')
        write(self.notes.name, os.path.basename(old), '{}')
        os.utime(old, (time.time() - 3 * 86400, time.time() - 3 * 86400))
        shellguard.before(self.payload(SED))
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(shellguard.tmp(shellguard.call_id(self.payload(SED)))))

    def test_a_project_with_more_files_than_it_looks_through_is_left_alone(self):
        with mock.patch.object(shellguard, 'MAX_FILES', 1):
            self.assertIsNone(self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi')))

    def test_a_project_that_cannot_be_read_is_left_alone_and_not_an_error(self):
        shellguard.before(self.payload('sor lock && sed -i s/Hello/Hi/ src/greet.py'))   # (a line that runs sor: the lock file is its business)
        write(self.dir, 'sor/sor-lock.json', '{"*format": 99}')
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        self.assertIsNone(shellguard.after(self.payload('sor lock && sed -i s/Hello/Hi/ src/greet.py')))   # a lock it cannot read: it cannot tell what drifts

    def test_a_session_with_no_project_notes_nothing(self):
        empty = self.tmp()
        self.assertIsNone(self.run_command(SED, lambda: None, cwd=empty))
        self.assertEqual(self.command_notes(), [])
        self.assertFalse(os.path.exists(shellguard.tmp(shellguard.call_id(self.payload(SED, cwd=empty)))))


class TestProjectsBelowTheFolderOfTheSession(Base):
    def setUp(self):
        super().setUp()
        self.parent = os.path.realpath(self.tmp())
        self.a, self.b = os.path.join(self.parent, 'apps', 'a'), os.path.join(self.parent, 'b')
        build(self.a)
        build(self.b)
        os.makedirs(os.path.join(self.parent, 'node_modules', 'x'))
        build(os.path.join(self.parent, 'node_modules', 'x'))   # not looked into
        build(os.path.join(self.parent, '.hidden'))             # nor is a hidden folder

    def test_projects_are_found_below_the_folder_and_the_one_that_changed_is_named(self):
        out = self.run_command(SED, lambda: change(self.b, 'src/greet.py', 'Hello', 'Hi'), cwd=self.parent)
        self.assertIn(f'In {self.b}:', out)
        self.assertIn('serves `greet/hello`', out)
        self.assertNotIn(self.a, out)
        self.assertNotIn('node_modules', out)

    def test_the_projects_found_are_kept_for_a_while_and_looked_for_again_after_it(self):
        self.assertEqual(sorted(shellguard.projects_of({'cwd': self.parent, 'session_id': 's'})), sorted([self.a, self.b]))
        build(os.path.join(self.parent, 'c'))
        self.assertEqual(sorted(shellguard.projects_of({'cwd': self.parent, 'session_id': 's'})), sorted([self.a, self.b]))   # kept
        with mock.patch.object(shellguard, 'FOUND_TTL', -1):
            self.assertEqual(len(shellguard.projects_of({'cwd': self.parent, 'session_id': 's'})), 3)

    def test_a_project_above_the_folder_is_the_only_one(self):
        inside = os.path.join(self.a, 'src')
        self.assertEqual(shellguard.projects_of({'cwd': inside, 'session_id': 's'}), [self.a])

    def test_a_project_inside_a_project_is_not_a_project_of_its_own(self):
        build(os.path.join(self.a, 'vendor', 'inner'))
        self.assertNotIn(os.path.join(self.a, 'vendor', 'inner'), shellguard.look_below(self.parent))

    def test_the_search_ends_at_the_number_of_projects_folders_and_seconds_it_is_given(self):
        with mock.patch.object(shellguard, 'MAX_PROJECTS', 1):
            self.assertEqual(len(shellguard.look_below(self.parent)), 1)
        with mock.patch.object(shellguard, 'FIND_DIRS', 1):
            self.assertEqual(shellguard.look_below(self.parent), [])
        with mock.patch.object(shellguard, 'FIND_SECONDS', -1):
            self.assertEqual(shellguard.look_below(self.parent), [])

    def test_it_counts_the_folders_it_looks_through_from_the_first_and_the_levels_from_the_folder_of_the_session(self):
        with mock.patch.object(shellguard, 'FIND_DIRS', 3):   # the folder itself, apps, and b
            self.assertEqual(shellguard.look_below(self.parent), [self.b])
        edge = os.path.join(self.parent, 'l1', 'l2', 'l3', 'l4')   # FIND_DEPTH levels down: still looked at
        build(edge)
        self.assertIn(edge, shellguard.look_below(self.parent))

    @unittest.skipIf(os.name != 'posix' or getattr(os, 'geteuid', lambda: 1)() == 0, 'needs a folder that cannot be read, which root can')
    def test_a_folder_that_cannot_be_read_is_passed_by(self):
        closed = os.path.join(self.parent, 'closed')
        os.makedirs(closed)
        os.chmod(closed, 0)
        self.addCleanup(os.chmod, closed, 0o755)
        self.assertEqual(sorted(shellguard.look_below(self.parent)), sorted([self.a, self.b]))

    def test_it_looks_through_a_bounded_number_of_levels(self):
        deep = os.path.join(self.parent, 'l1', 'l2', 'l3', 'l4', 'l5', 'p')
        build(deep)
        self.assertNotIn(deep, shellguard.look_below(self.parent))


class TestClaimsOfOthers(Base):
    def test_code_in_a_file_the_command_changed_that_someone_else_claimed_is_said_when_claims_are_enforced(self):
        project = Project(self.dir)
        scan = Scan(project)
        ok, _ = claims.claim(project, scan, set(lockfile.snapshot(project, scan)), ['greet/hello'], 'other', claims.DEFAULT_TTL, session='other-session')
        self.assertTrue(ok)
        os.environ['SOR_ENFORCE_CLAIMS'] = '1'
        out = self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi'))
        self.assertIn('Someone else is working on this', out)
        self.assertIn('other', out)
        del os.environ['SOR_ENFORCE_CLAIMS']
        out = self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Bye', 'Ciao'), call='c2')
        self.assertNotIn('Someone else', out)   # not enforcing: only the order of clause and code is said

    def test_code_the_command_did_not_touch_is_not_in_question(self):
        write(self.dir, 'src/greet.py', '# @clause greet/hello\nHELLO = "Hello"\n# @clause end\n')
        write(self.dir, 'src/other.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')   # the code of bye is in another file now
        base.run_sor(self.dir, 'lock', '--all')
        project = Project(self.dir)
        scan = Scan(project)
        claims.claim(project, scan, set(lockfile.snapshot(project, scan)), ['greet/bye'], 'other', claims.DEFAULT_TTL, session='other-session')
        os.environ['SOR_ENFORCE_CLAIMS'] = '1'
        out = self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi'))
        self.assertIn('serves `greet/hello`', out)
        self.assertNotIn('Someone else', out)   # bye is claimed, and its code is in src/other.py, which the command did not change

    def test_the_claims_of_the_session_itself_are_not_in_the_way(self):
        project = Project(self.dir)
        scan = Scan(project)
        claims.claim(project, scan, set(lockfile.snapshot(project, scan)), ['greet/hello'], 'me', claims.DEFAULT_TTL, session='s1')
        os.environ['SOR_ENFORCE_CLAIMS'] = '1'
        out = self.run_command(SED, lambda: change(self.dir, 'src/greet.py', 'Hello', 'Hi'))
        self.assertNotIn('Someone else', out)


class TestTheHooksAsPrograms(Base):
    def run_hook(self, which, payload):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=self.notes.name)
        return subprocess.run([sys.executable, base.SOR, 'hook', which], input=json.dumps(payload), cwd=self.dir, capture_output=True, text=True, env=env)

    def test_pre_bash_notes_and_post_bash_answers_on_stdout(self):
        done = self.run_hook('pre-bash', self.payload(SED))
        self.assertEqual((done.returncode, done.stdout), (0, ''), done.stderr)
        change(self.dir, 'src/greet.py', 'Hello', 'Hi')
        done = self.run_hook('post-bash', self.payload(SED))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('serves `greet/hello`', json.loads(done.stdout)['hookSpecificOutput']['additionalContext'])
        done = self.run_hook('post-bash', self.payload(SED))
        self.assertEqual((done.returncode, done.stdout), (0, ''))

    def test_a_real_write_between_the_two_programs_is_seen_without_setting_any_time_by_hand(self):
        done = self.run_hook('pre-bash', self.payload('sed -i s/Hello/Hiya/ src/greet.py', call='real'))
        self.assertEqual((done.returncode, done.stdout), (0, ''), done.stderr)
        path = os.path.join(self.dir, 'src', 'greet.py')
        with open(path, 'r+', encoding='utf8') as fh:   # what sed does: the file is rewritten, with whatever time and size the system gives it
            text = fh.read().replace('Hello', 'Hiya')
            fh.seek(0)
            fh.write(text)
            fh.truncate()
        done = self.run_hook('post-bash', self.payload('sed -i s/Hello/Hiya/ src/greet.py', call='real'))
        self.assertIn('serves `greet/hello`', json.loads(done.stdout)['hookSpecificOutput']['additionalContext'])

    def test_a_lock_that_asks_is_still_asked_when_the_command_is_noted_too(self):
        done = self.run_hook('pre-bash', self.payload('sor lock greet/bye --allow-behind ts'))
        self.assertEqual(json.loads(done.stdout)['hookSpecificOutput']['permissionDecision'], 'ask')

    def test_a_command_of_a_tool_other_than_bash_says_nothing(self):
        done = self.run_hook('post-bash', dict(self.payload(SED), tool_name='Edit'))
        self.assertEqual((done.returncode, done.stdout), (0, ''))


class TestTheRegisteredCommands(Base):
    """What Claude Code runs after a command, in the plugin and in this repository, and also after one that failed."""
    def commands(self, path, event, matcher):
        with open(path, encoding='utf8') as fh:
            groups = json.load(fh)['hooks'].get(event, [])
        return [h['command'] for g in groups if g.get('matcher') == matcher for h in g['hooks']]

    # The plugin is installed on any Claude Code, and it is not known whether an older one takes an event name it does not know or drops the file with it
    # (and with the edit guard), so the plugin has only PostToolUse; this repository, worked in with the current one, has PostToolUseFailure too.
    EVENTS = {'the plugin': ('PostToolUse',), 'this repository': ('PostToolUse', 'PostToolUseFailure')}

    def test_a_command_after_bash_is_registered_for_the_events_each_place_can_take(self):
        for name, path, env in guard.TestTheRegisteredCommands.WHERE:
            for event in self.EVENTS[name]:
                with self.subTest(name, event=event):
                    found = self.commands(path, event, 'Bash|PowerShell')
                    self.assertEqual(len(found), 1)
                    self.assertIn('hook post-bash', found[0])
                    self.assertIn('SOR_ENFORCE_CLAIMS=1', found[0])
        with open(guard.TestTheRegisteredCommands.WHERE[0][1], encoding='utf8') as fh:
            self.assertNotIn('PostToolUseFailure', json.load(fh)['hooks'])

    def test_the_registered_commands_note_and_then_say_what_a_command_changed(self):
        for name, path, env in guard.TestTheRegisteredCommands.WHERE:
            for event in self.EVENTS[name]:
                with self.subTest(name, event=event):
                    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=self.notes.name, **env)
                    before = self.commands(path, 'PreToolUse', 'Bash|PowerShell')
                    self.assertEqual(len(before), 1)
                    payload = self.payload(SED, hook_event_name=event, call=f'{name}-{event}')
                    run = lambda command: subprocess.run(['sh', '-c', command], input=json.dumps(payload), capture_output=True, text=True, cwd=self.dir, env=environment)  # noqa: E731
                    done = run(before[0])
                    self.assertEqual((done.returncode, done.stderr), (0, ''))
                    change(self.dir, 'src/greet.py', 'Hello', 'Hi')
                    done = run(self.commands(path, event, 'Bash|PowerShell')[0])
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(json.loads(done.stdout)['hookSpecificOutput']['hookEventName'], event)
                    change(self.dir, 'src/greet.py', 'Hi', 'Hello')


if __name__ == '__main__':
    unittest.main()
