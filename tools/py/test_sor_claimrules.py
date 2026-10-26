"""Tests for what happens to a claim whose holder is gone (proposals/shared-claims.md, "How a claim ends"): the decision `sor claim` makes about each claim in its
way, row by row of the table in the proposal, in one working folder and in a worktree of its own. A claim is never freed by the clock alone: what its holder left
behind decides, so a holder that works for five hours without a sign of life keeps what it holds.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, no sleeps: time is moved by changing the times a claim records.
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
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import claims, hook              # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
PAGE = base.doc('Greet', 'Says hello.',
                rules=['- **hello** - The page says {text: Hello}.', '', '- **bye** - The page says {text: Bye}.', '', '- **thanks** - The page says {text: Thanks}.'],
                tests=['- **hello** - says hello.', '  manual: a person looks'])
CODE = ('// @clause glue\n"use strict";\n// @clause end\n// @clause greet/hello\nconsole.log("Hello");\n// @clause end\n'
        '// @clause greet/bye\nconsole.log("Bye");\n// @clause end\n// @clause greet/thanks\nconsole.log("Thanks");\n// @clause end\n')
A, B = 'aaaaaaaa-1', 'bbbbbbbb-2'
OTHER_SESSION = 'cccccccc-3'
HOUR = 3600


def git(cwd, *args):
    done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'core.hooksPath=/dev/null', *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


class Scene(flows.Flow):
    """The greet project in a git repository with a second worktree. `self.dir` is the main folder, `self.second` the worktree. Agent a (session A) and agent b
    (session B) take turns."""

    def setUp(self):
        super().setUp()
        self.project({'greet': PAGE})
        write(self.dir, 'out/app.js', CODE)
        git(self.dir, 'init', '-q', '-b', 'main')
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        git(self.dir, 'add', '-A')
        git(self.dir, 'commit', '-q', '-m', 'base')
        holder = tempfile.mkdtemp(prefix='wt-')
        self.addCleanup(shutil.rmtree, holder, True)
        self.second = os.path.realpath(os.path.join(holder, 'second'))
        git(self.dir, 'worktree', 'add', '-q', self.second, '-b', 'second')

    # --- acting

    def run_at(self, root, session, *args, **env):
        with mock.patch.dict(os.environ, dict(env, CLAUDE_CODE_SESSION_ID=session)):
            code, out, err = base.run_sor(root, *args)
        return code, out + err

    def claim(self, root, session, *ids, take_over=False):
        extra = ('--take-over',) if take_over else ()
        return self.run_at(root, session, 'claim', *ids, '--as', 'a' if session == A else 'b', *extra)

    def project_at(self, root):
        return Project(root)

    def records(self):
        return claims.read(Project(self.dir))

    def of(self, session):
        return [c for c in self.records() if c.get('session') == session and not c.get('freed')]

    def rewrite(self, change):
        """Changes the records of the store with `change(c)`."""
        project = Project(self.dir)
        held = claims.read(project)
        for c in held:
            change(c)
        claims._write(project, held)

    def age(self, session, seconds):
        """As if `seconds` had gone by without a sign of life of the session."""
        def go(c):
            if c.get('session') == session:
                c['last'] -= seconds
                c['until'] -= seconds
        self.rewrite(go)

    def end(self, session, reason='other'):
        claims.mark_ended(Project(self.dir), session, reason)

    def unfinished(self, root, clause='hello', old='Hello', new='Hi'):
        """Work begun and not locked in a working folder: the clause changed, its code changed."""
        flows.replace_in(os.path.join(root, 'sor', 'greet.md'), '{text: %s}' % old, '{text: %s}' % new)
        flows.replace_in(os.path.join(root, 'out', 'app.js'), '"%s"' % old, '"%s"' % new)

    def finish(self, root, session, clause='hello'):
        """Lock it, as the agent of `session` that holds the claim would."""
        code, said = self.run_at(root, session, 'lock', f'greet/{clause}', '--as', 'a' if session == A else 'b')
        self.assertEqual(code, 0, said)

    def free(self, session=B, *ids):
        """Whether b can claim the clause now."""
        return self.claim(self.dir, session, *(ids or ('greet/hello',)))


class TestAHolderAtWork(Scene):
    def test_a_claim_is_held_while_its_holder_is_at_work_and_nothing_else_is_looked_at(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('held by', said)

    def test_it_stays_held_after_the_holder_locked_part_of_its_work(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.unfinished(self.second)
        self.finish(self.second, A)
        self.assertEqual(self.free()[0], 3)

    def test_a_holder_that_was_quiet_for_the_window_and_comes_back_has_its_claim(self):
        self.claim(self.second, A, 'greet/hello')
        self.age(A, HOUR)
        self.run_at(self.second, A, 'status', '--json')      # a sign of life before anybody asked
        self.assertEqual(self.free()[0], 3)

    def test_five_hours_of_a_build_in_the_background_keep_the_claim_whatever_the_clock_says(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        claims.mark_busy(Project(self.dir), A, True)       # the Stop it ended its turn with listed the build
        self.age(A, 5 * HOUR)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('held by', said)

    def test_without_that_signal_the_same_holder_is_parked_not_freed(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.age(A, 5 * HOUR)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)


class TestTheSameFolder(Scene):
    def test_nothing_left_by_a_quiet_holder_frees_the_claim_and_the_holder_is_told_later(self):
        self.claim(self.dir, A, 'greet/hello')
        self.age(A, HOUR)
        code, said = self.free()
        self.assertEqual(code, 0, said)
        self.assertIn('freed the claim of a on greet/hello', said)
        self.assertIn('claims on greet/hello expired at', self.run_at(self.dir, A, 'release', '--all', '--as', 'a')[1])

    def test_unfinished_work_of_a_quiet_holder_in_this_folder_keeps_the_claim_parked(self):
        self.claim(self.dir, A, 'greet/hello')
        self.unfinished(self.dir)
        self.age(A, HOUR)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)
        self.assertIn('1 change', said)

    def test_a_holder_whose_session_ended_leaves_the_claim_free_even_with_unfinished_work(self):
        self.claim(self.dir, A, 'greet/hello')
        self.unfinished(self.dir)
        self.end(A)
        code, said = self.free()
        self.assertEqual(code, 0, said)      # what it left is in the files of this folder, as changes to finish
        self.assertIn('freed the claim of a', said)

    def test_a_subagent_that_stopped_is_gone(self):
        self.claim(self.dir, A, 'greet/hello')
        self.rewrite(lambda c: c.update(stopped=time.time() - 5))
        self.assertEqual(self.free()[0], 0)

    def test_a_takeover_of_a_parked_claim_in_this_folder_continues_there(self):
        self.claim(self.dir, A, 'greet/hello')
        self.unfinished(self.dir)
        self.age(A, HOUR)
        code, said = self.free()
        self.assertEqual(code, 3)
        code, said = self.claim(self.dir, B, 'greet/hello', take_over=True)
        self.assertEqual(code, 0, said)
        self.assertIn('took over the claim of a', said)
        self.assertIn('an agent\'s unfinished work, not a person\'s change to keep', said)
        (mine,) = self.of(B)
        self.assertEqual(mine['took_over'][0]['agent'], 'a')
        self.assertEqual(mine['took_over'][0]['changes'], 1)
        (old,) = [c for c in self.records() if c.get('freed')]
        self.assertEqual((old['freed']['by'], old['freed']['why']), ('b', 'taken over'))
        self.assertIn('taken over by b', self.run_at(self.dir, A, 'release', '--all', '--as', 'a')[1])      # the old holder is told when it comes back


class TestAnotherFolder(Scene):
    def test_a_holder_that_ended_with_unfinished_work_in_its_worktree_is_parked(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)
        self.assertIn(self.second, said)
        self.assertIn('branch second', said)
        self.assertIn('--take-over', said)

    def test_a_holder_that_ended_having_done_nothing_leaves_the_claim_free(self):
        self.claim(self.second, A, 'greet/hello')
        self.end(A)
        self.assertEqual(self.free()[0], 0)

    def test_the_takeover_of_a_parked_claim_names_where_the_work_is(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        code, said = self.claim(self.dir, B, 'greet/hello', take_over=True)
        self.assertEqual(code, 0, said)
        self.assertIn(f'took over the claim of a on greet/hello: it left 1 unfinished change in {self.second} (branch second)', said)
        (mine,) = self.of(B)
        self.assertEqual(os.path.realpath(mine['took_over'][0]['where']['path']), self.second)

    def test_a_takeover_is_refused_for_a_holder_at_work(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        code, said = self.claim(self.dir, B, 'greet/hello', take_over=True)
        self.assertEqual(code, 3, said)
        self.assertIn('--take-over takes over a parked claim only', said)
        self.assertEqual(len(self.of(A)), 1)

    def test_the_old_holder_is_refused_when_it_comes_back_and_the_taker_holds_the_clause(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        self.claim(self.dir, B, 'greet/hello', take_over=True)
        code, said = self.run_at(self.second, A, 'lock', 'greet/hello', '--as', 'a')
        self.assertEqual(code, 2, said)
        self.assertIn('taken over by b', said)      # the fence: the old holder's lock is refused, and says why
        self.assertIn('claim again', said)
        self.assertIn('read the clause again', said)

    def test_finished_work_that_has_not_arrived_waits_for_its_merge_without_a_takeover(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.finish(self.second, A)
        self.end(A)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('waiting for the merge', said)
        self.assertIn('branch second', said)
        code, said = self.claim(self.dir, B, 'greet/hello', take_over=True)
        self.assertEqual(code, 3, said)
        self.assertEqual(len(self.of(A)), 1)

    def test_no_time_limit_holds_a_waiting_claim(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.finish(self.second, A)
        self.end(A)
        self.age(A, 400 * 24 * HOUR)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('waiting for the merge', said)

    def test_the_claim_is_freed_when_the_work_has_reached_this_copy(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.finish(self.second, A)
        self.end(A)
        self.assertEqual(self.free()[0], 3)
        git(self.second, 'add', '-A')
        git(self.second, 'commit', '-q', '-m', 'a finished hello')
        git(self.dir, 'merge', '-q', 'second')      # the merge
        code, said = self.free()
        self.assertEqual(code, 0, said)
        self.assertIn('its work has reached this copy', said)

    def test_a_clause_changed_again_after_the_merge_counts_as_arrived_too(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.finish(self.second, A)
        self.end(A)
        git(self.second, 'add', '-A')
        git(self.second, 'commit', '-q', '-m', 'a finished hello')
        git(self.dir, 'merge', '-q', 'second')
        self.unfinished(self.dir, old='Hi', new='Hey')      # somebody changed hello again, and locked it
        self.finish(self.dir, B)
        self.assertEqual(self.free()[0], 0)

    def test_the_parked_window_frees_a_claim_that_was_left_unfinished(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        self.assertEqual(self.free()[0], 3)
        self.rewrite(lambda c: c.update(ended={'reason': 'other', 'at': time.time() - 25 * HOUR}))
        code, said = self.free()
        self.assertEqual(code, 0, said)
        self.assertIn('the parked window passed', said)

    def test_the_root_file_sets_the_parked_window(self):
        root = os.path.join(self.dir, 'sor', 'SPECOFRECORD.md')
        write(self.dir, 'sor/SPECOFRECORD.md', read(root).replace('Why: ', 'Claims: idle 30m, parked 2h\nWhy: ', 1))
        self.assertEqual([p for p in Project(self.dir).check() if p.kind == 'claims'], [])
        self.assertEqual(claims.project_parked(Project(self.dir)), 2 * HOUR)
        self.assertEqual(claims.project_idle(Project(self.dir)), 30 * 60)
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        self.rewrite(lambda c: c.update(ended={'reason': 'other', 'at': time.time() - 3 * HOUR}))
        self.assertEqual(self.free()[0], 0)

    def test_a_working_folder_that_is_gone_frees_the_claim_unless_the_holder_locked_work(self):
        self.claim(self.second, A, 'greet/hello')
        self.claim(self.second, A, 'greet/bye')
        self.unfinished(self.second, clause='bye', old='Bye', new='Cya')
        self.finish(self.second, A, 'bye')
        git(self.dir, 'worktree', 'remove', '--force', self.second)      # the sweep, or a person, removes the worktree
        self.assertEqual(self.free(B, 'greet/hello')[0], 0)
        code, said = self.free(B, 'greet/bye')
        self.assertEqual(code, 3, said)
        self.assertIn('waiting for the merge', said)

    def test_a_folder_on_another_machine_leaves_the_idle_window_alone_to_decide(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.rewrite(lambda c: c['where'].update(host='another-machine'))
        self.end(A)
        self.assertEqual(self.free()[0], 3)      # ended, but its folder cannot be read from here, and the idle window has not passed
        self.age(A, HOUR)
        self.assertEqual(self.free()[0], 0)


class TestWorkThatIsPartlyDone(Scene):
    """A holder that locked one clause and went on with another is not done: the claim is arrived only when nothing is unfinished."""

    def setUp(self):
        super().setUp()
        self.claim_both = lambda root: self.run_at(root, A, 'claim', 'greet/hello', 'greet/bye', '--as', 'a')

    def test_in_the_same_folder_a_killed_holder_with_the_second_clause_unfinished_is_parked(self):
        self.assertEqual(self.claim_both(self.dir)[0], 0)
        self.unfinished(self.dir)
        self.finish(self.dir, A)
        self.unfinished(self.dir, old='Bye', new='Cya')      # then the second clause, never locked
        self.age(A, HOUR)      # killed: no SessionEnd, it just stops
        code, said = self.free(B, 'greet/bye')
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)

    def test_in_a_worktree_the_first_clause_has_arrived_and_the_second_has_not_so_the_claim_stands(self):
        self.assertEqual(self.claim_both(self.second)[0], 0)
        self.unfinished(self.second)
        self.finish(self.second, A)
        git(self.second, 'add', '-A')
        git(self.second, 'commit', '-q', '-m', 'hello')
        git(self.dir, 'merge', '-q', 'second')      # hello reaches the main folder
        self.unfinished(self.second, old='Bye', new='Cya')      # and the holder goes on with bye in its worktree
        self.end(A)
        code, said = self.free(B, 'greet/bye')
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)
        self.assertIn(self.second, said)

    def test_when_the_second_clause_is_finished_and_merged_too_the_claim_is_freed(self):
        self.assertEqual(self.claim_both(self.second)[0], 0)
        self.unfinished(self.second)
        self.unfinished(self.second, old='Bye', new='Cya')
        self.finish(self.second, A)
        self.finish(self.second, A, 'bye')
        git(self.second, 'add', '-A')
        git(self.second, 'commit', '-q', '-m', 'both')
        git(self.dir, 'merge', '-q', 'second')
        self.end(A)
        self.assertEqual(self.free(B, 'greet/bye')[0], 0)

    def test_the_takeover_records_the_old_folder_as_the_place_of_the_work_so_the_work_is_not_lost_again(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        self.assertEqual(self.claim(self.dir, B, 'greet/hello', take_over=True)[0], 0)
        (mine,) = self.of(B)
        self.assertEqual(os.path.realpath(mine['where']['path']), self.second)      # not the taker's folder
        self.assertEqual(mine['where']['label'], 'second')
        self.age(B, HOUR)      # the taker goes away too, with the work still unfinished in that folder
        code, said = self.run_at(self.dir, OTHER_SESSION, 'claim', 'greet/hello', '--as', 'c')
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)
        self.assertIn(self.second, said)


class TestWhatTheHolderDidAndWhatWasThereBefore(Scene):
    """`unfinished` is what the holder changed since the grant, not every pending change on its keys."""

    def test_a_project_with_no_lock_yet_does_not_park_a_claim_that_did_nothing(self):
        os.remove(os.path.join(self.dir, 'sor', 'sor-lock.json'))
        self.assertEqual(self.claim(self.dir, A, 'greet/hello')[0], 0)
        self.age(A, HOUR)      # quiet: every key of the project is `new`, and the holder did nothing
        self.assertEqual(self.free()[0], 0)

    def test_the_same_project_does_park_a_claim_whose_holder_began_work(self):
        os.remove(os.path.join(self.dir, 'sor', 'sor-lock.json'))
        self.assertEqual(self.claim(self.dir, A, 'greet/hello')[0], 0)
        self.unfinished(self.dir)
        self.age(A, HOUR)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)
        self.assertIn('1 change', said)

    def test_a_change_made_before_the_claim_is_not_the_holders_unfinished_work(self):
        self.unfinished(self.second)      # a person's edit, and then the holder claims and does nothing
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.end(A)
        self.assertEqual(self.free()[0], 0)

    def test_a_change_made_after_the_claim_is(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.unfinished(self.second)
        self.end(A)
        self.assertEqual(self.free()[0], 3)

    def test_after_a_takeover_what_the_old_holder_left_is_still_unfinished_work(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.unfinished(self.second)
        self.end(A)
        self.assertEqual(self.claim(self.dir, B, 'greet/hello', take_over=True)[0], 0)
        self.age(B, HOUR)
        code, said = self.run_at(self.dir, OTHER_SESSION, 'claim', 'greet/hello', '--as', 'c')
        self.assertEqual(code, 3, said)
        self.assertIn('parked', said)


class TestAWorkingFolderThatIsGoneAfterTheMerge(Scene):
    def test_the_work_reached_this_copy_so_the_claim_is_free(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.unfinished(self.second)
        self.finish(self.second, A)
        git(self.second, 'add', '-A')
        git(self.second, 'commit', '-q', '-m', 'hello')
        git(self.dir, 'merge', '-q', 'second')
        git(self.dir, 'worktree', 'remove', '--force', self.second)      # a person, or the sweep, removes the worktree after the merge
        code, said = self.free()
        self.assertEqual(code, 0, said)
        self.assertIn('its work has reached this copy', said)

    def test_before_the_merge_the_same_claim_waits(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.unfinished(self.second)
        self.finish(self.second, A)
        git(self.dir, 'worktree', 'remove', '--force', self.second)
        code, said = self.free()
        self.assertEqual(code, 3, said)
        self.assertIn('waiting for the merge', said)


class TestTheLastLookOfAClaim(Scene):
    def test_a_holder_whose_record_keeps_changing_is_held_and_never_freed_on_a_stale_look(self):
        self.assertEqual(self.claim(self.second, A, 'greet/hello')[0], 0)
        self.end(A)      # the first look says free (gone, nothing left)
        real = claims.decide
        looks = []

        def and_then_the_record_changes(project, c, *args, **kw):
            result = real(project, c, *args, **kw)
            looks.append(result.kind)
            self.rewrite(lambda r: r.update(note=len(looks)) if r['agent'] == 'a' else None)      # a write of the record: its rev moves after every look
            return result

        with mock.patch.object(claims, 'decide', and_then_the_record_changes):
            code, said = self.free()
        self.assertEqual(looks, ['free', 'free', 'free'])      # three looks, and then it stops looking
        self.assertEqual(code, 3, said)
        self.assertEqual(len(self.of(A)), 1)      # the holder kept its claim


class TestTheGuardReadsFewFolders(Scene):
    def gone_holders(self, folders):
        """Records of holders that ended, all on greet/hello, each with a working folder of its own (copies of the project)."""
        import shutil
        project = Project(self.dir)
        held = []
        for n, folder in enumerate(folders):
            held.append({'agent': f'h{n}', 'asked': ['greet/hello'], 'keys': ['greet/hello', 'greet/hello.text'], 'since': time.time(), 'until': time.time() + 600, 'idle': 1800,
                         'last': time.time(), 'regions': [], 'session': f'sess{n:04d}-x', 'where': {'path': folder, 'host': claims.socket.gethostname(), 'label': ''}, 'base': {},
                         'ended': {'reason': 'other', 'at': time.time() - 60}})
        claims._write(project, held)

    def copies(self, n):
        import shutil
        out = []
        for i in range(n):
            d = os.path.join(os.path.dirname(self.second), f'copy{i}')
            shutil.copytree(self.dir, d, ignore=shutil.ignore_patterns('.git'))
            out.append(d)
        return out

    def test_each_folder_is_read_once_however_many_claims_it_holds(self):
        folders = self.copies(2)
        self.gone_holders([folders[0], folders[1]] * 5)      # ten holders in two folders
        calls = []
        real = claims.lockfile.status

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        with mock.patch.object(claims.lockfile, 'status', counting):
            claims.others_for_session(Project(self.dir), B, ['greet/hello'])
        self.assertLessEqual(len(calls), 3)      # the requester's folder, and the two others once each

    def test_it_reads_at_most_a_few_holders_that_are_gone_and_takes_the_rest_to_stand(self):
        folders = self.copies(5)
        self.gone_holders(folders)
        calls = []
        real = claims.lockfile.status

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        with mock.patch.object(claims, 'GUARD_LOOKS', 2), mock.patch.object(claims.lockfile, 'status', counting):
            held = claims.standing(Project(self.dir), claims.active(Project(self.dir)))
        self.assertLessEqual(len(calls), 2)
        self.assertTrue(held)      # the first that stands ends the look, and what is not looked at stands

    def test_with_the_cap_gone_the_decision_is_still_made_in_full_by_sor_claim(self):
        folders = self.copies(3)
        self.gone_holders(folders)
        with mock.patch.object(claims, 'GUARD_LOOKS', 1):
            self.assertEqual(len(claims.states(Project(self.dir), claims.active(Project(self.dir)), limit=claims.GUARD_LOOKS)), 3)
        code, said = self.free()
        self.assertEqual(code, 0, said)      # every holder ended and left nothing: free, whatever the guard's cap


class TestWhatTheEditGuardDoes(Scene):
    def guard(self, root, session, clause='hello', old='Hello', new='Hi'):
        edit = flows.edit(os.path.join(root, 'sor', 'greet.md'), '{text: %s}' % old, '{text: %s}' % new, session_id=session)
        with mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'}):
            return flows.reason(hook.pre_edit(edit))

    def test_it_refuses_while_the_holder_is_at_work_and_lets_the_edit_through_when_nothing_is_left(self):
        self.claim(self.second, A, 'greet/hello')
        self.assertIn('Someone else is working on this', self.guard(self.dir, B))
        self.end(A)
        self.assertIsNone(self.guard(self.dir, B))      # the holder is gone and left nothing

    def test_it_refuses_while_unfinished_work_is_parked_in_another_folder(self):
        self.claim(self.second, A, 'greet/hello')
        self.unfinished(self.second)
        self.end(A)
        self.assertIn('Someone else is working on this', self.guard(self.dir, B))


if __name__ == '__main__':
    unittest.main()
