"""Tests for the hook that asks the user before `sor lock --allow-behind` runs (`sor hook pre-bash`): which shell commands it reads as such a
lock, what it answers, and that the commands registered for it in the plugin and in this repository run it.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. The registered commands are run through `sh`, as Claude Code runs them.
"""
import json
import os
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
from sorlib import hook                      # noqa: E402

PLUGIN = os.path.join(REPO, 'plugins', 'specofrecord')


def bash(command, **more):
    return dict({'session_id': 's', 'tool_name': 'Bash', 'tool_input': {'command': command}}, **more)


class TestWhichCommandsAreALockWithAllowBehind(unittest.TestCase):
    ASKED = [
        ('the plain form', 'sor lock greet/bye --allow-behind ts', (['greet/bye'], ['ts'])),
        ('the option with an equals sign and two languages', 'sor lock --all --allow-behind=ts,py', ([], ['ts', 'py'])),
        ('the shortest prefix argparse takes', 'sor lock a --allow-b ts', (['a'], ['ts'])),
        ('the script, with a project', 'python3 "$X/tools/sor.py" -C proj lock greet/bye --allow-behind ts', (['greet/bye'], ['ts'])),
        ('the Windows launcher', 'py -3 tools/sor.py lock a --allow-behind ts', (['a'], ['ts'])),
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
        ('another option that starts alike', 'sor lock a --allow-incomplete'),
        ('another command with the flag', 'sor status --allow-behind ts'),
        ('nothing', ''),
        ('a here-document that writes a file', "cat > x.sh <<'EOF'\nsor lock a --allow-behind ts\nEOF"),
        ('a here-document for a script of Python', "python3 - <<'EOF'\nprint('sor lock a --allow-behind ts')\nEOF"),
        ('a command that cannot be read and does not hold both', "echo 'unbalanced"),
        ('an unreadable line that has the word but not the flag', "sor lock a 'unbalanced"),
    ]

    def test_a_lock_that_carries_the_flag_is_found_with_its_ids_and_languages(self):
        for name, command, expected in self.ASKED:
            with self.subTest(name):
                self.assertEqual([(i, l) for i, l, _ in hook.lock_allowances(command)], [expected])

    def test_each_option_is_named_as_it_was_written(self):
        for command, options in (('sor lock a --allow-behind ts', {'allow-behind'}), ('sor lock a --already-fits ts', {'already-fits'}),
                                 ('sor lock a --already-fits=ts', {'already-fits'}), ('sor lock a --alr ts', {'already-fits'}),
                                 ('sor lock a --allow-behind ts --already-fits py', {'allow-behind', 'already-fits'}),
                                 ("sor lock a --already-fits ts 'unbalanced", {'already-fits'})):
            with self.subTest(command):
                (call,) = hook.lock_allowances(command)
                self.assertEqual(call[2], options)

    def test_a_command_that_only_mentions_it_is_not(self):
        for name, command in self.NOT_ASKED:
            with self.subTest(name):
                self.assertEqual(hook.lock_allowances(command), [])
                self.assertEqual(hook.lock_allowances(command.replace('allow-behind', 'already-fits')), [])

    def test_a_quoted_command_is_read_three_levels_deep_and_no_further(self):
        nested = 'bash -c "sor lock a --allow-behind ts"'
        self.assertEqual([(i, l) for i, l, _ in hook.lock_allowances(nested, depth=2)], [(['a'], ['ts'])])
        self.assertEqual(hook.lock_allowances(nested, depth=3), [])

    def test_two_locks_in_one_line_are_two_answers(self):
        found = hook.lock_allowances('sor lock a --allow-behind ts && sor lock b --allow-behind=py')
        self.assertEqual([(i, l) for i, l, _ in found], [(['a'], ['ts']), (['b'], ['py'])])


class TestWhatTheHookAnswers(unittest.TestCase):
    def test_it_asks_and_says_which_clauses_and_languages(self):
        out = hook.pre_bash(bash('sor lock greet/bye greet/hello --allow-behind ts'))['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'ask'))
        self.assertIn('greet/bye, greet/hello', out['permissionDecisionReason'])
        self.assertIn('ts would stay behind the clause or have no code for it', out['permissionDecisionReason'])
        self.assertIn('Allow it only if you have said that this language comes later, or have checked that its code fits', out['permissionDecisionReason'])

    def test_it_says_what_each_option_does(self):
        out = hook.pre_bash(bash('sor lock a --already-fits ts'))['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('with --already-fits: ts would be cleared as fitting the changed clause, with no code change', out)
        self.assertNotIn('--allow-behind', out)
        both = hook.pre_bash(bash('sor lock a --allow-behind ts --already-fits py'))['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('--allow-behind', both)
        self.assertIn('--already-fits', both)

    def test_a_lock_of_what_was_claimed_says_so(self):
        self.assertIn('of what it claimed', hook.pre_bash(bash('sor lock --allow-behind ts'))['hookSpecificOutput']['permissionDecisionReason'])

    def test_it_says_nothing_for_other_commands_and_other_tools(self):
        self.assertIsNone(hook.pre_bash(bash('sor lock greet/bye')))
        self.assertIsNone(hook.pre_bash(bash('grep -rn allow-behind docs')))
        self.assertIsNone(hook.pre_bash({'tool_name': 'Edit', 'tool_input': {'command': 'sor lock a --allow-behind ts'}}))
        self.assertIsNone(hook.pre_bash({}))

    def test_run_as_a_program_it_answers_on_stdout_and_never_blocks_on_its_own_failure(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
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
    """What Claude Code runs: a shell command that first looks at the text, so that Python starts only for a command that mentions the flag."""
    WHERE = [
        ('the plugin', os.path.join(PLUGIN, 'hooks', 'hooks.json'), {'CLAUDE_PLUGIN_ROOT': PLUGIN}),
        ('this repository', os.path.join(REPO, '.claude', 'settings.json'), {'CLAUDE_PROJECT_DIR': REPO}),
    ]

    def run_command(self, command, env, payload):
        return subprocess.run(['sh', '-c', command], input=json.dumps(payload), capture_output=True, text=True, cwd=REPO,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **env))

    def test_each_asks_for_a_lock_with_either_flag(self):
        for name, path, env in self.WHERE:
            for flag in ('--allow-behind ts', '--already-fits ts', '--alr ts'):
                with self.subTest(name, flag=flag):
                    done = self.run_command(registered_command(path, 'Bash'), env, bash(f'sor lock greet/bye {flag}'))
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
