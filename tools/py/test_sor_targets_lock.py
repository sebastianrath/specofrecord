"""Tests for code per target in the lock (SPEC §9, §11): the `Targets:` setting, a line `clause@target` for each target's code with
`built`, "behind" (a target whose code was accepted for an older text of the clause), a lock that refuses while one is behind unless
`--allow-behind` says so, and a lock that stays in format 1 until a clause has such lines.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
"""
import json
import os
import shutil
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import hook                      # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

doc, write, read = base.doc, base.write, base.read


def target(name, path):
    return doc(name.title(), 'Where the code of one language lives.', rules=[f'- **code** - The code is under {{path: {path}}}.'])


class Targeted(flows.Flow):
    """greet/hello and greet/bye, with code for hello in src_py/ and in src_ts/; `Targets: py, ts` unless a test says otherwise."""
    PY = '# @clause greet/hello\nHELLO = "Hello"\n# @clause end\n'
    TS = '// @clause greet/hello\nexport const HELLO = "Hello";\n// @clause end\n'
    TESTS = ['- **hello** - looks right.', '  manual: look', '- **bye** - looks right.', '  manual: look']

    def build(self, targets='py, ts', part_targets=None, rules=None, tests=None):
        shutil.rmtree(os.path.join(self.dir, 'sor'), ignore_errors=True)
        header = [f'Targets: {part_targets}'] if part_targets else []
        self.project({'targets/py': target('py', 'src_py/'), 'targets/ts': target('ts', 'src_ts/'),
                      'greet': doc('Greet', 'Says hello.', rules=rules or ['- **hello** - The greeting is "Hello".',
                                                                          '- **bye** - The farewell is "Bye".'],
                                   tests=tests or self.TESTS, header=header)})
        if targets:
            root = os.path.join(self.spec, 'SPECOFRECORD.md')
            write(self.dir, 'sor/SPECOFRECORD.md', read(root).replace('Why: A project the tests use.',
                                                                      f'Why: A project the tests use.\nTargets: {targets}', 1))

    def setUp(self):
        super().setUp()
        self.build()
        self.py = write(self.dir, 'src_py/greet.py', self.PY)
        self.ts = write(self.dir, 'src_ts/greet.ts', self.TS)
        self.spec_file = os.path.join(self.spec, 'greet.md')

    def lock_all(self, *args):
        code, out, err = self.sor('lock', '--all', *args)
        self.assertEqual(code, 0, out + err)
        return out

    def raw(self):
        return json.loads(flows.lock_bytes(self.dir))

    def findings(self, *statuses):
        code, out, _ = self.sor('status', '--json')
        return [f for f in json.loads(out)['findings'] if not statuses or f['status'] in statuses]

    def change_clause(self, new='The greeting is "Hi".'):
        flows.replace_in(self.spec_file, 'The greeting is "Hello".', new)


class TestTheLockLines(Targeted):
    def test_each_target_gets_a_line_with_built_and_the_clause_keeps_no_code(self):
        self.lock_all()
        raw = self.raw()
        text = raw['greet/hello']['text']
        self.assertNotIn('code', raw['greet/hello'])
        for t in ('py', 'ts'):
            line = raw[f'greet/hello@{t}']
            self.assertEqual((line['kind'], line['of'], line['target'], line['built']), ('code', 'greet/hello', t, text))
            self.assertEqual(len(line['code']), 12)
        self.assertTrue(flows.lock_bytes(self.dir).startswith(b'{\n"*format": 2,\n'))

    def test_the_lock_reads_back_the_same_and_a_second_lock_changes_nothing(self):
        self.lock_all()
        first = flows.lock_bytes(self.dir)
        self.lock_all()
        self.assertEqual(flows.lock_bytes(self.dir), first)
        project = Project(self.dir)
        entries = lockfile.read(project)
        self.assertEqual(sorted(entries['greet/hello']['targets']), ['py', 'ts'])
        self.assertEqual(lockfile.render(entries).encode('utf8'), first)

    def test_rehash_leaves_a_lock_with_lines_as_it_is(self):
        self.lock_all()
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', '--rehash')
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to rewrite', out)
        self.assertEqual(flows.lock_bytes(self.dir), before)

    def test_a_project_without_targets_setting_keeps_format_1_and_its_bytes(self):
        self.build(targets=None)
        self.lock_all()
        raw = self.raw()
        self.assertNotIn(b'*format', flows.lock_bytes(self.dir))
        self.assertFalse([k for k in raw if '@' in k])
        self.assertIn('code', raw['greet/hello'])

    def test_two_languages_make_two_lines_and_one_unchanged_status(self):
        self.lock_all()
        self.assertEqual(self.sor('status')[0], 0)
        self.assertEqual(self.findings(), [])


class TestAddingTargetsToAnOldLock(Targeted):
    def test_it_is_no_drift_nothing_is_behind_and_the_lock_stays_format_1_until_a_clause_is_locked(self):
        self.build(targets=None)
        self.lock_all()
        before = flows.lock_bytes(self.dir)
        self.build(targets='py, ts')
        write(self.dir, 'sor/sor-lock.json', before.decode('utf8'))   # the build wiped sor/, lock included
        found = self.findings()
        self.assertEqual({f['status'] for f in found}, {'changed'}, found)   # the root file, which now says its targets
        self.assertEqual([f['key'] for f in found], ['ROOT'])
        self.assertNotIn(b'*format', flows.lock_bytes(self.dir))
        code, out, _ = self.sor('lock', 'ROOT')
        self.assertEqual(code, 0, out)
        self.assertNotIn(b'*format', flows.lock_bytes(self.dir))     # the root has no code, so no line yet
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)
        self.assertTrue(flows.lock_bytes(self.dir).startswith(b'{\n"*format": 2,\n'))
        raw = self.raw()
        self.assertIn('greet/hello@py', raw)
        self.assertNotIn('greet/bye@py', raw)    # a clause without code has no lines
        self.assertEqual(self.findings('behind', 'drift'), [])

    def test_a_scoped_lock_leaves_a_lock_with_both_kinds_of_entry_and_each_is_still_compared_as_it_was_written(self):
        bye_py = '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n'
        self.build(targets=None)
        write(self.dir, 'src_py/bye.py', bye_py)
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        self.lock_all()
        old = flows.lock_bytes(self.dir).decode('utf8')
        self.build(targets='py, ts')
        write(self.dir, 'sor/sor-lock.json', old)
        self.assertEqual(self.sor('lock', 'ROOT', 'greet/hello')[0], 0)
        raw = self.raw()
        self.assertIn('greet/hello@py', raw)                      # locked: per target
        self.assertNotIn('greet/bye@py', raw)                     # not locked yet: still one joined hash
        self.assertIn('code', raw['greet/bye'])
        self.assertEqual(self.findings(), [])
        write(self.dir, 'src_py/bye.py', bye_py.replace('"Bye"', '"Goodbye"'))        # drift in the joined entry is still drift
        self.assertEqual([(f['status'], f['key']) for f in self.findings()], [('drift', 'greet/bye')])
        write(self.dir, 'src_py/bye.py', bye_py)
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Hi'))             # and drift in a per-target entry names its language
        self.assertEqual([(f['key'], f['detail']) for f in self.findings('drift')], [('greet/hello', 'ts')])
        write(self.dir, 'src_ts/greet.ts', self.TS)
        flows.replace_in(self.spec_file, 'The farewell is "Bye".', 'The farewell is "Goodbye".')
        write(self.dir, 'src_py/bye.py', bye_py.replace('"Bye"', '"Goodbye"'))
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Goodbye";\n// @clause end\n')
        self.assertEqual(self.sor('lock', 'greet/bye')[0], 0)
        raw = self.raw()
        self.assertIn('greet/bye@ts', raw)                        # the second clause moves to lines when it is locked
        self.assertNotIn('code', raw['greet/bye'])
        self.assertEqual(self.sor('status')[0], 0)

    def test_a_project_that_drops_targets_is_read_the_same_way_back_and_its_next_lock_is_format_1(self):
        self.lock_all()
        targeted = flows.lock_bytes(self.dir).decode('utf8')
        self.build(targets=None)
        write(self.dir, 'sor/sor-lock.json', targeted)
        found = self.findings()
        self.assertEqual([(f['status'], f['key']) for f in found], [('changed', 'ROOT')])     # only the root, which lost the line
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.assertNotIn(b'*format', flows.lock_bytes(self.dir))
        self.assertFalse([k for k in self.raw() if '@' in k])
        self.assertIn('code', self.raw()['greet/hello'])

    def test_a_manual_check_a_person_confirmed_survives_the_move_to_targets(self):
        self.build(targets=None)
        self.assertEqual(self.sor('lock', '--all', '--confirm', 'greet/test:hello')[0], 0)
        self.assertEqual(self.raw()['greet/test:hello']['result'], 'checked')
        lock = read(os.path.join(self.spec, 'sor-lock.json'))
        self.build(targets='py, ts')
        write(self.dir, 'sor/sor-lock.json', lock)
        project = Project(self.dir)
        scan = Scan(project)
        self.assertIn('greet/test:hello', lockfile.checked_manual(project, scan, lockfile.read(project)))


class TestTheHandEditCase(Targeted):
    def setUp(self):
        super().setUp()
        self.lock_all()

    def test_drift_names_the_language_a_person_changed(self):
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        found = self.findings('drift')
        self.assertEqual([(f['key'], f['detail']) for f in found], [('greet/hello', 'py')])
        self.assertIn('src_py/greet.py', found[0]['where'])
        self.assertNotIn('src_ts', found[0]['where'])
        self.assertEqual(self.sor('status')[0], 2)

    def test_the_clause_brought_in_line_leaves_the_other_language_behind_and_the_lock_refuses(self):
        before = flows.lock_bytes(self.dir)
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.change_clause()
        found = self.findings('changed')
        self.assertEqual(found[0]['detail'], 'code updated in py · not yet in ts')
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('behind  greet/hello  its code in ts', out)
        self.assertNotIn('code in py', out)
        self.assertIn('rebuild it (change that code)', out)
        self.assertIn('Only when the user has said that ts is rebuilt later', out)
        self.assertIn('--allow-behind <language>', out)
        self.assertNotIn('--allow-behind ts', out)                            # no flag ready to copy: it is the user's call
        self.assertEqual(flows.lock_bytes(self.dir), before)                  # a refusal writes nothing

    def test_allowing_it_locks_the_clause_and_the_language_stays_listed_as_behind(self):
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.change_clause()
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-behind', 'ts')
        self.assertEqual(code, 0, out)
        raw = self.raw()
        self.assertEqual(raw['greet/hello@py']['built'], raw['greet/hello']['text'])
        self.assertNotEqual(raw['greet/hello@ts']['built'], raw['greet/hello']['text'])
        found = self.findings('behind')
        self.assertEqual([(f['key'], f['detail']) for f in found], [('greet/hello', 'ts')])
        self.assertIn('src_ts/greet.ts', found[0]['where'])
        self.assertEqual(self.sor('status')[0], 1)

    def test_rebuilding_the_language_that_is_behind_is_not_drift_and_locking_clears_it(self):
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.change_clause()
        self.sor('lock', 'greet/hello', '--allow-behind', 'ts')
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Hi'))
        found = self.findings()
        self.assertEqual([(f['status'], f['detail']) for f in found], [('behind', 'ts (being rebuilt)')])
        self.assertIsNone(flows.reason(hook.pre_edit(flows.edit(self.ts, '"Hi"', '"Hi!"'))))     # the guard lets the rebuild go on
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)
        self.assertEqual(self.findings(), [])
        raw = self.raw()
        self.assertEqual(raw['greet/hello@ts']['built'], raw['greet/hello']['text'])

    def test_the_edit_guard_refuses_a_change_in_the_language_that_is_not_behind(self):
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.change_clause()
        self.sor('lock', 'greet/hello', '--allow-behind', 'ts')
        said = flows.reason(hook.pre_edit(flows.edit(self.py, '"Hi"', '"Hey"')))
        self.assertIn('Clauses come first', said)

    def test_a_second_language_drifting_on_top_of_the_first_is_more_drift_to_the_guard(self):
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))      # a person's change: drift in py already
        said = flows.reason(hook.pre_edit(flows.edit(self.ts, '"Hello"', '"Hey"')))
        self.assertIn('Clauses come first', said)

    def test_a_change_to_the_clause_alone_leaves_every_language_behind(self):
        self.change_clause()
        self.assertEqual(self.findings('changed')[0]['detail'], 'code not updated yet in py, ts')
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('its code in py, ts', out)
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')
        self.assertEqual(code, 0, out)
        self.assertEqual({f['detail'] for f in self.findings('behind')}, {'py, ts'})

    def test_allow_behind_names_a_target_that_exists(self):
        self.change_clause()
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-behind', 'rust')
        self.assertEqual(code, 2)
        self.assertIn('rust, which is no target', out)


class TestATableCellIsPartOfTheClause(Targeted):
    ROWS = ['- **hello** - The greeting per language.', '  | lang | text |', '  | en | Hello |', '  | fr | Salut |',
            '- **bye** - The farewell is "Bye".']

    def setUp(self):
        super().setUp()
        self.build(rules=self.ROWS)
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        self.lock_all()

    def test_a_spec_only_change_to_a_cell_leaves_every_language_behind(self):
        flows.replace_in(self.spec_file, '| fr | Salut |', '| fr | Bonjour |')
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('its code in py, ts', out)

    def test_rebuilding_one_language_is_not_enough(self):
        flows.replace_in(self.spec_file, '| fr | Salut |', '| fr | Bonjour |')
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('its code in ts', out)
        self.assertNotIn('its code in py', out)
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Hi'))
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)
        self.assertEqual(self.findings(), [])

    def test_allowing_it_leaves_the_language_listed_after_the_row_is_locked(self):
        flows.replace_in(self.spec_file, '| fr | Salut |', '| fr | Bonjour |')
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.assertEqual(self.sor('lock', 'greet/hello', '--allow-behind', 'ts')[0], 0)
        self.assertEqual([(f['key'], f['detail']) for f in self.findings('behind')], [('greet/hello', 'ts')])

    def test_a_row_with_code_of_its_own_is_behind_on_its_own_and_not_counted_twice(self):
        py = self.PY + 'FR = "Salut"  # @clause greet/hello/fr\n'
        ts = self.TS + 'export const FR = "Salut";  // @clause greet/hello/fr\n'
        write(self.dir, 'src_py/greet.py', py)
        write(self.dir, 'src_ts/greet.ts', ts)
        self.build(rules=self.ROWS)       # start the lock again with the row marked from the first lock: marking it later moves it
        self.lock_all()                   # out of what the item's code is built for, and that counts as a change of the item
        self.assertIn('greet/hello/fr@ts', self.raw())
        flows.replace_in(self.spec_file, '| fr | Salut |', '| fr | Bonjour |')
        write(self.dir, 'src_py/greet.py', py.replace('Salut', 'Bonjour'))
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('behind  greet/hello/fr  its code in ts', out)
        self.assertNotIn('behind  greet/hello  ', out)


class TestWhichTargetsApply(Targeted):
    def test_a_part_can_say_it_is_only_for_one_target(self):
        self.build(part_targets='py')
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        self.lock_all()
        self.change_clause()
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 2, out)
        self.assertIn('its code in py', out)
        self.assertNotIn('its code in py, ts', out)
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)    # ts does not apply, so it is not behind
        self.assertEqual(self.findings('behind'), [])

    def test_a_part_for_one_target_is_left_out_by_the_note_the_status_line_and_behind_alike(self):
        # The note about missing code was written before a part could limit its targets, and no test joined the two: it blamed a
        # Python-only clause for having no TypeScript. Everything that asks "which targets apply" has to answer the same.
        bye_py = '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n'
        for part_targets, reported in (('py', False), (None, True)):
            with self.subTest(part_targets=part_targets):
                self.build(part_targets=part_targets)
                write(self.dir, 'src_py/greet.py', self.PY + bye_py)
                write(self.dir, 'src_ts/greet.ts', self.TS)
                self.lock_all(*(('--allow-behind', 'ts') if reported else ()))   # the lock refuses a clause with no code in a language that applies
                code, status, _ = self.sor('status')
                self.assertEqual(code, 0, status)
                code, check, _ = self.sor('check')
                self.assertEqual(code, 0, check)
                for out in (status, check):
                    self.assertEqual('greet/bye' in out and 'none in ts' in out, reported, out)
                self.assertEqual(self.findings('behind'), [])

    def test_problems_with_a_targets_line(self):
        cases = {
            'a name that is no target': dict(targets='py, rust'),
            'a name twice': dict(targets='py, py'),
            'an empty name': dict(targets='py,, ts'),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.build(**kw)
                found = [p for p in Project(self.dir).check() if p.kind == 'targets']
                self.assertTrue(found, name)
        self.build(targets=None, part_targets='py')
        found = [p for p in Project(self.dir).check() if p.kind == 'targets']
        self.assertTrue(any('default in the root file' in p.text for p in found))
        self.build()
        self.assertEqual([p for p in Project(self.dir).check() if p.kind == 'targets'], [])


class TestAClauseWithNoCodeInALanguageThatApplies(Targeted):
    """`sor lock` asks a clause that is new, changed or built now to have code in every language that applies to it. The note of
    `sor check` and `sor status` counts the same way, and what stays unbuilt shows there."""
    BYE_PY = '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n'
    BYE_TS = '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n'
    NOTE = '1 clause(s) have code in py but none in ts: greet/bye'

    def setUp(self):
        super().setUp()
        self.lock_all()                                  # hello has code in both languages, bye has none yet
        write(self.dir, 'src_py/bye.py', self.BYE_PY)    # and now bye is built in Python only

    def test_a_clause_built_in_one_language_is_refused_and_allowing_it_leaves_a_note(self):
        self.assertEqual([f['key'] for f in self.findings('built')], ['greet/bye'])
        before = flows.lock_bytes(self.dir)
        code, out, _ = self.sor('lock', 'greet/bye')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/bye  it applies to ts', out)
        self.assertNotIn('--allow-behind ts', out)                         # no flag ready to copy: it is the user's call
        self.assertEqual(flows.lock_bytes(self.dir), before)
        code, out, _ = self.sor('lock', 'greet/bye', '--allow-behind', 'ts')
        self.assertEqual(code, 0, out)
        code, status, _ = self.sor('status')
        self.assertEqual(code, 0, status)
        self.assertIn(self.NOTE, status)
        self.assertIn(self.NOTE, self.sor('check')[1])                     # the refusal and the note agree on what lacks code

    def test_a_clause_that_is_new_is_asked_too(self):
        self.build(rules=['- **hello** - The greeting is "Hello".', '- **bye** - The farewell is "Bye".', '- **extra** - Says it twice.'])
        write(self.dir, 'src_py/extra.py', '# @clause greet/extra\nEXTRA = 2\n# @clause end\n')
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/extra', out)

    def test_a_later_change_to_an_allowed_clause_is_asked_again(self):
        self.assertEqual(self.sor('lock', 'greet/bye', '--allow-behind', 'ts')[0], 0)
        flows.replace_in(self.spec_file, 'The farewell is "Bye".', 'The farewell is "Goodbye".')
        write(self.dir, 'src_py/bye.py', self.BYE_PY.replace('Bye', 'Goodbye'))
        code, out, _ = self.sor('lock', 'greet/bye')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/bye', out)

    def test_adding_the_code_is_the_way_out(self):
        write(self.dir, 'src_ts/bye.ts', self.BYE_TS)
        self.assertEqual(self.sor('lock', 'greet/bye')[0], 0)
        self.assertNotIn('none in ts', self.sor('status')[1])

    def test_a_flag_that_names_another_language_does_not_allow_it(self):
        self.build(targets='py, ts')
        write(self.dir, 'src_py/bye.py', self.BYE_PY)
        code, out, _ = self.sor('lock', 'greet/bye', '--allow-behind', 'py')
        self.assertEqual(code, 2, out)
        self.assertIn('no code  greet/bye  it applies to ts', out)

    def test_nothing_is_asked_where_nothing_is_missing(self):
        # a part that is only for Python
        self.build(part_targets='py')
        write(self.dir, 'src_py/greet.py', self.PY + self.BYE_PY)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.assertNotIn('none in ts', self.sor('check')[1])
        # a project that never said its targets
        self.build(targets=None)
        write(self.dir, 'src_py/greet.py', self.PY + self.BYE_PY)
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        # a lock of another clause while this one is pending
        self.build()
        write(self.dir, 'src_py/greet.py', self.PY + self.BYE_PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)

    def test_only_the_clauses_in_the_scope_are_asked(self):
        # the command line cuts the findings down to the scope; accept() does not rely on that
        project = Project(self.dir)
        scan = Scan(project)
        old = lockfile.read(project)
        findings, _ = lockfile.status(project, scan, old)
        self.assertEqual([f.key for f in findings], ['greet/bye'])
        _, reasons = lockfile.accept(project, scan, {}, True, findings, old, scope={'greet/hello'})
        self.assertEqual([r for r in reasons if r.startswith('no code')], [])
        _, reasons = lockfile.accept(project, scan, {}, True, findings, old, scope={'greet/bye'})
        self.assertEqual(len([r for r in reasons if r.startswith('no code  greet/bye')]), 1)

    def test_a_review_of_an_allowed_clause_is_not_asked(self):
        # bye refers to hello; hello changes in both languages and is locked, so bye is flagged for review, not changed
        self.build(rules=['- **hello** - The greeting is "Hello".', '- **bye** - The farewell follows {hello}.'])
        write(self.dir, 'src_py/greet.py', self.PY + self.BYE_PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        self.assertEqual(self.sor('lock', '--all', '--allow-behind', 'ts')[0], 0)
        self.change_clause()
        write(self.dir, 'src_py/greet.py', (self.PY + self.BYE_PY).replace('Hello', 'Hi'))
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Hi'))
        self.assertEqual(self.sor('lock', 'greet/hello')[0], 0)
        self.assertEqual([(f['status'], f['key']) for f in self.findings()], [('stale', 'greet/bye')])
        self.assertEqual(self.sor('lock', 'greet/bye')[0], 0)

    def test_a_project_that_adds_a_second_language_is_not_refused_for_what_it_locked_before(self):
        self.build(targets=None)
        write(self.dir, 'src_py/greet.py', self.PY + self.BYE_PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        self.lock_all()
        before = flows.lock_bytes(self.dir).decode('utf8')
        self.build(targets='py, ts')
        write(self.dir, 'sor/sor-lock.json', before)                      # the build wiped sor/, lock included
        self.assertEqual([(f['status'], f['key']) for f in self.findings()], [('changed', 'ROOT')])
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        self.assertIn(self.NOTE, self.sor('status')[1])                    # and the note says what it lacks


class TestStatusAndKeys(Targeted):
    def test_the_other_commands_that_read_status_cope_with_a_language_that_is_behind(self):
        self.lock_all()
        self.change_clause()
        self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')
        for args in (('changes',), ('check',), ('markers', 'greet/hello'), ('show', 'greet/hello')):
            with self.subTest(args):
                code, out, err = self.sor(*args)
                self.assertNotIn('Traceback', out + err)
                self.assertIn(code, (0, 1), out + err)

    def test_behind_is_a_finding_and_status_json_gets_no_new_key(self):
        self.lock_all()
        code, out, _ = self.sor('status', '--json')
        keys = set(json.loads(out))
        self.change_clause()
        self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')
        code, out, _ = self.sor('status', '--json')
        self.assertEqual(set(json.loads(out)), keys)
        self.assertEqual([f['status'] for f in json.loads(out)['findings']], ['behind'])
        text = self.sor('status')[1]
        self.assertIn('recompile (1)', text)
        self.assertIn('behind', text)

    def test_a_clause_named_like_a_lock_line_is_a_problem(self):
        self.build(rules=['- **hello** - The greeting is "Hello".', '- **hello@py** - A clause named like a lock line.'])
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2, out)
        self.assertIn('greet/hello@py is also the name of something else', out)

    def test_the_evidence_fingerprint_follows_the_code_of_every_language(self):
        from sorlib import evidence
        self.build(tests=['- **hello** - says hello.', '  expect: ok', '  runs on: linux', '- **bye** - looks right.', '  manual: look'])

        def fingerprint():
            project = Project(self.dir)
            return evidence.fingerprints(project, Scan(project))['greet/test:hello']
        before = fingerprint()
        write(self.dir, 'src_ts/greet.ts', self.TS.replace('Hello', 'Hi'))
        changed = fingerprint()
        self.assertNotEqual(changed, before)
        write(self.dir, 'src_py/greet.py', self.PY.replace('Hello', 'Hi'))
        self.assertNotEqual(fingerprint(), changed)


class TestCodeThatIsSharedOrGone(Targeted):
    SHARED_PY = '# @clause greet/hello greet/bye\nHELLO = "Hello"\n# @clause end\n'
    SHARED_TS = '// @clause greet/hello greet/bye\nexport const HELLO = "Hello";\n// @clause end\n'

    def test_a_clause_that_shares_the_code_and_whose_lines_would_not_change_is_not_dragged_into_the_lock(self):
        write(self.dir, 'src_py/greet.py', self.SHARED_PY)
        write(self.dir, 'src_ts/greet.ts', self.SHARED_TS)
        self.lock_all()
        kept = {k: v for k, v in self.raw().items() if k.startswith('greet/bye')}
        self.assertIn('greet/bye@py', kept)
        self.change_clause()                       # the words of hello only: the code both clauses share stays as it is
        code, out, _ = self.sor('lock', 'greet/hello', '--allow-behind', 'py,ts')
        self.assertEqual(code, 0, out)
        self.assertNotIn('locking with them', out)
        self.assertEqual({k: v for k, v in self.raw().items() if k.startswith('greet/bye')}, kept)

    def test_a_clause_whose_code_is_gone_from_every_language_is_drift(self):
        self.lock_all()
        os.remove(self.py)
        os.remove(self.ts)
        found = self.findings()
        self.assertEqual([(f['status'], f['key'], f['where']) for f in found], [('drift', 'greet/hello', 'code removed')], found)


class TestTheGuardInATargetedProject(Targeted):
    def test_it_works_out_which_clauses_a_spec_edit_touches(self):
        # a failure here is swallowed (None: the edit is not blocked), so a claim would stop holding in a targeted project
        project = Project(self.dir)
        new = read(self.spec_file).replace('The greeting is "Hello".', 'The greeting is "Hi".')
        self.assertEqual(hook.spec_keys_touched(project, self.spec_file, new), {'greet/hello'})


class TestTheRealProjectsDoNotChange(unittest.TestCase):
    def test_their_locks_are_what_this_tool_would_write(self):
        for rel in ('examples/solar-system', 'editors/vscode'):
            with self.subTest(rel):
                project = Project(os.path.join(REPO, rel))
                self.assertFalse(project.targeted())
                with open(project.lock_path, encoding='utf8', newline='') as fh:
                    self.assertEqual(lockfile.render(lockfile.read(project)), fh.read())


if __name__ == '__main__':
    unittest.main()
