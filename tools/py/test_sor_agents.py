"""Tests for how claims tell agents apart inside one Claude Code session (proposals/shared-claims.md, "Who holds a claim"). Subagents share their parent's session
id, but Claude Code gives a hook an `agent_id` inside one: the Bash hook binds it to the name it passes with `--as`, the edit guard attributes an edit to that name, a
subagent's activity renews its own claims and not the parent's, and the events of a subagent (`SubagentStart`, `SubagentStop`) and of the session (`Stop`, `SessionStart`)
say whether a holder is gone. Also `sor claims --json`, `sor queued`, and what an agent may not do from a shell (`sor release --force`).

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps.
"""
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import claims, hook              # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
S = 'ssssssss-0'           # the session of a parent and its subagents
OTHER = 'oooooooo-9'
X, Y, Z = 'agentx1234567890', 'agenty1234567890', 'agentz1234567890'
PAGE = base.doc('Greet', 'Says hello.',
                rules=['- **hello** - The page says {text: Hello}.', '', '- **bye** - The page says {text: Bye}.', '', '- **thanks** - The page says {text: Thanks}.'],
                tests=['- **hello** - says hello.', '  manual: a person looks'])
CODE = ('// @clause glue\n"use strict";\n// @clause end\n// @clause greet/hello\nconsole.log("Hello");\n// @clause end\n'
        '// @clause greet/bye\nconsole.log("Bye");\n// @clause end\n// @clause greet/thanks\nconsole.log("Thanks");\n// @clause end\n')


class Agents(flows.Flow):
    def setUp(self):
        super().setUp()
        self.project({'greet': PAGE})
        write(self.dir, 'out/app.js', CODE)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        patcher = mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def bash(self, command, agent_id='', session=S):
        payload = {'tool_name': 'Bash', 'tool_input': {'command': command}, 'session_id': session, 'cwd': self.dir}
        if agent_id:
            payload['agent_id'] = agent_id
        return hook.pre_bash(payload)

    def claim(self, name, *ids, session=S):
        code, out, err = self.sor('claim', *ids, '--as', name, CLAUDE_CODE_SESSION_ID=session)
        self.assertEqual(code, 0, out + err)

    def edit(self, agent_id='', session=S, clause='hello', old='Hello', new='Hi'):
        spec = os.path.join(self.spec, 'greet.md')
        payload = dict(flows.edit(spec, '{text: %s}' % old, '{text: %s}' % new), session_id=session)
        if agent_id:
            payload['agent_id'] = agent_id
        return flows.reason(hook.pre_edit(payload))

    def records(self, name):
        return [c for c in claims.read(Project(self.dir)) if c['agent'] == name and not c.get('freed')]

    def age(self, name, seconds):
        project = Project(self.dir)
        held = claims.read(project)
        for c in held:
            if c['agent'] == name:
                c['last'] -= seconds
                c['until'] -= seconds
        claims._write(project, held)


class TestASubagentNamesItself(Agents):
    def test_a_claim_lock_or_release_from_a_subagent_without_a_name_is_refused_with_what_to_pass(self):
        for command in ('sor claim greet/hello', 'sor lock greet/hello', 'sor release --all', 'cd x && sor claim greet/bye'):
            said = flows.reason(self.bash(command, agent_id=X))
            self.assertIn('You are a subagent', said, command)
            self.assertIn('--as', said)
            self.assertIn(X[:8], said)

    def test_the_parent_needs_no_name_and_neither_does_a_command_that_is_not_a_claim_lock_or_release(self):
        self.assertIsNone(self.bash('sor claim greet/hello'))
        self.assertIsNone(self.bash('sor status', agent_id=X))
        self.assertIsNone(self.bash('sor check', agent_id=X))
        self.assertIsNone(self.bash('echo sor claim greet/hello', agent_id=X))
        self.assertIsNone(self.bash('grep -rn "sor claim" docs', agent_id=X))

    def test_a_name_binds_the_subagent_and_only_one_subagent_may_have_it(self):
        self.assertIsNone(self.bash('sor claim greet/hello --as sub-a', agent_id=X))
        self.assertEqual(claims.bound_name(Project(self.dir), S, X), 'sub-a')
        self.assertIsNone(self.bash('sor lock greet/hello --as sub-a', agent_id=X))      # again, the same subagent
        said = flows.reason(self.bash('sor claim greet/bye --as sub-a', agent_id=Y))
        self.assertIn('already used by another subagent', said)
        self.assertEqual(claims.bound_name(Project(self.dir), S, Y), '')
        self.assertIsNone(self.bash('sor claim greet/bye --as sub-b', agent_id=Y))

    def test_the_name_may_be_given_in_the_other_spellings_and_inside_a_shell(self):
        self.assertIsNone(self.bash('SOR_X=1 sor claim greet/hello --as=sub-a', agent_id=X))
        self.assertIsNone(self.bash('bash -c "sor claim greet/bye --as sub-b"', agent_id=Y))
        self.assertEqual((claims.bound_name(Project(self.dir), S, X), claims.bound_name(Project(self.dir), S, Y)), ('sub-a', 'sub-b'))
        self.assertIn('You are a subagent', flows.reason(self.bash('bash -c "sor claim greet/bye"', agent_id=Z)))

    def test_the_same_name_in_another_session_is_another_subagent(self):
        self.assertIsNone(self.bash('sor claim greet/hello --as sub-a', agent_id=X))
        self.assertIsNone(self.bash('sor claim greet/bye --as sub-a', agent_id=Y, session=OTHER))


class TestHooksAtARepositoryRoot(flows.Flow):
    """A repository root that holds projects in subfolders has no `sor/` above it: the hooks find the project from the folder `sor -C <folder>` names, or from the
    projects below the cwd (the pattern CLAUDE.md prescribes for this repository: examples/solar-system, editors/vscode)."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.dir, 'proj')
        base.make_project(self.proj, {'greet': PAGE})
        write(self.proj, 'out/app.js', CODE)
        self.assertEqual(base.run_sor(self.proj, 'lock', '--all')[0], 0)
        patcher = mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def bash(self, command, agent_id=X, cwd=None):
        return hook.pre_bash({'tool_name': 'Bash', 'tool_input': {'command': command}, 'session_id': S, 'agent_id': agent_id, 'cwd': cwd or self.dir})

    def test_the_folder_a_c_option_names_decides_where_a_subagent_is_bound(self):
        for spelling in (f'-C {self.proj}', f'-C proj', f'-Cproj'):
            claims._write(claims.at(self.proj), [])
            for path in (claims.bindings_file(claims.at(self.proj)),):
                if os.path.exists(path):
                    os.remove(path)
            self.assertIsNone(self.bash(f'python3 tools/py/sor.py {spelling} claim greet/hello --as sub-a'), spelling)
            self.assertEqual(claims.bound_name(claims.at(self.proj), S, X), 'sub-a', spelling)

    def test_a_c_folder_that_is_no_project_binds_nothing_and_does_not_fail(self):
        self.assertIsNone(self.bash('python3 tools/py/sor.py -C /nonexistent claim greet/hello --as sub-a'))
        self.assertEqual(claims.read_bindings(claims.at(self.proj)), {})

    def test_without_c_the_projects_below_the_cwd_are_bound_in(self):
        self.assertIsNone(self.bash('cd proj && sor claim greet/hello --as sub-a'))
        self.assertEqual(claims.bound_name(claims.at(self.proj), S, X), 'sub-a')

    def test_the_binding_makes_the_subagents_own_edit_pass_and_a_siblings_not(self):
        self.bash(f'python3 tools/py/sor.py -C {self.proj} claim greet/hello --as sub-a')
        with mock.patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': S}):
            self.assertEqual(base.run_sor(self.proj, 'claim', 'greet/hello', '--as', 'sub-a')[0], 0)
        spec = os.path.join(self.proj, 'sor', 'greet.md')
        own = dict(flows.edit(spec, '{text: Hello}', '{text: Hi}'), session_id=S, agent_id=X, cwd=self.dir)
        sibling = dict(flows.edit(spec, '{text: Hello}', '{text: Hi}'), session_id=S, agent_id=Y, cwd=self.dir)
        self.assertIsNone(flows.reason(hook.pre_edit(own)))
        self.assertIn('Someone else is working on this', flows.reason(hook.pre_edit(sibling)))

    def test_the_end_of_the_session_and_the_events_are_recorded_in_the_projects_below_the_cwd(self):
        with mock.patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': S}):
            self.assertEqual(base.run_sor(self.proj, 'claim', 'greet/hello', '--as', 'sub-a')[0], 0)
        self.bash(f'python3 tools/py/sor.py -C {self.proj} claim greet/hello --as sub-a')
        payload = {'session_id': S, 'cwd': self.dir, 'agent_id': X}
        hook.stop(dict(payload, background_tasks=[{'type': 'shell'}]))
        (c,) = claims.read(claims.at(self.proj))
        self.assertTrue(c['busy_at'])
        hook.subagent_stop(payload)
        self.assertTrue(claims.read(claims.at(self.proj))[0]['stopped'])
        hook.subagent_start(payload)
        self.assertNotIn('stopped', claims.read(claims.at(self.proj))[0])
        hook.session_end(dict(payload, reason='other'))
        self.assertEqual(claims.read(claims.at(self.proj))[0]['ended']['reason'], 'other')

    def test_a_folder_with_no_project_below_it_is_left_alone(self):
        import shutil
        import tempfile
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, True)
        self.assertIsNone(hook.session_end({'session_id': S, 'cwd': empty}))
        self.assertIsNone(hook.stop({'session_id': S, 'cwd': empty, 'background_tasks': [{'type': 'shell'}]}))


class TestTheEditGuardTellsSiblingsApart(Agents):
    def setUp(self):
        super().setUp()
        self.bash('sor claim greet/hello --as sub-a', agent_id=X)
        self.claim('sub-a', 'greet/hello')
        self.bash('sor claim greet/bye --as sub-b', agent_id=Y)

    def test_a_subagent_may_edit_what_it_holds(self):
        self.assertIsNone(self.edit(agent_id=X))

    def test_a_sibling_may_not(self):
        said = self.edit(agent_id=Y)
        self.assertIn('Someone else is working on this', said)
        self.assertIn('sub-a', said)

    def test_a_subagent_that_has_bound_no_name_holds_nothing_and_is_refused_what_somebody_holds(self):
        self.assertIn('Someone else is working on this', self.edit(agent_id=Z))
        self.assertIsNone(self.edit(agent_id=Z, clause='thanks', old='Thanks', new='Ta'))      # nobody holds thanks

    def test_the_parent_is_the_session_and_may_edit_the_clauses_its_subagents_hold(self):
        self.assertIsNone(self.edit())      # as it always could: the session is one agent for the guard

    def test_another_session_is_refused_as_before(self):
        self.assertIn('Someone else is working on this', self.edit(session=OTHER))

    def test_a_claim_of_the_parent_is_not_a_subagents_own(self):
        self.claim('main', 'greet/thanks')
        self.assertIn('Someone else is working on this', self.edit(agent_id=X, clause='thanks', old='Thanks', new='Ta'))


class TestAgentsMayNotForceARelease(Agents):
    def test_release_force_is_refused_to_the_parent_and_to_a_subagent(self):
        for agent in ('', X):
            for command in ('sor release greet/hello --force', 'sor release --force greet/hello --as sub-a', 'sor release --all --force', 'python3 tools/py/sor.py release x --force'):
                said = flows.reason(self.bash(command, agent_id=agent))
                self.assertIn('frees a claim somebody else holds', said, (agent, command))
                self.assertIn('claim <id>', said)

    def test_the_abbreviations_argparse_takes_for_force_are_refused_too(self):
        for flag in ('--f', '--fo', '--for', '--forc', '--force', '--force=1'):
            said = flows.reason(self.bash(f'sor release greet/hello {flag}'))
            self.assertIn('frees a claim somebody else holds', said, flag)
        for flag in ('--all', '--as main', '--fr', '--fo2'):
            self.assertIsNone(self.bash(f'sor release greet/hello {flag}'), flag)

    def test_a_release_without_force_and_talk_about_it_pass(self):
        self.assertIsNone(self.bash('sor release --all'))
        self.assertIsNone(self.bash('sor release greet/hello --as main'))
        self.assertIsNone(self.bash('git commit -m "sor release --force"'))
        self.assertIsNone(self.bash('grep -rn "release --force" docs'))

    def test_a_person_at_a_terminal_still_can(self):
        self.claim('sub-a', 'greet/hello')
        code, out, err = self.sor('release', 'greet/hello', '--force')
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.records('sub-a'), [])


class TestWhatRenewsWhom(Agents):
    def setUp(self):
        super().setUp()
        self.claim('main', 'greet/thanks')
        self.bash('sor claim greet/hello --as sub-a', agent_id=X)
        self.claim('sub-a', 'greet/hello')
        self.bash('sor claim greet/bye --as sub-b', agent_id=Y)
        self.claim('sub-b', 'greet/bye')
        for name in ('main', 'sub-a', 'sub-b'):
            self.age(name, 20 * 60)

    def until(self, name):
        return self.records(name)[0]['until']

    def read(self, agent_id=''):
        payload = {'session_id': S, 'tool_input': {'file_path': self.app}}
        if agent_id:
            payload['agent_id'] = agent_id
        hook.post_read(payload)

    def test_a_subagent_renews_its_own_claims_and_nobody_elses(self):
        before = {n: self.until(n) for n in ('main', 'sub-a', 'sub-b')}
        self.read(agent_id=X)
        self.assertGreater(self.until('sub-a'), before['sub-a'] + 60)
        self.assertEqual((self.until('main'), self.until('sub-b')), (before['main'], before['sub-b']))

    def test_the_parent_renews_its_own_and_not_a_subagents(self):
        before = {n: self.until(n) for n in ('main', 'sub-a', 'sub-b')}
        self.read()
        self.assertGreater(self.until('main'), before['main'] + 60)
        self.assertEqual((self.until('sub-a'), self.until('sub-b')), (before['sub-a'], before['sub-b']))      # a finished subagent's claim is not kept alive by its parent

    def test_a_subagent_with_no_name_renews_nothing(self):
        before = {n: self.until(n) for n in ('main', 'sub-a', 'sub-b')}
        self.read(agent_id=Z)
        self.assertEqual({n: self.until(n) for n in before}, before)

    def test_a_command_with_a_name_renews_that_name_only(self):
        before = {n: self.until(n) for n in ('main', 'sub-a', 'sub-b')}
        self.sor('lock', 'greet/test:hello', '--as', 'sub-b', '--allow-incomplete', CLAUDE_CODE_SESSION_ID=S)
        self.assertGreater(self.until('sub-b'), before['sub-b'] + 60)
        self.assertEqual((self.until('main'), self.until('sub-a')), (before['main'], before['sub-a']))


class TestTheEventsOfSubagentsAndSessions(Agents):
    def setUp(self):
        super().setUp()
        self.bash('sor claim greet/hello --as sub-a', agent_id=X)
        self.claim('sub-a', 'greet/hello')

    def payload(self, **more):
        return dict({'session_id': S, 'cwd': self.dir}, **more)

    def test_a_subagent_that_stopped_is_gone_and_one_that_is_resumed_is_not(self):
        hook.subagent_stop(self.payload(agent_id=X))
        self.assertTrue(self.records('sub-a')[0]['stopped'])
        self.assertEqual(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello']), [])      # gone, and nothing left
        hook.subagent_start(self.payload(agent_id=X))
        self.assertNotIn('stopped', self.records('sub-a')[0])
        self.assertEqual(len(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello'])), 1)

    def test_a_subagent_that_stopped_leaves_its_parents_claims_alone(self):
        self.claim('main', 'greet/thanks')
        hook.subagent_stop(self.payload(agent_id=X))
        self.assertNotIn('stopped', self.records('main')[0])

    def test_the_start_of_a_subagent_tells_it_to_name_itself(self):
        out = hook.subagent_start(self.payload(agent_id=Y))
        self.assertIn('--as', out['hookSpecificOutput']['additionalContext'])
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'SubagentStart')

    def test_the_events_do_nothing_in_a_folder_with_no_project(self):
        empty = self.folder_without_a_project()
        self.assertIsNone(hook.subagent_stop({'session_id': S, 'cwd': empty, 'agent_id': X}))
        self.assertIsNone(hook.subagent_start({'session_id': S, 'cwd': empty, 'agent_id': X}))
        self.assertIsNone(hook.stop({'session_id': S, 'cwd': empty, 'background_tasks': [{'type': 'shell'}]}))

    def folder_without_a_project(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_a_stop_with_work_in_the_background_keeps_the_claims_from_falling_quiet_and_an_empty_one_forgets_it(self):
        self.age('sub-a', 3 * 3600)
        hook.stop(self.payload(background_tasks=[{'type': 'shell', 'status': 'running'}]))
        self.assertTrue(self.records('sub-a')[0]['busy_at'])
        self.assertEqual(len(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello'])), 1)      # not quiet: a long build
        hook.stop(self.payload(background_tasks=[]))
        self.assertNotIn('busy_at', self.records('sub-a')[0])
        self.assertEqual(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello']), [])      # quiet, and nothing left

    def test_the_end_of_the_session_ends_the_busy_fact_too(self):
        hook.stop(self.payload(background_tasks=[{'type': 'subagent'}]))
        self.age('sub-a', 3 * 3600)
        hook.session_end(self.payload(reason='other'))
        self.assertEqual(claims.others_for_session(Project(self.dir), OTHER, ['greet/hello']), [])

    def test_the_busy_fact_lasts_the_parked_window_and_no_longer(self):
        hook.stop(self.payload(background_tasks=[{'type': 'shell'}]))
        self.age('sub-a', 3 * 3600)
        project = Project(self.dir)
        held = claims.read(project)
        for c in held:
            c['busy_at'] -= 25 * 3600
        claims._write(project, held)
        self.assertEqual(claims.others_for_session(project, OTHER, ['greet/hello']), [])


class TestWhatASessionStartsWith(Agents):
    def payload(self, **more):
        return dict({'session_id': S, 'cwd': self.dir}, **more)

    def note(self, **more):
        return hook.session_start(self.payload(**more))['hookSpecificOutput']['additionalContext']

    def test_a_resumed_session_is_told_its_claims_and_loses_the_fact_that_it_ended(self):
        self.claim('main', 'greet/hello')
        hook.session_end(self.payload(reason='other'))
        self.assertIn('ended', self.records('main')[0])
        text = self.note(source='resume')
        self.assertIn('Claims you hold in this session: main: greet/hello', text)
        self.assertNotIn('ended', self.records('main')[0])

    def test_after_a_compaction_the_claims_are_listed_again_and_at_a_fresh_start_they_are_not_the_sessions(self):
        self.claim('main', 'greet/hello')
        self.assertIn('Claims you hold in this session', self.note(source='compact'))
        self.assertNotIn('Claims you hold in this session', self.note(source='startup'))

    def test_the_store_is_said_to_be_shared_with_whom(self):
        self.claim('main', 'greet/hello')
        self.assertIn('Claims are shared by this working folder only', self.note(source='startup'))

    def test_a_note_looks_at_a_few_holders_that_are_gone_and_says_how_many_it_left(self):
        for name, clause, session in (('h1', 'greet/hello', 'hhhhhhh1-1'), ('h2', 'greet/bye', 'hhhhhhh2-1'), ('h3', 'greet/thanks', 'hhhhhhh3-1')):
            self.claim(name, clause, session=session)
            claims.mark_ended(Project(self.dir), session, 'other')
        with mock.patch.object(hook, 'GONE_LOOKED_AT', 1):
            text = self.note(source='startup')
        self.assertIn('2 more claims of holders that are gone were not looked at', text)
        with mock.patch.object(hook, 'GONE_LOOKED_AT', 5):
            self.assertNotIn('were not looked at', self.note(source='startup'))

    def test_nothing_is_said_without_claims_in_a_project_of_its_own_folder(self):
        self.assertNotIn('Claims are shared', self.note(source='startup'))


class TestTheClaimsCommand(Agents):
    def test_json_has_the_documented_fields(self):
        self.claim('main', 'greet/hello')
        code, out, err = self.sor('claims', '--json')
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data['store']['kind'], 'folder')
        (row,) = data['claims']
        self.assertEqual({'holder', 'ids', 'keys', 'session', 'folder', 'branch', 'host', 'since', 'last', 'until', 'state', 'why', 'changes', 'ended', 'locked', 'queued',
                          'grant', 'rev'}, set(row))
        self.assertEqual((row['holder'], row['ids'], row['state'], row['locked'], row['queued'], row['ended']), ('main', ['greet/hello'], 'held', False, None, None))
        self.assertEqual(os.path.realpath(row['folder']), os.path.realpath(self.dir))

    def test_the_text_form_says_what_is_shared_and_lists_the_claims(self):
        self.claim('main', 'greet/hello')
        code, out, err = self.sor('claims')
        self.assertEqual(code, 0, err)
        self.assertIn('claims are shared by this working folder only', out)
        self.assertIn('main: greet/hello', out)
        self.sor('release', '--all', '--as', 'main', CLAUDE_CODE_SESSION_ID=S)
        self.assertIn('no claims', self.sor('claims')[1])

    def test_a_record_counts_its_writes_and_never_reuses_a_grant(self):
        self.claim('main', 'greet/hello')
        (first,) = self.records('main')
        self.assertEqual(first['rev'], 1)
        self.sor('status', '--json', CLAUDE_CODE_SESSION_ID=S)
        self.assertEqual(self.records('main')[0]['grant'], first['grant'])
        self.age('main', 20 * 60)
        self.sor('status', '--json', CLAUDE_CODE_SESSION_ID=S)
        self.assertGreater(self.records('main')[0]['rev'], first['rev'])      # a renewal is a write
        self.sor('release', '--all', '--as', 'main', CLAUDE_CODE_SESSION_ID=S)
        self.claim('main', 'greet/hello')
        self.assertGreater(self.records('main')[0]['grant'], first['grant'])

    def test_a_lock_of_what_a_holder_lost_is_refused_until_it_claims_again(self):
        self.claim('main', 'greet/hello')
        self.expire(freed=True)
        code, out, err = self.sor('lock', 'greet/hello', '--as', 'main', '--allow-incomplete', CLAUDE_CODE_SESSION_ID=S)
        self.assertEqual(code, 2, out + err)      # the fence: it may have changed since, so claim again first
        self.assertIn('lock refused', out)
        self.assertIn('your claims on greet/hello expired', out)
        self.assertIn('read the clause again', out)
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'main', CLAUDE_CODE_SESSION_ID=S)[0], 0)
        self.assertEqual(self.sor('lock', 'greet/hello', '--as', 'main', '--allow-incomplete', CLAUDE_CODE_SESSION_ID=S)[0], 0)


class TestTheQueuedSignal(Agents):
    """Whoever merges says that the work of a holder is queued. It is a notice and nothing else."""

    def setUp(self):
        super().setUp()
        import shutil
        import subprocess
        import tempfile
        if not shutil.which('git'):
            self.skipTest('git is not installed')
        run = lambda cwd, *a: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'core.hooksPath=/dev/null', *a], cwd=cwd, capture_output=True, text=True)
        run(self.dir, 'init', '-q', '-b', 'main')
        run(self.dir, 'add', '-A')
        run(self.dir, 'commit', '-q', '-m', 'base')
        holder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, holder, True)
        self.second = os.path.realpath(os.path.join(holder, 'second'))
        run(self.dir, 'worktree', 'add', '-q', self.second, '-b', 'second')
        with mock.patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': S}):
            base.run_sor(self.second, 'claim', 'greet/hello', '--as', 'maker')
            flows.replace_in(os.path.join(self.second, 'sor', 'greet.md'), '{text: Hello}', '{text: Hi}')
            flows.replace_in(os.path.join(self.second, 'out', 'app.js'), '"Hello"', '"Hi"')
            self.assertEqual(base.run_sor(self.second, 'lock', 'greet/hello', '--as', 'maker')[0], 0)
        claims.mark_ended(Project(self.dir), S, 'other')

    def status_text(self):
        with mock.patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': OTHER}):
            return base.run_sor(self.dir, 'claim', 'greet/hello', '--as', 'taker')[1]

    def test_without_a_signal_the_notice_says_that_nobody_has_said_they_will_merge_it(self):
        self.assertIn('waiting for the merge (nobody has said they will merge it)', self.status_text())

    def test_the_note_a_session_starts_with_lists_it_with_its_age(self):
        text = hook.session_start({'session_id': OTHER, 'cwd': self.dir, 'source': 'startup'})['hookSpecificOutput']['additionalContext']
        self.assertRegex(text, r'Waiting for \d+ min: maker: greet/hello')
        self.assertIn('waiting for the merge (nobody has said they will merge it)', text)

    def test_with_the_signal_it_says_who_queued_it_and_since_when(self):
        code, out, err = self.sor('queued', 'maker', '--by', 'merge-queue')
        self.assertEqual((code, out.strip()), (0, 'queued 1 claim of maker, by merge-queue'))
        self.assertRegex(self.status_text(), r'waiting for the merge \(queued by merge-queue since \d\d:\d\d\)')

    def test_a_queue_that_went_silent_is_said_to_have(self):
        self.sor('queued', 'maker', '--by', 'merge-queue')
        project = Project(self.dir)
        held = claims.read(project)
        for c in held:
            c['queued']['at'] -= 7 * 3600
        claims._write(project, held)
        self.assertRegex(self.status_text(), r'queued by merge-queue, but the queue has been silent since \d\d:\d\d')

    def test_it_frees_nothing_and_changes_no_rule(self):
        self.sor('queued', 'maker', '--by', 'merge-queue')
        (c,) = [c for c in claims.read(Project(self.dir)) if c['agent'] == 'maker']
        self.assertTrue(c['locked'])
        with mock.patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': OTHER}):
            self.assertEqual(base.run_sor(self.dir, 'claim', 'greet/hello', '--as', 'taker')[0], 3)
            self.assertEqual(base.run_sor(self.dir, 'claim', 'greet/hello', '--as', 'taker', '--take-over')[0], 3)      # finished work is never taken over

    def test_a_holder_that_holds_nothing_is_an_error(self):
        code, out, err = self.sor('queued', 'nobody', '--by', 'merge-queue')
        self.assertEqual(code, 2)
        self.assertIn('nobody holds no claim', err)


if __name__ == '__main__':
    unittest.main()
