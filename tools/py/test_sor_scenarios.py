"""The situations the shared claim store (proposals/shared-claims.md) is for, one scenario per class, each on its own copy of examples/solar-system.

Nothing is called in process: every actor is its own `python3 sor.py` (and its own hook program) with a session id of its own, in a folder of its own, the way
separate agents run. That is what the older tests did not do: they ran every agent in one folder, so two worktrees never had a claims file apiece.

    python3 -m unittest tools.py.test_sor_scenarios -v
    SOR_SCENARIO_TOOL=<folder holding an older sor.py> SOR_SCENARIO_EXAMPLE=<its examples/solar-system> python3 -m unittest tools.py.test_sor_scenarios   # another version

Scenarios: one folder (git, no VCS), git worktrees, clones, copies with no VCS (the layout of Perforce workspaces, which this does not run: there is no p4 server),
two branches that lock different clauses, a parked claim and its take-over, finished work that waits for its merge, subagents of one session, and a repository
root that holds the project in a subfolder.

Python 3.9, standard library only. Needs git (scenarios that need a repository are skipped without it); no browser: the scenarios that lock hand `sor lock` the
result of the one test their change touches, as `--results` does for a project's own test framework.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EXAMPLE = os.path.join(REPO, 'examples', 'solar-system')
TOOL = os.environ.get('SOR_SCENARIO_TOOL') or HERE
SOR = os.path.join(TOOL, 'sor.py')
GIT = shutil.which('git')
NODE = shutil.which('node')
JS = os.path.join(REPO, 'tools', 'js', 'sor.js')

REFUSED = 3
JUPITER = 'bodies/planets/Jupiter'


def clean_env(session, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SOR_', 'CLAUDE_'))}
    env.update(PYTHONDONTWRITEBYTECODE='1', CLAUDE_CODE_SESSION_ID=session)
    env.update(extra)
    return env


class Scene(unittest.TestCase):
    """A temporary place to build folders in, and actors that each have a session id of their own."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sor-scenario-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # folders
    def copy(self, name='project', into=None):
        dest = os.path.join(into or self.tmp, name)
        shutil.copytree(EXAMPLE, dest)
        return dest

    def git(self, cwd, *args):
        done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args],
                              cwd=cwd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, f'git {args}: {done.stdout}{done.stderr}')
        return done.stdout

    def repository(self, name='repo', subfolder=None):
        """A git repository holding the project at its root, or in `subfolder`, committed. Returns (repository, project)."""
        root = os.path.join(self.tmp, name)
        if subfolder:
            os.makedirs(root)
            project = os.path.join(root, subfolder)
            shutil.copytree(EXAMPLE, project)
        else:
            shutil.copytree(EXAMPLE, root)
            project = root
        self.git(root, 'init', '-q', '-b', 'main')
        self.git(root, 'add', '-A')
        self.git(root, 'commit', '-q', '-m', 'start')
        return root, project

    def worktree(self, repo, name, project_in_repo=''):
        path = os.path.join(self.tmp, name)
        self.git(repo, 'worktree', 'add', '-q', '-b', name, path)
        return os.path.join(path, project_in_repo) if project_in_repo else path

    # actors
    def sor(self, folder, session, *args, **env):
        done = subprocess.run([sys.executable, SOR, '-C', folder, *args], capture_output=True, text=True, env=clean_env(session, **env))
        return done.returncode, done.stdout + done.stderr

    def ok(self, folder, session, *args, **env):
        code, said = self.sor(folder, session, *args, **env)
        self.assertEqual(code, 0, f'sor {" ".join(args)} -> {code}\n{said}')
        return said

    def refused(self, folder, session, *args, **env):
        code, said = self.sor(folder, session, *args, **env)
        self.assertEqual(code, REFUSED, f'sor {" ".join(args)} should be refused -> {code}\n{said}')
        return said

    def hook(self, which, payload, **env):
        done = subprocess.run([sys.executable, SOR, 'hook', which], input=json.dumps(payload), capture_output=True, text=True, env=clean_env(payload.get('session_id', ''), **env))
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def denial(self, answer):
        """The refusal text of a hook answer, None when it lets the call through."""
        if not answer:
            return None
        out = answer['hookSpecificOutput']
        if 'permissionDecision' not in out:      # a note to the agent, not a refusal
            return None
        self.assertEqual(out['permissionDecision'], 'deny', out)
        return out['permissionDecisionReason']

    def claims(self, folder, session='observer', **env):
        code, said = self.sor(folder, session, 'claims', '--json', **env)
        self.assertEqual(code, 0, said)
        return json.loads(said)

    # the work: Jupiter's size is a row of the table in sor/bodies.md and a line of code in out/index.html
    @staticmethod
    def text(*path):
        with open(os.path.join(*path), encoding='utf8') as fh:
            return fh.read()

    def size(self, folder, planet='Jupiter'):
        return int(re.search(r'\| ' + planet + r'\s*\| (\d+)', self.text(folder, 'sor', 'bodies.md')).group(1))

    def jupiter(self, folder):
        return self.size(folder)

    def resize(self, folder, planet, size):
        for rel, pattern in (('sor/bodies.md', r'(\| ' + planet + r'\s*\| )\d+'), ('out/index.html', r"(name: '" + planet.lower() + r"', size: )\d+")):
            path = os.path.join(folder, rel)
            text = self.text(path)
            new = re.sub(pattern, lambda m: m.group(1) + str(size), text, count=1)
            self.assertNotEqual(new, text, rel)
            with open(path, 'w', encoding='utf8') as fh:
                fh.write(new)

    def resize_jupiter(self, folder, size):
        self.resize(folder, 'Jupiter', size)

    def lock(self, folder, session, name):
        """Locks what `name` claimed, with the test result a framework would report (no browser: the example's other tests were locked as passing)."""
        results = os.path.join(self.tmp, f'results-{name}.json')
        with open(results, 'w') as fh:
            json.dump({'bodies/test:planets': 'pass'}, fh)
        return self.ok(folder, session, 'lock', '--results', results, '--as', name)


@unittest.skipUnless(GIT, 'needs git')
class GitScene(Scene):
    pass


class OneFolderScenarios(GitScene):
    """Agents in one folder: the case that always worked, and must go on working."""

    def holds_and_frees(self, folder):
        self.ok(folder, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        said = self.refused(folder, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.assertIn('ana', said)
        self.assertEqual(self.sor(folder, 'sess-bob', 'claim', 'clock', '--as', 'bob')[0], 0, 'a clause nobody holds is free')
        self.ok(folder, 'sess-ana', 'release', '--all')
        self.ok(folder, 'sess-bob', 'claim', JUPITER, '--as', 'bob')

    def test_one_folder_in_git(self):
        self.holds_and_frees(self.repository()[1])

    def test_one_folder_without_any_version_control(self):
        folder = self.copy()
        self.holds_and_frees(folder)
        self.assertTrue(os.path.exists(os.path.join(folder, 'sor', '.sor-claims.json')))      # with no repository the claims stay in the project's own folder
        self.assertIn('this working folder only', self.ok(folder, 'sess-ana', 'status'))


class WorktreeScenarios(GitScene):
    """The bug that began this: each git worktree kept claims of its own, so two agents in two worktrees were both told yes."""

    def test_a_claim_in_one_worktree_refuses_the_other(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        said = self.refused(wt, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.assertIn('ana', said)
        self.assertIn('held', said)

    def test_it_works_the_other_way_round_too(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.refused(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(wt, 'sess-bob', 'release', '--all')
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')

    def test_both_folders_list_the_same_claims_and_no_claims_file_is_left_in_either(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(wt, 'sess-bob', 'claim', 'clock', '--as', 'bob')
        for folder in (repo, wt):
            names = sorted(c['holder'] for c in self.claims(folder)['claims'])
            self.assertEqual(names, ['ana', 'bob'], folder)
            self.assertFalse(os.path.exists(os.path.join(folder, 'sor', '.sor-claims.json')), folder)
        self.assertTrue(os.path.isdir(os.path.join(repo, '.git', 'sor-claims')))

    def test_a_branch_that_edits_the_root_title_still_shares_the_claims_of_the_repository(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        root = os.path.join(wt, 'sor', 'SPECOFRECORD.md')
        text = self.text(root)
        with open(root, 'w', encoding='utf8') as fh:
            fh.write(text.replace('# ', '# Renamed ', 1))
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.assertIn('ana', self.refused(wt, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))

    def test_a_worktree_of_another_project_is_not_held_up(self):
        repo, project = self.repository()
        other = self.repository('other')[1]
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(other, 'sess-bob', 'claim', JUPITER, '--as', 'bob')


class CloneAndCopyScenarios(GitScene):
    """Folders that share no git directory (clones, Perforce workspaces, a copy on a shared drive) share claims only through SOR_CLAIMS_DIR."""

    def clones(self):
        repo, _ = self.repository('origin')
        one, two = (os.path.join(self.tmp, n) for n in ('clone1', 'clone2'))
        for path in (one, two):
            self.git(self.tmp, 'clone', '-q', repo, path)
        return one, two

    def test_two_clones_without_the_variable_do_not_see_each_other_and_say_so(self):
        one, two = self.clones()
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(two, 'sess-bob', 'claim', JUPITER, '--as', 'bob')      # the documented limit: nothing joins them
        self.assertIn('SOR_CLAIMS_DIR', self.ok(two, 'sess-bob', 'claims'))

    def test_two_clones_with_one_shared_folder_refuse_each_other(self):
        one, two = self.clones()
        shared = os.path.join(self.tmp, 'shared-claims')
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana', SOR_CLAIMS_DIR=shared)
        said = self.refused(two, 'sess-bob', 'claim', JUPITER, '--as', 'bob', SOR_CLAIMS_DIR=shared)
        self.assertIn('ana', said)
        self.ok(one, 'sess-ana', 'release', '--all', SOR_CLAIMS_DIR=shared)
        self.ok(two, 'sess-bob', 'claim', JUPITER, '--as', 'bob', SOR_CLAIMS_DIR=shared)

    def test_workspaces_with_no_version_control_at_all_share_through_the_variable(self):
        """The layout of two Perforce clients (separate folders, no git): not run against a p4 server, which is not here."""
        one, two = self.copy('client1'), self.copy('client2')
        shared = os.path.join(self.tmp, 'shared-claims')
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(two, 'sess-bob', 'claim', JUPITER, '--as', 'bob')      # without it, the same limit
        self.ok(one, 'sess-ana', 'release', '--all')
        self.ok(two, 'sess-bob', 'release', '--all')
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana', SOR_CLAIMS_DIR=shared)
        self.refused(two, 'sess-bob', 'claim', JUPITER, '--as', 'bob', SOR_CLAIMS_DIR=shared)

    def test_a_relative_path_is_refused_because_each_process_would_read_it_against_its_own_folder(self):
        one = self.copy('client1')
        code, said = self.sor(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana', SOR_CLAIMS_DIR='../claims')
        self.assertEqual(code, 2, said)
        self.assertIn('relative path', said)
        self.assertNotIn('Traceback', said)


class LockMergeScenario(GitScene):
    def test_two_branches_that_lock_different_clauses_merge_without_a_conflict(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(wt, 'sess-bob', 'claim', 'bodies/planets/Mercury', '--as', 'bob')
        self.resize_jupiter(repo, self.jupiter(repo) + 1)
        self.resize(wt, 'Mercury', self.size(wt, 'Mercury') + 1)
        self.lock(repo, 'sess-ana', 'ana')
        self.lock(wt, 'sess-bob', 'bob')
        for folder in (repo, wt):
            self.git(folder, 'add', '-A')
            self.git(folder, 'commit', '-q', '-m', 'lock')
        self.git(repo, 'merge', '-q', '--no-edit', 'feature')       # a conflict here fails the test: the rows are far apart, so only the lock file could clash
        self.assertNotIn('<<<<<<<', self.text(repo, 'sor', 'sor-lock.json'))
        said = self.ok(repo, 'sess-ana', 'status')
        self.assertIn('clauses, code and lock agree', said)
        self.assertEqual((self.size(repo), self.size(repo, 'Mercury')), (17, 5))      # both branches' work is in the merged tree


class GoneHolderScenarios(GitScene):
    """The holder is gone. What it left decides: nothing (free), unfinished work (parked), finished work not merged yet (waiting)."""

    def ended(self, folder, session):
        self.hook('session-end', {'session_id': session, 'cwd': folder, 'reason': 'other'})

    def test_a_holder_that_is_still_there_holds_the_claim(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)
        self.assertIn('held', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))

    def test_the_same_name_in_a_new_session_holds_the_claim_against_a_third_agent(self):
        repo, project = self.repository()
        self.ok(repo, 'sess-a1', 'claim', JUPITER, '--as', 'ana')
        self.ended(repo, 'sess-a1')
        self.ok(repo, 'sess-a2', 'claim', JUPITER, '--as', 'ana')      # ana comes back in a new session
        self.assertIn('ana', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))
        (claim,) = [c for c in self.claims(repo)['claims'] if c['holder'] == 'ana']
        self.assertEqual((claim['state'], claim['ended']), ('held', None))

    def test_a_holder_that_left_nothing_frees_the_claim_when_its_session_ends(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ended(wt, 'sess-ana')
        self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')

    def test_unfinished_work_in_another_folder_parks_the_claim_and_a_take_over_continues_it(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)
        self.ended(wt, 'sess-ana')
        said = self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.assertIn('parked', said)
        self.assertIn('--take-over', said)
        took = self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob', '--take-over')
        self.assertIn('feature', took)      # it says where the unfinished work is
        self.assertEqual([c['holder'] for c in self.claims(repo)['claims'] if JUPITER in c['ids']], ['bob'])

    def test_a_holder_that_left_no_unfinished_work_of_its_own_is_not_parked_by_a_change_that_was_there_before(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)      # a person's edit, before anybody claims
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ended(wt, 'sess-ana')
        self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')

    def finished_in(self, repo, wt):
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)
        self.lock(wt, 'sess-ana', 'ana')
        self.ended(wt, 'sess-ana')
        self.git(wt, 'add', '-A')
        self.git(wt, 'commit', '-q', '-m', 'Jupiter')

    def test_finished_work_that_is_not_merged_yet_makes_the_next_claim_wait(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.finished_in(repo, wt)
        said = self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.assertIn('waiting for the merge', said)
        self.git(repo, 'merge', '-q', '--no-edit', 'feature')
        self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')

    def test_the_claim_is_free_after_the_merge_also_when_the_worktree_was_removed(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.finished_in(repo, wt)
        self.git(repo, 'merge', '-q', '--no-edit', 'feature')
        self.git(repo, 'worktree', 'remove', '--force', wt)
        self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')

    def test_a_removed_worktree_whose_work_was_never_merged_still_waits(self):
        repo, project = self.repository()
        wt = self.worktree(repo, 'feature')
        self.finished_in(repo, wt)
        self.git(repo, 'worktree', 'remove', '--force', wt)
        self.assertIn('waiting for the merge', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))


class Subagents(GitScene):
    """Hook calls of a parent session and two subagents, which share its session id and tell themselves apart by the name they claim under (SKILL.md, "Claims")."""
    PARENT, X, Y = 'sess-parent', 'agent-x', 'agent-y'

    def bash(self, folder, agent, command):
        return self.denial(self.hook('pre-bash', {'tool_name': 'Bash', 'tool_input': {'command': command}, 'session_id': self.PARENT, 'agent_id': agent, 'cwd': folder}))

    def edit(self, folder, agent, rel='sor/bodies.md'):
        path = os.path.join(folder, rel)
        payload = {'tool_name': 'Edit', 'session_id': self.PARENT, 'agent_id': agent, 'cwd': folder,
                   'tool_input': {'file_path': path, 'old_string': f'| Jupiter | {self.jupiter(folder)} ', 'new_string': f'| Jupiter | {self.jupiter(folder) + 1} '}}
        return self.denial(self.hook('pre-edit', payload, SOR_ENFORCE_CLAIMS='1'))


class SubagentScenarios(Subagents):
    def test_a_subagent_that_claims_without_a_name_is_refused(self):
        project = self.repository()[1]
        said = self.bash(project, self.X, f'sor claim {JUPITER}')
        self.assertIn('--as', said)

    def test_two_subagents_of_one_session_exclude_each_other(self):
        project = self.repository()[1]
        self.assertIsNone(self.bash(project, self.X, f'python3 {SOR} claim {JUPITER} --as sub-x'))
        self.ok(project, self.PARENT, 'claim', JUPITER, '--as', 'sub-x')
        self.assertIsNone(self.bash(project, self.Y, f'python3 {SOR} claim {JUPITER} --as sub-y'))
        self.assertIn('sub-x', self.refused(project, self.PARENT, 'claim', JUPITER, '--as', 'sub-y'))

    def test_the_edit_guard_lets_the_claiming_subagent_through_and_stops_its_sibling(self):
        project = self.repository()[1]
        self.bash(project, self.X, f'python3 {SOR} claim {JUPITER} --as sub-x')
        self.ok(project, self.PARENT, 'claim', JUPITER, '--as', 'sub-x')
        self.bash(project, self.Y, f'python3 {SOR} claim clock --as sub-y')
        self.assertIsNone(self.edit(project, self.X))
        self.assertIn('Someone else is working on this', self.edit(project, self.Y))

    def test_a_subagent_may_not_force_another_holder_free_not_even_by_an_abbreviation(self):
        project = self.repository()[1]
        for flag in ('--force', '--forc', '--f'):
            self.assertIn('somebody else holds', self.bash(project, self.Y, f'sor release {JUPITER} {flag}'), flag)

    def test_the_end_of_the_session_is_recorded_on_the_claims(self):
        project = self.repository()[1]
        self.bash(project, self.X, f'python3 {SOR} claim {JUPITER} --as sub-x')
        self.ok(project, self.PARENT, 'claim', JUPITER, '--as', 'sub-x')
        self.bash(project, self.Y, f'python3 {SOR} claim clock --as sub-y')
        self.ok(project, self.PARENT, 'claim', 'clock', '--as', 'sub-y')
        states = lambda: {c['holder']: c for c in self.claims(project)['claims']}      # noqa: E731
        self.assertEqual({k: v['state'] for k, v in states().items()}, {'sub-x': 'held', 'sub-y': 'held'})
        self.hook('subagent-stop', {'session_id': self.PARENT, 'agent_id': self.X, 'cwd': project})
        self.assertEqual({k: v['state'] for k, v in states().items()}, {'sub-x': 'free', 'sub-y': 'held'})      # it stopped and left nothing; its sibling still works
        self.assertIsNone(states()['sub-y']['ended'])
        self.hook('session-end', {'session_id': self.PARENT, 'cwd': project, 'reason': 'other'})
        self.assertIsNotNone(states()['sub-y']['ended'])
        self.assertEqual(states()['sub-y']['state'], 'free')


class RepositoryRootScenario(Subagents):
    """The agent's folder is a repository root and the project is a subfolder, named with -C (this repository's own layout)."""

    def test_the_binding_and_the_guard_follow_the_c_folder(self):
        repo, project = self.repository(subfolder='proj')
        self.assertIsNone(self.bash(repo, self.X, f'python3 {SOR} -C proj claim {JUPITER} --as sub-x'))
        self.ok(project, self.PARENT, 'claim', JUPITER, '--as', 'sub-x')
        self.bash(repo, self.Y, f'python3 {SOR} -C proj claim clock --as sub-y')
        self.assertIsNone(self.edit(project, self.X))
        self.assertIn('Someone else is working on this', self.edit(project, self.Y))
        self.hook('session-end', {'session_id': self.PARENT, 'cwd': repo, 'reason': 'other'})
        (claim,) = [c for c in self.claims(project)['claims'] if c['holder'] == 'sub-x']
        self.assertIsNotNone(claim['ended'])


class SharedFolderScenarios(GitScene):
    def test_the_shared_folder_holds_exactly_the_claims_the_bindings_and_the_lock_of_one_project(self):
        repo, _ = self.repository('origin')
        one, two = (os.path.join(self.tmp, n) for n in ('clone1', 'clone2'))
        for path in (one, two):
            self.git(self.tmp, 'clone', '-q', repo, path)
        shared = os.path.join(self.tmp, 'shared')
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana', SOR_CLAIMS_DIR=shared)
        payload = {'tool_name': 'Bash', 'tool_input': {'command': f'python3 {SOR} claim clock --as sub-x'}, 'session_id': 'sess-par', 'agent_id': 'agent-x', 'cwd': two}
        self.assertIsNone(self.denial(self.hook('pre-bash', payload, SOR_CLAIMS_DIR=shared)))
        self.ok(two, 'sess-par', 'claim', 'clock', '--as', 'sub-x', SOR_CLAIMS_DIR=shared)
        self.hook('subagent-stop', {'session_id': 'sess-par', 'agent_id': 'agent-x', 'cwd': two}, SOR_CLAIMS_DIR=shared)
        self.hook('session-end', {'session_id': 'sess-ana', 'cwd': one, 'reason': 'other'}, SOR_CLAIMS_DIR=shared)
        (key,) = os.listdir(shared)
        found = sorted(os.path.relpath(os.path.join(d, f), shared) for d, _, files in os.walk(shared) for f in files)
        self.assertEqual(found, [f'{key}/bindings.json', f'{key}/claims.json', f'{key}/claims.lock'])


class MoreThanOneProjectScenarios(GitScene):
    def test_two_projects_in_one_repository_do_not_hold_each_other_up(self):
        root = os.path.join(self.tmp, 'mono')
        os.makedirs(root)
        for name in ('a', 'b'):
            shutil.copytree(EXAMPLE, os.path.join(root, name))
        self.git(root, 'init', '-q', '-b', 'main')
        self.git(root, 'add', '-A')
        self.git(root, 'commit', '-q', '-m', 'start')
        wt = self.worktree(root, 'feature')
        self.ok(os.path.join(root, 'a'), 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.ok(os.path.join(wt, 'b'), 'sess-bob', 'claim', JUPITER, '--as', 'bob')      # the other project: free
        self.refused(os.path.join(wt, 'a'), 'sess-carl', 'claim', JUPITER, '--as', 'carl')      # the same project in another worktree: held
        (key_a, key_b) = sorted(os.listdir(os.path.join(root, '.git', 'sor-claims')))
        self.assertNotEqual(key_a, key_b)

    def test_unrelated_repositories_that_set_one_shared_folder_do_not_hold_each_other_up(self):
        """SOR_CLAIMS_DIR set once for a whole machine (a shell profile, the user's settings) serves every project there."""
        shared = os.path.join(self.tmp, 'shared')
        one, two = self.repository('first')[1], self.repository('second')[1]
        other = os.path.join(two, 'sor', 'SPECOFRECORD.md')
        with open(other, encoding='utf8') as fh:
            text = fh.read()
        with open(other, 'w', encoding='utf8') as fh:
            fh.write(text.replace('# Solar System', '# A different project', 1) if '# Solar System' in text else '# A different project\n' + text)
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana', SOR_CLAIMS_DIR=shared)
        self.ok(two, 'sess-bob', 'claim', JUPITER, '--as', 'bob', SOR_CLAIMS_DIR=shared)


class CrashedHolderScenarios(GitScene):
    """A holder that died with no SessionEnd (the machine slept, the process was killed): nothing records it, so only its quiet window can say it is gone."""

    def test_inside_its_window_the_claim_still_holds(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana', '--ttl', '1h')
        self.assertIn('held', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))

    def test_after_its_window_with_nothing_left_it_is_free(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana', '--ttl', '1s')
        time.sleep(2.2)
        said = self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.assertIn('freed the claim of ana', said)

    def test_after_its_window_with_unfinished_work_elsewhere_it_is_parked(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana', '--ttl', '1s')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)
        time.sleep(2.2)
        self.assertIn('parked', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))


class ResumeAndClearScenarios(GitScene):
    def start(self, folder, session, source):
        self.hook('session-start', {'session_id': session, 'cwd': folder, 'source': source})

    def end(self, folder, session, reason):
        self.hook('session-end', {'session_id': session, 'cwd': folder, 'reason': reason})

    def claim_of(self, folder, holder='ana'):
        (claim,) = [c for c in self.claims(folder)['claims'] if c['holder'] == holder]
        return claim

    def test_a_resumed_session_keeps_its_claim_and_the_ended_mark_goes(self):
        repo, _ = self.repository()
        self.ok(repo, 'sess-a', 'claim', JUPITER, '--as', 'ana')
        self.end(repo, 'sess-a', 'other')
        self.assertIsNotNone(self.claim_of(repo)['ended'])
        self.start(repo, 'sess-a', 'resume')
        claim = self.claim_of(repo)
        self.assertEqual((claim['ended'], claim['state']), (None, 'held'))
        self.assertIn('held', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))

    def test_after_clear_the_old_session_has_ended_and_the_agent_claims_again_in_the_same_folder(self):
        repo, _ = self.repository()
        self.ok(repo, 'sess-a', 'claim', JUPITER, '--as', 'ana')
        self.end(repo, 'sess-a', 'clear')
        self.start(repo, 'sess-b', 'clear')
        self.assertEqual(self.claim_of(repo)['state'], 'free')
        self.ok(repo, 'sess-b', 'claim', JUPITER, '--as', 'ana')
        self.assertIn('ana', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))

    def test_after_clear_the_agent_may_lock_its_work_until_somebody_else_has_claimed_it(self):
        repo, _ = self.repository()
        self.ok(repo, 'sess-a', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(repo, self.jupiter(repo) + 1)
        self.end(repo, 'sess-a', 'clear')
        self.start(repo, 'sess-b', 'clear')
        self.ok(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')      # the old claim was free (same folder, session ended): bob takes the clause
        code, said = self.sor(repo, 'sess-b', 'lock', JUPITER, '--as', 'ana', '--results', self.write_results())
        self.assertNotEqual(code, 0, said)      # her claim was freed while she was away, and bob holds the clause now
        self.assertIn('bob', said)

    def write_results(self):
        path = os.path.join(self.tmp, 'results.json')
        with open(path, 'w') as fh:
            json.dump({'bodies/test:planets': 'pass'}, fh)
        return path


class SwarmScenario(GitScene):
    PLANETS = ('Mercury', 'Venus', 'Earth', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune')

    def test_many_gone_holders_in_many_worktrees_are_read_once_each(self):
        sys.path.insert(0, HERE)
        from sorlib import claims
        from sorlib.model import Project
        repo, _ = self.repository()
        for n, planet in enumerate(self.PLANETS):
            wt = self.worktree(repo, f'wt{n}')
            self.ok(wt, f'sess-{n}', 'claim', f'bodies/planets/{planet}', '--as', f'agent{n}')
            self.resize(wt, planet, self.size(wt, planet) + 1)
            self.hook('session-end', {'session_id': f'sess-{n}', 'cwd': wt, 'reason': 'other'})
        project = Project(repo)
        reads = []
        real = claims.lockfile.status

        def counting(*a, **k):
            reads.append(1)
            return real(*a, **k)

        claims.lockfile.status = counting
        try:
            started = time.time()
            decided = claims.states(project, claims.active(project))
            took = time.time() - started
        finally:
            claims.lockfile.status = real
        self.assertEqual(len(decided), len(self.PLANETS))
        self.assertTrue(all(d.kind == 'parked' for _, d in decided), [d.kind for _, d in decided])
        self.assertLessEqual(len(reads), len(self.PLANETS) + 1)      # one look per working folder and one at home, however many claims
        print(f'\n  swarm: {len(decided)} gone holders in {len(decided)} worktrees decided in {took:.2f} s with {len(reads)} folder reads', file=sys.stderr)


@unittest.skipUnless(NODE, 'needs node')
class EditorReaderScenarios(GitScene):
    """The VS Code extension reads the same claims with its own JavaScript tool (tools/js); it does not decide states, it must list the same holders and clauses."""

    def js_claims(self, folder, **env):
        done = subprocess.run([NODE, JS, '-C', folder, 'status', '--json'], capture_output=True, text=True, env=clean_env('editor', **env))
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)['claims']

    def same(self, folder, **env):
        python = sorted((c['holder'], tuple(c['ids'])) for c in self.claims(folder, **env)['claims'])
        js = self.js_claims(folder, **env)
        self.assertTrue(js, 'the editor sees no claims')
        theirs = sorted((c.get('agent') or c.get('holder'), tuple(c.get('asked') or c.get('ids'))) for c in js)
        self.assertEqual(theirs, python)

    def test_the_editor_sees_the_claims_of_other_worktrees(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.same(repo)
        self.same(wt)

    def test_the_editor_sees_the_claims_in_a_shared_folder(self):
        one, two = self.copy('client1'), self.copy('client2')
        shared = os.path.join(self.tmp, 'shared')
        self.ok(one, 'sess-ana', 'claim', JUPITER, '--as', 'ana', SOR_CLAIMS_DIR=shared)
        self.same(two, SOR_CLAIMS_DIR=shared)

    def test_the_editor_finds_the_claims_of_a_project_in_a_subfolder_in_both_kinds_of_store(self):
        repo, project = self.repository(subfolder='proj')
        wt = self.worktree(repo, 'feature', 'proj')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.same(project)      # the common git directory
        shared = os.path.join(self.tmp, 'shared')
        self.ok(project, 'sess-bob', 'claim', 'clock', '--as', 'bob', SOR_CLAIMS_DIR=shared)
        self.same(wt, SOR_CLAIMS_DIR=shared)      # a folder named by the variable, with the root title in the key

    def test_the_editor_sees_a_parked_and_a_waiting_claim(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)
        self.hook('session-end', {'session_id': 'sess-ana', 'cwd': wt, 'reason': 'other'})
        self.same(repo)      # parked
        self.lock(wt, 'sess-ana', 'ana')
        self.same(repo)      # waiting for the merge


class SameClauseOnTwoBranchesScenario(GitScene):
    """Nothing stops two agents from locking one clause on two branches once the first has released and the second has not got the first's work: the merge must say so."""

    def test_the_conflict_is_reported_clearly_edits_still_pass_and_the_resolved_project_reads_again(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(repo, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(repo, 17)
        self.lock(repo, 'sess-ana', 'ana')
        self.ok(repo, 'sess-ana', 'release', '--all')
        self.git(repo, 'add', '-A')
        self.git(repo, 'commit', '-q', '-m', 'ana')
        self.ok(wt, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.resize_jupiter(wt, 18)
        self.lock(wt, 'sess-bob', 'bob')
        self.ok(wt, 'sess-bob', 'release', '--all')
        self.git(wt, 'add', '-A')
        self.git(wt, 'commit', '-q', '-m', 'bob')
        merge = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'merge', '--no-edit', 'feature'], cwd=repo, capture_output=True, text=True)
        self.assertNotEqual(merge.returncode, 0, merge.stdout)
        self.assertIn('<<<<<<<', self.text(repo, 'sor', 'sor-lock.json'))
        for command in ('status', 'check'):
            code, said = self.sor(repo, 'sess-ana', command)
            self.assertNotEqual(code, 0, said)
            self.assertIn('conflict', said.lower(), said)
        payload = {'tool_name': 'Edit', 'session_id': 'sess-ana', 'cwd': repo,
                   'tool_input': {'file_path': os.path.join(repo, 'out', 'index.html'), 'old_string': 'x', 'new_string': 'y'}}
        self.assertIsNone(self.denial(self.hook('pre-edit', payload, SOR_ENFORCE_CLAIMS='1')))      # the guard does not stand in the way of resolving it
        self.git(repo, 'checkout', '--ours', '--', 'sor/sor-lock.json', 'sor/bodies.md', 'out/index.html')
        self.git(repo, 'add', '-A')
        self.git(repo, 'commit', '-q', '--no-edit')
        self.assertIn('clauses, code and lock agree', self.ok(repo, 'sess-ana', 'status'))


class QueuedScenario(GitScene):
    def test_whoever_merges_can_say_so_and_the_refusal_names_them(self):
        repo, _ = self.repository()
        wt = self.worktree(repo, 'feature')
        self.ok(wt, 'sess-ana', 'claim', JUPITER, '--as', 'ana')
        self.resize_jupiter(wt, self.jupiter(wt) + 1)
        self.lock(wt, 'sess-ana', 'ana')
        self.hook('session-end', {'session_id': 'sess-ana', 'cwd': wt, 'reason': 'other'})
        self.assertIn('nobody has said they will merge it', self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob'))
        self.ok(repo, 'sess-merger', 'queued', 'ana', '--by', 'merge-bot')
        said = self.refused(repo, 'sess-bob', 'claim', JUPITER, '--as', 'bob')
        self.assertIn('merge-bot', said)
        (claim,) = [c for c in self.claims(repo)['claims'] if c['holder'] == 'ana']
        self.assertIsNotNone(claim['queued'])
        self.assertEqual(claim['state'], 'waiting')      # a notice only: nothing is freed by it


if __name__ == '__main__':
    unittest.main()
