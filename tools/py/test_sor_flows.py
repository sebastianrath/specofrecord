"""Tests for the flows of the `sor` tool that test_sor.py does not reach: the edit and read hooks, claims,
`sor lock`, the design export, `sor test` without a browser, the `.tests.md` files and
`plugins/sync-tools.sh`.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. No browser, no network, no sleeps (a clock is moved by editing the
`until` of a claim, a wait by patching a constant). Every project lives in a temporary folder; the real
projects are never touched. The environment is cleared of everything that says who is running the tool
(CLAUDE_CODE_SESSION_ID, SOR_AGENT, the enforce flag, the Chrome path), because the suite runs inside Claude
Code sessions and in plain terminals alike; a test that needs one of them sets it itself.

Not covered, because it cannot be done here: a real Chrome run (`sor test` against a browser), Windows paths
and file locking, and the tool run as root (chmod does not stop root, so those tests skip themselves).
"""
import glob
import json
import os
import shutil
import stat
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

import test_sor as base                          # noqa: E402  (its helpers only)
from sorlib import claims, cli, hook, lint, testrun    # noqa: E402
from sorlib import lock as lockfile              # noqa: E402
from sorlib.markers import Scan                  # noqa: E402
from sorlib.model import Project                 # noqa: E402

doc, write, read, tree = base.doc, base.write, base.read, base.tree
run_sor, run_hook = base.run_sor, base.run_hook

ENV = ('CLAUDE_CODE_SESSION_ID', 'SOR_AGENT', 'SOR_ENFORCE_CLAIMS', 'SOR_CHROME')
CAN_CHMOD = os.name != 'nt' and (not hasattr(os, 'geteuid') or os.geteuid() != 0)   # root ignores file modes

GREET = doc('Greet', 'Says hello.',
            rules=['- **hello** - The page says {text: Hello}.', '- **bye** - The page says {text: Bye}.'],
            tests=['- **hello** - says hello.', '  expect: ok'])
APP = ('// @clause glue\n"use strict";\n// @clause end\n'          # lines 1-3
       '// @clause greet/hello\nconsole.log("Hello");\n// @clause end\n'   # lines 4-6
       '// @clause greet/bye\nconsole.log("Bye");\n// @clause end\n')       # lines 7-9


def accepted(root):
    """Writes the lock for the files as they are, with every test passed: the state `sor lock` leaves."""
    project = Project(root)
    entries = lockfile.snapshot(project, Scan(project))
    for entry in entries.values():
        if entry.get('kind') == 'test' and entry['result'] == 'none':
            entry['result'] = 'pass'
    lockfile.write(project, entries)
    return project


def lock_bytes(root):
    with open(os.path.join(root, 'sor', 'sor-lock.json'), 'rb') as fh:
        return fh.read()


def replace_in(path, old, new):
    text = read(path)
    assert old in text, (old, path)
    with open(path, 'w', encoding='utf8', newline='') as fh:
        fh.write(text.replace(old, new))


def edit(path, old, new, tool='Edit', **extra):
    """The payload Claude Code sends a hook for an Edit."""
    return dict({'tool_name': tool, 'tool_input': {'file_path': path, 'old_string': old, 'new_string': new}}, **extra)


def reason(result):
    """The refusal text of a hook answer, or None when it lets the edit through."""
    if not result:
        return None
    out = result['hookSpecificOutput']
    assert out['permissionDecision'] == 'deny', out
    return out['permissionDecisionReason']


class Flow(base.Case):
    """A temporary folder and an environment that says nobody is running the tool."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ENV:
            os.environ.pop(name, None)
        self.spec = os.path.join(self.dir, 'sor')
        self.app = os.path.join(self.dir, 'out', 'app.js')

    def greet_project(self, lock=True, extra=None):
        """sor/SPECOFRECORD.md, sor/greet.md and out/app.js, locked with every test passed."""
        self.project(dict({'greet': GREET}, **(extra or {})))
        write(self.dir, 'out/app.js', APP)
        return accepted(self.dir) if lock else Project(self.dir)

    def sor(self, *args, **env):
        with mock.patch.dict(os.environ, env):
            return run_sor(self.dir, *args)

    def claim(self, ids, agent, session='', ttl=claims.DEFAULT_TTL):
        project = Project(self.dir)
        scan = Scan(project)
        return claims.claim(project, scan, set(lockfile.snapshot(project, scan)), ids, agent, ttl, session)

    def expire(self, when=None):
        """Moves every claim to the past (or to `when`), as if the time had gone by."""
        path = os.path.join(self.spec, '.sor-claims.json')
        data = json.loads(read(path))
        for c in data['claims']:
            c['until'] = time.time() - 5 if when is None else when
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))

    def claims_file(self):
        path = os.path.join(self.spec, '.sor-claims.json')
        return json.loads(read(path))['claims'] if os.path.exists(path) else []


# --- the edit hook ------------------------------------------------------------------------------------------

class TestPreEditHook(Flow):
    def setUp(self):
        super().setUp()
        self.greet_project()

    def test_the_lock_and_the_claims_file_are_never_edited_by_hand(self):
        for name in ('sor-lock.json', '.sor-claims.json'):
            said = reason(hook.pre_edit(edit(os.path.join(self.spec, name), 'a', 'b')))
            self.assertIn(name, said)
            self.assertIn('sor', said)

    def test_a_spec_file_is_not_rewritten_with_write_but_a_new_one_may_be_written(self):
        existing = os.path.join(self.spec, 'greet.md')
        said = reason(hook.pre_edit({'tool_name': 'Write', 'tool_input': {'file_path': existing, 'content': 'x'}}))
        self.assertIn('Do not rewrite', said)
        fresh = os.path.join(self.spec, 'new.md')
        self.assertIsNone(hook.pre_edit({'tool_name': 'Write', 'tool_input': {'file_path': fresh, 'content': 'x'}}))

    def test_a_clause_may_be_edited_first(self):
        path = os.path.join(self.spec, 'greet.md')
        self.assertIsNone(hook.pre_edit(edit(path, '{text: Hello}', '{text: Hi}')))

    def test_code_whose_clause_did_not_change_is_refused_and_the_message_names_the_clause(self):
        said = reason(hook.pre_edit(edit(self.app, '"Hello"', '"Hi"')))
        self.assertIn('Clauses come first', said)
        self.assertIn('greet/hello', said)
        self.assertIn('sor/greet.md', said)

    def test_the_same_edit_passes_once_its_clause_changed(self):
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        self.assertIsNone(hook.pre_edit(edit(self.app, '"Hello"', '"Hi"')))

    def test_a_changed_clause_frees_only_its_own_code(self):
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        said = reason(hook.pre_edit(edit(self.app, '"Bye"', '"Ciao"')))
        self.assertIn('greet/bye', said)

    def test_new_code_outside_every_region_is_refused(self):
        said = reason(hook.pre_edit(edit(self.app, '// @clause end\n// @clause greet/hello',
                                         '// @clause end\nconsole.log("x");\n// @clause greet/hello')))
        self.assertIn('unmarked', said)

    def test_a_marker_naming_a_clause_that_does_not_exist_is_refused(self):
        said = reason(hook.pre_edit(edit(self.app, '// @clause greet/bye', '// @clause greet/nothing')))
        self.assertIn('marker', said)
        self.assertIn('add the clause first', said)

    def test_a_marker_that_breaks_the_shape_of_the_regions_is_told_to_close_them_and_not_to_add_a_clause(self):
        """Only the markers change here, so the refusal is the marker problem alone; `add the clause first` is for an id nobody wrote."""
        said = reason(hook.pre_edit(edit(self.app, '"Hello");\n// @clause end\n', '"Hello");\n')))
        self.assertIn('regions never nest', said)
        self.assertIn('close every region with `@clause end`', said)
        self.assertNotIn('add the clause first', said)

    def test_wiring_may_not_change_while_no_clause_is_being_built(self):
        said = reason(hook.pre_edit(edit(self.app, '"use strict"', '"use asm"')))
        self.assertIn('glue changed', said)

    def test_wiring_may_change_while_a_clause_is_being_built(self):
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        self.assertIsNone(hook.pre_edit(edit(self.app, '"use strict"', '"use asm"')))

    def test_a_multiedit_is_judged_as_one_change(self):
        payload = {'tool_name': 'MultiEdit', 'tool_input': {'file_path': self.app, 'edits': [
            {'old_string': '"Hello"', 'new_string': '"Hi"'}, {'old_string': '"Bye"', 'new_string': '"Ciao"'}]}}
        said = reason(hook.pre_edit(payload))
        self.assertIn('greet/hello', said)
        self.assertIn('greet/bye', said)

    def test_an_edit_that_cannot_apply_is_left_to_fail_on_its_own(self):
        self.assertIsNone(hook.pre_edit(edit(self.app, 'text that is not there', 'x')))
        payload = {'tool_name': 'MultiEdit', 'tool_input': {'file_path': self.app, 'edits': [
            {'old_string': '"Hello"', 'new_string': '"Hi"'}, {'old_string': 'missing', 'new_string': 'x'}]}}
        self.assertIsNone(hook.pre_edit(payload))

    def test_files_outside_the_project_and_files_that_are_not_code_pass(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        outside = write(other.name, 'notes.js', 'x\n')
        self.assertIsNone(hook.pre_edit(edit(outside, 'x', 'y')))
        self.assertIsNone(hook.pre_edit(edit(os.path.join(self.dir, 'README.md'), 'x', 'y')))
        self.assertIsNone(hook.pre_edit({'tool_name': 'Edit', 'tool_input': {}}))

    def test_nothing_is_refused_before_the_first_lock(self):
        os.remove(os.path.join(self.spec, 'sor-lock.json'))
        self.assertIsNone(hook.pre_edit(edit(self.app, '"Hello"', '"Hi"')))

    def test_a_path_through_a_symlink_or_dots_is_judged_like_the_real_one(self):
        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)
        link = os.path.join(elsewhere.name, 'project')
        os.symlink(self.dir, link)
        for path in (os.path.join(link, 'out', 'app.js'), os.path.join(self.dir, 'out', '..', 'out', 'app.js')):
            self.assertIn('Clauses come first', reason(hook.pre_edit(edit(path, '"Hello"', '"Hi"'))), path)

    def test_every_refusal_the_hook_makes_contains_a_phrase_the_skill_lists(self):
        listed = ('Clauses come first', 'Someone else is working on this', 'Do not rewrite', 'is written only by', 'is in lock format')
        skill = read(os.path.join(REPO, 'plugins', 'specofrecord', 'skills', 'specofrecord', 'SKILL.md'))
        for phrase in listed:
            self.assertIn(phrase, skill, 'the skill must tell an agent what a refusal looks like')
        os.environ['SOR_ENFORCE_CLAIMS'] = '1'
        self.claim(['greet/bye'], 'alice', session='A')
        spec = os.path.join(self.spec, 'greet.md')
        refusals = [
            hook.pre_edit(edit(os.path.join(self.spec, 'sor-lock.json'), 'a', 'b')),
            hook.pre_edit(edit(os.path.join(self.spec, '.sor-claims.json'), 'a', 'b')),
            hook.pre_edit({'tool_name': 'Write', 'tool_input': {'file_path': spec, 'content': 'x'}}),
            hook.pre_edit(edit(self.app, '"Hello"', '"Hi"')),
            hook.pre_edit(dict(edit(spec, '{text: Bye}', '{text: Ciao}'), session_id='B')),
        ]
        for result in refusals:
            said = reason(result)
            self.assertTrue(any(p in said for p in listed), said[:90])
        lock = os.path.join(self.spec, 'sor-lock.json')   # and a lock this copy of the tool cannot read
        write(self.dir, 'sor/sor-lock.json', read(lock).replace('{\n', '{\n"*format": 99,\n', 1))
        said = reason(hook.pre_edit(edit(self.app, '"Hello"', '"Hi"')))
        self.assertTrue(any(p in said for p in listed), said[:90])

    def test_run_as_a_program_it_answers_on_stdout_and_never_blocks_on_its_own_failure(self):
        code, out, err = run_hook('pre-edit', edit(self.app, '"Hello"', '"Hi"'))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['hookSpecificOutput']['permissionDecision'], 'deny')
        code, out, err = run_hook('pre-edit', edit(self.app, 'text that is not there', 'x'))
        self.assertEqual((code, out), (0, ''))
        done = subprocess.run([sys.executable, base.SOR, 'hook', 'pre-edit'], input='this is not json', cwd=REPO,
                              capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, '')
        self.assertIn('sor hook pre-edit failed', done.stderr)


class TestFixAgainstAProvingTest(Flow):
    """SPEC §8: a test proves the item it is named after and every item its `expect:` or `measure:` refers to.
    A bug fix may add such a second test and leave the first one as it is; the guard, `sor status` and a
    scoped lock all see that test as one of the item's own."""

    REGRESSION = ['- **hello-twice** - saying hello twice shows it once.', '  do: say(Hello) · say(Hello)',
                  '  expect: page = {hello.text}', '  bug: PROJ-1']

    def setUp(self):
        super().setUp()
        self.greet_project()
        self.part = os.path.join(self.spec, 'greet.md')

    def add_test(self, lines):
        replace_in(self.part, '  expect: ok\n', '  expect: ok\n' + '\n'.join(lines) + '\n')

    def fix(self):
        return edit(self.app, '"Hello"', '"Hi"')

    def test_a_new_test_whose_expect_refers_to_a_value_of_the_item_frees_its_code(self):
        self.add_test(self.REGRESSION)
        self.assertIsNone(hook.pre_edit(self.fix()))

    def test_a_second_scenario_and_a_second_bug_line_on_the_items_own_test_free_its_code(self):
        replace_in(self.part, '  expect: ok\n', '  expect: ok\n  do: say(Hello) - say(Hello)\n  expect: ok\n  bug: PROJ-1\n  bug: #7\n')
        self.assertIsNone(hook.pre_edit(self.fix()))
        replace_in(self.app, '"Hello"', '"Hi"')
        out = self.sor('status')[1]
        self.assertIn('fixing', out)
        changes = self.sor('changes')[1]
        self.assertIn('PROJ-1', changes)
        self.assertIn('#7', changes)

    def test_a_new_test_whose_expect_refers_to_a_table_row_of_the_item_frees_its_code(self):
        table = ['- **planets** - The planets:', '', '| Planet | Size |', '|---|---|', '| Mars | 5 |', '| Venus | 12 |']
        self.project({'bodies': doc('Bodies', 'The sky.', rules=table, tests=['- **planets** - eight of them.', '  expect: ok'])})
        write(self.dir, 'out/app.js', '// @clause bodies/planets\nconst planets = [5, 12];\n// @clause end\n')
        accepted(self.dir)
        spec = os.path.join(self.spec, 'bodies.md')
        replace_in(spec, '  expect: ok\n', '  expect: ok\n- **mars** - Mars is five.\n  expect: size = {planets/Mars.size}\n  bug: PROJ-3\n')
        self.assertIsNone(hook.pre_edit(edit(self.app, '[5, 12]', '[5, 12, 3]')))

    def test_a_new_test_in_another_part_that_refers_to_the_item_frees_its_code(self):
        self.project({'greet': GREET, 'tour': doc('Tour', 'A walk.', rules=['- **walk** - Walks.'],
                                                  tests=['- **walk** - walks.', '  expect: ok'])})
        write(self.dir, 'out/app.js', APP)
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'tour.md'), '  expect: ok\n',
                   '  expect: ok\n- **tour-greets** - the tour starts with the greeting.\n  expect: page = {greet/hello.text}\n  bug: PROJ-4\n')
        self.assertIsNone(hook.pre_edit(self.fix()))

    def test_it_frees_only_the_code_of_the_items_it_proves(self):
        self.add_test(self.REGRESSION)
        said = reason(hook.pre_edit(edit(self.app, '"Bye"', '"Ciao"')))
        self.assertIn('greet/bye', said)

    def test_a_test_that_only_uses_the_value_as_an_input_frees_nothing(self):
        self.add_test(['- **hello-twice** - saying hello twice shows it once.', '  do: say({hello.text})',
                       '  expect: ok', '  bug: PROJ-1'])
        self.assertIn('greet/hello', reason(hook.pre_edit(self.fix())))

    def test_a_test_that_proves_another_item_frees_nothing(self):
        self.add_test(['- **bye-twice** - saying bye twice shows it once.', '  expect: page = {bye.text}', '  bug: PROJ-2'])
        self.assertIn('greet/hello', reason(hook.pre_edit(self.fix())))

    def test_a_test_that_was_already_locked_frees_nothing(self):
        self.add_test(self.REGRESSION)
        accepted(self.dir)
        self.assertIn('greet/hello', reason(hook.pre_edit(self.fix())))

    def test_the_refusal_says_which_kind_of_test_helps(self):
        said = reason(hook.pre_edit(self.fix()))
        self.assertIn("own test another `do:` / `expect:` pair and a `bug:` line", said)
        self.assertIn('a second test with `proves: {clause}` and a `bug:` line', said)

    def test_status_calls_the_edited_code_fixing_and_not_drift(self):
        self.add_test(self.REGRESSION)
        replace_in(self.app, '"Hello"', '"Hi"')
        out = self.sor('status')[1]
        self.assertIn('fixing', out)
        self.assertIn('its test changed first', out)
        self.assertNotIn('drift', out)

    def test_a_test_that_did_not_pass_at_the_last_lock_also_makes_the_code_fixing(self):
        self.add_test(['- **hello-twice** - saying hello twice shows it once.', '  expect: page = {hello.text}',
                       '  bug: PROJ-1 open'])
        project = Project(self.dir)
        entries = lockfile.snapshot(project, Scan(project))
        for k, e in entries.items():
            if e.get('kind') == 'test':
                e['result'] = 'fail' if k.endswith('hello-twice') else 'pass'
        lockfile.write(project, entries)
        self.assertIsNone(hook.pre_edit(self.fix()))
        replace_in(self.app, '"Hello"', '"Hi"')
        self.assertIn('its test did not pass at the last lock', self.sor('status')[1])

    def test_a_test_of_another_item_that_failed_at_the_last_lock_does_not_keep_this_code_free(self):
        # `bye` proves bye and mentions hello's value in passing; it failed at the last lock (an open bug of bye)
        replace_in(self.part, '  expect: ok\n', '  expect: ok\n- **bye** - says bye.\n  expect: page = {hello.text}\n  bug: PROJ-9 open\n')
        project = Project(self.dir)
        entries = lockfile.snapshot(project, Scan(project))
        for k, e in entries.items():
            if e.get('kind') == 'test':
                e['result'] = 'fail' if k.endswith('test:bye') else 'pass'
        lockfile.write(project, entries)
        self.assertIn('greet/hello', reason(hook.pre_edit(self.fix())))
        self.assertIsNone(hook.pre_edit(edit(self.app, '"Bye"', '"Ciao"')))   # its own item is free, as before

    def test_a_scoped_lock_takes_the_new_test_with_the_item(self):
        self.add_test(self.REGRESSION)
        replace_in(self.app, '"Hello"', '"Hi"')
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass', 'greet/test:hello-twice': 'pass'}))
        code, out, _ = self.sor('lock', 'greet/hello', '--results', results)
        self.assertEqual(code, 0, out)
        self.assertNotIn('still pending', out)
        entries = json.loads(lock_bytes(self.dir))
        self.assertEqual(entries['greet/test:hello-twice']['result'], 'pass')
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])

    def test_a_scoped_lock_leaves_a_new_test_of_another_item_pending(self):
        self.add_test(['- **bye-twice** - saying bye twice shows it once.', '  expect: page = {bye.text}', '  bug: PROJ-2'])
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass'}))
        self.assertEqual(self.sor('lock', 'greet/hello', '--results', results)[0], 0)
        self.assertIn('greet/test:bye-twice', self.sor('status')[1])

    def test_a_check_still_asks_for_bug_on_a_test_that_proves_nothing(self):
        self.add_test(['- **hello-twice** - saying hello twice shows it once.', '  expect: ok'])
        self.assertIn('orphan test', [p.kind for p in Project(self.dir).check()])


class TestProvesLine(Flow):
    """`proves: {clause}` on a test says what it proves, for a clause that has no value or row to refer to (SPEC §8).
    It is read as a reference, so the lock records it, a changed clause makes the test stale, and a broken one is
    reported; everything that asks what a test proves (guard, status, scoped lock, coverage, `sor test`) asks one function."""

    SPLIT = ['- **hello-twice** - saying hello twice shows it once.', '  proves: {hello}', '  do: say(Hello) · say(Hello)',
             '  expect: page contains "Hello"']

    def setUp(self):
        super().setUp()
        self.greet_project()
        self.part = os.path.join(self.spec, 'greet.md')
        self.original = read(self.part)

    def add_test(self, lines):
        replace_in(self.part, '  expect: ok\n', '  expect: ok\n' + '\n'.join(lines) + '\n')

    def only(self, lines):
        """The part as it was, with these lines after its test and nothing else added."""
        write(self.dir, 'sor/greet.md', self.original)
        self.add_test(lines)

    def problems(self):
        return [(p.kind, p.text) for p in Project(self.dir).check()]

    def kinds(self):
        return [k for k, _ in self.problems()]

    def test_a_split_test_with_proves_needs_no_bug_line_and_is_not_a_problem(self):
        self.add_test(self.SPLIT)
        self.assertEqual(self.problems(), [])

    def test_a_test_named_after_nothing_needs_proves_or_bug_and_the_message_says_both(self):
        self.add_test(['- **hello-twice** - x.', '  expect: ok'])
        found = [t for k, t in self.problems() if k == 'orphan test']
        self.assertEqual(len(found), 1)
        self.assertIn('proves: {item}', found[0])
        self.assertIn('bug:', found[0])

    def test_proves_frees_the_code_of_a_clause_without_values_and_only_that_one(self):
        self.add_test(['- **hello-twice** - x.', '  proves: {bye}', '  expect: ok'])
        self.assertIsNone(hook.pre_edit(edit(self.app, '"Bye"', '"Ciao"')))
        self.assertIn('greet/hello', reason(hook.pre_edit(edit(self.app, '"Hello"', '"Hi"'))))

    def test_status_calls_the_edited_code_fixing_and_the_scoped_lock_takes_the_test(self):
        self.add_test(self.SPLIT)
        replace_in(self.app, '"Hello"', '"Hi"')
        self.assertIn('fixing', self.sor('status')[1])
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass', 'greet/test:hello-twice': 'pass'}))
        code, out, _ = self.sor('lock', 'greet/hello', '--results', results)
        self.assertEqual(code, 0, out)
        self.assertNotIn('still pending', out)
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])

    def test_the_line_after_an_expect_does_not_become_part_of_it(self):
        self.project({'targets/web': TARGET, 'greet': GREET})
        replace_in(self.part, '  expect: ok\n', '  expect: ok\n- **hello-twice** - x.\n  expect: paused is false\n  proves: {hello}\n')
        project = Project(self.dir)
        t = testrun.Test(project, testrun.web_targets(project)[0], project.items['greet/test:hello-twice'])
        self.assertEqual(t.steps, [('expect', 'paused is false'), ('proves', '{hello}')])

    def test_a_changed_clause_makes_the_test_stale_and_a_changed_proves_line_makes_it_changed(self):
        self.add_test(self.SPLIT)
        accepted(self.dir)
        replace_in(self.part, 'The page says {text: Hello}.', 'The page says {text: Hello} twice.')
        out = self.sor('status')[1]
        self.assertIn('stale', out)
        self.assertIn('greet/test:hello-twice', out)
        accepted(self.dir)
        replace_in(self.part, '  proves: {hello}\n', '  proves: {bye}\n')
        self.assertRegex(self.sor('status')[1], r'changed\s+greet/test:hello-twice')

    def test_then_and_should_count_like_expect_for_what_a_test_proves(self):
        self.add_test(['- **a** - x.', '  then: page = {hello.text}', '  bug: P-1',
                       '- **b** - y.', '  should: page = {bye.text}', '  bug: P-2'])
        project = Project(self.dir)
        self.assertEqual(project.proves(project.items['greet/test:a']), {'greet/hello'})
        self.assertEqual(project.proves(project.items['greet/test:b']), {'greet/bye'})

    def test_a_wrapped_expect_line_still_counts(self):
        self.add_test(['- **a** - x.', '  expect: page =', '    {hello.text}', '  bug: P-1'])
        project = Project(self.dir)
        self.assertEqual(project.proves(project.items['greet/test:a']), {'greet/hello'})

    def test_proves_that_names_a_value_a_part_or_nothing_is_a_problem(self):
        cases = {'{hello.text}': 'is a value', '{greet}': 'is a part', '{nosuch}': 'broken'}
        for ref, said in cases.items():
            with self.subTest(ref=ref):
                self.only(['- **hello-twice** - x.', f'  proves: {ref}', '  expect: ok'])
                found = [f'{k} {t}' for k, t in self.problems()]
                self.assertTrue(any(said in f for f in found), (ref, found))

    def test_proves_may_name_a_table_row_and_means_its_table(self):
        self.project({'bodies': doc('Bodies', 'The sky.', rules=['- **planets** - The planets:', '', '| Planet | Size |', '|---|---|',
                                                                    '| Mars | 5 |'], tests=['- **planets** - there.', '  expect: ok'])})
        replace_in(os.path.join(self.spec, 'bodies.md'), '  expect: ok\n', '  expect: ok\n- **mars-split** - x.\n  proves: {planets/Mars}\n  expect: ok\n')
        project = Project(self.dir)
        self.assertEqual([p.kind for p in project.check()], [])
        self.assertEqual(project.proves(project.items['bodies/test:mars-split']), {'bodies/planets'})

    def test_proves_without_a_reference_is_a_problem_that_shows_the_form(self):
        self.add_test(['- **hello-twice** - x.', '  proves: hello', '  expect: ok'])
        found = [t for k, t in self.problems() if k == 'proves']
        self.assertEqual(len(found), 1)
        self.assertIn('proves: {hello-twice}', found[0])

    def test_proves_on_a_rule_is_a_problem(self):
        replace_in(self.part, 'The page says {text: Bye}.\n', 'The page says {text: Bye}.\n  proves: {hello}\n')
        self.assertIn('proves', self.kinds())

    def test_an_expect_that_is_only_a_reference_is_a_problem_that_points_to_proves(self):
        for word in ('expect', 'then', 'should', 'shows'):
            with self.subTest(word=word):
                self.only(['- **hello-twice** - x.', f'  {word}: {{hello}}', '  bug: P-1'])
                found = [t for k, t in self.problems() if k == 'expect']
                self.assertEqual(len(found), 1, word)
                self.assertIn('proves: {hello}', found[0])

    def test_an_expect_that_compares_a_reference_is_fine(self):
        self.add_test(['- **hello-twice** - x.', '  expect: page = {hello.text}', '  bug: P-1'])
        self.assertEqual(self.problems(), [])

    def test_a_failing_test_that_says_proves_keeps_the_code_free_even_when_named_after_another_item(self):
        replace_in(self.part, '  expect: ok\n', '  expect: ok\n- **bye** - says bye.\n  proves: {hello}\n  expect: page = {bye.text}\n')
        project = Project(self.dir)
        entries = lockfile.snapshot(project, Scan(project))
        for k, e in entries.items():
            if e.get('kind') == 'test':
                e['result'] = 'fail' if k.endswith('test:bye') else 'pass'
        lockfile.write(project, entries)
        self.assertIsNone(hook.pre_edit(edit(self.app, '"Hello"', '"Hi"')))

    def test_sor_test_with_a_clause_runs_the_tests_that_prove_it(self):
        self.project({'targets/web': TARGET, 'greet': GREET})
        self.add_test(self.SPLIT)
        project = Project(self.dir)
        split = project.items['greet/test:hello-twice']
        self.assertTrue(testrun.selects(project, split, ['greet/hello']))
        self.assertFalse(testrun.selects(project, split, ['greet/bye']))

    def test_show_prints_every_test_that_proves_the_clause(self):
        self.add_test(self.SPLIT)
        out = self.sor('show', 'greet/hello')[1]
        self.assertIn('**hello** - says hello.', out)
        self.assertIn('**hello-twice**', out)
        self.assertIn('proves: {hello}', out)


class TestEditGuardAndClaims(Flow):
    """SOR_ENFORCE_CLAIMS=1: the hook refuses an edit to what another session holds (SPEC §16)."""

    def setUp(self):
        super().setUp()
        self.greet_project()
        os.environ['SOR_ENFORCE_CLAIMS'] = '1'
        self.clause_edit = edit(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')

    def with_session(self, payload, session):
        return dict(payload, session_id=session)

    def test_another_session_is_refused_and_told_who_holds_it(self):
        self.assertTrue(self.claim(['greet/hello'], 'alice', session='A')[0])
        said = reason(hook.pre_edit(self.with_session(self.clause_edit, 'B')))
        self.assertIn('Someone else is working on this', said)
        self.assertIn('alice', said)
        self.assertIn('greet/hello', said)

    def test_the_holders_own_session_passes_whatever_name_it_claimed_under(self):
        self.claim(['greet/hello'], 'sub-agent-1', session='A')
        self.assertIsNone(hook.pre_edit(self.with_session(self.clause_edit, 'A')))

    def test_without_a_session_id_nobody_can_be_told_apart_so_the_edit_passes(self):
        self.claim(['greet/hello'], 'alice', session='A')
        self.assertIsNone(hook.pre_edit(self.clause_edit))

    def test_a_claim_nobody_enforces_is_only_advice(self):
        self.claim(['greet/hello'], 'alice', session='A')
        del os.environ['SOR_ENFORCE_CLAIMS']
        self.assertIsNone(hook.pre_edit(self.with_session(self.clause_edit, 'B')))

    def test_another_clause_is_free(self):
        self.claim(['greet/hello'], 'alice', session='A')
        other = edit(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}')
        self.assertIsNone(hook.pre_edit(self.with_session(other, 'B')))

    def test_a_claim_made_at_a_terminal_blocks_every_agent(self):
        self.claim(['greet/hello'], 'sebastian', session='')
        self.assertIn('sebastian', reason(hook.pre_edit(self.with_session(self.clause_edit, 'A'))))

    def test_an_expired_claim_blocks_nobody(self):
        self.claim(['greet/hello'], 'alice', session='A')
        self.expire()
        self.assertIsNone(hook.pre_edit(self.with_session(self.clause_edit, 'B')))

    def test_the_code_of_a_held_clause_is_held_too(self):
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        self.claim(['greet/hello'], 'alice', session='A')
        code = edit(self.app, '"Hello"', '"Hi"')
        self.assertIn('alice', reason(hook.pre_edit(self.with_session(code, 'B'))))
        self.assertIsNone(hook.pre_edit(self.with_session(code, 'A')))

    def test_a_part_claim_holds_its_clauses(self):
        self.claim(['greet'], 'alice', session='A')
        self.assertIn('alice', reason(hook.pre_edit(self.with_session(self.clause_edit, 'B'))))

    def test_the_claims_file_is_still_not_editable_by_the_holder(self):
        self.claim(['greet'], 'alice', session='A')
        path = os.path.join(self.spec, '.sor-claims.json')
        self.assertIn('.sor-claims.json', reason(hook.pre_edit(self.with_session(edit(path, 'a', 'b'), 'A'))))


# --- the read hook ------------------------------------------------------------------------------------------

class TestPostReadHook(Flow):
    def setUp(self):
        super().setUp()
        self.greet_project()

    def read(self, path=None, **tool_input):
        out = hook.post_read({'tool_input': dict(file_path=path or self.app, **tool_input)})
        return out and out['hookSpecificOutput']['additionalContext']

    def test_reading_code_shows_the_clauses_behind_it(self):
        said = self.read()
        self.assertIn('built from the clauses in sor/', said)
        self.assertIn('lines 4-6 serve greet/hello', said)
        self.assertIn('The page says {text: Hello}', said)
        self.assertIn('lines 7-9 serve greet/bye', said)

    def test_the_lines_read_choose_the_clauses_shown(self):
        said = self.read(offset=7, limit=3)
        self.assertIn('greet/bye', said)
        self.assertNotIn('greet/hello', said)
        self.assertNotIn('lines 4-6', self.read(offset=7))

    def test_a_range_without_a_clause_says_nothing(self):
        write(self.dir, 'out/plain.js', 'x\n' * 10 + '// @clause greet/hello\ny\n// @clause end\n')
        accepted(self.dir)
        self.assertIsNone(self.read(os.path.join(self.dir, 'out', 'plain.js'), offset=1, limit=5))

    def test_spec_files_and_files_outside_a_project_say_nothing(self):
        self.assertIsNone(self.read(os.path.join(self.spec, 'greet.md')))
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        self.assertIsNone(self.read(write(other.name, 'a.js', '// @clause greet/hello\n// @clause end\n')))
        self.assertIsNone(hook.post_read({'tool_input': {}}))

    def test_it_lists_the_clauses_that_changed_since_the_last_lock(self):
        self.assertNotIn('changed since the last lock', self.read())
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        self.assertIn('Clauses changed since the last lock, so their code may change now: greet/hello', self.read())

    def test_a_test_region_shows_its_test_and_a_marker_naming_no_test_does_not_break_it(self):
        write(self.dir, 'out/t.js', '// @clause test greet/nothing\nx()\n// @clause end\n'
                                    '// @clause test greet/hello\ny()\n// @clause end\n')
        said = self.read(os.path.join(self.dir, 'out', 't.js'))
        self.assertIn('lines 4-6 serve greet/test:hello', said)
        self.assertIn('says hello', said)

    def test_a_long_answer_is_cut_and_says_how_to_see_the_rest(self):
        replace_in(os.path.join(self.spec, 'greet.md'), '- **bye** - The page says {text: Bye}.',
                   '- **bye** - The page says {text: Bye}. ' + 'Very long. ' * 800)
        said = self.read()
        self.assertEqual(len(said.splitlines()[-1]) < 200, True)
        self.assertIn('(more:', said)
        self.assertLessEqual(len(said), hook.MAX_CONTEXT + 200)

    def test_run_as_a_program_it_answers_with_additional_context(self):
        code, out, err = run_hook('post-read', {'tool_input': {'file_path': self.app}})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['hookSpecificOutput']['hookEventName'], 'PostToolUse')


# --- claim and release --------------------------------------------------------------------------------------

class TestClaimCommands(Flow):
    def setUp(self):
        super().setUp()
        self.greet_project(extra={'greet/extra': doc('Extra', 'More.', rules=['- **more** - More.'])})

    def test_a_claim_is_recorded_and_status_shows_it(self):
        code, out, _ = self.sor('claim', 'greet/hello', '--as', 'alice')
        self.assertEqual(code, 0)
        self.assertIn('claimed greet/hello, held while you work', out)
        (held,) = self.claims_file()
        self.assertEqual((held['agent'], held['asked']), ('alice', ['greet/hello']))
        self.assertIn('greet/hello', held['keys'])
        self.assertIn(['out/app.js', ['greet/hello']], held['regions'])
        code, out, _ = self.sor('status')
        self.assertIn('claims (1)', out)
        self.assertIn('alice: greet/hello', out)
        code, out, _ = self.sor('status', '--json')
        self.assertEqual(json.loads(out)['claims'][0]['agent'], 'alice')

    def test_a_clause_held_by_someone_else_is_refused_with_exit_3_and_the_holder(self):
        self.sor('claim', 'greet/hello', '--as', 'alice')
        code, out, _ = self.sor('claim', 'greet/hello', '--as', 'bob')
        self.assertEqual(code, 3)
        self.assertIn('REFUSED greet/hello', out)
        self.assertIn('alice: greet/hello', out)

    def test_a_part_and_its_items_conflict_in_both_directions(self):
        self.sor('claim', 'greet', '--as', 'alice')
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'bob')[0], 3)
        self.sor('release', '--all', '--as', 'alice')
        self.sor('claim', 'greet/hello', '--as', 'alice')
        self.assertEqual(self.sor('claim', 'greet', '--as', 'bob')[0], 3)

    def test_two_items_that_share_no_code_are_both_free(self):
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual(self.sor('claim', 'greet/bye', '--as', 'bob')[0], 0)

    def test_two_clauses_marked_on_one_region_conflict_and_the_claim_says_so(self):
        write(self.dir, 'out/app.js', '// @clause greet/hello greet/bye\nconsole.log("both");\n// @clause end\n')
        accepted(self.dir)
        code, out, _ = self.sor('claim', 'greet/hello', '--as', 'alice')
        self.assertIn('shared with greet/bye', out)
        self.assertEqual(self.sor('claim', 'greet/bye', '--as', 'bob')[0], 3)

    def test_a_child_part_in_a_folder_is_not_held_by_its_parent(self):
        self.sor('claim', 'greet', '--as', 'alice')
        self.assertEqual(self.sor('claim', 'greet/extra', '--as', 'bob')[0], 0)

    def test_claiming_again_keeps_the_original_start_and_renews_the_end(self):
        self.sor('claim', 'greet/hello', '--as', 'alice', '--ttl', '1m')
        data = json.loads(read(os.path.join(self.spec, '.sor-claims.json')))
        data['claims'][0]['since'] -= 1000
        write(self.dir, 'sor/.sor-claims.json', json.dumps(data))
        since = data['claims'][0]['since']
        self.sor('claim', 'greet/hello', '--as', 'alice', '--ttl', '2h')
        (held,) = self.claims_file()
        self.assertEqual(held['since'], since)
        self.assertGreater(held['until'] - time.time(), 3600)

    def test_bad_input_is_exit_2_with_a_sentence(self):
        code, _, err = self.sor('claim', 'greet')
        self.assertEqual(code, 2)
        self.assertIn('say who you are', err)
        code, _, err = self.sor('claim', 'nope', '--as', 'alice')
        self.assertEqual(code, 2)
        self.assertIn('no such clause or part: nope', err)
        code, _, err = self.sor('claim', 'greet', '--as', 'alice', '--ttl', 'soon')
        self.assertEqual(code, 2)
        self.assertIn('--ttl "soon"', err)
        self.assertEqual(self.claims_file(), [])

    def test_an_expired_claim_blocks_nobody_and_is_dropped_by_the_next_claim(self):
        self.sor('claim', 'greet', '--as', 'alice')
        self.expire()
        code, out, _ = self.sor('claim', 'greet', '--as', 'bob')
        self.assertEqual(code, 0)
        self.assertEqual([c['agent'] for c in self.claims_file() if c['until'] > time.time()], ['bob'])   # alice's stays as a tombstone
        self.assertNotIn('alice', self.sor('status')[1])

    def test_a_busy_claims_file_is_a_message_not_a_hang_and_a_dead_holders_mutex_is_broken(self):
        mutex = write(self.dir, 'sor/.sor-claims.lock', '1')
        with mock.patch.object(claims, 'WAIT_LOCK', 0.2):
            code, _, err = self.sor('claim', 'greet', '--as', 'alice')
        self.assertEqual(code, 2)
        self.assertIn('busy', err)
        old = time.time() - 60
        os.utime(mutex, (old, old))
        self.assertEqual(self.sor('claim', 'greet', '--as', 'alice')[0], 0)
        self.assertFalse(os.path.exists(mutex))

    def test_a_claim_is_released_by_its_holder_and_nothing_is_left_behind(self):
        self.sor('claim', 'greet/hello', '--as', 'alice')
        code, out, _ = self.sor('release', 'greet/hello', '--as', 'alice')
        self.assertEqual((code, out.strip()), (0, 'released greet/hello'))
        self.assertFalse(os.path.exists(os.path.join(self.spec, '.sor-claims.json')))
        self.assertEqual(self.sor('release', '--all', '--as', 'alice')[1].strip(), 'nothing to release')

    def test_release_needs_ids_or_all(self):
        code, _, err = self.sor('release', '--as', 'alice')
        self.assertEqual(code, 2)
        self.assertIn('name the clauses, or --all', err)

    def test_someone_elses_claim_is_not_released_without_force(self):
        self.sor('claim', 'greet/hello', '--as', 'alice')
        code, out, _ = self.sor('release', 'greet/hello', '--as', 'bob')
        self.assertEqual(code, 3)
        self.assertIn('NOT released', out)
        self.assertEqual(self.sor('release', '--all', '--as', 'bob')[1].strip(), 'nothing to release')
        self.assertEqual(len(self.claims_file()), 1)
        code, out, _ = self.sor('release', '--all', '--as', 'bob', '--force')
        self.assertEqual((code, out.strip()), (0, 'released greet/hello'))
        self.assertEqual(self.claims_file(), [])

    def test_a_session_is_one_agent_for_release_and_names_are_per_session(self):
        self.sor('claim', 'greet/hello', '--as', 'sub-1', CLAUDE_CODE_SESSION_ID='session-one')
        code, out, _ = self.sor('release', '--all', CLAUDE_CODE_SESSION_ID='session-one')   # the parent gives no name
        self.assertEqual((code, out.strip()), (0, 'released greet/hello'))
        self.sor('claim', 'greet/hello', '--as', 'sub-1', CLAUDE_CODE_SESSION_ID='session-one')
        code, out, _ = self.sor('claim', 'greet/hello', '--as', 'sub-1', CLAUDE_CODE_SESSION_ID='session-two')
        self.assertEqual(code, 3)

    def test_without_a_name_the_claude_code_session_is_the_agent(self):
        code, out, _ = self.sor('claim', 'greet/hello', CLAUDE_CODE_SESSION_ID='abcdefgh-1234')
        self.assertEqual(code, 0)
        self.assertEqual(self.claims_file()[0]['agent'], 'session-abcdefgh')
        self.assertEqual(self.claims_file()[0]['session'], 'abcdefgh-1234')

    def test_sor_agent_names_the_agent(self):
        self.sor('claim', 'greet/hello', SOR_AGENT='carol')
        self.assertEqual(self.claims_file()[0]['agent'], 'carol')

    def test_an_old_claim_without_a_session_field_is_compared_by_name(self):
        write(self.dir, 'sor/.sor-claims.json', json.dumps({'claims': [{
            'agent': 'dave', 'asked': ['greet/hello'], 'keys': ['greet/hello'], 'since': time.time(),
            'until': time.time() + 600, 'regions': []}]}))
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'dave')[0], 0)
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'erin')[0], 3)


# --- sor lock -----------------------------------------------------------------------------------------------

class TestLockCommand(Flow):
    def setUp(self):
        super().setUp()
        self.greet_project(lock=False)

    def lock_entries(self):
        return json.loads(lock_bytes(self.dir))

    def test_a_plain_lock_with_nothing_claimed_is_refused_and_says_what_to_do(self):
        code, out, _ = self.sor('lock')
        self.assertEqual(code, 2)
        self.assertIn('say which clauses', out)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))

    def test_locking_a_part_retires_the_entries_of_items_that_left_it(self):
        self.greet_project()
        replace_in(os.path.join(self.spec, 'greet.md'), '- **bye** - The page says {text: Bye}.\n', '')
        replace_in(self.app, '// @clause greet/bye\nconsole.log("Bye");\n// @clause end\n', '')
        self.assertIn('greet/bye', self.lock_entries())
        self.assertEqual(self.sor('claim', 'greet', '--as', 'a')[0], 0)
        code, out, _ = self.sor('lock', '--as', 'a', '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertNotIn('greet/bye', self.lock_entries())
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])

    def test_the_glue_of_a_file_that_is_only_glue_goes_with_a_scoped_lock(self):
        self.greet_project()
        write(self.dir, 'out/init.js', '// @clause glue\n"use strict";\n// @clause end\n')
        self.assertEqual(self.sor('claim', 'greet', '--as', 'a')[0], 0)
        self.assertEqual(self.sor('lock', '--as', 'a', '--allow-incomplete')[0], 0)
        self.assertIn('glue:out/init.js', self.lock_entries())
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])

    def test_a_folder_that_starts_with_a_dot_is_never_read_for_markers(self):
        self.greet_project()
        write(self.dir, '.claude/skills/x/example.js', '// @clause no/such\nconsole.log(1);\n// @clause end\n')
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertNotIn('no/such', out)

    def test_lock_all_with_tests_that_did_not_run_is_refused_unless_allowed(self):
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 2)
        self.assertIn('1 test(s) did not pass (0 failed, 1 not run)', out)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))
        code, out, _ = self.sor('lock', '--all', '--allow-incomplete')
        self.assertEqual(code, 0)
        self.assertIn('1 not passed', out)
        self.assertEqual(self.lock_entries()['greet/test:hello']['result'], 'none')

    def test_the_lock_is_reproducible_to_the_byte(self):
        self.sor('lock', '--all', '--allow-incomplete')
        first = lock_bytes(self.dir)
        self.sor('lock', '--all', '--allow-incomplete')
        self.assertEqual(lock_bytes(self.dir), first)
        keys = [line.split('": ')[0] for line in first.decode().splitlines()[1:-1]]
        self.assertEqual(keys, sorted(keys))

    def test_results_from_a_file_are_recorded(self):
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass'}))
        code, out, _ = self.sor('lock', '--all', '--results', results)
        self.assertEqual(code, 0)
        self.assertIn('1 passed', out)
        self.assertEqual(self.lock_entries()['greet/test:hello']['result'], 'pass')

    def test_a_failed_result_is_recorded_only_when_incomplete_locks_are_allowed(self):
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'fail'}))
        code, out, _ = self.sor('lock', '--all', '--results', results)
        self.assertEqual(code, 2)
        self.assertIn('1 failed', out)
        self.assertEqual(self.sor('lock', '--all', '--results', results, '--allow-incomplete')[0], 0)
        self.assertEqual(self.lock_entries()['greet/test:hello']['result'], 'fail')

    def test_a_result_for_something_that_is_not_a_test_is_refused(self):
        results = write(self.dir, 'results.json', json.dumps({'greet/hello': 'pass'}))
        code, out, _ = self.sor('lock', '--all', '--results', results, '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('greet/hello is not a test', out)

    def test_a_claimed_part_is_locked_without_naming_it_and_the_rest_stays_pending(self):
        self.sor('lock', '--all', '--allow-incomplete')
        write(self.dir, 'sor/other.md', doc('Other', 'Another part.', rules=['- **thing** - A thing.']))
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        self.sor('claim', 'greet/hello', '--as', 'alice')
        code, out, _ = self.sor('lock', '--as', 'alice', '--allow-incomplete')
        self.assertEqual(code, 0)
        self.assertIn('locking what you claimed: greet/hello', out)
        self.assertIn('still pending outside what you locked', out)
        entries = self.lock_entries()
        self.assertIn('other', self.sor('status')[1])
        self.assertNotIn('other', entries)
        self.assertEqual(entries['greet/hello'], lockfile.snapshot(Project(self.dir), Scan(Project(self.dir)))['greet/hello'])

    def test_two_agents_locking_their_own_clauses_keep_each_others_entries(self):
        self.sor('claim', 'greet/hello', '--as', 'alice')
        self.sor('claim', 'greet/bye', '--as', 'bob')
        self.assertEqual(self.sor('lock', '--as', 'alice', '--allow-incomplete')[0], 0)
        self.assertEqual(self.sor('lock', '--as', 'bob', '--allow-incomplete')[0], 0)
        entries = self.lock_entries()
        for key in ('greet/hello', 'greet/hello.text', 'greet/bye', 'greet/bye.text'):
            self.assertIn(key, entries)

    def test_a_lock_does_not_wait_for_code_and_code_that_comes_later_is_reported_as_built(self):
        write(self.dir, 'sor/greet.md', doc('Greet', 'Says hello.', rules=[
            '- **hello** - The page says {text: Hello}.', '- **bye** - The page says {text: Bye}.']))
        os.remove(self.app)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        write(self.dir, 'out/app.js', APP)
        code, out, _ = self.sor('status')
        self.assertEqual(code, 1)
        self.assertIn('built', out)
        self.assertIn('first code for a locked clause', out)

    def test_a_clause_held_by_someone_else_cannot_be_locked(self):
        self.sor('claim', 'greet', '--as', 'alice')
        code, out, _ = self.sor('lock', 'greet/hello', '--as', 'bob', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('claimed  alice: greet', out)
        self.assertIn('wait for them, or ask them to release', out)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))

    def test_lock_all_is_refused_while_anyone_holds_a_claim_but_the_holder_may(self):
        self.sor('claim', 'greet', '--as', 'alice')
        code, out, _ = self.sor('lock', '--all', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('say who you are with --as NAME', out)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete', '--as', 'alice')[0], 0)

    def test_a_session_that_claimed_under_another_name_is_told_which(self):
        self.sor('claim', 'greet', '--as', 'sub-1', CLAUDE_CODE_SESSION_ID='s1')
        code, out, _ = self.sor('lock', '--allow-incomplete', CLAUDE_CODE_SESSION_ID='s1')
        self.assertEqual(code, 2)
        self.assertIn('you claimed in this session as sub-1', out)

    def test_an_unknown_id_is_refused(self):
        code, out, _ = self.sor('lock', 'nope', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('no such clause or part: nope', out)

    def test_drift_blocks_lock_all_and_leaves_the_lock_alone(self):
        accepted(self.dir)
        before = lock_bytes(self.dir)
        replace_in(self.app, '"Hello"', '"Hi"')
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 2)
        self.assertIn('drift  greet/hello', out)
        self.assertEqual(lock_bytes(self.dir), before)

    def test_code_a_person_changed_is_kept_by_changing_its_clause_to_match(self):
        accepted(self.dir)
        replace_in(self.app, '"Hello"', '"Hi"')   # a person edits the code in their editor: the hook never sees it
        code, out, _ = self.sor('status')
        self.assertEqual(code, 2)
        self.assertRegex(out, r'drift\s+greet/hello')
        self.assertIn('update the clause to say what the code now does', out)
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')   # the agent brings the clause in line
        code, out, _ = self.sor('status')
        self.assertEqual(code, 1, out)
        self.assertNotIn('drift', out)
        self.assertRegex(out, r'changed\s+greet/hello.*code updated')
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'bob')[0], 0)
        code, out, _ = self.sor('lock', '--as', 'bob', '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])

    def test_drift_in_another_clause_does_not_block_a_scoped_lock(self):
        accepted(self.dir)
        replace_in(self.app, '"Hello"', '"Hi"')
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}')
        replace_in(self.app, '"Bye"', '"Ciao"')
        self.sor('claim', 'greet/bye', '--as', 'bob')
        code, out, _ = self.sor('lock', '--as', 'bob', '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.lock_entries()['greet/bye.text']['text'], base.sha12('Ciao'))

    def test_a_spec_problem_blocks_lock_all_but_only_a_problem_in_scope_blocks_a_scoped_lock(self):
        write(self.dir, 'sor/other.md', doc('Other', 'Another part.', rules=['- **thing** - See {nowhere/at-all}.']))
        code, out, _ = self.sor('lock', '--all', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('broken', out)
        self.sor('claim', 'greet/hello', '--as', 'alice')
        code, out, _ = self.sor('lock', '--as', 'alice', '--allow-incomplete')
        self.assertEqual(code, 0)
        self.assertIn('1 problem(s) in other files do not block this lock', out)
        self.sor('claim', 'other', '--as', 'alice')
        self.assertEqual(self.sor('lock', 'other', '--as', 'alice', '--allow-incomplete')[0], 2)

    def test_a_clause_that_shares_code_with_a_clause_that_has_its_own_change_is_refused(self):
        write(self.dir, 'out/app.js', '// @clause greet/hello greet/bye\nconsole.log("both");\n// @clause end\n')
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}')
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('greet/bye shares code with greet/hello and has its own pending change', out)

    def manual_greet(self):
        write(self.dir, 'sor/greet.md', doc('Greet', 'Says hello.', rules=['- **hello** - The page says {text: Hello}.'],
                                                tests=['- **hello** - looks right.', '  manual: look at it']))
        write(self.dir, 'out/app.js', '// @clause greet/hello\nconsole.log("Hello");\n// @clause end\n')

    def test_a_manual_test_is_confirmed_by_name_and_only_when_it_is_manual(self):
        self.manual_greet()
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 0)
        self.assertIn('1 manual and not yet checked by a person', out)
        code, out, _ = self.sor('lock', '--all', '--confirm', 'greet/hello')
        self.assertEqual(code, 0)
        self.assertIn('1 manual and checked by a person', out)
        self.assertEqual(self.lock_entries()['greet/test:hello']['result'], 'checked')
        code, out, _ = self.sor('lock', '--all', '--confirm', 'greet/nothing')
        self.assertEqual(code, 2)
        self.assertIn('is not a manual test', out)

    def test_a_confirmed_manual_test_stays_confirmed_until_its_code_or_text_changes(self):
        self.manual_greet()
        self.sor('lock', '--all', '--confirm', 'greet/hello')
        self.sor('lock', '--all')
        self.assertEqual(self.lock_entries()['greet/test:hello']['result'], 'checked')
        replace_in(os.path.join(self.spec, 'greet.md'), 'look at it', 'look closely')
        self.sor('lock', '--all')
        self.assertEqual(self.lock_entries()['greet/test:hello']['result'], 'manual')

    @unittest.skipUnless(CAN_CHMOD, 'file modes do not stop root, and Windows has no chmod')
    def test_a_read_only_lock_is_refused_and_the_message_is_relative_to_the_project(self):
        accepted(self.dir)
        path = os.path.join(self.spec, 'sor-lock.json')
        before = lock_bytes(self.dir)
        os.chmod(path, 0o444)
        self.addCleanup(os.chmod, path, 0o644)
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        code, out, _ = self.sor('lock', '--all', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('sor/sor-lock.json is read-only', out)
        self.assertNotIn('..', out)
        self.assertEqual(lock_bytes(self.dir), before)

    @unittest.skipUnless(CAN_CHMOD, 'file modes do not stop root, and Windows has no chmod')
    def test_the_lock_keeps_the_permissions_it_had(self):
        accepted(self.dir)
        path = os.path.join(self.spec, 'sor-lock.json')
        os.chmod(path, 0o640)
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o640)
        self.assertEqual(glob.glob(path + '.*.tmp'), [])

    def test_the_lock_waits_for_a_busy_mutex_and_refuses_with_a_message(self):
        self.sor('claim', 'greet/hello', '--as', 'alice')
        write(self.dir, 'sor/.sor-lock.mutex', '1')
        with mock.patch.object(claims, 'WAIT_LOCK', 0.2):
            code, _, err = self.sor('lock', '--as', 'alice', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('busy', err)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))


class TestCheckStrict(Flow):
    def test_strict_fails_on_a_note(self):
        self.greet_project(lock=False)
        replace_in(os.path.join(self.spec, 'greet.md'), '  expect: ok', '  manual: a person looks')   # a test nothing runs is a note of its own
        self.assertEqual(self.sor('check', '--strict')[0], 0)
        write(self.dir, 'sor/big.md', doc('Big', 'Too many rules.', rules=base.bullets(lint.LIMIT_ITEMS + 1)))
        self.assertEqual(self.sor('check')[0], 0)
        self.assertEqual(self.sor('check', '--strict')[0], 2)


class TestEditorIndex(Flow):
    """`sor markers --json` is what the editor extension reads."""

    def test_the_index_names_the_spec_folder_and_lists_the_clauses_of_each_region(self):
        self.greet_project(lock=False)
        code, out, _ = self.sor('markers', '--json')
        self.assertEqual(code, 0)
        index = json.loads(out)
        self.assertEqual(index['specDir'], self.spec)
        self.assertEqual(sorted(index), ['items', 'refs', 'regions', 'root', 'specDir', 'version'])
        code, out, _ = self.sor('markers', 'out/app.js:5', '--json')
        region = json.loads(out)['regions'][0]
        self.assertEqual([c['id'] for c in region['clauses']], ['greet/hello'])
        self.assertNotIn('facts', region)


class TestRootName(Flow):
    """The root part: its id is ROOT, its file is sor/SPECOFRECORD.md, and CLAUSES stays an accepted name."""

    def root_file(self, name):
        return os.path.join(self.spec, name + '.md')

    def test_the_root_file_is_specofrecord_and_a_project_made_with_the_older_name_still_works(self):
        self.greet_project(lock=False)
        self.assertTrue(os.path.isfile(self.root_file('SPECOFRECORD')))
        self.assertEqual(self.sor('check')[0], 0)
        os.rename(self.root_file('SPECOFRECORD'), self.root_file('CLAUSES'))   # how a project was made before
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertEqual(Project(self.dir).parts[''].key, 'ROOT')

    def test_both_root_files_together_are_refused_with_a_message_that_names_the_one_to_keep(self):
        self.greet_project(lock=False)
        write(self.dir, 'sor/CLAUSES.md', read(self.root_file('SPECOFRECORD')))
        code, out, err = self.sor('check')
        self.assertNotEqual(code, 0)
        self.assertIn('both sor/SPECOFRECORD.md and sor/CLAUSES.md exist', out + err)

    def test_a_folder_part_has_its_own_file_called_specofrecord_and_the_older_clauses_still_works(self):
        self.greet_project(lock=False, extra={'render/SPECOFRECORD': doc('Render', 'Draws.')})
        self.assertIn('render', Project(self.dir).parts)
        self.assertNotIn('render/SPECOFRECORD', Project(self.dir).parts)
        os.rename(os.path.join(self.spec, 'render', 'SPECOFRECORD.md'), os.path.join(self.spec, 'render', 'CLAUSES.md'))
        self.assertIn('render', Project(self.dir).parts)
        self.assertEqual(self.sor('check')[0], 0)

    def test_two_files_for_one_part_are_a_problem_that_names_both_and_none_replaces_the_other_silently(self):
        self.greet_project(lock=False, extra={'render': doc('Render', 'Draws.', rules=['- **draw** - Draws.']),
                                              'render/SPECOFRECORD': doc('Render again', 'Draws, in a folder.', rules=['- **other** - Other.'])})
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2)
        self.assertIn('render/SPECOFRECORD.md claims the same part `render` as render.md', out)
        part = Project(self.dir).parts['render']
        self.assertEqual(part.rel, 'render.md', 'the plain file counts first')
        self.assertIn('render/draw', Project(self.dir).items)
        self.assertNotIn('render/other', Project(self.dir).items)

    def test_the_two_file_names_of_a_folder_are_a_problem_too(self):
        self.greet_project(lock=False, extra={'render/SPECOFRECORD': doc('Render', 'Draws.'), 'render/CLAUSES': doc('Render', 'Older.')})
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2)
        self.assertIn('render/CLAUSES.md claims the same part `render` as render/SPECOFRECORD.md', out)

    def test_a_part_with_children_is_its_file_beside_its_folder_and_children_refer_upward(self):
        self.greet_project(lock=False, extra={
            'web': doc('Web', 'What the customer sees.', rules=['- **look** - Calm, {pad: 8 px}.']),
            'web/page': doc('Page', 'The page.', rules=['- **title** - Uses {look.pad}.'])})
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(Project(self.dir).parts)[1:], ['greet', 'web', 'web/page'])

    def test_a_folder_that_only_groups_parts_needs_no_file(self):
        self.greet_project(lock=False, extra={'api/orders': doc('Orders', 'Placing orders.')})
        self.assertEqual(self.sor('check')[0], 0)
        self.assertIn('api/orders', Project(self.dir).parts)
        self.assertNotIn('api', Project(self.dir).parts)

    def test_a_folder_with_a_project_of_its_own_is_not_scanned_by_the_project_around_it(self):
        self.greet_project(lock=False)
        write(self.dir, 'apps/web/sor/SPECOFRECORD.md', doc('Web', 'The web app.', rules=['- **page** - A page.']))
        write(self.dir, 'apps/web/src/a.js', '// @clause page\nconsole.log(1);\n// @clause end\n')
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertNotIn('apps/web', out)
        inner = run_sor(os.path.join(self.dir, 'apps', 'web'), 'check')
        self.assertEqual(inner[0], 0, inner[1])
        self.assertEqual(hook.find_root(os.path.join(self.dir, 'apps', 'web', 'src', 'a.js')), os.path.join(self.dir, 'apps', 'web'))

    def test_the_root_answers_to_root_clauses_and_specofrecord(self):
        self.greet_project(lock=False)
        for name in ('ROOT', 'CLAUSES', 'SPECOFRECORD'):
            self.assertEqual(self.sor('show', name)[0], 0, name)
            self.assertEqual(self.sor('claim', name, '--as', 'a')[0], 0, name)
            self.assertEqual(self.sor('release', '--all', '--as', 'a')[0], 0, name)
        self.assertEqual(self.sor('show', 'ROOT')[1], self.sor('show', 'CLAUSES')[1])

    def test_a_lock_that_calls_the_root_clauses_reads_as_unchanged_and_is_rewritten_as_root(self):
        self.greet_project(lock=True)
        path = os.path.join(self.spec, 'sor-lock.json')
        old = json.loads(read(path))
        self.assertIn('ROOT', old)
        before = {k: v for k, v in old.items() if k != 'ROOT'}
        text = read(path).replace('"ROOT":', '"CLAUSES":', 1)   # a lock written before the rename
        write(self.dir, 'sor/sor-lock.json', text)
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])   # same hashes: nothing changed
        self.assertEqual(self.sor('claim', 'ROOT', '--as', 'a')[0], 0)
        code, out, _ = self.sor('lock', '--as', 'a', '--allow-incomplete')
        self.assertEqual(code, 0, out)
        new = json.loads(read(path))
        self.assertIn('ROOT', new)
        self.assertNotIn('CLAUSES', new)
        self.assertEqual(new['ROOT'], old['ROOT'])
        self.assertEqual({k: v for k, v in new.items() if k != 'ROOT'}, before)

    def test_a_lock_called_clauses_lock_json_is_read_and_replaced_by_sor_lock_json(self):
        self.greet_project(lock=True)
        new = os.path.join(self.spec, 'sor-lock.json')
        old = os.path.join(self.spec, 'clauses-lock.json')
        kept = read(new)
        os.rename(new, old)
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])   # the older file is read
        self.assertEqual(self.sor('claim', 'ROOT', '--as', 'a')[0], 0)
        self.assertEqual(self.sor('lock', '--as', 'a', '--allow-incomplete')[0], 0)
        self.assertTrue(os.path.isfile(new))
        self.assertFalse(os.path.exists(old), 'the older lock file is gone after the lock was written')
        self.assertEqual(read(new), kept)

    def test_a_scoped_lock_never_leaves_both_keys(self):
        self.greet_project(lock=True)
        path = os.path.join(self.spec, 'sor-lock.json')
        write(self.dir, 'sor/sor-lock.json', read(path).replace('"ROOT":', '"CLAUSES":', 1))
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Goodbye}')   # the clause first, then its code
        replace_in(self.app, 'console.log("Bye");', 'console.log("Goodbye");')
        self.assertEqual(self.sor('claim', 'greet/bye', '--as', 'a')[0], 0)
        self.assertEqual(self.sor('lock', '--as', 'a', '--allow-incomplete')[0], 0)
        keys = json.loads(read(path))
        self.assertFalse('CLAUSES' in keys and 'ROOT' in keys)


class TestFoldersCalledSor(Flow):
    """The spec folder is called `sor`, and so may be a repository (cloned under that name) or a project's own folder."""

    def test_a_project_folder_that_is_itself_called_sor_is_found_through_its_spec_folder(self):
        project = os.path.join(self.dir, 'sor')
        base.make_project(project)
        self.assertTrue(os.path.isfile(os.path.join(project, 'sor', 'SPECOFRECORD.md')))
        code, out, err = run_sor(project, 'check')
        self.assertEqual(code, 0, out + err)
        self.assertIn('0 problem(s)', out)

    def test_pointing_at_the_spec_folder_itself_works(self):
        self.greet_project(lock=False)
        code, out, err = run_sor(self.spec, 'check')
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.sor('check')[1], out)

    def test_nothing_is_a_project_without_the_root_file_and_the_message_names_the_folder(self):
        code, _, err = run_sor(self.dir, 'check')
        self.assertNotEqual(code, 0)
        self.assertIn('no sor/SPECOFRECORD.md under', err)

    def test_the_old_folder_name_is_not_found_any_more(self):
        write(self.dir, 'clauses/CLAUSES.md', base.ROOT_DOC)
        code, _, err = run_sor(self.dir, 'check')
        self.assertNotEqual(code, 0)
        self.assertIn('no sor/SPECOFRECORD.md under', err)


class TestNewScaffold(Flow):
    def test_the_root_file_has_rules_and_approach_and_a_part_has_all_four_sections(self):
        self.assertEqual(self.sor('new', '--root')[0], 0)
        self.assertEqual(self.sor('new', 'render')[0], 0)
        headings = lambda rel: [l for l in read(os.path.join(self.dir, 'sor', rel)).splitlines() if l.startswith('## ')]
        self.assertEqual(headings('SPECOFRECORD.md'), ['## Rules', '## Approach'])
        self.assertEqual(headings('render.md'), ['## Rules', '## Approach', '## Contract', '## Tests'])

    def test_the_limit_in_the_hint_comments_is_the_one_the_tool_enforces(self):
        with mock.patch.object(lint, 'LIMIT_ITEMS', 9):
            self.sor('new', '--root')
            self.sor('new', 'render')
        for rel in ('SPECOFRECORD.md', 'render.md'):
            self.assertIn('At most 9 items', read(os.path.join(self.dir, 'sor', rel)), rel)


# --- the design export --------------------------------------------------------------------------------------

TOKENS = {'planet': {'mars': {'$value': '#c1440e'}, 'earth': {'$value': '#2e6fd8'}}, 'ui': {'bg': {'$value': '#000000'}}}


class TestDesignExport(Flow):
    def setUp(self):
        super().setUp()
        write(self.dir, 'design/tokens.json', json.dumps(TOKENS, indent=1))
        write(self.dir, 'design/assets/logo.svg', '<svg><circle r="1"/></svg>')
        write(self.dir, 'sor/SPECOFRECORD.md', doc('Demo', 'A project with a design.', header=['Design: design/tokens.json'],
                                                  rules=['- **out-of-scope** - other.']))
        write(self.dir, 'sor/screen.md', doc('Screen', 'Draws things.', rules=[
            '- **mars-color** - Mars is drawn in {design/planet/mars}.',
            '- **earth-color** - Earth is drawn in {design/planet/earth.value}.',
            '- **plain** - Nothing to do with the design.']))
        write(self.dir, 'out/app.js', '// @clause screen/mars-color\nfill("#c1440e");\n// @clause end\n')
        accepted(self.dir)
        self.tokens = os.path.join(self.dir, 'design', 'tokens.json')
        self.logo = os.path.join(self.dir, 'design', 'assets', 'logo.svg')

    def changes(self):
        code, out, _ = self.sor('changes')
        self.assertEqual(code, 0)
        return out

    def test_the_export_becomes_a_part_whose_tokens_are_locked(self):
        entries = json.loads(lock_bytes(self.dir))
        for key in ('design', 'design/planet', 'design/planet/mars', 'design/planet/mars.value', 'design/assets/logo',
                    'design/assets/logo.file'):
            self.assertIn(key, entries)
        self.assertEqual(self.sor('check')[1].strip().splitlines()[-1], '3 parts, 2 references, 1 code regions; 0 problem(s)')
        self.assertEqual(self.sor('status')[1].strip(), 'clauses, code and lock agree')
        self.assertIn('generated from design/tokens.json', self.sor('parts')[1])

    def test_a_changed_token_is_a_change_and_the_clause_that_uses_it_is_flagged(self):
        replace_in(self.tokens, '#c1440e', '#ff0000')
        self.assertIn('Changed (1)', self.changes())
        self.assertIn('design/planet/mars', self.changes())
        code, out, _ = self.sor('status')
        self.assertEqual(code, 1)
        self.assertIn('changed      design/planet/mars', out)
        self.assertIn('stale        screen/mars-color', out)
        self.assertNotIn('earth-color', out)

    def test_changing_it_back_is_no_change(self):
        replace_in(self.tokens, '#c1440e', '#ff0000')
        replace_in(self.tokens, '#ff0000', '#c1440e')
        self.assertEqual(self.sor('status')[1].strip(), 'clauses, code and lock agree')
        self.assertIn('nothing pending', self.changes())

    def test_an_added_and_a_removed_token_are_reported(self):
        data = dict(TOKENS, planet=dict(TOKENS['planet'], venus={'$value': '#e6c229'}))
        del data['planet']['earth']
        write(self.dir, 'design/tokens.json', json.dumps(data))
        said = self.changes()
        self.assertIn('Added (1)', said)
        self.assertIn('design/planet/venus', said)
        self.assertIn('Removed (', said)
        self.assertIn('design/planet/earth', said)
        self.assertIn('stale        screen/earth-color', self.sor('status')[1])

    def test_a_changed_and_an_added_picture_are_reported(self):
        replace_in(self.logo, 'r="1"', 'r="2"')
        self.assertIn('design/assets/logo', self.changes())
        replace_in(self.logo, 'r="2"', 'r="1"')
        write(self.dir, 'design/assets/new.svg', '<svg/>')
        said = self.changes()
        self.assertIn('Added (1)', said)
        self.assertIn('design/assets/new', said)

    def test_an_unreadable_export_is_one_problem_per_cause_and_nothing_crashes(self):
        write(self.dir, 'design/tokens.json', '{ not json')
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2)
        self.assertIn('cannot read the design export', out)
        self.assertIn('broken  screen.md:5  {design/planet/mars}', out)
        for args in (('parts',), ('status',), ('changes',), ('needs', 'screen'), ('markers',), ('show', 'screen')):
            self.assertIn(self.sor(*args)[0], (0, 1, 2), args)
        said = hook.session_start({'cwd': self.dir})['hookSpecificOutput']['additionalContext']
        self.assertIn('Parts:', said)

    def test_a_missing_export_is_the_same_problem(self):
        os.remove(self.tokens)
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2)
        self.assertIn('cannot read the design export', out)

    def test_code_that_follows_the_design_is_guarded_until_the_design_changes(self):
        said = reason(hook.pre_edit(edit(self.app, '#c1440e', '#ff0000')))
        self.assertIn('Clauses come first', said)
        self.assertIn('screen/mars-color', said)
        replace_in(self.tokens, '#c1440e', '#ff0000')   # the export changed, so the clause that uses it is to be rebuilt
        self.assertIsNone(hook.pre_edit(edit(self.app, '#c1440e', '#ff0000')))


# --- sor test without a browser -----------------------------------------------------------------------------

TARGET = doc('Web', 'The page the tests drive.',
             rules=['- **path** - The page is {path: out/index.html}.'],
             contract=['- gives **probes** - members of window.__probe.', '  read: errors, hud', '  do: step(seconds)',
                       '  metrics: fps'],
             tests=['- **path** - The page opens.', '  expect: count(errors) = 0'])
PAGE = '<!-- @clause glue -->\n<html><body><p>hi</p></body></html>\n<!-- @clause end -->\n'


TARGET_WITH_TEST_CODE = doc('Web', 'The page the tests drive.',
                            rules=['- **path** - The page is {path: out/index.html}.',
                                   '- **test-code** - Hand-written tests are in {path: test/}.'],
                            contract=['- gives **probes** - members of window.__probe.', '  read: errors, hud', '  do: step(seconds)',
                                      '  metrics: fps'],
                            tests=['- **path** - The page opens.', '  expect: count(errors) = 0'])
TEST_CODE = '// @clause test lim/loose\nit("errors stay below the cap", () => {});\n// @clause end\n'


class TestExternalTests(Flow):
    """A test with no `do:` / `expect:` lines, whose code is marked `@clause test`, is written in the project's own
    framework: `sor test` shows it as EXTERNAL (not run, not failed) and its result comes from `sor lock --results`."""

    DIRECT = ['- **limit** - the cap holds.', '  expect: count(errors) = {limit.max}']
    LOOSE = ['- **loose** - test that errors stay below the cap.', '  proves: {limit}']

    def setUp(self):
        super().setUp()
        self.build(TARGET_WITH_TEST_CODE, TEST_CODE)

    def build(self, target, test_code):
        shutil.rmtree(os.path.join(self.dir, 'sor'), ignore_errors=True)
        shutil.rmtree(os.path.join(self.dir, 'test'), ignore_errors=True)
        self.project({'targets/web': target, 'lim': doc('Limits', 'How many errors.', rules=['- **limit** - At most {max: 5} errors.'],
                                                       tests=self.DIRECT + self.LOOSE)})
        write(self.dir, 'out/index.html', PAGE)
        if test_code:
            write(self.dir, 'test/limit.test.js', test_code)

    def ask(self, *args, status='pass'):
        """`sor` with the browser replaced: the page passes every test it is asked for. (code, output, ids asked of the page)"""
        asked = []

        def page(target, script, ids, timeout):
            asked.extend(ids)
            return [{'id': i, 'status': status} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            code, out, err = self.sor(*args)
        return code, out + err, asked

    def results(self, data):
        return write(self.dir, 'framework.json', json.dumps(data))

    def test_a_test_without_steps_whose_code_is_marked_is_external_and_not_failed(self):
        code, out, asked = self.ask('test')
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r'EXTERNAL\s+lim/test:loose\s+test code at test/limit\.test\.js:1-3')
        self.assertIn('2 passed, 0 failed, 0 skipped, 0 manual, 1 external', out)
        self.assertNotIn('lim/test:loose', ' '.join(asked))

    def test_the_summary_line_is_unchanged_when_nothing_is_external(self):
        self.build(TARGET_WITH_TEST_CODE, TEST_CODE)
        replace_in(os.path.join(self.spec, 'lim.md'), '- **loose** - test that errors stay below the cap.\n  proves: {limit}\n', '')
        out = self.ask('test')[1]
        self.assertNotIn('external', out)
        self.assertNotIn('EXTERNAL', out)

    def test_without_test_code_the_test_still_fails_and_says_how_to_mark_it(self):
        self.build(TARGET_WITH_TEST_CODE, None)
        code, out, _ = self.ask('test')
        self.assertEqual(code, 1)
        self.assertRegex(out, r'FAIL\s+lim/test:loose\s+test error: the test has no `do:`')
        self.assertIn('// @clause test <id>', out)
        self.assertIn('{path: test/}', out)

    def test_a_test_folder_the_target_does_not_declare_is_not_read(self):
        self.build(TARGET, TEST_CODE)
        code, out, _ = self.ask('test')
        self.assertEqual(code, 1)
        self.assertRegex(out, r'FAIL\s+lim/test:loose')

    def test_code_marked_for_the_clause_is_not_test_code(self):
        self.build(TARGET_WITH_TEST_CODE, '// @clause lim/limit\nit("x", () => {});\n// @clause end\n')
        code, out, _ = self.ask('test')
        self.assertRegex(out, r'FAIL\s+lim/test:loose')

    def test_a_manual_test_stays_manual_even_with_test_code(self):
        replace_in(os.path.join(self.spec, 'lim.md'), '  proves: {limit}\n', '  proves: {limit}\n  manual: needs a person\n')
        self.assertRegex(self.ask('test')[1], r'MANUAL\s+lim/test:loose')

    def test_the_lock_waits_for_the_framework_and_says_which_tests_and_how(self):
        code, out, _ = self.ask('lock', '--all', '--run-tests')
        self.assertEqual(code, 2)
        self.assertIn('EXTERNAL lim/test:loose: no result yet', out)
        self.assertIn('--results F', out)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))

    def test_results_from_the_framework_join_the_run_and_the_lock_goes_through(self):
        code, out, _ = self.ask('lock', '--all', '--run-tests', '--results', self.results({'lim/test:loose': 'pass'}))
        self.assertEqual(code, 0, out)
        entries = json.loads(lock_bytes(self.dir))
        self.assertEqual((entries['lim/test:loose']['result'], entries['lim/test:limit']['result']), ('pass', 'pass'))
        self.assertIn('clauses, code and lock agree', self.sor('status')[1])

    def test_a_result_in_the_file_for_a_test_sor_ran_itself_is_ignored_and_said(self):
        code, out, _ = self.ask('lock', '--all', '--run-tests', '--results',
                                self.results({'lim/test:loose': 'pass', 'lim/test:limit': 'fail', 'lim/test:nothing': 'pass'}))
        self.assertEqual(code, 0, out)
        self.assertIn('--results: ignored lim/test:limit, lim/test:nothing', out)
        self.assertEqual(json.loads(lock_bytes(self.dir))['lim/test:limit']['result'], 'pass')

    def test_a_failed_framework_result_refuses_the_lock_unless_incomplete_locks_are_allowed(self):
        given = self.results({'lim/test:loose': 'fail'})
        code, out, _ = self.ask('lock', '--all', '--run-tests', '--results', given)
        self.assertEqual(code, 2)
        self.assertIn('1 failed', out)
        code, out, _ = self.ask('lock', '--all', '--run-tests', '--results', given, '--allow-incomplete')
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(lock_bytes(self.dir))['lim/test:loose']['result'], 'fail')

    def test_only_a_known_result_is_taken(self):
        code, out, _ = self.ask('lock', '--all', '--run-tests', '--results', self.results({'lim/test:loose': 'maybe'}))
        self.assertEqual(code, 2)
        self.assertIn('EXTERNAL lim/test:loose: no result yet', out)

    def test_sor_test_out_writes_only_what_it_decided_itself(self):
        out_file = os.path.join(self.dir, 'out.json')
        self.ask('test', '--out', out_file)
        self.assertEqual(sorted(json.loads(read(out_file))), ['lim/test:limit', 'targets/web/test:path'])


class TestSorTestWithoutABrowser(Flow):
    def setUp(self):
        super().setUp()
        self.project({'targets/web': TARGET})
        self.page = write(self.dir, 'out/index.html', PAGE)

    def no_browser(self):
        return mock.patch.object(testrun, 'find_chrome', side_effect=AssertionError('a browser was asked for'))

    def test_without_a_web_target_it_says_what_is_missing(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        base.make_project(other.name)
        code, _, err = run_sor(other.name, 'test')
        self.assertEqual(code, 1)
        self.assertIn('no web target', err)

    def test_a_page_that_is_not_built_fails_every_test_without_asking_for_a_browser(self):
        os.remove(self.page)
        with self.no_browser():
            code, out, _ = self.sor('test')
        self.assertEqual(code, 1)
        self.assertIn('nothing is built', out)
        self.assertIn('FAIL', out)

    def test_no_chrome_installed_says_how_to_point_to_one(self):
        with mock.patch.object(testrun, 'find_chrome', return_value=None):
            code, _, err = self.sor('test')
        self.assertEqual(code, 1)
        self.assertIn('no Chrome or Edge found; set SOR_CHROME', err)
        self.assertEqual(glob.glob(os.path.join(self.dir, 'out', '.sor-test-*')), [])

    @unittest.skipIf(os.name == 'nt', 'the stand-in browser is a shell script')
    def test_a_chrome_that_will_not_start_is_a_message_and_leaves_nothing_behind(self):
        fake = write(self.dir, 'fake-chrome', '#!/bin/sh\nexit 1\n')
        os.chmod(fake, 0o755)
        profiles = lambda: set(glob.glob(os.path.join(tempfile.gettempdir(), 'sor-chrome-*')))
        before = profiles()
        with mock.patch.object(testrun, 'find_chrome', return_value=fake):
            code, out, err = self.sor('test')
        self.assertNotEqual(code, 0)
        self.assertIn('Chrome did not start', err)
        self.assertIn('SOR_CHROME', err)
        self.assertEqual(glob.glob(os.path.join(self.dir, 'out', '.sor-test-*')), [])
        self.assertEqual(profiles() - before, set())

    def test_the_chrome_named_by_sor_chrome_is_found_first(self):
        fake = write(self.dir, 'my-chrome', '')
        with mock.patch.object(testrun, 'CHROMES', [fake, '/nonexistent']):
            self.assertEqual(testrun.find_chrome(), fake)
        with mock.patch.object(testrun, 'CHROMES', ['', '/nonexistent']), mock.patch.object(shutil, 'which', return_value=None):
            self.assertIsNone(testrun.find_chrome())

    def run_with_page_stubbed(self, parts):
        """testrun.run with the browser replaced: (results, the script handed to the page, the ids it was asked for)."""
        base.make_project(self.dir, parts)
        seen = {}

        def page(target, script, ids, timeout):
            seen['script'], seen['ids'] = script, ids
            return [{'id': i, 'status': 'pass'} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            results, summary = testrun.run(Project(self.dir))
        return results, seen

    def test_tests_that_need_no_browser_are_decided_without_one(self):
        wrong = doc('Extra', 'More tests.', rules=['- **a** - Thing.'], tests=[
            '- **a** - manual one.', '  manual: look at it'])
        results, seen = self.run_with_page_stubbed({'targets/web': TARGET + '- **fps** - a benchmark.\n  measure: fps ≥ 30\n'
                                                    '- **path-bad** - a wrong probe.\n  expect: nosuch(x) = 1\n',
                                                    'extra': wrong})
        self.assertEqual(results['extra/test:a']['status'], 'manual')
        self.assertEqual(results['targets/web/test:fps']['status'], 'skipped')
        self.assertIn('benchmarks', results['targets/web/test:fps']['message'])
        self.assertEqual(results['targets/web/test:path-bad']['status'], 'fail')
        self.assertTrue(results['targets/web/test:path-bad']['message'].startswith('test error:'))
        self.assertEqual(seen['ids'], ['targets/web/test:path'])
        self.assertEqual(results['targets/web/test:path']['status'], 'pass')
        self.assertIn('targets/web/test:path', seen['script'])

    def test_a_test_can_be_asked_for_by_part_item_or_id(self):
        base.make_project(self.dir, {'targets/web': TARGET})
        asked = []

        def page(target, script, ids, timeout):
            asked.append(ids)
            return [{'id': i, 'status': 'pass'} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            testrun.run(Project(self.dir), only=['targets/web'])
            testrun.run(Project(self.dir), only=['targets/web/path'])
            testrun.run(Project(self.dir), only=['nothing'])
        self.assertEqual(asked, [['targets/web/test:path'], ['targets/web/test:path']])

    def strength_project(self, tests):
        self.project({'targets/web': TARGET, 'lim': doc('Limits', 'How many errors.', rules=['- **limit** - At most {max: 5} errors.'],
                                                       tests=tests)})
        project = Project(self.dir)
        return {t.id: {'status': 'pass'} for t in project.all_items() if t.is_test and t.part.id == 'lim'}

    def strength(self, tests, mutants_pass):
        """`sor test --strength` with the browser replaced: every test passes, and so do the changed versions when
        mutants_pass. (exit code, output, number of changed versions that were run)"""
        results = self.strength_project(tests)
        ran = []

        def page(target, script, ids, timeout):
            ran.extend(ids)
            return [{'id': i, 'status': 'pass' if mutants_pass else 'fail'} for i in ids], {}

        with mock.patch.object(testrun, 'run', return_value=(results, {})), mock.patch.object(testrun, 'run_page', page):
            code, out, err = self.sor('test', '--strength')
        self.assertEqual(err, '')
        return code, out, len(ran)

    CHECKS = ['- **limit** - the cap holds.', '  expect: count(errors) = {limit.max}']
    NO_VALUE = ['- **plain** - nothing to compare with.', '  expect: count(errors) = 0', '  bug: P-1']

    def test_strength_names_the_passing_tests_it_cannot_vary_and_does_not_fail_on_them(self):
        code, out, ran = self.strength(self.CHECKS + self.NO_VALUE, mutants_pass=False)
        self.assertEqual(code, 0, out)
        self.assertGreater(ran, 0)
        self.assertIn('no weak tests: every value that was changed made its test fail', out)
        self.assertRegex(out, r'IDLE\s+lim/test:plain\s+it refers to no \{value\} to change')
        self.assertNotIn('lim/test:limit', out.split('IDLE')[1])
        self.assertIn('nothing to vary in 1 passing test(s)', out)
        self.assertRegex(out, r'\d+ reruns of 1 of 2 passing tests')

    def test_strength_with_nothing_changed_at_all_does_not_claim_the_tests_are_strong(self):
        code, out, ran = self.strength(self.NO_VALUE + ['- **proven** - says what it proves.', '  proves: {limit}', '  expect: count(errors) = 0'],
                                       mutants_pass=True)
        self.assertEqual((code, ran), (0, 0))
        self.assertIn('0 reruns of 0 of 2 passing tests', out)
        self.assertIn('nothing was changed: strength says nothing about these tests', out)
        self.assertNotIn('every value', out)
        self.assertEqual(out.count('IDLE'), 2)

    def test_strength_still_fails_on_a_weak_test_and_lists_the_idle_ones_after_it(self):
        code, out, ran = self.strength(self.CHECKS + self.NO_VALUE, mutants_pass=True)
        self.assertEqual(code, 1)
        self.assertIn('WEAK   lim/test:limit', out)
        self.assertLess(out.index('WEAK'), out.index('IDLE'))

    def test_a_test_that_only_measures_is_idle_with_that_reason(self):
        code, out, ran = self.strength(['- **budget** - it is fast.', '  measure: clause-coverage ≥ 50'], mutants_pass=False)
        self.assertEqual((code, ran), (0, 0))
        self.assertRegex(out, r'IDLE\s+lim/test:budget\s+it only measures')

    def test_an_id_that_matches_no_test_is_an_error_and_not_a_pass(self):
        for ids in (['targets/web/nothing'], ['targets/web', 'typo']):
            with self.no_browser():
                code, out, err = self.sor('test', *ids)
            self.assertEqual(code, 2, ids)
            self.assertIn(f'no test matches {ids[-1]}', err)
            self.assertNotIn('passed', out)
        with self.no_browser():
            self.assertEqual(self.sor('test', '--strength', 'typo')[0], 2)

    def test_the_root_part_is_selected_by_its_name_and_by_its_tests(self):
        base.make_project(self.dir, {'targets/web': TARGET}, root_text=doc(
            'Demo', 'A project the tests use.', rules=['- **title** - The page has a title.', '- **out-of-scope** - Other.'],
            tests=['- **title** - It is there.', '  expect: count(errors) = 0']))
        project = Project(self.dir)
        root_test = project.items['test:title']
        for ident in ('ROOT', 'CLAUSES', 'SPECOFRECORD', 'title', 'test:title'):
            self.assertTrue(testrun.selects(project, root_test, [ident]), ident)
        web_test = project.items['targets/web/test:path']
        self.assertFalse(testrun.selects(project, web_test, ['ROOT']))
        self.assertFalse(testrun.selects(project, root_test, ['targets']))
        asked = []

        def page(target, script, ids, timeout):
            asked.append(ids)
            return [{'id': i, 'status': 'pass'} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            code, out, err = self.sor('test', 'ROOT')
        self.assertEqual((code, err, asked), (0, '', [['test:title']]))

    def results(self, **status):
        found = {tid: {'status': s, 'message': ''} for tid, s in status.items()}
        summary = {'clause_coverage': 100.0, 'line_coverage': None, 'unproven': [], 'lines': (0, 0), 'by_clause': {}}
        return mock.patch.object(testrun, 'run', return_value=(found, summary))

    def test_out_writes_only_what_lock_can_use_and_the_exit_code_follows_the_failures(self):
        out_file = os.path.join(self.dir, 'results.json')
        with self.results(a='pass', b='fail', c='skipped', d='manual'):
            code, out, _ = self.sor('test', '--out', out_file)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(read(out_file)), {'a': 'pass', 'b': 'fail'})
        self.assertIn('1 passed, 1 failed, 1 skipped, 1 manual', out)
        with self.results(a='pass'):
            self.assertEqual(self.sor('test')[0], 0)

    def test_lock_run_tests_locks_with_the_results_of_the_runner(self):
        with self.results(**{'targets/web/test:path': 'pass'}):
            code, out, _ = self.sor('lock', '--all', '--run-tests')
        self.assertEqual(code, 0, out)
        self.assertIn('1 passed', out)
        self.assertEqual(json.loads(lock_bytes(self.dir))['targets/web/test:path']['result'], 'pass')

    def test_lock_run_tests_does_not_lock_a_failing_test_unless_allowed(self):
        with self.results(**{'targets/web/test:path': 'fail'}):
            code, out, _ = self.sor('lock', '--all', '--run-tests')
        self.assertEqual(code, 2)
        self.assertIn('1 failed', out)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))

    def test_lock_run_tests_in_a_project_without_a_web_target_locks_nothing_and_says_why(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        base.make_project(other.name)
        code, _, err = run_sor(other.name, 'lock', '--all', '--run-tests')
        self.assertEqual(code, 1)
        self.assertIn('no web target', err)
        self.assertFalse(os.path.exists(os.path.join(other.name, 'sor', 'sor-lock.json')))

    def test_lock_run_tests_without_a_browser_locks_nothing(self):
        with mock.patch.object(testrun, 'find_chrome', return_value=None):
            code, _, err = self.sor('lock', '--all', '--run-tests')
        self.assertEqual(code, 1)
        self.assertIn('no Chrome or Edge found', err)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))

    @unittest.skipUnless(shutil.which('osascript'), 'the page script is parsed by JavaScriptCore (macOS)')
    def test_the_script_injected_into_the_page_is_valid_javascript(self):
        project = Project(self.dir)
        target = testrun.web_targets(project)[0]
        item = project.items['targets/web/test:path']
        js = testrun.Test(project, target, item).js()
        script = testrun.harness(target, [(item.id, js)], testrun.before_each(project, target))
        inner = script.split('<script>', 1)[1].rsplit('</script>', 1)[0]
        driver = write(self.dir, 'parse.js', 'try { new Function(%s); "ok" } catch (e) { "SYNTAX " + e.message }' % json.dumps(inner))
        done = subprocess.run(['osascript', '-l', 'JavaScript', driver], capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), 'ok', done.stderr)


# --- unreadable files ---------------------------------------------------------------------------------------

@unittest.skipUnless(CAN_CHMOD, 'file modes do not stop root, and Windows has no chmod')
class TestUnreadableFiles(Flow):
    def test_a_spec_file_that_cannot_be_read_is_named_in_a_message_not_a_traceback(self):
        self.greet_project()
        path = os.path.join(self.spec, 'greet.md')
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o644)
        for command in (('status',), ('check',), ('parts',), ('lock', '--all')):
            code, out, err = self.sor(*command)
            self.assertEqual(code, 2, command)
            self.assertIn('greet.md', err, command)
            self.assertIn('Permission denied', err, command)


# --- .tests.md files ----------------------------------------------------------------------------------------

class TestTestsFiles(Flow):
    """Long tests may live in `<part>.tests.md` (SPEC §13); they are the part's tests, wherever they are written."""

    def part(self, tests_file, tests=(), main_tests=()):
        rules = ['- **limits** - Zoom stays inside the limits.', '- **step** - A step is {factor: 1.2}.']
        self.project({'zoom': doc('Zoom', rules=rules, tests=list(main_tests))})
        write(self.dir, 'sor/zoom.tests.md', tests_file)
        return Project(self.dir)

    def test_the_tests_in_the_file_belong_to_the_part(self):
        project = self.part('## Tests\n- **limits** - stays inside.\n  expect: a\n')
        self.assertIn('zoom/test:limits', project.items)
        self.assertEqual(project.items['zoom/test:limits'].part.id, 'zoom')
        self.assert_clean(project)

    def test_a_test_named_in_both_files_is_a_duplicate_reported_where_the_second_one_is(self):
        project = self.part('## Tests\n- **limits** - second.\n  expect: b\n',
                            main_tests=['- **limits** - first.', '  expect: a'])
        found = [p for p in project.check() if p.kind == 'duplicate']
        self.assertEqual([p.where for p in found], ['zoom.tests.md:2'])
        self.assertIn('limits', found[0].text)
        self.assertIn('zoom.md', found[0].text)

    def test_the_first_test_wins_and_the_second_does_not_replace_it(self):
        project = self.part('## Tests\n- **limits** - second.\n  expect: b\n',
                            main_tests=['- **limits** - first.', '  expect: a'])
        self.assertIn('first', ' '.join(t for _, t in project.items['zoom/test:limits'].lines))

    def test_a_test_named_twice_inside_the_file_is_reported(self):
        project = self.part('## Tests\n- **limits** - one.\n  expect: a\n- **limits** - two.\n  expect: b\n')
        found = [p for p in project.check() if p.kind == 'duplicate']
        self.assertEqual([p.where for p in found], ['zoom.tests.md:4'])

    def test_a_tests_file_with_no_part_is_reported(self):
        project = self.part('## Tests\n- **limits** - stays inside.\n  expect: a\n')
        write(self.dir, 'sor/ghost.tests.md', '## Tests\n- **x** - proves nothing.\n  expect: a\n')
        found = [p for p in Project(self.dir).check() if p.kind == 'tests file']
        self.assertEqual([p.where for p in found], ['ghost.tests.md'])
        self.assertIn('ghost', found[0].text)
        self.assertEqual(self.sor('check')[0], 2)

    def test_a_broken_reference_in_a_test_is_reported_in_the_tests_file(self):
        project = self.part('## Tests\n- **limits** - stays inside.\n  expect: {nowhere/at-all} = 1\n')
        found = [p for p in project.check() if p.kind == 'broken']
        self.assertEqual([p.where for p in found], ['zoom.tests.md:3'])

    def test_a_test_that_proves_nothing_is_reported_in_the_tests_file(self):
        project = self.part('## Tests\n- **nothing** - proves no rule.\n  expect: a\n')
        found = [p for p in project.check() if p.kind == 'orphan test']
        self.assertEqual([p.where for p in found], ['zoom.tests.md:2'])

    def test_anything_but_tests_in_a_tests_file_is_reported_and_not_dropped(self):
        project = self.part('## Rules\n- **extra** - A rule that would silently not exist.\n\n'
                            '## Tests\n- **limits** - stays inside.\n  expect: a\n')
        found = [p for p in project.check() if p.kind == 'misplaced']
        self.assertEqual([p.where for p in found], ['zoom.tests.md:2'])
        self.assertIn('holds only tests', found[0].text)

    def test_a_marker_for_a_test_in_the_file_finds_it(self):
        self.part('## Tests\n- **limits** - stays inside.\n  expect: a\n')
        write(self.dir, 'out/zoom.js', '// @clause test zoom/limits\ncheck()\n// @clause end\n'
                                       '// @clause zoom/limits\nclamp()\n// @clause end\n')
        self.assert_clean(Project(self.dir))
        self.assertEqual(self.sor('check')[0], 0)

    def test_a_problem_in_the_file_blocks_a_scoped_lock_of_its_part(self):
        self.part('## Tests\n- **limits** - stays inside.\n  expect: {nowhere/at-all} = 1\n')
        self.sor('claim', 'zoom', '--as', 'alice')
        code, out, _ = self.sor('lock', '--as', 'alice', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('zoom.tests.md:3', out)


# --- sor new --why ------------------------------------------------------------------------------------------

class TestNewWhy(Flow):
    def test_a_why_that_the_reader_would_split_into_a_setting_is_refused_and_nothing_is_written(self):
        self.project()
        before = tree(self.dir)
        code, out, err = self.sor('new', 'render', '--why', 'Draws the world. Owner: sebastian')
        self.assertEqual(code, 2)
        self.assertIn('"Owner:" in the sentence would be read as a setting', err + out)
        self.assertEqual(tree(self.dir), before)

    def test_a_colon_that_is_not_a_setting_is_fine(self):
        self.project()
        self.assertEqual(self.sor('new', 'render', '--why', 'Draws the world: sky, ground and the owner of the sun.')[0], 0)
        self.assertEqual(Project(self.dir).parts['render'].header['Why'], 'Draws the world: sky, ground and the owner of the sun.')


# --- plugins/sync-tools.sh ----------------------------------------------------------------------------------

@unittest.skipUnless(shutil.which('sh') and shutil.which('diff') and shutil.which('mktemp'), 'needs a POSIX shell')
class TestSyncTools(unittest.TestCase):
    """Runs the script on a copy of the repository's tools, plugin and SPEC.md, never on the real plugin."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store')
        shutil.copytree(os.path.join(REPO, 'tools'), os.path.join(self.root, 'tools'), ignore=ignore)
        shutil.copytree(os.path.join(REPO, 'plugins'), os.path.join(self.root, 'plugins'), ignore=ignore)
        shutil.copy(os.path.join(REPO, 'SPEC.md'), os.path.join(self.root, 'SPEC.md'))
        self.plugin = os.path.join(self.root, 'plugins', 'specofrecord')
        self.extension = os.path.join(self.root, 'editors', 'vscode')
        write(self.root, 'editors/vscode/package.json', '{}\n')   # all the script needs of the extension: that it exists
        self.sync()   # the copy starts in sync, whatever state the real plugin is in

    def sh(self, *args):
        done = subprocess.run(['sh', os.path.join(self.root, 'plugins', 'sync-tools.sh'), *args],
                              capture_output=True, text=True)
        return done.returncode, done.stdout, done.stderr

    def sync(self):
        code, out, err = self.sh()
        self.assertEqual(code, 0, err)
        self.assertIn('copied tools/ and the cheat sheet', out)

    def test_a_copy_in_sync_passes_and_check_changes_nothing(self):
        before = tree(self.root)
        code, out, err = self.sh('--check')
        self.assertEqual((code, err), (0, ''))
        self.assertIn('plugin tools and cheat sheet are in sync', out)
        self.assertEqual(tree(self.root), before)

    def test_the_plugin_carries_the_current_tools_and_the_cheat_sheet(self):
        for name in sorted(os.listdir(os.path.join(self.root, 'tools', 'py', 'sorlib'))):
            if name.endswith('.py'):
                self.assertEqual(read(os.path.join(self.plugin, 'tools', 'sorlib', name)),
                                 read(os.path.join(self.root, 'tools', 'py', 'sorlib', name)), name)
        sheet = read(os.path.join(self.plugin, 'skills', 'specofrecord', 'reference', 'format-cheatsheet.md'))
        self.assertTrue(sheet.startswith('# Spec of Record: the format cheat sheet'))
        self.assertIn('CC BY 4.0', sheet)
        self.assertNotIn('## Cheat sheet', sheet)

    def stale(self, change):
        change()
        code, out, err = self.sh('--check')
        self.assertEqual(code, 1, out)
        self.assertIn('the plugin is out of date: run sh plugins/sync-tools.sh', err)
        self.sync()
        self.assertEqual(self.sh('--check')[0], 0)

    def test_a_tool_edited_in_tools_makes_the_plugin_stale_until_it_is_synced(self):
        def change():
            with open(os.path.join(self.root, 'tools', 'py', 'sorlib', 'lint.py'), 'a', encoding='utf8') as fh:
                fh.write('\n# changed\n')
        self.stale(change)

    def test_the_spec_cheat_sheet_edited_makes_the_plugin_stale(self):
        self.stale(lambda: replace_in(os.path.join(self.root, 'SPEC.md'), '## Cheat sheet', '## Cheat sheet\n\nA new line.'))

    def test_a_file_edited_inside_the_plugin_is_overwritten_by_the_sync(self):
        def change():
            with open(os.path.join(self.plugin, 'tools', 'sor.py'), 'a', encoding='utf8') as fh:
                fh.write('\n# edited in the plugin\n')
        self.stale(change)

    def test_a_file_missing_from_the_plugin_or_left_over_in_it_is_stale(self):
        self.stale(lambda: os.remove(os.path.join(self.plugin, 'tools', 'sorlib', 'views.py')))
        self.stale(lambda: write(self.plugin, 'tools/sorlib/leftover.py', 'x = 1\n'))
        self.assertFalse(os.path.exists(os.path.join(self.plugin, 'tools', 'sorlib', 'leftover.py')))

    def test_the_sync_leaves_the_rest_of_the_plugin_alone(self):
        kept = {k: v for k, v in tree(self.plugin).items() if not k.startswith('tools')
                and 'format-cheatsheet.md' not in k}
        self.sync()
        now = tree(self.plugin)
        for k, v in kept.items():
            self.assertEqual(now.get(k), v, k)

    def test_the_extension_carries_the_current_javascript_tool_and_nothing_else(self):
        ext_tools = os.path.join(self.extension, 'tools')
        js = os.path.join(self.root, 'tools', 'js')
        self.assertEqual(sorted(os.listdir(ext_tools)), ['sor.js', 'sorlib'])   # no Python, and not the tests or the README next to the tool in tools/js
        self.assertEqual(read(os.path.join(ext_tools, 'sor.js')), read(os.path.join(js, 'sor.js')))
        names = sorted(n for n in os.listdir(os.path.join(js, 'sorlib')) if n.endswith('.js'))
        self.assertGreater(len(names), 5)
        self.assertEqual(sorted(os.listdir(os.path.join(ext_tools, 'sorlib'))), names)
        for name in names:
            self.assertEqual(read(os.path.join(ext_tools, 'sorlib', name)), read(os.path.join(js, 'sorlib', name)), name)
        self.assertEqual(read(os.path.join(self.extension, 'package.json')), '{}\n')   # the rest of the extension is left alone

    def test_an_extension_that_still_has_the_python_tool_is_stale_and_the_sync_removes_it(self):
        write(self.extension, 'tools/sor.py', 'print(1)\n')
        write(self.extension, 'tools/sorlib/cli.py', 'x = 1\n')
        code, out, err = self.sh('--check')
        self.assertEqual(code, 1, out)
        self.sync()
        self.assertEqual(sorted(os.listdir(os.path.join(self.extension, 'tools'))), ['sor.js', 'sorlib'])
        self.assertEqual(self.sh('--check')[0], 0)

    def stale_extension(self, change):
        change()
        code, out, err = self.sh('--check')
        self.assertEqual(code, 1, out)
        self.assertIn('the extension copy of tools/ is out of date: run sh plugins/sync-tools.sh', err)
        self.assertNotIn('the plugin is out of date', err)   # the plugin copy is fine, and the message says whose copy is not
        self.sync()
        self.assertEqual(self.sh('--check')[0], 0)

    def test_an_extension_copy_edited_missing_or_left_over_is_stale_until_it_is_synced(self):
        def edit():
            with open(os.path.join(self.extension, 'tools', 'sor.js'), 'a', encoding='utf8') as fh:
                fh.write('\n// edited in the extension\n')
        self.stale_extension(edit)
        self.stale_extension(lambda: os.remove(os.path.join(self.extension, 'tools', 'sorlib', 'views.js')))
        self.stale_extension(lambda: write(self.extension, 'tools/sorlib/leftover.js', 'x = 1;\n'))
        self.assertFalse(os.path.exists(os.path.join(self.extension, 'tools', 'sorlib', 'leftover.js')))

    def test_a_change_in_tools_js_makes_the_extension_stale_and_the_plugin_not(self):
        with open(os.path.join(self.root, 'tools', 'js', 'sorlib', 'views.js'), 'a', encoding='utf8') as fh:
            fh.write('\n// changed\n')
        self.stale_extension(lambda: None)

    def test_a_repository_without_the_extension_gets_no_extension_copy(self):
        shutil.rmtree(os.path.join(self.root, 'editors'))
        code, out, err = self.sh()
        self.assertEqual((code, err), (0, ''))
        self.assertNotIn('editors/vscode', out)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'editors')))
        code, out, err = self.sh('--check')
        self.assertEqual((code, err), (0, ''))
        self.assertNotIn('extension', out)


if __name__ == '__main__':
    unittest.main()
