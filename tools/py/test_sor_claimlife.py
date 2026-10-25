"""Tests for how long a claim holds (SPEC §16): it ends after a window with no activity, or when its session ends, and the work of its holder
renews it. What counts as work, what never does (a command with no session, a claim that already ran out), the project setting, and that a claims
file from a tool that knows no `idle` reads as before.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps (a clock is moved by editing `last` and `until`, or handed to `renew`). Every project lives in a
temporary folder.
"""
import json
import os
import shutil
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

import test_sor as base                            # noqa: E402
import test_sor_flows as flows                     # noqa: E402
from sorlib import claims, hook                    # noqa: E402
from sorlib.model import Project                   # noqa: E402

doc, write, read = base.doc, base.write, base.read
SESSION = 'session-one'
OTHER = 'session-two'
GREET = doc('Greet', 'Says hello.', rules=['- **hello** - The page says {text: Hello}.', '- **bye** - The page says {text: Bye}.'])


class Lives(flows.Flow):
    def setUp(self):
        super().setUp()
        self.project({'greet': GREET})
        write(self.dir, 'out/app.js', flows.APP)
        flows.accepted(self.dir)
        self.path = os.path.join(self.spec, '.sor-claims.json')

    def run_as(self, session, *args, **env):
        env = dict(env, CLAUDE_CODE_SESSION_ID=session) if session else env
        return self.sor(*args, **env)

    def claim(self, *ids, session=SESSION, ttl=None):
        extra = ('--ttl', ttl) if ttl else ()
        code, out, err = self.run_as(session, 'claim', *ids, *extra)
        self.assertEqual(code, 0, out + err)
        return [c for c in self.mine(session) if c['asked'] == sorted(ids)]

    def mine(self, session=SESSION):
        return [c for c in self.claims_file() if c.get('session') == session]

    def age(self, seconds, session=SESSION):
        """Moves the last activity of a session's claims into the past, and their end with it: as if that much time had gone by."""
        data = json.loads(read(self.path))
        for c in data['claims']:
            if c.get('session') == session:
                c['last'] -= seconds
                c['since'] -= seconds
                if c['until'] != claims.NEVER:
                    c['until'] -= seconds
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))


class TestWhatAClaimRecords(Lives):
    def test_a_claim_records_its_window_its_last_activity_and_its_end(self):
        before = time.time()
        (c,) = self.claim('greet/hello')
        self.assertEqual(c['idle'], claims.DEFAULT_TTL)
        self.assertGreaterEqual(c['last'], before - 1)
        self.assertAlmostEqual(c['until'], c['last'] + c['idle'], delta=1)

    def test_never_is_a_date_every_tool_can_read(self):
        (c,) = self.claim('greet/hello', ttl='never')
        self.assertEqual((c['idle'], c['until']), (None, claims.NEVER))
        self.assertEqual(time.gmtime(claims.NEVER)[:3], (2100, 1, 1))
        self.assertEqual(len(claims.active(Project(self.dir))), 1)

    def test_describe_shows_the_last_activity_and_when_it_ends_if_nothing_happens(self):
        (c,) = self.claim('greet/hello')
        self.age(7 * 60)
        (c,) = self.mine()
        text = claims.describe(c)
        self.assertIn('last active 7 min ago', text)
        self.assertIn(f'ends at {claims.when(c["until"])} if idle', text)
        (c,) = self.claim('greet/bye', ttl='never')
        self.assertIn('no idle limit', claims.describe(c))


class TestWhatRenewsAClaim(Lives):
    def setUp(self):
        super().setUp()
        self.claim('greet/hello')
        self.age(20 * 60)                      # 20 of its 30 minutes are gone: more than half the window

    def until(self):
        return self.mine()[0]['until']

    def test_a_command_with_the_session_id_renews_it(self):
        stale = self.until()
        self.run_as(SESSION, 'status', '--json')
        self.assertGreater(self.until(), stale + 60)
        self.assertAlmostEqual(self.until(), self.mine()[0]['last'] + claims.DEFAULT_TTL, delta=1)

    def test_a_command_with_no_session_renews_nothing(self):
        # the editor extension runs `status --json` on every refresh, and has no session: it must not keep a claim alive for ever
        stale = self.until()
        self.run_as(None, 'status', '--json')
        self.run_as(None, 'check')
        self.run_as(None, 'parts')
        self.assertEqual(self.until(), stale)

    def test_a_command_of_another_session_renews_nothing(self):
        stale = self.until()
        self.run_as(OTHER, 'status', '--json')
        self.assertEqual(self.until(), stale)

    def test_an_edit_and_a_read_by_the_session_renew_it(self):
        stale = self.until()
        spec = os.path.join(self.spec, 'greet.md')
        hook.pre_edit(dict(flows.edit(spec, '{text: Bye}', '{text: Ciao}'), session_id=SESSION))
        renewed = self.until()
        self.assertGreater(renewed, stale + 60)
        self.age(20 * 60)
        hook.post_read({'session_id': SESSION, 'tool_input': {'file_path': self.app}})
        self.assertGreater(self.until(), renewed - 20 * 60 + 60)

    def test_an_edit_by_another_session_renews_nothing(self):
        stale = self.until()
        hook.pre_edit(dict(flows.edit(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}'), session_id=OTHER))
        self.assertEqual(self.until(), stale)

    def test_it_is_not_rewritten_while_more_than_half_the_window_is_left(self):
        self.run_as(SESSION, 'status', '--json')           # renewed: the window is whole again
        before = os.stat(self.path).st_mtime_ns
        content = read(self.path)
        self.assertEqual(claims.renew(Project(self.dir), SESSION), 0)
        self.assertEqual((os.stat(self.path).st_mtime_ns, read(self.path)), (before, content))

    def test_a_claim_that_only_ran_out_is_renewed_by_its_holder_nobody_freed_it(self):
        self.age(60 * 60)
        gone = self.until()
        self.assertLess(gone, time.time())
        self.run_as(SESSION, 'status', '--json')
        self.assertGreater(self.until(), time.time())
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 3)

    def test_a_claim_that_was_freed_is_never_renewed(self):
        # it may be someone else's by now; its holder is told at the next lock or release
        self.age(60 * 60)
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 0)         # nothing was left in it: freed
        (old,) = [c for c in self.claims_file() if c['session'] == SESSION]
        gone = old['until']
        self.run_as(SESSION, 'status', '--json')
        hook.pre_edit(dict(flows.edit(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}'), session_id=SESSION))
        (old,) = [c for c in self.claims_file() if c['session'] == SESSION]
        self.assertEqual(old['until'], gone)
        code, out, _ = self.run_as(SESSION, 'lock')
        self.assertEqual(code, 2)
        self.assertIn('expired at', out)

    def test_a_person_at_a_terminal_who_names_themselves_renews_at_lock(self):
        self.run_as(None, 'claim', 'greet/bye', '--as', 'dana')
        data = json.loads(read(self.path))
        for c in data['claims']:
            if c['agent'] == 'dana':
                c['last'] -= 20 * 60
                c['until'] -= 20 * 60
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))
        (dana,) = [c for c in self.claims_file() if c['agent'] == 'dana']
        self.run_as(None, 'lock', '--as', 'dana', '--allow-incomplete')
        (after,) = [c for c in self.claims_file() if c['agent'] == 'dana']
        self.assertGreater(after['until'], dana['until'] + 60)

    def test_a_claim_is_renewed_at_least_every_five_minutes_so_it_ends_at_most_that_early(self):
        self.run_as(SESSION, 'release', '--all')
        self.claim('greet/hello')                       # 30 minutes
        (c,) = self.mine()
        project = Project(self.dir)
        self.assertEqual(claims.renew(project, SESSION, now=c['last'] + 4 * 60), 0)
        self.assertEqual(claims.renew(project, SESSION, now=c['last'] + 6 * 60), 1)
        self.run_as(SESSION, 'release', '--all')
        self.claim('greet/hello', ttl='90s')            # half its window is 45 seconds
        (c,) = self.mine()
        self.assertEqual(claims.renew(project, SESSION, now=c['last'] + 30), 0)
        self.assertEqual(claims.renew(project, SESSION, now=c['last'] + 50), 1)

    def test_every_command_a_session_runs_renews_its_claims_and_a_hook_command_leaves_that_to_the_hook(self):
        for args in (('status', '--json'), ('check',), ('parts',), ('show', 'greet'), ('markers', '--json'), ('needs',), ('changes',)):
            with self.subTest(args):
                self.run_as(SESSION, 'release', '--all')
                self.claim('greet/hello')
                self.age(20 * 60)
                stale = self.until()
                self.run_as(SESSION, *args)
                self.assertGreater(self.until(), stale + 60)

    def test_a_renewal_that_cannot_be_written_costs_the_command_nothing(self):
        def status():
            code, out, _ = self.run_as(SESSION, 'status', '--json')
            return code, {k: v for k, v in json.loads(out).items() if k != 'claims'}     # the claims carry the times that renewal moves

        expected = status()                                                # this renews the claim, which setUp had aged ...
        read_answer = hook.post_read({'session_id': SESSION, 'tool_input': {'file_path': self.app}})
        self.age(20 * 60)                                                 # ... so age it again: a renewal is due
        stale = self.until()
        for what, failure in (('a folder that cannot be written', mock.patch.object(claims, '_write', side_effect=OSError('read-only'))),
                              ('a busy claims file', mock.patch.object(claims._Mutex, '__enter__', side_effect=claims.ClaimError('busy')))):
            with self.subTest(what), failure:
                self.assertEqual(status(), expected)
                self.assertEqual(hook.post_read({'session_id': SESSION, 'tool_input': {'file_path': self.app}}), read_answer)
                self.assertIsNotNone(hook.pre_edit(dict(flows.edit(self.app, '"Hello"', '"Hi"'), session_id=SESSION)))   # and still refuses
        self.assertEqual(self.until(), stale)

    def test_an_edit_renews_without_parsing_the_project(self):
        stale = self.until()
        with mock.patch.object(hook, 'Project', side_effect=AssertionError('the project was parsed')):
            hook.renew_claims(self.dir, {'session_id': SESSION})
        self.assertGreater(self.until(), stale + 60)

    def test_a_claim_someone_else_renewed_meanwhile_is_not_written_again(self):
        # two processes see the same stale claim; the one that gets the mutex second finds it already renewed
        stale = self.claims_file()
        fresh = json.loads(json.dumps(stale))
        fresh[0]['last'] = time.time()
        with mock.patch.object(claims, 'read', side_effect=[stale, fresh]), mock.patch.object(claims, '_write') as write_:
            self.assertEqual(claims.renew(Project(self.dir), SESSION), 0)
        write_.assert_not_called()

    def test_a_failure_while_renewing_never_costs_an_edit_its_check(self):
        with mock.patch.object(claims, 'renew', side_effect=RuntimeError('broken')):
            result = hook.pre_edit(dict(flows.edit(self.app, '"Hello"', '"Hi"'), session_id=SESSION))
        self.assertIn('Clauses come first', flows.reason(result))

    def test_a_claim_with_no_window_records_its_activity_at_most_every_few_minutes(self):
        self.run_as(SESSION, 'release', '--all')
        self.claim('greet/hello', ttl='never')
        (c,) = self.mine()
        self.assertEqual(claims.renew(Project(self.dir), SESSION, now=c['last'] + 60), 0)
        self.assertEqual(claims.renew(Project(self.dir), SESSION, now=c['last'] + claims.RENEW_FLOOR + 1), 1)
        (c,) = self.mine()
        self.assertEqual(c['until'], claims.NEVER)

    def test_nothing_that_renews_nothing_makes_a_claims_file(self):
        self.run_as(SESSION, 'release', '--all')
        self.assertFalse(os.path.exists(self.path))
        self.run_as(SESSION, 'status', '--json')
        hook.post_read({'session_id': SESSION, 'tool_input': {'file_path': self.app}})
        hook.pre_edit(dict(flows.edit(self.app, '"Hello"', '"Hi"'), session_id=SESSION))
        self.assertFalse(os.path.exists(self.path))


class TestAClaimThatEnds(Lives):
    def test_after_its_idle_window_a_claim_blocks_nobody_when_nothing_is_left_to_protect(self):
        self.claim('greet/hello', ttl='90s')
        self.age(120)
        self.assertEqual(len(claims.active(Project(self.dir))), 1)         # quiet, not freed: nobody has decided anything about it yet
        self.assertEqual(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello']), [])      # but it holds nothing back
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 0)
        (old,) = [c for c in self.claims_file() if c['session'] == SESSION]
        self.assertEqual((old['freed']['by'], old['freed']['why']), (claims.session_agent(OTHER), 'quiet'))      # and it is told when it comes back
        self.assertEqual(claims.active(Project(self.dir))[0]['session'], OTHER)

    def test_a_claim_with_no_window_blocks_until_it_is_released_or_forced(self):
        self.claim('greet/hello', ttl='never')
        self.age(10 * 24 * 3600)
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 3)
        self.assertEqual(self.run_as(OTHER, 'release', 'greet/hello')[0], 3)
        self.assertEqual(self.run_as(OTHER, 'release', 'greet/hello', '--force')[0], 0)
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 0)

    def test_the_end_of_a_session_is_recorded_on_its_claims_and_only_those_and_frees_nothing(self):
        self.claim('greet/hello', session=SESSION)
        self.claim('greet/bye', session=OTHER)
        self.assertEqual(claims.mark_ended(Project(self.dir), SESSION, 'other'), 1)
        mine, theirs = self.mine(SESSION)[0], self.mine(OTHER)[0]
        self.assertEqual(mine['ended']['reason'], 'other')
        self.assertNotIn('ended', theirs)
        self.assertEqual(sorted(c['asked'][0] for c in claims.active(Project(self.dir))), ['greet/bye', 'greet/hello'])      # still in the file, still claims
        self.assertEqual(claims.mark_ended(Project(self.dir), '', 'other'), 0)

    def test_what_a_session_that_ended_held_is_free_to_the_next_agent_in_the_same_folder(self):
        self.claim('greet/hello', session=SESSION)
        claims.mark_ended(Project(self.dir), SESSION, 'other')
        self.assertEqual(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello']), [])
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 0)

    def test_a_session_that_ends_and_is_resumed_has_its_claims_back(self):
        self.claim('greet/hello', session=SESSION)
        claims.mark_ended(Project(self.dir), SESSION, 'other')
        self.run_as(SESSION, 'status', '--json')          # the resumed session shows signs of life
        self.assertNotIn('ended', self.mine(SESSION)[0])
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 3)

    def test_the_session_end_hook_run_as_a_program_records_the_end(self):
        self.claim('greet/hello', session=SESSION)
        code, out, err = flows.run_hook('session-end', {'session_id': SESSION, 'cwd': self.dir, 'reason': 'prompt_input_exit'})
        self.assertEqual((code, out), (0, ''), err)
        self.assertEqual([c['ended']['reason'] for c in self.claims_file()], ['prompt_input_exit'])
        done = subprocess.run([sys.executable, base.SOR, 'hook', 'session-end'], input='not json', cwd=REPO, capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual((done.returncode, done.stdout), (0, ''))      # a hook that fails fails open; SessionEnd output is discarded anyway
        self.assertIn('sor hook session-end failed', done.stderr)

    def test_the_session_end_hook_of_a_folder_with_no_project_does_nothing(self):
        empty = tempfile.mkdtemp()           # outside this project: a folder inside it would find it
        self.addCleanup(shutil.rmtree, empty, True)
        self.claim('greet/hello', session=SESSION)
        self.assertEqual(flows.run_hook('session-end', {'session_id': SESSION, 'cwd': empty}), (0, '', ''))
        self.assertEqual(len(self.mine(SESSION)), 1)           # the project of another folder is not touched


class TestAnOlderToolsClaims(Lives):
    def test_a_claim_without_idle_and_last_reads_as_before_and_is_never_renewed(self):
        write(self.dir, 'sor/.sor-claims.json', json.dumps({'claims': [{
            'agent': 'old', 'asked': ['greet/hello'], 'keys': ['greet/hello'], 'since': time.time() - 1200, 'until': time.time() + 600,
            'regions': [], 'session': SESSION}]}))
        (c,) = claims.active(Project(self.dir))
        self.assertIn('until', claims.describe(c))
        self.assertNotIn('last active', claims.describe(c))
        self.assertEqual(claims.renew(Project(self.dir), SESSION, now=time.time() + 590), 0)
        self.assertEqual(self.run_as(OTHER, 'claim', 'greet/hello')[0], 3)

    def test_a_claim_is_written_back_with_the_fields_a_tool_does_not_know(self):
        self.claim('greet/hello')
        data = json.loads(read(self.path))
        data['claims'][0]['note'] = 'from a later tool'
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))
        self.age(20 * 60)
        self.run_as(SESSION, 'status', '--json')
        self.assertEqual(self.mine()[0]['note'], 'from a later tool')


class TestTheProjectSetting(Lives):
    def set_claims_line(self, text):
        root = os.path.join(self.spec, 'SPECOFRECORD.md')
        write(self.dir, 'sor/SPECOFRECORD.md', read(root).replace('Why: ', f'Claims: {text}\nWhy: ', 1) if 'Why: ' in read(root)
              else read(root).replace('\n', f'\nClaims: {text}\n', 1))

    def test_the_root_file_sets_the_window_and_a_ttl_beats_it(self):
        self.set_claims_line('idle 2h')
        self.assertEqual([p for p in Project(self.dir).check() if p.kind == 'claims'], [])
        self.assertEqual(self.claim('greet/hello')[0]['idle'], 2 * 3600)
        self.assertEqual(self.claim('greet/bye', ttl='10m')[0]['idle'], 600)
        self.run_as(SESSION, 'release', '--all')
        self.set_claims_line('idle never')
        self.assertIsNone(self.claim('greet/hello')[0]['idle'])

    def test_nothing_set_is_thirty_minutes(self):
        self.assertEqual(self.claim('greet/hello')[0]['idle'], 1800)

    def test_a_line_that_is_not_understood_is_a_problem_and_the_default_holds(self):
        for text in ('idle soon', 'forever', '30m'):
            with self.subTest(text):
                self.set_claims_line(text)
                found = [p for p in Project(self.dir).check() if p.kind == 'claims']
                self.assertEqual(len(found), 1, found)
                self.assertIn('idle 30m', found[0].text)
                self.assertEqual(self.claim('greet/hello')[0]['idle'], 1800)
                self.run_as(SESSION, 'release', '--all')
                self.set_claims_line('idle 30m')

    def test_the_line_belongs_in_the_root_file(self):
        part = os.path.join(self.spec, 'greet.md')
        write(self.dir, 'sor/greet.md', read(part).replace('Why: ', 'Claims: idle 5m\nWhy: ', 1))
        found = [p for p in Project(self.dir).check() if p.kind == 'claims']
        self.assertEqual(len(found), 1, found)
        self.assertIn('root file only', found[0].text)


class TestTheRegisteredSessionEndCommands(unittest.TestCase):
    WHERE = [
        ('the plugin', os.path.join(REPO, 'plugins', 'specofrecord', 'hooks', 'hooks.json'),
         {'CLAUDE_PLUGIN_ROOT': os.path.join(REPO, 'plugins', 'specofrecord')}),
        ('this repository', os.path.join(REPO, '.claude', 'settings.json'), {'CLAUDE_PROJECT_DIR': REPO}),
    ]

    def test_each_registers_one_command_with_a_timeout_of_a_few_seconds(self):
        for name, path, _ in self.WHERE:
            with self.subTest(name):
                groups = json.loads(read(path))['hooks']['SessionEnd']
                (hook_,) = [h for g in groups for h in g['hooks']]
                self.assertIn('hook session-end', hook_['command'])
                self.assertGreaterEqual(hook_['timeout'], 3)   # the default budget of this event is 1.5 s

    def test_each_runs_the_hook_and_never_fails_without_a_project(self):
        for name, path, env in self.WHERE:
            with self.subTest(name):
                command = json.loads(read(path))['hooks']['SessionEnd'][0]['hooks'][0]['command']
                done = subprocess.run(['sh', '-c', command], input=json.dumps({'session_id': 'x', 'cwd': '/'}), capture_output=True, text=True,
                                      cwd=REPO, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **env))
                self.assertEqual((done.returncode, done.stdout), (0, ''), done.stderr)


if __name__ == '__main__':
    unittest.main()
