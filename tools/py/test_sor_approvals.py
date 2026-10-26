"""Tests for the test commands a person has allowed (`sorlib/approvals.py`): the hook asks about a `--targets` call only when a command is new or changed, writes
down what a call that went through ran, and refuses an edit of the file that holds it.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_sor_approvals.py' -v

Python 3.9, standard library only.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
from sorlib import approvals, hook           # noqa: E402
from sorlib.model import Project             # noqa: E402

NOTES = tempfile.mkdtemp(prefix='sor-approvals-notes-')   # where the hooks keep what they note about a shell command: not the system's temporary folder


def setUpModule():
    tempfile.tempdir = NOTES


def tearDownModule():
    tempfile.tempdir = None
    shutil.rmtree(NOTES, ignore_errors=True)


class Approved(base.Case):
    def setUp(self):
        super().setUp()
        env = os.environ.get('SOR_CLAIMS_DIR')
        os.environ.pop('SOR_CLAIMS_DIR', None)
        self.addCleanup(lambda: os.environ.__setitem__('SOR_CLAIMS_DIR', env) if env is not None else None)

    def targets(self, folder=None, **runs):
        parts = {f'targets/{name}': base.doc(name.title(), 'Where the code lives and how its tests run.',
                                             rules=[f'- **code** - The code is {{path: src_{name}/}}.'] +
                                                   ([f'- **runner** - Run with {{run: {run}}}, results in {{results: out/{name}.json}}.'] if run else []))
                 for name, run in runs.items()}
        self.project(parts, folder=folder)
        return self.dir if folder is None else os.path.join(self.dir, folder)

    def pay(self, command, **more):
        return dict({'session_id': 's', 'tool_name': 'Bash', 'cwd': self.dir, 'tool_input': {'command': command}}, **more)

    def asks(self, command):
        out = hook.pre_bash(self.pay(command))
        return out['hookSpecificOutput']['permissionDecisionReason'] if out else None

    def went_through(self, command, **more):
        """The user is asked about the call (when the hook asks) and says yes: the call runs and the hook after it fires."""
        hook.pre_bash(self.pay(command, **more))
        hook.post_bash(self.pay(command, **dict({'hook_event_name': 'PostToolUse'}, **more)))


class TestOnlyANewOrChangedCommandIsAskedAbout(Approved):
    def test_the_first_call_asks_and_the_same_command_afterwards_does_not(self):
        self.targets(py='python3 tests/runner.py')
        call = 'sor lock a --run-tests --targets py'
        self.assertIn('python3 tests/runner.py', self.asks(call))
        self.went_through(call)
        self.assertIsNone(self.asks(call))
        self.assertIsNone(self.asks('sor test --targets py'))   # a target is allowed whichever command names it

    def test_a_call_that_was_refused_writes_nothing_down(self):
        self.targets(py='python3 tests/runner.py')
        self.assertIn('Claude wants to run', self.asks('sor test --targets py'))   # asked, and the user said no: no hook runs after the call
        self.assertFalse(os.path.exists(approvals.file(Project(self.dir))))
        self.assertIn('Claude wants to run', self.asks('sor test --targets py'))

    def test_a_call_that_failed_writes_nothing_down(self):
        """A refused call may also reach the hook for failures: only a call that went through says the user allowed it."""
        self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py', hook_event_name='PostToolUseFailure')
        self.assertFalse(os.path.exists(approvals.file(Project(self.dir))))
        self.assertIn('Claude wants to run', self.asks('sor test --targets py'))

    def test_a_command_that_changed_after_the_question_is_not_taken_as_allowed(self):
        """Another agent edits the spec while the question is open: what runs is not what the user saw."""
        root = self.targets(py='python3 tests/runner.py')
        call = 'sor test --targets py'
        self.assertIn('python3 tests/runner.py', self.asks(call))
        self.targets(py='python3 tests/evil.py')
        hook.post_bash(self.pay(call, hook_event_name='PostToolUse'))
        self.assertEqual(approvals.read(Project(root)), {})
        self.assertIn('python3 tests/evil.py', self.asks(call))

    def test_a_call_that_was_not_asked_about_writes_nothing_down(self):
        """A note left by an agent for a call that the hook did not ask about is removed, not read."""
        root = self.targets(py='python3 tests/runner.py')
        call = 'sor test --targets py'
        self.went_through(call)
        note = hook.asked_note(self.pay(call))
        with open(note, 'w', encoding='utf8') as fh:
            fh.write('{"shown": [{"root": "%s", "run": {"py": "python3 tests/other.py"}}]}' % root)
        self.assertIsNone(self.asks(call))   # the spec is as allowed: the call is silent, and the note goes
        self.assertFalse(os.path.exists(note))
        self.targets(py='python3 tests/other.py')
        hook.post_bash(self.pay(call, hook_event_name='PostToolUse'))
        self.assertEqual(approvals.read(Project(root))['py']['run'], 'python3 tests/runner.py')

    def test_a_mode_that_answers_the_question_itself_writes_nothing_down(self):
        root = self.targets(py='python3 tests/runner.py')
        for mode in ('bypassPermissions', 'auto'):
            with self.subTest(mode):
                self.went_through('sor test --targets py', permission_mode=mode)
                self.assertEqual(approvals.read(Project(root)), {})
        self.went_through('sor test --targets py', permission_mode='default')
        self.assertIn('py', approvals.read(Project(root)))

    def test_a_changed_command_is_asked_about_and_said_to_be_changed(self):
        root = self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        self.targets(py='python3 tests/other.py')
        said = self.asks('sor test --targets py')
        self.assertIn('`python3 tests/other.py` (not the one you allowed before)', said)
        self.went_through('sor test --targets py')
        self.assertIsNone(self.asks('sor test --targets py'))
        self.assertEqual(approvals.read(Project(root))['py']['run'], 'python3 tests/other.py')

    def test_a_new_target_is_asked_about_though_another_was_allowed(self):
        self.targets(py='python3 tests/runner.py', ts='npm test')
        self.went_through('sor test --targets py')
        said = self.asks('sor test --targets py,ts')
        self.assertIn('`python3 tests/runner.py` and `npm test`', said)
        self.assertNotIn('not the one you allowed before', said)   # ts is new, not changed
        self.went_through('sor test --targets py,ts')
        self.assertIsNone(self.asks('sor test --targets py,ts'))

    def test_two_calls_in_one_line_are_allowed_only_when_both_are(self):
        self.targets(py='python3 tests/runner.py', ts='npm test')
        self.went_through('sor test --targets py')
        self.assertIsNotNone(self.asks('sor test --targets py && sor test --targets ts'))
        self.went_through('sor test --targets ts')
        self.assertIsNone(self.asks('sor test --targets py && sor test --targets ts'))

    def test_a_target_that_gives_no_command_is_never_allowed(self):
        self.targets(py='python3 tests/runner.py', ts='')
        self.went_through('sor test --targets py,ts')
        self.assertIsNotNone(self.asks('sor test --targets ts'))


class TestTheOtherOptionsStillAsk(Approved):
    def test_an_allowed_command_does_not_allow_the_options_that_come_with_it(self):
        self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        said = self.asks('sor lock a --targets py --allow-incomplete')
        self.assertIn('some tests have not passed', said)
        self.assertNotIn('python3 tests/runner.py', said)

    def test_a_program_that_may_not_be_sor_is_asked_about(self):
        self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        for command in ('$P test --targets py', './run-sor.sh test --targets py', "sor test --targets 'py"):
            with self.subTest(command):
                self.assertIsNotNone(self.asks(command))

    def test_a_call_of_another_project_is_asked_about_though_this_one_was_allowed(self):
        self.targets(py='python3 tests/runner.py')
        other = self.targets(folder='other', py='python3 tests/runner.py')   # the same text, another project
        self.went_through('sor test --targets py')
        self.assertIsNone(self.asks('sor test --targets py'))
        self.assertIsNotNone(self.asks(f'sor -C {other} test --targets py'))
        self.went_through(f'sor -C {other} test --targets py')
        self.assertIsNone(self.asks(f'sor -C {other} test --targets py'))

    def test_the_question_shows_the_commands_of_the_project_the_call_names(self):
        self.targets(py='python3 tests/runner.py')
        other = self.targets(folder='other', py='python3 tests/other.py')
        said = self.asks(f'sor -C {other} test --targets py')
        self.assertIn('`python3 tests/other.py`', said)
        self.assertNotIn('runner.py', said)

    def test_a_line_that_changes_folder_first_is_asked_about(self):
        """`cd` runs after the hook has looked at the cwd: the call runs in a folder (a worktree) whose spec the hook did not read."""
        self.targets(py='python3 tests/runner.py')
        other = self.targets(folder='other', py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        self.assertIsNone(self.asks('sor test --targets py'))
        for command in (f'cd {other} && sor test --targets py', f'(cd {other} && sor test --targets py)', f'pushd {other}; sor test --targets py',
                        f'bash -c "cd {other} && sor test --targets py"', f'env -C {other} sor test --targets py', f'cd {other}\nsor test --targets py'):
            with self.subTest(command):
                self.assertIsNotNone(self.asks(command))

    def test_env_with_options_in_front_of_sor_is_still_read_as_a_call(self):
        for command in ('env -C other sor lock a --results r.json', 'env -i -u HOME sor lock a --allow-incomplete', 'env -i FOO=1 sor lock a --confirm t'):
            with self.subTest(command):
                self.assertIsNotNone(self.asks(command))

    def test_a_project_below_the_folder_is_not_one_a_call_runs_in(self):
        """`sor` finds the project above its folder, or the one `-C` names: from a folder that has projects below it, a call has none, and nothing is written down."""
        root = self.targets(folder='sub', py='python3 tests/runner.py')
        said = self.asks('sor test --targets py')
        self.assertNotIn('python3 tests/runner.py', said)
        self.went_through('sor test --targets py')
        self.assertFalse(os.path.exists(approvals.file(Project(root))))
        self.assertIsNotNone(self.asks('sor test --targets py'))

    def test_a_project_that_cannot_be_read_does_not_turn_the_question_off(self):
        """A hook that fails says nothing, and the permission rules then let the call run: whatever goes wrong here, the call is asked about."""
        self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        self.assertIsNone(self.asks('sor test --targets py'))
        with mock.patch.object(hook, 'Project', side_effect=RuntimeError('cannot read')):
            self.assertIsNotNone(self.asks('sor test --targets py'))
        with mock.patch.object(approvals, 'state', side_effect=RuntimeError('cannot read')):
            self.assertIsNotNone(self.asks('sor test --targets py'))

    def test_a_call_outside_any_project_is_asked_about(self):
        self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        with tempfile.TemporaryDirectory() as elsewhere:
            out = hook.pre_bash(dict(self.pay('sor test --targets py'), cwd=elsewhere))
        self.assertIsNotNone(out)


class TestTheFileIsTheUsersAnswer(Approved):
    def test_a_shell_command_that_may_write_it_is_refused_and_one_that_reads_it_is_not(self):
        root = self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        path = approvals.file(Project(root))
        for command in (f"echo '{{}}' > {path}", f"printf x >> {path}", f'python3 - <<EOF\nopen("{path}", "w")\nEOF', f'cp /tmp/x {path}',
                        f'sed -i s/a/b/ {path}', f"cat {path} 'unbalanced > {path}"):
            with self.subTest(command):
                out = hook.pre_bash(self.pay(command))
                self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')
        for command in (f'cat {path}', 'grep -rn approved-targets.json .', f'ls -l {path} && git status'):
            with self.subTest(command):
                self.assertIsNone(hook.pre_bash(self.pay(command)))

    def test_an_edit_of_it_is_refused(self):
        root = self.targets(py='python3 tests/runner.py')
        self.went_through('sor test --targets py')
        path = approvals.file(Project(root))
        self.assertTrue(os.path.isfile(path))
        for tool in ('Edit', 'Write'):
            with self.subTest(tool):
                out = hook.pre_edit({'session_id': 's', 'tool_name': tool, 'cwd': root, 'tool_input': {'file_path': path}})
                self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')
                self.assertIn('written only by the hook', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_another_file_of_that_name_is_not_in_the_way(self):
        root = self.targets(py='python3 tests/runner.py')
        other = os.path.join(root, 'notes', approvals.OWN_FILE)
        self.assertIsNone(hook.approvals_refusal({'cwd': root, 'tool_input': {'file_path': other}}))


if __name__ == '__main__':
    unittest.main()
