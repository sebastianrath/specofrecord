"""Tests for what a claim finds of its holder's work in another folder when that work is new: an item the holder added under an id it claimed has no key in the
claim, and a claim that looks only at the keys of its grant finds nothing of it (SPEC §16, `claims.owns`). And which machine a claim was made on: `socket.gethostname()`
changes on a Mac with the network, so `claims.machine` is what a claim is compared by.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps. Needs git.
"""
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
import test_sor_permutations as perm         # noqa: E402
from sorlib import claims                    # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

A = perm.A


class TestOwns(unittest.TestCase):
    def test_a_claim_owns_its_keys_and_what_is_new_under_the_ids_it_asked_for(self):
        c = {'keys': ['greet', 'greet/hello', 'greet/hello.text'], 'asked': ['greet']}
        for key in ('greet/hello', 'greet/extra', 'greet/extra.text', 'greet/test:extra', 'greet/deeper/part', 'greet/hello@ts'):
            self.assertTrue(claims.owns(c, key), key)
        for key in ('greeter/hello', 'bye', 'bye/hello'):
            self.assertFalse(claims.owns(c, key), key)

    def test_a_claim_of_one_item_owns_the_values_of_it_and_nothing_next_to_it(self):
        c = {'keys': ['greet/hello', 'greet/hello.text'], 'asked': ['greet/hello']}
        self.assertTrue(claims.owns(c, 'greet/hello.size'))
        self.assertFalse(claims.owns(c, 'greet/bye'))
        self.assertFalse(claims.owns(c, 'greet/helloo'))


@unittest.skipUnless(perm.GIT, 'git is not installed')
class TestWhatAHolderAddedInAnotherFolder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = perm.World()

    @classmethod
    def tearDownClass(cls):
        cls.w.close()

    def setUp(self):
        self.w.reset()
        os.environ.pop('SOR_ENFORCE_CLAIMS', None)

    def decide(self):
        w = self.w
        project = Project(w.main)
        (c,) = w.records('a')
        return claims.decide(project, c, Scan(project), lockfile.read(project), time.time(), None)

    def claim_and_add(self, lock=True):
        """The holder claims the part in the second folder and adds a rule with its code, which the claim did not have a key for; locks it (`lock`), and stops."""
        w = self.w
        self.assertEqual(w.run(w.second, A, 'claim', 'greet', '--as', 'a')[0], 0)
        flows.replace_in(os.path.join(w.second, 'sor', 'greet.md'), '## Tests', '- **extra** - The page says {text: Extra}.\n\n## Tests')
        flows.replace_in(os.path.join(w.second, 'out', 'app.js'), '// @clause greet/thanks',
                         '// @clause greet/extra\nconsole.log("Extra");\n// @clause end\n// @clause greet/thanks')
        if lock:
            code, out = w.run(w.second, A, 'lock', '--as', 'a')
            self.assertEqual(code, 0, out)
            self.assertIn('greet/extra', w.records('a')[0]['locked_keys'])
        w.rewrite(lambda c: c.update(stopped=time.time()))

    def test_an_item_the_holder_added_and_locked_is_finished_work_waiting_for_its_merge(self):
        self.claim_and_add()
        self.assertNotIn('greet/extra', self.w.records('a')[0]['keys'])
        d = self.decide()
        self.assertEqual((d.kind, d.why), ('waiting', 'its holder is gone and its finished work has not reached this copy'))

    def test_the_claim_frees_when_the_new_item_reaches_this_copy(self):
        self.claim_and_add()
        self.w.commit_and_merge(self.w.second)
        self.assertEqual(self.decide().kind, 'free')

    def test_an_item_the_holder_added_and_did_not_lock_is_unfinished_work(self):
        self.claim_and_add(lock=False)
        self.assertEqual(self.decide().kind, 'parked')

    def test_a_folder_that_is_gone_leaves_the_new_item_waiting_and_the_merge_frees_it(self):
        self.claim_and_add()
        self.w.commit_and_merge(self.w.second)
        perm.git(self.w.main, 'reset', '--hard', '-q', self.w.base)         # the merge is undone: the work is in the branch only
        perm.git(self.w.main, 'worktree', 'remove', '--force', self.w.second)
        self.assertEqual(self.decide().kind, 'waiting')
        perm.git(self.w.main, 'merge', '-q', 'second')
        self.assertEqual(self.decide().kind, 'free')

    def test_a_folder_that_is_gone_is_not_read_as_arrived_by_a_change_of_a_key_the_holder_did_not_lock(self):
        w = self.w
        self.assertEqual(w.run(w.second, A, 'claim', 'greet', '--as', 'a')[0], 0)
        w.edit(w.second, 'hello', 'Hello', 'Hi')
        code, out = w.run(w.second, A, 'lock', 'greet/hello', '--as', 'a')
        self.assertEqual(code, 0, out)
        w.rewrite(lambda c: c.update(stopped=time.time()))
        project = Project(w.main)
        entries = lockfile.read(project)
        entries['greet/bye'] = dict(entries['greet/bye'], note='somebody else changed it here')      # not what the holder locked, and not merged
        lockfile.write(project, entries)
        perm.git(w.main, 'worktree', 'remove', '--force', w.second)
        self.assertEqual(self.decide().kind, 'waiting')


@unittest.skipUnless(perm.GIT, 'git is not installed')
class TestWhichMachineAClaimWasMadeOn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = perm.World()

    @classmethod
    def tearDownClass(cls):
        cls.w.close()

    def setUp(self):
        self.w.reset()
        os.environ.pop('SOR_ENFORCE_CLAIMS', None)

    def test_a_claim_is_here_by_its_machine_when_both_have_one_and_by_its_host_name_when_not(self):
        with mock.patch.object(claims, 'machine', return_value='m1'):
            self.assertTrue(claims.is_here({'host': 'renamed-by-the-network', 'machine': 'm1'}))
            self.assertFalse(claims.is_here({'host': claims.socket.gethostname(), 'machine': 'm2'}))
            self.assertTrue(claims.is_here({'host': claims.socket.gethostname()}))        # a claim from before it recorded one
            self.assertFalse(claims.is_here({'host': 'elsewhere'}))
            self.assertTrue(claims.is_here({}))
        with mock.patch.object(claims, 'machine', return_value=''):                      # this machine has none to give
            self.assertTrue(claims.is_here({'host': claims.socket.gethostname(), 'machine': 'm1'}))
            self.assertFalse(claims.is_here({'host': 'elsewhere', 'machine': 'm1'}))

    def test_a_claim_records_the_machine_it_was_made_on(self):
        w = self.w
        with mock.patch.object(claims, 'machine', return_value='m1'):
            self.assertEqual(w.run(w.second, A, 'claim', 'greet/hello', '--as', 'a')[0], 0)
        where = w.records('a')[0]['where']
        self.assertEqual((where['machine'], where['host']), ('m1', claims.socket.gethostname()))
        with mock.patch.object(claims, 'machine', return_value=''):
            self.assertEqual(w.run(w.second, 'dddddddd-4', 'claim', 'greet/bye', '--as', 'b')[0], 0)
        self.assertNotIn('machine', w.records('b')[0]['where'])

    def test_a_folder_on_this_machine_is_read_although_the_network_has_renamed_the_host(self):
        w = self.w
        with mock.patch.object(claims, 'machine', return_value='m1'):
            self.assertEqual(w.run(w.second, A, 'claim', 'greet/hello', '--as', 'a')[0], 0)
            w.edit(w.second, 'hello', 'Hello', 'Hi')
            self.assertEqual(w.run(w.second, A, 'lock', 'greet/hello', '--as', 'a')[0], 0)
            w.rewrite(lambda c: c.update(stopped=time.time()))
            w.rewrite(lambda c: c['where'].update(host='renamed-by-the-network'))
            project = Project(w.main)
            (c,) = w.records('a')
            d = claims.decide(project, c, Scan(project), lockfile.read(project), time.time(), None)
            self.assertEqual((d.kind, d.why), ('waiting', 'its holder is gone and its finished work has not reached this copy'))
            w.rewrite(lambda c: c['where'].update(machine='m2'))                       # another computer: its folder says nothing here
            (c,) = w.records('a')
            d = claims.decide(project, c, Scan(project), lockfile.read(project), time.time(), None)
            self.assertEqual((d.kind, d.why), ('held', 'its folder cannot be read from here'))


if __name__ == '__main__':
    unittest.main()
