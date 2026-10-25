"""Tests for where claims live (proposals/shared-claims.md, "One store, found per environment"): one set of claims for every working folder of a project, whichever way
the folders are made. In a git repository every worktree shares the common git directory; SOR_CLAIMS_DIR names a folder for clones, Perforce workspaces and shared
drives; without either, the claims stay in the project's own folder, as they always did. The first tests are the bug that began this: two worktrees both claimed the
same clause, because each had a claims file of its own.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps. Needs git for the repository tests, which are skipped without it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
GIT = shutil.which('git')
NODE = shutil.which('node')
JS = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools', 'js', 'sor.js')


def js_claims(root, **env):
    """The claims the JavaScript tool (the editor extension's) reads in a folder."""
    done = subprocess.run([NODE, JS, '-C', root, 'status', '--json'], capture_output=True, text=True, env=dict(os.environ, **env))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)['claims']


def git(cwd, *args):
    done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'core.hooksPath=/dev/null', *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


class Folders(flows.Flow):
    """The greet project, locked, and helpers to run sor in any working folder of it."""

    def setUp(self):
        super().setUp()
        self.greet_project()
        self.extra = []

    def sor_at(self, root, *args, **env):
        with mock.patch.dict(os.environ, env):
            return base.run_sor(root, *args)

    def folder(self, name):
        """A new empty folder next to the project, removed at the end."""
        d = tempfile.mkdtemp(prefix=name + '-')
        self.addCleanup(shutil.rmtree, d, True)
        return os.path.realpath(d)

    def holders(self, root):
        return sorted(c['agent'] for c in claims.active(Project(root)))


class TestAProjectInNoRepository(Folders):
    def test_the_claims_stay_in_the_projects_own_folder_as_always(self):
        st = claims.store(Project(self.dir))
        self.assertEqual(st.kind, 'folder')
        self.assertEqual(st.file, os.path.join(self.spec, '.sor-claims.json'))
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual([c['agent'] for c in json.loads(read(st.file))['claims']], ['alice'])

    def test_the_store_says_with_whom_it_is_shared(self):
        self.assertIn('this working folder only', claims.store(Project(self.dir)).shared)


@unittest.skipUnless(GIT, 'git is not installed')
class TestWorktreesOfOneRepository(Folders):
    def setUp(self):
        super().setUp()
        git(self.dir, 'init', '-q', '-b', 'main')
        git(self.dir, 'add', '-A')
        git(self.dir, 'commit', '-q', '-m', 'base')
        self.second = os.path.join(self.folder('wt'), 'second')
        git(self.dir, 'worktree', 'add', '-q', self.second, '-b', 'second')
        self.second = os.path.realpath(self.second)

    def test_both_folders_find_the_same_store_in_the_common_git_directory(self):
        a, b = claims.store(Project(self.dir)), claims.store(Project(self.second))
        self.assertEqual((a.kind, b.kind), ('git', 'git'))
        self.assertEqual(a.file, b.file)
        self.assertTrue(a.file.startswith(os.path.join(os.path.realpath(self.dir), '.git', 'sor-claims') + os.sep), a.file)
        self.assertIn('git repository', a.shared)

    def test_a_clause_claimed_in_one_worktree_is_refused_in_the_other(self):      # the bug that began this
        self.assertEqual(self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')[0], 0)
        code, out, err = self.sor_at(self.second, 'claim', 'greet/hello', '--as', 'bob')
        self.assertEqual(code, 3, out + err)
        self.assertIn('alice', out)
        self.assertEqual(self.holders(self.second), ['alice'])

    def test_a_clause_that_nobody_holds_can_be_claimed_in_the_other_worktree_and_both_see_both_claims(self):
        self.assertEqual(self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual(self.sor_at(self.second, 'claim', 'greet/bye', '--as', 'bob')[0], 0)
        self.assertEqual(self.holders(self.dir), ['alice', 'bob'])
        self.assertEqual(self.holders(self.second), ['alice', 'bob'])

    def test_status_in_the_other_worktree_lists_the_claim(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        code, out, err = self.sor_at(self.second, 'status')
        self.assertIn('alice', out)

    def test_a_release_in_the_other_worktree_does_not_free_somebody_elses_claim(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        code, out, err = self.sor_at(self.second, 'release', 'greet/hello', '--as', 'bob')
        self.assertEqual(code, 3, out + err)
        self.assertIn('NOT released', out)
        self.assertEqual(self.holders(self.dir), ['alice'])

    def test_the_holder_releases_from_the_other_worktree_too(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        self.assertEqual(self.sor_at(self.second, 'release', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual(self.holders(self.dir), [])

    def test_a_lock_leaves_nothing_untracked_in_either_worktree(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        flows.replace_in(os.path.join(self.dir, 'sor', 'greet.md'), '{text: Hello}', '{text: Hi}')
        flows.replace_in(os.path.join(self.dir, 'out', 'app.js'), '"Hello"', '"Hi"')
        self.assertEqual(self.sor_at(self.dir, 'lock', 'greet/hello', '--as', 'alice', '--allow-incomplete')[0], 0)
        self.assertEqual(self.sor_at(self.second, 'claim', 'greet/bye', '--as', 'bob')[0], 0)
        self.assertEqual(self.sor_at(self.second, 'lock', 'greet/bye', '--as', 'bob', '--allow-incomplete')[0], 0)
        for root in (self.dir, self.second):
            untracked = [line for line in git(root, 'status', '--porcelain').splitlines() if line.startswith('??')]
            self.assertEqual(untracked, [], root)      # the lock mutex is in the git directory, and git has nothing to ignore
        self.assertTrue(any(name.startswith('sor-lock-') for name in os.listdir(claims.own_git_dir(self.dir))))

    def test_the_claims_are_not_files_of_the_working_folder(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        self.assertFalse(os.path.exists(os.path.join(self.spec, '.sor-claims.json')))
        self.assertEqual(git(self.dir, 'status', '--porcelain'), '')      # and git has nothing to ignore
        self.assertEqual(git(self.second, 'status', '--porcelain'), '')

    def test_the_session_of_a_claim_made_in_one_worktree_is_one_the_other_recognises_as_the_holders(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', CLAUDE_CODE_SESSION_ID='aaaaaaaa-1')
        held = claims.active(Project(self.second))
        self.assertEqual([c['session'] for c in held], ['aaaaaaaa-1'])
        self.assertEqual(claims.others_for_session(Project(self.second), 'aaaaaaaa-1', {'greet/hello'}), [])      # its own claim, seen from the other folder
        self.assertEqual(len(claims.others_for_session(Project(self.second), 'bbbbbbbb-2', {'greet/hello'})), 1)

    def test_a_record_knows_where_it_was_made(self):
        self.sor_at(self.second, 'claim', 'greet/hello', '--as', 'alice')
        (c,) = claims.active(Project(self.dir))
        self.assertEqual(os.path.realpath(c['where']['path']), self.second)
        self.assertEqual(c['where']['host'], claims.socket.gethostname())

    def test_two_projects_in_one_repository_do_not_share_claims(self):
        other = os.path.join(self.dir, 'tools', 'other')
        base.make_project(other, {'greet': flows.GREET})
        git(self.dir, 'add', '-A')
        a, b = claims.store(Project(self.dir)), claims.store(Project(other))
        self.assertNotEqual(a.dir, b.dir)
        self.assertEqual(os.path.dirname(a.dir), os.path.dirname(b.dir))
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        self.assertEqual(self.holders(other), [])

    def test_claims_of_the_projects_own_folder_from_before_the_store_move_into_it_once(self):
        old = write(self.dir, 'sor/.sor-claims.json', json.dumps({'claims': [{
            'agent': 'carol', 'asked': ['greet/bye'], 'keys': ['greet/bye'], 'since': 1, 'until': 4102444800, 'idle': None, 'last': 1, 'regions': [], 'session': ''}]}))
        self.assertEqual(self.holders(self.dir), ['carol'])      # the first read of the folder moves them
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isfile(claims.store(Project(self.dir)).file))
        self.assertEqual(self.holders(self.second), ['carol'])      # and the other worktree finds them where they are now
        self.assertEqual(self.holders(self.dir), ['carol'])

    def test_the_edit_guard_in_one_worktree_refuses_an_edit_of_a_clause_another_worktree_holds(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', CLAUDE_CODE_SESSION_ID='aaaaaaaa-1')
        edit = flows.edit(os.path.join(self.second, 'sor', 'greet.md'), '{text: Hello}', '{text: Hi}', session_id='bbbbbbbb-2')
        with mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'}):
            said = flows.reason(hook.pre_edit(edit))
            self.assertIn('Someone else is working on this', said)
            own = flows.edit(os.path.join(self.second, 'sor', 'greet.md'), '{text: Hello}', '{text: Hi}', session_id='aaaaaaaa-1')
            self.assertIsNone(flows.reason(hook.pre_edit(own)))      # the holder itself, from the other worktree
        code_edit = flows.edit(os.path.join(self.second, 'out', 'app.js'), '"Hello"', '"Hi"', session_id='bbbbbbbb-2')
        with mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'}):
            self.assertIn('Someone else is working on this', flows.reason(hook.pre_edit(code_edit)) or '')      # and the code of the clause, in the folder of the other

    def test_a_worktree_made_later_finds_the_same_store(self):
        self.sor_at(self.dir, 'claim', 'greet/hello', '--as', 'alice')
        third = os.path.join(self.folder('wt3'), 'third')
        git(self.dir, 'worktree', 'add', '-q', third, '-b', 'third')
        self.assertEqual(self.holders(third), ['alice'])


@unittest.skipUnless(GIT and NODE, 'needs git and node')
class TestTheEditorSeesTheSameClaims(Folders):
    """The extension runs the JavaScript tool, which finds the store the way the Python tool does."""

    def py_claims(self, root, **env):
        with mock.patch.dict(os.environ, env):
            code, out, err = base.run_sor(root, 'status', '--json')
        return json.loads(out)['claims']

    def test_in_a_folder_of_its_own_in_a_worktree_and_with_the_variable(self):
        self.assertEqual(js_claims(self.dir), [])
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual([c['agent'] for c in js_claims(self.dir)], ['alice'])      # the folder's own file
        git(self.dir, 'init', '-q', '-b', 'main')
        git(self.dir, 'add', '-A')
        git(self.dir, 'commit', '-q', '-m', 'base')
        second = os.path.join(self.folder('wt'), 'second')
        git(self.dir, 'worktree', 'add', '-q', second, '-b', 'second')
        self.assertEqual(self.sor('claim', 'greet/bye', '--as', 'bob')[0], 0)      # now in the git directory
        self.assertEqual(js_claims(second), self.py_claims(second))
        self.assertEqual(sorted(c['agent'] for c in js_claims(second)), ['alice', 'bob'])
        shared = self.folder('shared')
        env = {'SOR_CLAIMS_DIR': shared}
        self.assertEqual(js_claims(self.dir, **env), [])
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'carol', SOR_CLAIMS_DIR=shared)[0], 0)      # another store: nothing in the way there
        self.assertEqual([c['agent'] for c in js_claims(self.dir, **env)], ['carol'])
        self.assertEqual(js_claims(self.dir, **env), self.py_claims(self.dir, **env))

    def test_a_freed_claim_is_not_in_force_for_the_editor_either(self):
        self.sor('claim', 'greet/hello', '--as', 'alice')
        self.expire(freed=True)
        self.assertEqual(js_claims(self.dir), [])
        self.assertEqual(self.py_claims(self.dir), [])


class TestClaimsDirChosenByTheUser(Folders):
    """Two folders that share no repository (clones, Perforce workspaces, a shared drive) share claims when both set SOR_CLAIMS_DIR."""

    def setUp(self):
        super().setUp()
        self.shared = self.folder('shared')
        self.clone = self.folder('clone')
        shutil.rmtree(self.clone)
        shutil.copytree(self.dir, self.clone)

    def test_with_the_variable_two_unrelated_folders_share_claims_and_without_it_they_do_not(self):
        with mock.patch.dict(os.environ, {'SOR_CLAIMS_DIR': self.shared}):
            self.assertEqual(base.run_sor(self.dir, 'claim', 'greet/hello', '--as', 'alice')[0], 0)
            code, out, err = base.run_sor(self.clone, 'claim', 'greet/hello', '--as', 'bob')
            self.assertEqual(code, 3, out + err)
            self.assertEqual(claims.store(Project(self.clone)).kind, 'dir')
        self.assertEqual(claims.store(Project(self.clone)).kind, 'folder')
        self.assertEqual(base.run_sor(self.clone, 'claim', 'greet/hello', '--as', 'bob')[0], 0)      # no variable: nothing is shared, and nothing says so yet

    def test_each_project_has_a_folder_of_its_own_in_the_shared_one(self):
        other = self.folder('other')
        base.make_project(other, {'greet': flows.GREET}, root_text=base.doc('Another', 'A second project.', rules=['- **out-of-scope** - everything else.']))
        write(other, 'out/app.js', flows.APP)
        with mock.patch.dict(os.environ, {'SOR_CLAIMS_DIR': self.shared}):
            a, b = claims.store(Project(self.dir)), claims.store(Project(other))
            self.assertNotEqual(a.dir, b.dir)
            self.assertEqual(base.run_sor(self.dir, 'claim', 'greet/hello', '--as', 'alice')[0], 0)
            self.assertEqual(base.run_sor(other, 'claim', 'greet/hello', '--as', 'bob')[0], 0)      # the same id in another project: no clash
            self.assertEqual(sorted(c['agent'] for c in claims.active(Project(self.dir))), ['alice'])

    def test_the_variable_may_name_a_folder_that_does_not_exist_yet(self):
        later = os.path.join(self.shared, 'a', 'b')
        with mock.patch.dict(os.environ, {'SOR_CLAIMS_DIR': later}):
            self.assertEqual(base.run_sor(self.dir, 'claim', 'greet/hello', '--as', 'alice')[0], 0)
            self.assertTrue(os.path.isfile(claims.store(Project(self.dir)).file))


if __name__ == '__main__':
    unittest.main()
