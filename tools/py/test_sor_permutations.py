"""Every combination of what a claim can meet, checked against an oracle written apart from the code (SPEC §16).

A holder `a` claims `greet/hello` in a working folder; time and events change what its claim is; a requester `b` in the main folder asks for the clause in four ways
(`sor claims --json`, the edit guard on the text and on the code, `sor claim`, `sor claim --take-over`), and every way has to agree with the oracle:

    where the holder is   the requester's folder, another worktree, another machine, a folder that is gone
    what it is            at work, quiet, busy in the background (within the parked window, and past it), session ended, subagent stopped, ended and resumed
    what it left          nothing, unfinished work, locked work that has not arrived, work that arrived, work that arrived and more unfinished, one clause of two
                          done and the other not, one of two locked and merged and the other locked and not, a clause changed again after the merge
    how long ago          before the parked window is over, after

The oracle (`expected`) is the proposal's table, transcribed, and does not call `claims.decide`. The same cases are run through mutants of `decide`, each with one rule
broken, and every mutant has to give a wrong answer for at least one case: that is the proof that the cases check something. Further down: who may edit what when a session
has subagents (30 cases), random sequences of operations across two worktrees with the invariant "at most one claim stands for a key" after every step, and real processes
racing for one clause.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v
    SOR_MATRIX_OUT=/some/file.md python3 -m unittest tools/py/test_sor_permutations.py     also writes the table of what each case gave

Python 3.9, standard library only, no sleeps: time is moved by changing the times a claim records. Needs git.
"""
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import claims, hook              # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
GIT = shutil.which('git')
A, B, C = 'aaaaaaaa-1', 'bbbbbbbb-2', 'cccccccc-3'
HOUR = 3600
SOR = os.path.join(HERE, 'sor.py')
PAGE = base.doc('Greet', 'Says hello.',
                rules=['- **hello** - The page says {text: Hello}.', '', '- **bye** - The page says {text: Bye}.', '', '- **thanks** - The page says {text: Thanks}.'],
                tests=['- **hello** - says hello.', '  manual: a person looks'])
CODE = ('// @clause glue\n"use strict";\n// @clause end\n// @clause greet/hello\nconsole.log("Hello");\n// @clause end\n'
        '// @clause greet/bye\nconsole.log("Bye");\n// @clause end\n// @clause greet/thanks\nconsole.log("Thanks");\n// @clause end\n')


def run_cli(root, *args):
    """`base.run_sor` without its comparison with the JavaScript tool before and after every command (with SOR_COMPARE_JS set): these tests run thousands of commands.
    `compare` does it once per case, for the state the case built."""
    import contextlib
    import io
    from sorlib import cli
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(['-C', root, *args])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def compare(*roots):
    """With SOR_COMPARE_JS set: the state of these folders through the JavaScript tool and the Python tool, which must read it the same way."""
    if os.environ.get('SOR_COMPARE_JS'):
        import test_sor_js
        for root in roots:
            if os.path.isdir(os.path.join(root, 'sor')):
                found = test_sor_js.compare_with_javascript(root, fresh=True)
                assert not found, f'the JavaScript tool reads {root} otherwise:\n' + '\n'.join(found)


def git(cwd, *args, check=True):
    done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'core.hooksPath=/dev/null', *args], cwd=cwd, capture_output=True, text=True)
    if check:
        assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


class World:
    """One git repository with the greet project, a main folder and a second worktree, put back to its first state between cases."""

    def __init__(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='perm-'))
        self.main = os.path.join(self.tmp, 'main')
        self.second = os.path.join(self.tmp, 'second')
        base.make_project(self.main, {'greet': PAGE})
        write(self.main, 'out/app.js', CODE)
        git(self.main, 'init', '-q', '-b', 'main')
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in flows.ENV:
                os.environ.pop(name, None)
            code, out, err = run_cli(self.main, 'lock', '--all')
            assert code == 0, out + err
        git(self.main, 'add', '-A')
        git(self.main, 'commit', '-q', '-m', 'base')
        self.base = git(self.main, 'rev-parse', 'HEAD').strip()
        git(self.main, 'worktree', 'add', '-q', self.second, '-b', 'second')

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reset(self):
        """Back to the first state: no claims, no work, no commits, both folders there."""
        st = claims.store(Project(self.main))
        for name in os.listdir(st.dir) if os.path.isdir(st.dir) else ():
            try:
                os.remove(os.path.join(st.dir, name))
            except OSError:
                pass
        if not os.path.isdir(self.second):
            git(self.main, 'worktree', 'prune')
            git(self.main, 'branch', '-f', 'second', self.base)
            git(self.main, 'worktree', 'add', '-q', '-f', self.second, 'second')
        for root in (self.main, self.second):
            git(root, 'reset', '--hard', '-q', self.base)
            git(root, 'clean', '-fdq')

    def run(self, root, session, *args, **env):
        with mock.patch.dict(os.environ, dict(env, CLAUDE_CODE_SESSION_ID=session)):
            os.environ.pop('SOR_ENFORCE_CLAIMS', None)
            code, out, err = run_cli(root, *args)
        return code, out + err

    def edit(self, root, clause, old, new):
        flows.replace_in(os.path.join(root, 'sor', 'greet.md'), '{text: %s}' % old, '{text: %s}' % new)
        flows.replace_in(os.path.join(root, 'out', 'app.js'), '"%s"' % old, '"%s"' % new)

    def current(self, root, clause='hello'):
        return re.search(r'\*\*%s\*\* - The page says \{text: (\w+)\}' % clause, read(os.path.join(root, 'sor', 'greet.md'))).group(1)

    def commit_and_merge(self, root):
        git(root, 'add', '-A')
        git(root, 'commit', '-q', '-m', 'work')
        if root != self.main:
            git(self.main, 'merge', '-q', 'second')

    def records(self, agent='a'):
        return [c for c in claims.read(Project(self.main)) if c['agent'] == agent]

    def rewrite(self, change):
        project = Project(self.main)
        held = claims.read(project)
        for c in held:
            change(c)
        claims._write(project, held)

    def age(self, agent, seconds):
        def go(c):
            if c['agent'] == agent:
                c['last'] -= seconds
                c['until'] -= seconds
        self.rewrite(go)


# --- the oracle: the proposal's table, transcribed ------------------------------------------------------------------------------------

PLACES = ('here', 'other', 'host', 'gone')
LIVES = ('active', 'quiet', 'busy', 'busy_past', 'ended', 'stopped', 'resumed')
WORKS = ('none', 'earlier_edit', 'unfinished', 'locked', 'arrived', 'arrived_plus_unfinished', 'partial', 'half_arrived', 'changed_again')
GONE = ('quiet', 'busy_past', 'ended', 'stopped')


def cases():
    out = []
    for place, live, work, late in itertools.product(PLACES, LIVES, WORKS, (False, True)):
        if place == 'here' and work in ('arrived', 'changed_again'):
            continue      # locked in the requester's own folder is arrived: the same case as `locked`
        if place in ('host', 'gone') and work in ('half_arrived', 'earlier_edit'):
            continue
        if place == 'host' and work not in ('none', 'unfinished', 'locked'):
            continue      # a folder nobody here can read: what it holds does not matter
        if place == 'gone' and (work not in ('none', 'locked', 'arrived') or late):
            continue      # a folder that is gone holds nothing; it only matters whether the holder locked work
        out.append((place, live, work, late))
    return out


def expected(place, live, work, late):
    """What `sor claim` finds for the holder: free, held, parked or waiting."""
    locked_work = work in ('locked', 'arrived', 'arrived_plus_unfinished', 'partial', 'half_arrived', 'changed_again')
    unfinished_work = work in ('unfinished', 'arrived_plus_unfinished', 'partial')
    if place == 'gone':      # the folder cannot say; this copy can: work that reached it is arrived
        return 'free' if work in ('arrived', 'changed_again') or not locked_work else 'waiting'
    if live not in GONE:
        return 'held'
    if place == 'host':
        return 'free' if live in ('quiet', 'busy_past') else 'held'      # unreadable: only the idle window speaks; ended and stopped have not passed it
    arrived = work in ('arrived', 'changed_again') or (work in ('locked', 'half_arrived') and place == 'here')
    if arrived:
        return 'free'
    if place == 'here' and live in ('ended', 'stopped'):
        return 'free'      # what it left is in this folder's files
    if unfinished_work:
        return 'free' if late else 'parked'
    if work in ('locked', 'half_arrived'):
        return 'waiting'
    return 'free'


class Arranged:
    """One case set up in a World: the holder's claim in the state the case names."""

    def __init__(self, world, place, live, work, late):
        self.w, self.place, self.live, self.work, self.late = world, place, live, work, late
        world.reset()
        w = world
        root = w.main if place == 'here' else w.second
        ids = ('greet/hello', 'greet/bye') if work in ('partial', 'half_arrived') else ('greet/hello',)
        if work == 'earlier_edit':      # somebody changed hello before the holder claimed it, and the holder did nothing
            w.edit(root, 'hello', 'Hello', 'Hi')
        code, said = w.run(root, A, 'claim', *ids, '--as', 'a')
        assert code == 0, said
        name = lambda clause: ['--as', 'a']
        if work in ('unfinished', 'locked', 'arrived', 'arrived_plus_unfinished', 'partial', 'half_arrived', 'changed_again'):
            w.edit(root, 'hello', 'Hello', 'Hi')
        if work in ('locked', 'arrived', 'arrived_plus_unfinished', 'partial', 'half_arrived', 'changed_again'):
            code, said = w.run(root, A, 'lock', 'greet/hello', '--as', 'a')
            assert code == 0, said
        if work in ('arrived', 'arrived_plus_unfinished', 'partial', 'half_arrived', 'changed_again') and place != 'here':
            w.commit_and_merge(root)
        if work == 'half_arrived':      # hello reached the requester's copy; bye is locked too, but only in the holder's folder
            w.edit(root, 'bye', 'Bye', 'Cya')
            code, said = w.run(root, A, 'lock', 'greet/bye', '--as', 'a')
            assert code == 0, said
        if work == 'arrived_plus_unfinished':
            w.edit(root, 'hello', 'Hi', 'Hey')
        if work == 'partial':
            w.edit(root, 'bye', 'Bye', 'Cya')
        if work == 'changed_again':
            w.edit(w.main, 'hello', 'Hi', 'Hey')
            flows.accepted(w.main)      # somebody else changed hello again in the requester's copy and locked it
        self.live_up(late)
        if place == 'host':
            w.rewrite(lambda c: c['where'].update(host='another-machine'))
        if place == 'gone':
            git(w.main, 'worktree', 'remove', '--force', w.second)
        compare(w.main, w.second)

    def live_up(self, late):
        w, live = self.w, self.live
        project = Project(w.main)
        if live == 'quiet':
            w.age('a', 26 * HOUR if late else HOUR)
        elif live == 'busy':
            claims.mark_busy(project, A, True)
            w.age('a', 5 * HOUR)
        elif live == 'busy_past':
            claims.mark_busy(project, A, True)
            w.rewrite(lambda c: c.update(busy_at=c['busy_at'] - 25 * HOUR))
            w.age('a', 26 * HOUR if late else HOUR)
        elif live == 'ended':
            claims.mark_ended(project, A, 'other')
            if late:
                w.rewrite(lambda c: c.update(ended=dict(c['ended'], at=c['ended']['at'] - 25 * HOUR)))
        elif live == 'stopped':
            w.rewrite(lambda c: c.update(stopped=time.time() - (25 * HOUR if late else 5)))
        elif live == 'resumed':
            claims.mark_ended(project, A, 'other')
            claims.renew(project, A)

    def decide_inputs(self):
        project = Project(self.w.main)
        (c,) = [r for r in claims.read(project) if r['agent'] == 'a' and not r.get('freed')]
        return project, c, Scan(project), claims._lock_of(project)


def mutant(*changes):
    """The claims module with `changes` ([(old text, new text)]) made in its source: a copy with one rule broken."""
    with open(claims.__file__, encoding='utf8') as fh:
        src = fh.read()
    for old, new in changes:
        assert old in src, f'the mutant\'s text is not in claims.py any more: {old[:60]}'
        src = src.replace(old, new)
    mod = types.ModuleType('sorlib._mutant')
    mod.__package__ = 'sorlib'
    mod.__file__ = claims.__file__
    exec(compile(src, claims.__file__, 'exec'), mod.__dict__)
    return mod


MUTANTS = {
    'the lock of the requester is not compared with the base': [("all(entry_sig(lock.get(k)) != base.get(k, '') for k in seen.changed)", 'True')],
    'one changed entry in the requester\'s copy is enough (any, not all)': [("all(entry_sig(lock.get(k)) != base.get(k, '') for k in seen.changed)", "any(entry_sig(lock.get(k)) != base.get(k, '') for k in seen.changed)")],
    'unfinished work does not keep arrived work from being arrived': [("seen.worked and not seen.unfinished and lock is not None", 'seen.worked and lock is not None')],
    'the background signal is ignored': [("return bool(at) and not c.get('ended') and (window is None or now - at < window)", 'return False')],
    'a folder that is gone frees the claim even if the holder locked work': [("        if not c.get('locked'):\n            return Decision('free', 'its working folder is gone'", "        if True:\n            return Decision('free', 'its working folder is gone'")],
    'a folder that is gone is never read as arrived': [("if lock is not None and base and any(entry_sig(lock.get(k)) != base.get(k, '') for k in c.get('keys', []) if '@' not in k):", 'if False:')],
    'unfinished counts what was there before the grant': [("and (start is None or f.key.split('@')[0] not in start or entry_sig(now.get(f.key.split('@')[0])) != start[f.key.split('@')[0]])", 'and True')],
    'a folder on another machine is read as if it were here': [("on_this_machine = where.get('host') in (None, socket.gethostname())", 'on_this_machine = True'),
                                                              ("if (c.get('where') or {}).get('host') not in (None, socket.gethostname()):\n            return None", 'if False:\n            return None')],
    'a holder that ended in this folder is parked like one in another': [('if same_folder and ended:', 'if False:')],
    'the parked window never passes': [('if window is not None and now - since >= window:', 'if False:')],
    'a subagent that stopped is not gone': [("return bool(c.get('ended') or c.get('stopped')) or is_quiet(c, now, window)", "return bool(c.get('ended')) or is_quiet(c, now, window)")],
    'finished work that has not arrived is free': [("if seen.worked:\n        return Decision('waiting'", "if False:\n        return Decision('waiting'")],
}


@unittest.skipUnless(GIT, 'git is not installed')
class TestEveryCombination(unittest.TestCase):
    """Run once for all cases (a class of its own so that the world is built once): the tests below read the results."""
    results = None

    @classmethod
    def setUpClass(cls):
        os.environ.pop('SOR_ENFORCE_CLAIMS', None)
        cls.world = World()
        cls.mutants = {name: mutant(*changes) for name, changes in MUTANTS.items()}
        cls.rows = []
        for place, live, work, late in cases():
            case = Arranged(cls.world, place, live, work, late)
            project, c, scan, lock = case.decide_inputs()
            now = time.time()
            real = claims.decide(project, c, scan, lock, now, None)
            by_mutant = {name: m.decide(project, c, scan, lock, now, None).kind for name, m in cls.mutants.items()}
            guard_spec, guard_code = cls.guard(case)
            states = cls.states_json(case)
            claimed = cls.world.run(cls.world.main, B, 'claim', 'greet/hello', '--as', 'b')
            took = None
            if claimed[0] == 3:
                took = cls.world.run(cls.world.main, B, 'claim', 'greet/hello', '--as', 'b', '--take-over')
            cls.rows.append(dict(case=(place, live, work, late), want=expected(place, live, work, late), decide=real.kind, mutants=by_mutant, spec=guard_spec,
                                 code=guard_code, state=states, claim=claimed, takeover=took))
        if os.environ.get('SOR_MATRIX_OUT'):
            cls.write_table(os.environ['SOR_MATRIX_OUT'])

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    @classmethod
    def guard(cls, case):
        w = cls.world
        spec = os.path.join(w.main, 'sor', 'greet.md')
        cur = w.current(w.main)
        out = []
        for payload in (flows.edit(spec, '{text: %s}' % cur, '{text: Zed}', session_id=B),
                        flows.edit(os.path.join(w.main, 'out', 'app.js'), '"%s"' % cur, '"Zed"', session_id=B)):
            with mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'}):
                reason = flows.reason(hook.pre_edit(payload))
            out.append('Someone else is working on this' in (reason or ''))
        return out

    @classmethod
    def states_json(cls, case):
        code, said = cls.world.run(cls.world.main, B, 'claims', '--json')
        data = json.loads(said)
        mine = [r for r in data['claims'] if r['holder'] == 'a']
        return mine[0]['state'] if mine else None

    @classmethod
    def write_table(cls, path):
        lines = ['# What each combination gave', '', 'Generated by `tools/py/test_sor_permutations.py` (`SOR_MATRIX_OUT`). Each row: where the holder is, what it is, what it left, whether the '
                 'parked window is over; then what the oracle expects, what `sor claims --json`, the edit guard (text, code), `sor claim` and `sor claim --take-over` gave.', '',
                 '| place | holder | left | window over | expected | claims --json | guard text | guard code | claim | take-over |', '|---|---|---|---|---|---|---|---|---|---|']
        for r in cls.rows:
            place, live, work, late = r['case']
            claim = 'ok' if r['claim'][0] == 0 else 'refused'
            took = '' if r['takeover'] is None else ('ok' if r['takeover'][0] == 0 else 'refused')
            lines.append(f"| {place} | {live} | {work} | {'yes' if late else 'no'} | {r['want']} | {r['state']} | {'refused' if r['spec'] else 'allowed'} | "
                         f"{'refused' if r['code'] else 'allowed'} | {claim} | {took} |")
        with open(path, 'w', encoding='utf8') as fh:
            fh.write('\n'.join(lines) + '\n')

    def test_there_are_cases_for_every_value_of_every_dimension(self):
        seen = [set(r['case'][i] for r in self.rows) for i in range(4)]
        self.assertEqual(seen[0], set(PLACES))
        self.assertEqual(seen[1], set(LIVES))
        self.assertEqual(seen[2], set(WORKS))
        self.assertEqual(seen[3], {False, True})
        self.assertGreater(len(self.rows), 200)

    def test_decide_agrees_with_the_oracle_in_every_case(self):
        wrong = [(r['case'], r['want'], r['decide']) for r in self.rows if r['decide'] != r['want']]
        self.assertEqual(wrong, [])

    def test_sor_claims_json_says_the_same(self):
        wrong = [(r['case'], r['want'], r['state']) for r in self.rows if r['state'] != ('held' if r['want'] == 'held' else r['want'])]
        self.assertEqual(wrong, [])

    def test_the_edit_guard_refuses_exactly_when_the_claim_stands(self):
        wrong = [(r['case'], r['want'], r['spec'], r['code']) for r in self.rows if r['spec'] != (r['want'] != 'free') or r['code'] != (r['want'] != 'free')]
        self.assertEqual(wrong, [])

    def test_sor_claim_succeeds_exactly_when_nothing_stands_and_says_what_stands(self):
        wrong = []
        for r in self.rows:
            code, said = r['claim']
            if r['want'] == 'free':
                ok = code == 0
            else:
                ok = code == 3 and {'held': 'held by', 'parked': 'parked', 'waiting': 'waiting for the merge'}[r['want']] in said
            if not ok:
                wrong.append((r['case'], r['want'], code, said[:120]))
        self.assertEqual(wrong, [])

    def test_a_takeover_works_for_a_parked_claim_and_for_nothing_else(self):
        wrong = []
        for r in self.rows:
            if r['want'] == 'free':
                self.assertIsNone(r['takeover'], r['case'])
                continue
            ok = r['takeover'][0] == (0 if r['want'] == 'parked' else 3)
            if not ok:
                wrong.append((r['case'], r['want'], r['takeover']))
        self.assertEqual(wrong, [])

    def test_no_state_with_unfinished_work_is_freed_by_the_clock_before_the_parked_window(self):
        for r in self.rows:
            place, live, work, late = r['case']
            if work in ('unfinished', 'arrived_plus_unfinished', 'partial') and not late and place in ('here', 'other'):
                if live in ('ended', 'stopped') and place == 'here':
                    continue      # the one exception: what it left is in the folder of the one who asks
                self.assertNotEqual(r['decide'], 'free', r['case'])

    def test_finished_work_that_has_not_arrived_is_held_whatever_the_time(self):
        for r in self.rows:
            place, live, work, late = r['case']
            if place == 'other' and work == 'locked' and live in GONE:
                self.assertEqual(r['decide'], 'waiting', r['case'])

    def test_a_holder_at_work_is_never_freed(self):
        for r in self.rows:
            place, live, work, late = r['case']
            if live in ('active', 'busy', 'resumed') and place != 'gone':
                self.assertEqual(r['decide'], 'held', r['case'])

    def test_every_mutant_gives_a_wrong_answer_for_at_least_one_case(self):
        """If a rule were broken, the cases would notice: this is the proof that they check something."""
        for name in MUTANTS:
            wrong = [r['case'] for r in self.rows if r['mutants'][name] != r['want']]
            self.assertTrue(wrong, f'mutant "{name}" is not caught by any case')


# --- who may edit what when a session has subagents ----------------------------------------------------------------------------------------

S, OTHER = 'ssssssss-0', 'oooooooo-9'
X, Y, Z = 'agentx1234567890', 'agenty1234567890', 'agentz1234567890'


class TestWhoMayEditWhat(flows.Flow):
    ACTORS = ('parent', 'sub_a', 'sub_unbound', 'other_session')
    HOLDERS = ('nobody', 'parent', 'sub_a', 'sub_b', 'other_session')

    def setUp(self):
        super().setUp()
        self.project({'greet': PAGE})
        write(self.dir, 'out/app.js', CODE)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        patcher = mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'})
        patcher.start()
        self.addCleanup(patcher.stop)
        for agent_id, name in ((X, 'sub-a'), (Y, 'sub-b')):
            hook.pre_bash({'tool_name': 'Bash', 'tool_input': {'command': f'sor status && sor claim greet/thanks --as {name}'}, 'session_id': S, 'agent_id': agent_id, 'cwd': self.dir})
        self.sor('release', '--all', '--as', 'sub-a', CLAUDE_CODE_SESSION_ID=S)
        self.sor('release', '--all', '--as', 'sub-b', CLAUDE_CODE_SESSION_ID=S)

    def hold(self, holder):
        name, session = {'parent': ('main', S), 'sub_a': ('sub-a', S), 'sub_b': ('sub-b', S), 'other_session': ('someone', OTHER)}[holder]
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', name, CLAUDE_CODE_SESSION_ID=session)[0], 0)

    def actor_payload(self, actor, payload):
        return {'parent': dict(payload, session_id=S), 'sub_a': dict(payload, session_id=S, agent_id=X), 'sub_unbound': dict(payload, session_id=S, agent_id=Z),
                'other_session': dict(payload, session_id=OTHER)}[actor]

    @staticmethod
    def allowed(actor, holder):
        """Who may edit a clause that `holder` holds: its own, and the parent may edit the session's; a subagent that bound no name holds nothing."""
        if holder == 'nobody':
            return True
        return {'parent': holder in ('parent', 'sub_a', 'sub_b'), 'sub_a': holder == 'sub_a', 'sub_unbound': False, 'other_session': holder == 'other_session'}[actor]

    def test_every_actor_against_every_holder_on_the_text_and_the_code(self):
        spec = os.path.join(self.spec, 'greet.md')
        wrong = []
        for actor, holder, where in itertools.product(self.ACTORS, self.HOLDERS, ('text', 'code')):
            self.sor('release', '--all', '--force', CLAUDE_CODE_SESSION_ID=S)
            self.sor('release', '--all', '--force', CLAUDE_CODE_SESSION_ID=OTHER)
            if holder != 'nobody':
                self.hold(holder)
            payload = flows.edit(spec, '{text: Hello}', '{text: Hi}') if where == 'text' else flows.edit(self.app, '"Hello"', '"Hi"')
            reason = flows.reason(hook.pre_edit(self.actor_payload(actor, payload)))
            refused = 'Someone else is working on this' in (reason or '')
            if refused == self.allowed(actor, holder):
                wrong.append((actor, holder, where, reason))
        self.assertEqual(wrong, [])

    def test_a_subagent_renews_only_its_own_and_a_parent_only_its_own(self):
        wrong = []
        for actor in ('parent', 'sub_a', 'sub_unbound'):
            self.sor('release', '--all', '--force', CLAUDE_CODE_SESSION_ID=S)
            for holder, name in (('parent', 'main'), ('sub_a', 'sub-a'), ('sub_b', 'sub-b')):
                self.assertEqual(self.sor('claim', {'parent': 'greet/thanks', 'sub_a': 'greet/hello', 'sub_b': 'greet/bye'}[holder], '--as', name, CLAUDE_CODE_SESSION_ID=S)[0], 0)
            project = Project(self.dir)
            held = claims.read(project)
            for c in held:
                c['until'] -= 20 * 60
                c['last'] -= 20 * 60
            claims._write(project, held)
            before = {c['agent']: c['until'] for c in claims.read(project)}
            hook.post_read(self.actor_payload(actor, {'tool_input': {'file_path': self.app}}))
            after = {c['agent']: c['until'] for c in claims.read(project)}
            renewed = {n for n in after if after[n] > before[n] + 60}
            want = {'parent': {'main'}, 'sub_a': {'sub-a'}, 'sub_unbound': set()}[actor]
            if renewed != want:
                wrong.append((actor, renewed, want))
        self.assertEqual(wrong, [])


# --- random sequences across two worktrees ----------------------------------------------------------------------------------------------

@unittest.skipUnless(GIT, 'git is not installed')
class TestRandomSequences(unittest.TestCase):
    """Claim, release, edit, lock, end, stop, age, take over and merge, in random order, in two folders, by three agents. After every step at most one claim stands for any
    key, the edit guard agrees with `sor claim` about what is free, and the store is valid JSON. The seeds are fixed, so a failure can be run again."""
    SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
    STEPS = 40
    CLAUSES = ('hello', 'bye', 'thanks')

    @classmethod
    def setUpClass(cls):
        cls.world = World()

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def stands(self, w):
        """The claims that stand, seen from the main folder: the ones in force that a requester there would be refused by."""
        project = Project(w.main)
        held = claims.active(project)
        return [c for c, _ in claims.standing(project, held)]

    def check_invariants(self, w, history):
        path = claims.store(Project(w.main)).file
        if os.path.exists(path):
            json.loads(read(path))
        stand = self.stands(w)
        for one, other in itertools.combinations(stand, 2):
            if one['agent'] == other['agent'] and one.get('session') == other.get('session'):
                continue
            overlap = set(one['keys']) & set(other['keys'])
            self.assertFalse(overlap, f'two claims stand for {sorted(overlap)} after {history[-6:]}: {one["agent"]} and {other["agent"]}')

    def step(self, w, rnd, history):
        agent = rnd.choice(('a', 'b', 'c'))
        session = {'a': A, 'b': B, 'c': C}[agent]
        root = rnd.choice((w.main, w.second))
        clause = rnd.choice(self.CLAUSES)
        op = rnd.choice(('claim', 'claim', 'claim', 'release', 'edit', 'lock', 'end', 'stop', 'age', 'takeover', 'merge', 'renew'))
        history.append((op, agent, 'main' if root == w.main else 'second', clause))
        if op in ('claim', 'takeover'):
            args = ['claim', f'greet/{clause}', '--as', agent] + (['--take-over'] if op == 'takeover' else [])
            w.run(root, session, *args)
        elif op == 'release':
            w.run(root, session, 'release', '--all', '--as', agent)
        elif op == 'edit':
            cur = w.current(root, clause)
            if w.run(root, session, 'status')[0] in (0, 2):
                w.edit(root, clause, cur, 'X' + cur if not cur.startswith('X') else cur[1:])
        elif op == 'lock':
            w.run(root, session, 'lock', f'greet/{clause}', '--as', agent, '--allow-incomplete')
        elif op == 'end':
            claims.mark_ended(Project(w.main), session, 'other')
        elif op == 'stop':
            w.rewrite(lambda c: c.update(stopped=time.time()) if c['agent'] == agent else None)
        elif op == 'age':
            w.age(agent, rnd.choice((HOUR, 5 * HOUR, 26 * HOUR)))
        elif op == 'merge':
            git(w.second, 'add', '-A')
            git(w.second, 'commit', '-q', '-m', 'work', check=False)
            git(w.main, 'merge', '-q', '--no-edit', 'second', check=False)
            if git(w.main, 'diff', '--name-only', '--diff-filter=U', check=False).strip():
                git(w.main, 'merge', '--abort', check=False)
        elif op == 'renew':
            claims.renew(Project(w.main), session)

    def test_the_invariants_hold_after_every_step_of_every_sequence(self):
        w = self.world
        for seed in self.SEEDS:
            w.reset()
            rnd = random.Random(seed)
            history = []
            for _ in range(self.STEPS):
                self.step(w, rnd, history)
                try:
                    self.check_invariants(w, history)
                except AssertionError as e:
                    raise AssertionError(f'seed {seed}: {e}') from None

    def test_the_guard_and_the_claim_agree_after_a_random_sequence(self):
        w = self.world
        for seed in self.SEEDS:
            w.reset()
            rnd = random.Random(1000 + seed)
            history = []
            for _ in range(self.STEPS):
                self.step(w, rnd, history)
            for clause in self.CLAUSES:
                cur = w.current(w.main, clause)
                spec = os.path.join(w.main, 'sor', 'greet.md')
                with mock.patch.dict(os.environ, {'SOR_ENFORCE_CLAIMS': '1'}):
                    refused = 'Someone else is working on this' in (flows.reason(hook.pre_edit(flows.edit(spec, '{text: %s}' % cur, '{text: Zed}', session_id='dddddddd-4'))) or '')
                code, said = w.run(w.main, 'dddddddd-4', 'claim', f'greet/{clause}', '--as', 'd')
                self.assertEqual(refused, code == 3, (seed, clause, said[:100], history[-5:]))
                w.run(w.main, 'dddddddd-4', 'release', '--all', '--as', 'd')


# --- real processes racing ----------------------------------------------------------------------------------------------------------------

@unittest.skipUnless(GIT, 'git is not installed')
class TestRacingProcesses(unittest.TestCase):
    ROUNDS = 5
    PROCESSES = 20

    @classmethod
    def setUpClass(cls):
        cls.world = World()

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def spawn(self, root, n, ids, extra=()):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CLAUDE_CODE_SESSION_ID=f'race{n:04d}-x')
        for name in ('SOR_ENFORCE_CLAIMS', 'SOR_AGENT'):
            env.pop(name, None)
        return subprocess.Popen([sys.executable, SOR, '-C', root, 'claim', *ids, '--as', f'agent{n}', *extra], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_twenty_processes_across_two_worktrees_exactly_one_gets_the_clause(self):
        w = self.world
        for round_ in range(self.ROUNDS):
            w.reset()
            procs = [self.spawn(w.main if n % 2 else w.second, n, ['greet/hello']) for n in range(self.PROCESSES)]
            codes = []
            for p in procs:
                out, err = p.communicate(timeout=120)
                codes.append(p.returncode)
            self.assertEqual(sorted(codes), [0] + [3] * (self.PROCESSES - 1), (round_, codes))
            path = claims.store(Project(w.main)).file
            data = json.loads(read(path))      # valid JSON after all of it
            standing = [c for c in data['claims'] if not c.get('freed')]
            self.assertEqual(len(standing), 1, [c['agent'] for c in standing])
            self.assertEqual(standing[0]['asked'], ['greet/hello'])

    def test_twenty_requesters_for_a_clause_whose_holder_ended_and_left_nothing_one_gets_it_and_it_is_freed_once(self):
        w = self.world
        for round_ in range(self.ROUNDS):
            w.reset()
            self.assertEqual(w.run(w.second, A, 'claim', 'greet/hello', '--as', 'a')[0], 0)
            claims.mark_ended(Project(w.main), A, 'other')
            procs = [self.spawn(w.main if n % 2 else w.second, n, ['greet/hello']) for n in range(self.PROCESSES)]
            codes = [(p.communicate(timeout=120), p.returncode)[1] for p in procs]
            self.assertEqual(sorted(codes), [0] + [3] * (self.PROCESSES - 1), (round_, codes))
            records = json.loads(read(claims.store(Project(w.main)).file))['claims']
            self.assertEqual([c['agent'] for c in records if c.get('freed')], ['a'])      # the holder's claim was freed once, by the one that got the clause
            self.assertEqual(len([c for c in records if not c.get('freed')]), 1)

    def test_several_takers_of_one_parked_claim_exactly_one_takes_it_over(self):
        w = self.world
        for round_ in range(self.ROUNDS):
            w.reset()
            self.assertEqual(w.run(w.second, A, 'claim', 'greet/hello', '--as', 'a')[0], 0)
            w.edit(w.second, 'hello', 'Hello', 'Hi')      # unfinished work in its worktree
            claims.mark_ended(Project(w.main), A, 'other')
            procs = [self.spawn(w.main, n, ['greet/hello'], extra=('--take-over',)) for n in range(8)]
            codes = [(p.communicate(timeout=120), p.returncode)[1] for p in procs]
            self.assertEqual(sorted(codes), [0] + [3] * 7, (round_, codes))
            records = json.loads(read(claims.store(Project(w.main)).file))['claims']
            (taker,) = [c for c in records if not c.get('freed')]
            self.assertEqual(taker['took_over'][0]['agent'], 'a')
            self.assertEqual(os.path.realpath(taker['where']['path']), os.path.realpath(w.second))      # and the work stays where it is

    def test_overlapping_claims_race_and_at_most_one_of_two_overlapping_ones_wins(self):
        w = self.world
        for round_ in range(self.ROUNDS):
            w.reset()
            asks = [['greet'], ['greet/hello'], ['greet/bye'], ['greet/hello', 'greet/thanks'], ['greet/test:hello'], ['greet/thanks']]
            procs = [self.spawn(w.main if n % 2 else w.second, n, asks[n % len(asks)]) for n in range(12)]
            for p in procs:
                p.communicate(timeout=120)
            held = [c for c in json.loads(read(claims.store(Project(w.main)).file))['claims'] if not c.get('freed')]
            for one, other in itertools.combinations(held, 2):
                self.assertFalse(set(one['keys']) & set(other['keys']), (round_, one['asked'], other['asked']))
            self.assertGreaterEqual(len(held), 1)

    def test_a_holder_whose_record_changes_between_the_look_and_the_mutex_makes_the_claim_look_again(self):
        w = self.world
        w.reset()
        self.assertEqual(w.run(w.second, A, 'claim', 'greet/hello', '--as', 'a')[0], 0)
        claims.mark_ended(Project(w.main), A, 'other')      # gone, and nothing left: the look says free
        real = claims.decide
        looks = []

        def renew_then_decide(project, c, *args, **kw):
            result = real(project, c, *args, **kw)
            looks.append(result.kind)
            if len(looks) == 1:
                claims.renew(Project(w.main), A)      # the holder resumes between the look and the mutex
            return result

        with mock.patch.object(claims, 'decide', renew_then_decide):
            code, said = w.run(w.main, B, 'claim', 'greet/hello', '--as', 'b')
        self.assertEqual(looks[0], 'free')
        self.assertGreaterEqual(len(looks), 2, 'the claim took no second look')
        self.assertEqual(looks[-1], 'held')
        self.assertEqual(code, 3, said)
        self.assertEqual(len([c for c in w.records('a') if not c.get('freed')]), 1)      # the holder kept its claim

    def test_a_process_killed_while_it_holds_the_mutex_blocks_nobody(self):
        if not claims.fcntl:
            self.skipTest('needs fcntl')
        w = self.world
        w.reset()
        mutex = claims.store(Project(w.main)).mutex
        os.makedirs(os.path.dirname(mutex), exist_ok=True)
        holder = subprocess.Popen([sys.executable, '-c', 'import fcntl, os, sys, time\nfd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT)\nfcntl.flock(fd, fcntl.LOCK_EX)\nprint("held", flush=True)\ntime.sleep(60)', mutex],
                                  stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), 'held')
        holder.kill()
        holder.wait()
        self.assertEqual(w.run(w.main, B, 'claim', 'greet/hello', '--as', 'b')[0], 0)


if __name__ == '__main__':
    unittest.main()
