"""Tests for the hook that asks the user before `sor lock --allow-behind` runs (`sor hook pre-bash`): which shell commands it reads as such a
lock, what it answers, and that the commands registered for it in the plugin and in this repository run it.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. The registered commands are run through `sh`, as Claude Code runs them.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
from sorlib import hook                      # noqa: E402

PLUGIN = os.path.join(REPO, 'plugins', 'specofrecord')
NOTES = tempfile.mkdtemp(prefix='sor-guard-notes-')   # where the hooks keep what they note about a shell command: not the system's temporary folder


def setUpModule():
    tempfile.tempdir = NOTES


def tearDownModule():
    tempfile.tempdir = None
    shutil.rmtree(NOTES, ignore_errors=True)


def bash(command, **more):
    return dict({'session_id': 's', 'tool_name': 'Bash', 'tool_input': {'command': command}}, **more)


class TestWhichCommandsAreAskedAbout(unittest.TestCase):
    ASKED = [
        ('the plain form', 'sor lock greet/bye --allow-behind ts', (['greet/bye'], ['ts'])),
        ('the option with an equals sign and two languages', 'sor lock --all --allow-behind=ts,py', ([], ['ts', 'py'])),
        ('the shortest prefix argparse takes', 'sor lock a --allow-b ts', (['a'], ['ts'])),
        ('the script, with a project', 'python3 "$X/tools/py/sor.py" -C proj lock greet/bye --allow-behind ts', (['greet/bye'], ['ts'])),
        ('the Windows launcher', 'py -3 tools/py/sor.py lock a --allow-behind ts', (['a'], ['ts'])),
        ('a path to the launcher', 'cd p && /opt/x/bin/sor lock a --allow-behind ts', (['a'], ['ts'])),
        ('an agent name in the environment', 'SOR_AGENT=bob sor lock a --allow-behind ts', (['a'], ['ts'])),
        ('env and timeout in front', 'env SOR_AGENT=bob timeout 30 sor lock a --allow-behind ts', (['a'], ['ts'])),
        ('behind other commands, with a redirection', 'sor status | head -3 && sor lock a --allow-behind ts 2>&1', (['a'], ['ts'])),
        ('on the second line', 'sor status\nsor lock a --allow-behind ts', (['a'], ['ts'])),
        ('in a command substitution', 'X=$(sor lock a --allow-behind ts)', (['a'], ['ts'])),
        ('inside bash -c', 'bash -c "sor lock a --allow-behind ts"', (['a'], ['ts'])),
        ('inside eval', "eval 'cd p && sor lock a --allow-behind ts'", (['a'], ['ts'])),
        ('the values of other options are not ids', 'sor lock a --as bob --results r.json --allow-behind ts', (['a'], ['ts'])),
        ('a command that cannot be read still counts', "sor lock a --allow-behind ts 'unbalanced", ([], [])),
        ('the confirmation flag', 'sor lock greet/bye --already-fits ts', (['greet/bye'], ['ts'])),
        ('one language of a clause', 'sor lock greet/hello@ts --already-fits ts', (['greet/hello@ts'], ['ts'])),
        ('the confirmation flag with an equals sign', 'sor lock --all --already-fits=ts,py', ([], ['ts', 'py'])),
        ('the shortest prefix argparse takes for the confirmation flag', 'sor lock a --alr ts', (['a'], ['ts'])),
        ('a here-document for a shell is a list of commands', "bash <<EOF\nsor lock a --allow-behind ts\nEOF", (['a'], ['ts'])),
        ('the command after a here-document', "cat <<EOF\nsor status\nEOF\nsor lock a --allow-behind ts", (['a'], ['ts'])),
        ('the command after a here-document with tabs', "cat <<-EOF\n\tbody\n\tEOF\nsor lock a --allow-behind ts", (['a'], ['ts'])),
    ]
    NOT_ASKED = [
        ('a search for the flag', 'grep -rn "allow-behind" docs/'),
        ('a log search', 'git log --grep=allow-behind'),
        ('a search in a pipe', 'cat SPEC.md | grep -n "lock --allow-behind"'),
        ('a commit message', 'git commit -m "sor lock --allow-behind ts"'),
        ('an echo', 'echo sor lock --allow-behind ts'),
        ('a quoted string that is not run', 'echo "sor lock a --allow-behind ts"'),
        ('a lock without the flag', 'sor lock greet/bye'),
        ('an option that starts alike', 'sor lock a --all'),
        ('the short form that argparse refuses as ambiguous', 'sor lock a --allow ts'),
        ('another command with the flag', 'sor status --allow-behind ts'),
        ('nothing', ''),
        ('a here-document that writes a file', "cat > x.sh <<'EOF'\nsor lock a --allow-behind ts\nEOF"),
        ('a here-document for a script of Python', "python3 - <<'EOF'\nprint('sor lock a --allow-behind ts')\nEOF"),
        ('a command that cannot be read and does not hold both', "echo 'unbalanced"),
        ('an unreadable line that has the word but not the flag', "sor lock a 'unbalanced"),
    ]

    @staticmethod
    def ids_and_languages(command, **more):
        """(ids, languages after --allow-behind or --already-fits) of each call found in a command line."""
        return [(ids, found.get('allow-behind', []) + found.get('already-fits', [])) for _, ids, found in hook.guarded_calls(command, **more)]

    def test_a_lock_that_carries_the_flag_is_found_with_its_ids_and_languages(self):
        for name, command, expected in self.ASKED:
            with self.subTest(name):
                self.assertEqual(self.ids_and_languages(command), [expected])

    def test_each_option_is_named_as_it_was_written(self):
        for command, options in (('sor lock a --allow-behind ts', {'allow-behind'}), ('sor lock a --already-fits ts', {'already-fits'}),
                                 ('sor lock a --already-fits=ts', {'already-fits'}), ('sor lock a --alr ts', {'already-fits'}),
                                 ('sor lock a --allow-behind ts --already-fits py', {'allow-behind', 'already-fits'}),
                                 ("sor lock a --already-fits ts 'unbalanced", {'already-fits'})):
            with self.subTest(command):
                (call,) = hook.guarded_calls(command)
                self.assertEqual(set(call[2]), options)

    def test_a_command_that_only_mentions_it_is_not(self):
        for name, command in self.NOT_ASKED:
            with self.subTest(name):
                self.assertEqual(hook.guarded_calls(command), [])
                self.assertEqual(hook.guarded_calls(command.replace('allow-behind', 'already-fits')), [])

    def test_a_quoted_command_is_read_three_levels_deep_and_no_further(self):
        nested = 'bash -c "sor lock a --allow-behind ts"'
        self.assertEqual(self.ids_and_languages(nested, depth=2), [(['a'], ['ts'])])
        self.assertEqual(hook.guarded_calls(nested, depth=3), [])

    def test_two_locks_in_one_line_are_two_answers(self):
        found = self.ids_and_languages('sor lock a --allow-behind ts && sor lock b --allow-behind=py')
        self.assertEqual(found, [(['a'], ['ts']), (['b'], ['py'])])


class TestTheOtherOptionsTheUserDecides(unittest.TestCase):
    """--allow-incomplete, --confirm, --results and --targets: what a lock or a test run does with them is the user's call too."""
    ASKED = [
        ('the plain form of each', 'sor lock a --allow-incomplete', 'lock', ['a'], {'allow-incomplete': []}),
        ('its shortest prefix', 'sor lock a --allow-i', 'lock', ['a'], {'allow-incomplete': []}),
        ('a list of tests after --confirm, none of them an id', 'sor lock a --confirm t1 t2', 'lock', ['a'], {'confirm': ['t1', 't2']}),
        ('--confirm with an equals sign', 'sor lock --confirm=t1', 'lock', [], {'confirm': ['t1']}),
        ('the shortest prefix of --confirm', 'sor lock --c t1', 'lock', [], {'confirm': ['t1']}),
        ('a results file', 'sor lock a --results r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('a results file with an equals sign', 'sor lock a --results=r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('the shortest prefix of --results', 'sor lock a --res r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('a lock that runs a target', 'sor lock a --run-tests --targets py', 'lock', ['a'], {'targets': ['py']}),
        ('a test run that runs a target', 'sor test --targets py', 'test', [], {'targets': ['py']}),
        ('a test run with two targets and a test', 'sor test greet --targets=py,ts', 'test', ['greet'], {'targets': ['py', 'ts']}),
        ('the shortest prefix of --targets', 'sor test --t py', 'test', [], {'targets': ['py']}),
        ('the script, with a project in front of the command', 'python3 tools/py/sor.py -C proj test --targets py', 'test', [], {'targets': ['py']}),
        ('a project folder that is named like a command', 'sor -C test lock a --results r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('inside bash -c', 'bash -c "sor test --targets py"', 'test', [], {'targets': ['py']}),
        ('a variable that holds the command', 'P="python3 tools/py/sor.py -C proj"; $P lock a --results r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('a variable in braces and quotes', '"${P}" lock a --results r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('a variable that holds the Python launcher', '$PY tools/py/sor.py -C proj lock a --results r.json', 'lock', ['a'], {'results': ['r.json']}),
        ('a variable that holds the command, with a test run', '$SOR test --targets py', 'test', [], {'targets': ['py']}),
        ('several at once', 'sor lock a --results r.json --allow-incomplete', 'lock', ['a'], {'results': ['r.json'], 'allow-incomplete': []}),
        ('a command that cannot be read', "sor test --targets py 'unbalanced", 'test', [], {'targets': []}),
        ('an unreadable lock with the shortest prefix of --confirm', "sor lock --c t1 'unbalanced", 'lock', [], {'confirm': []}),
    ]
    NOT_ASKED = [
        ('a plain test run', 'sor test'),
        ('a test run with the options that are not guarded', 'sor test greet --coverage --out r.json --provides linux'),
        ('a lock that runs the web tests', 'sor lock a --run-tests'),
        ('a lock with the options that are not guarded', 'sor lock --all --as bob --rehash'),
        ('the results of a CI job, which are not a lock', 'sor evidence --job linux --provides linux --results r.json'),
        ('another command with the option', 'sor status --targets py'),
        ('a project folder that is named like a command', 'sor -C lock status'),
        ('a search for the options', 'grep -rn -e "--targets" -e "--results" docs/'),
        ('an echo', 'echo sor test --targets py'),
        ('a path that starts with a variable', '$HOME/bin/tool lock a --results r.json'),
        ('a variable that holds something else with the option on another command', '$P status --targets py'),
        ('a commit message', 'git commit -m "sor lock --allow-incomplete"'),
        ('a here-document that writes a file', "cat > x.sh <<'EOF'\nsor test --targets py\nEOF"),
        ('an unreadable line that has lock and an option that only starts alike', "git diff --cached lock 'unbalanced"),
        ('an unreadable line that has test and an option that only starts alike', "pytest 'a test --tb=short"),
        ('an unreadable line that has test and --coverage', "sor test --coverage 'unbalanced"),
    ]

    def test_each_is_found_with_its_command_ids_and_values(self):
        for name, command, which, ids, found in self.ASKED:
            with self.subTest(name):
                self.assertEqual(hook.guarded_calls(command), [(which, ids, found)])

    def test_a_command_that_only_mentions_them_is_not_asked_about(self):
        for name, command in self.NOT_ASKED:
            with self.subTest(name):
                self.assertEqual(hook.guarded_calls(command), [])

    def test_the_user_is_told_what_each_one_does(self):
        for command, said in (
                ('sor lock a --allow-incomplete', 'Claude wants to save its work on a even though some tests have not passed'),
                ('sor lock a --confirm t1 t2', 'Claude wants to write down that a person has checked t1, t2 by hand'),
                ('sor lock a --results r.json', 'using the test results in r.json, a file that nothing checks against a real test run'),
                ('sor test --targets py', 'Claude wants to run the test command the spec gives for py')):
            with self.subTest(command):
                out = hook.pre_bash(bash(command))['hookSpecificOutput']
                self.assertEqual(out['permissionDecision'], 'ask')
                self.assertIn(said, out['permissionDecisionReason'])

    def test_the_question_is_in_plain_words_with_no_option_or_command_in_it(self):
        """The user reads it in a permission dialog and may never have heard of the options; the dialog shows the command itself."""
        for flag in ('--allow-behind ts', '--already-fits ts', '--allow-incomplete', '--confirm t1', '--results r.json', '--targets py'):
            with self.subTest(flag):
                reason = hook.pre_bash(bash(f'sor lock greet/bye {flag}'))['hookSpecificOutput']['permissionDecisionReason']
                self.assertTrue(reason.startswith('Claude wants to '), reason)
                self.assertIn(' Say yes only if ', reason)
                for word in ('--', 'sor ', '{run:}', 'allow-', 'already-fits'):
                    self.assertNotIn(word, reason, word)

    def test_a_test_run_is_not_said_to_be_a_lock(self):
        reason = hook.pre_bash(bash('sor test --targets py'))['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('Claude wants to run the test command', reason)
        self.assertNotIn('lock', reason)
        self.assertNotIn('save', reason)
        self.assertIn('and save its work with its results', hook.pre_bash(bash('sor lock --run-tests --targets py'))['hookSpecificOutput']['permissionDecisionReason'])


class TestTheTestCommandTheUserIsAskedAbout(base.Case):
    """A target's name tells the user nothing; the command the spec gives for it is what would run on their computer."""

    def payload(self, command):
        return dict(bash(command), cwd=self.dir)

    def reason(self, command):
        return hook.pre_bash(self.payload(command))['hookSpecificOutput']['permissionDecisionReason']

    def targets(self, **runs):
        parts = {f'targets/{name}': base.doc(name.title(), 'Where the code lives and how its tests run.',
                                             rules=[f'- **code** - The code is {{path: src_{name}/}}.'] +
                                                   ([f'- **runner** - Run with {{run: {run}}}, results in {{results: out/{name}.json}}.'] if run else []))
                 for name, run in runs.items()}
        self.project(parts)

    def test_the_command_of_the_spec_is_named(self):
        self.targets(py='python3 tests/runner.py')
        said = self.reason('sor lock --run-tests --targets py')
        self.assertIn('Claude wants to run the test command `python3 tests/runner.py` and save its work with its results.', said)
        self.assertIn('you trust that command', said)
        self.assertNotIn('--', said)

    def test_two_targets_are_named_with_their_commands(self):
        self.targets(py='python3 tests/runner.py', ts='npm test')
        self.assertIn('the test command py: `python3 tests/runner.py`, ts: `npm test`', self.reason('sor test --targets py,ts'))

    def test_a_target_with_no_command_or_no_project_is_named_instead(self):
        self.targets(py='python3 tests/runner.py', ts='')
        self.assertIn('the test command the spec gives for ts', self.reason('sor test --targets ts'))
        self.assertIn('the test command the spec gives for py and ts', self.reason('sor test --targets py,ts'))
        with tempfile.TemporaryDirectory() as elsewhere:   # a folder above which there is no project
            said = hook.pre_bash(dict(bash('sor test --targets py'), cwd=elsewhere))['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('the test command the spec gives for py', said)


class TestWhatTheHookAnswers(unittest.TestCase):
    def test_it_asks_and_says_which_clauses_and_languages(self):
        out = hook.pre_bash(bash('sor lock greet/bye greet/hello --allow-behind ts'))['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'ask'))
        self.assertIn('its work on greet/bye, greet/hello', out['permissionDecisionReason'])
        self.assertIn('the code for ts is out of date with the changed spec, or missing', out['permissionDecisionReason'])
        self.assertIn('Say yes only if you have already agreed that ts can come later.', out['permissionDecisionReason'])

    def test_it_says_what_each_option_does(self):
        out = hook.pre_bash(bash('sor lock a --already-fits ts'))['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('mark the code for ts as already matching the changed spec, without changing it', out)
        self.assertNotIn('out of date', out)
        both = hook.pre_bash(bash('sor lock a --allow-behind ts --already-fits py'))['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('the code for ts is out of date', both)
        self.assertIn('It also wants to save its work on a and mark the code for py as already matching', both)
        self.assertEqual(both.count('Say yes only if'), 1)    # one sentence for both, not one for each
        self.assertIn('ts can come later, and you have checked that the code still does what the changed spec says.', both)

    def test_a_lock_of_what_was_claimed_says_so(self):
        self.assertIn('Claude wants to save its work although', hook.pre_bash(bash('sor lock --allow-behind ts'))['hookSpecificOutput']['permissionDecisionReason'])

    def test_it_says_nothing_for_other_commands_and_other_tools(self):
        self.assertIsNone(hook.pre_bash(bash('sor lock greet/bye')))
        self.assertIsNone(hook.pre_bash(bash('grep -rn allow-behind docs')))
        self.assertIsNone(hook.pre_bash({'tool_name': 'Edit', 'tool_input': {'command': 'sor lock a --allow-behind ts'}}))
        self.assertIsNone(hook.pre_bash({}))

    def test_run_as_a_program_it_answers_on_stdout_and_never_blocks_on_its_own_failure(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=NOTES)
        done = subprocess.run([sys.executable, base.SOR, 'hook', 'pre-bash'], input=json.dumps(bash('sor lock a --allow-behind ts')),
                              cwd=REPO, capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['hookSpecificOutput']['permissionDecision'], 'ask')
        done = subprocess.run([sys.executable, base.SOR, 'hook', 'pre-bash'], input=json.dumps(bash('ls')), cwd=REPO,
                              capture_output=True, text=True, env=env)
        self.assertEqual((done.returncode, done.stdout), (0, ''))
        done = subprocess.run([sys.executable, base.SOR, 'hook', 'pre-bash'], input='this is not json', cwd=REPO,
                              capture_output=True, text=True, env=env)
        self.assertEqual((done.returncode, done.stdout), (1, ''))      # exit 1 does not block the tool call
        self.assertIn('sor hook pre-bash failed', done.stderr)


def registered_command(path, matcher):
    with open(path, encoding='utf8') as fh:
        groups = json.load(fh)['hooks']['PreToolUse']
    found = [h['command'] for g in groups if g.get('matcher') == matcher for h in g['hooks']]
    assert len(found) == 1, f'{path} should register one command for {matcher}'
    return found[0]


class TestTheRegisteredCommands(unittest.TestCase):
    """What Claude Code runs before a shell command: one command that starts the hook for every command, because the check after a command needs the
    stamps of the files before it (a command that mentions neither flag still gets no answer)."""
    WHERE = [
        ('the plugin', os.path.join(PLUGIN, 'hooks', 'hooks.json'), {'CLAUDE_PLUGIN_ROOT': PLUGIN}),
        ('this repository', os.path.join(REPO, '.claude', 'settings.json'), {'CLAUDE_PROJECT_DIR': REPO}),
    ]

    def run_command(self, command, env, payload):
        return subprocess.run(['sh', '-c', command], input=json.dumps(payload), capture_output=True, text=True, cwd=REPO,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=NOTES, **env))

    def test_each_asks_for_a_lock_with_any_of_the_options_the_user_decides(self):
        for name, path, env in self.WHERE:
            for flag in ('--allow-behind ts', '--already-fits ts', '--alr ts', '--allow-incomplete', '--confirm t1', '--results r.json', '--targets py'):
                with self.subTest(name, flag=flag):
                    done = self.run_command(registered_command(path, 'Bash'), env, bash(f'sor lock greet/bye {flag}'))
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(json.loads(done.stdout)['hookSpecificOutput']['permissionDecision'], 'ask')

    def test_each_asks_for_a_test_run_that_names_a_target(self):
        for name, path, env in self.WHERE:
            with self.subTest(name):
                done = self.run_command(registered_command(path, 'Bash'), env, bash('sor test --targets py'))
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(json.loads(done.stdout)['hookSpecificOutput']['permissionDecision'], 'ask')

    def test_each_is_silent_for_a_command_that_only_mentions_it_or_does_not_at_all(self):
        for name, path, env in self.WHERE:
            for command in ('grep -rn allow-behind docs', 'grep -rn already-fits docs', 'ls -la', 'sor lock greet/bye'):
                with self.subTest(name, command=command):
                    done = self.run_command(registered_command(path, 'Bash'), env, bash(command))
                    self.assertEqual((done.returncode, done.stdout, done.stderr), (0, '', ''))

    def test_the_commands_for_edits_are_still_the_ones_for_edits(self):
        for name, path, env in self.WHERE:
            with self.subTest(name):
                self.assertIn('hook pre-edit', registered_command(path, 'Edit|Write|MultiEdit'))
                self.assertIn('hook pre-bash', registered_command(path, 'Bash'))


if __name__ == '__main__':
    unittest.main()
