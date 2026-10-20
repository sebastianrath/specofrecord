"""Tests for what other parts and agents rely on: the JSON of `sor status`, the text of `sor markers` and `sor show`, the
rules that keep a lock safe, what the edit guard says, and the claims commands' refusals.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, no browser.
"""
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import hook                           # noqa: E402
from test_sor_flows import APP, GREET, Flow, accepted, edit, lock_bytes, reason, replace_in   # noqa: E402

doc, write, read = base.doc, base.write, base.read

PAIR = doc('Pair', 'Two clauses, one piece of code.',
           rules=['- **a** - The page says {text: A}.', '- **b** - The page says {text: B}.'],
           tests=['- **a** - says a.', '  expect: ok', '- **b** - says b.', '  expect: ok'])
PAIR_APP = '// @clause pair/a pair/b\nconsole.log("A", "B");\n// @clause end\n'

BODIES = doc('Bodies', 'The sky.', rules=['- **planets** - The planets:', '', '| Planet | Size |', '|---|---|', '| Mars | 5 |', '| Venus | 12 |'],
             tests=['- **planets** - there.', '  expect: ok'])
BODIES_APP = '// @clause bodies/planets\nconst planets = [5, 12];\n// @clause end\n'


class TestStatusJson(Flow):
    """`sor status --json` is what the editor extension reads."""

    def status(self, *args):
        code, out, _ = self.sor('status', '--json', *args)
        return code, json.loads(out)

    def test_a_changed_clause_is_a_finding_with_its_status_key_and_place(self):
        self.greet_project()
        replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        code, data = self.status()
        self.assertEqual(code, 1)
        self.assertEqual(sorted(data), ['claims', 'findings', 'locked', 'problems', 'tests_not_passed', 'tests_pending'])
        self.assertTrue(data['locked'])
        finding = next(f for f in data['findings'] if f['key'] == 'greet/hello')
        self.assertEqual((finding['status'], finding['where']), ('changed', 'out/app.js:4-6'))
        self.assertIn('values: text', finding['detail'])
        self.assertEqual((data['problems'], data['tests_not_passed'], data['claims']), ([], [], []))

    def test_code_that_changed_without_its_clause_is_drift_and_exits_two(self):
        self.greet_project()
        replace_in(self.app, '"Hello"', '"Hi"')
        code, data = self.status()
        self.assertEqual(code, 2)
        self.assertEqual([(f['status'], f['key']) for f in data['findings']], [('drift', 'greet/hello')])
        self.assertNotIn('by', data['findings'][0])   # not a git repository: nobody is named

    def test_a_clean_project_has_no_findings_and_exits_zero(self):
        self.greet_project()
        code, data = self.status()
        self.assertEqual((code, data['findings']), (0, []))

    def test_claims_are_listed_with_who_what_and_until_when(self):
        self.greet_project()
        self.claim(['greet/bye'], 'alice')
        data = self.status()[1]
        self.assertEqual(len(data['claims']), 1)
        claim = data['claims'][0]
        self.assertEqual((claim['agent'], claim['asked']), ('alice', ['greet/bye']))
        self.assertGreater(claim['until'], claim['since'])

    def test_a_problem_is_listed_and_exits_two(self):
        self.greet_project()
        write(self.dir, 'out/app.js', APP + '// @clause greet/nothing\nx();\n// @clause end\n')
        code, data = self.status()
        self.assertEqual(code, 2)
        self.assertEqual([p['kind'] for p in data['problems']], ['marker'])

    def test_before_the_first_lock_it_says_so_and_counts_what_is_new(self):
        self.greet_project(lock=False)
        code, out, _ = self.sor('status')
        self.assertEqual(code, 1)
        self.assertIn('no sor-lock.json yet: everything is new', out)
        self.assertRegex(out, r'\d+ new entries \(--all lists them\)')
        self.assertNotIn('recompile', out)
        self.assertIn('recompile', self.sor('status', '--all')[1])

    def test_tests_that_had_not_passed_at_the_last_lock_are_counted(self):
        self.greet_project(lock=False)
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        code, out, _ = self.sor('status')
        self.assertIn('1 test(s) had not passed at the last lock', out)
        self.assertIn('clauses, code and lock agree (but not every test passed)', out)
        self.assertEqual(self.status()[1]['tests_not_passed'], ['greet/test:hello'])


class TestMarkersCommand(Flow):
    """`sor markers`: where a clause's code is, or which clauses a line serves. The skill tells agents to use it."""

    def setUp(self):
        super().setUp()
        self.greet_project()
        write(self.dir, 'out/greet.test.js', '// @clause test greet/hello\nit("says hello", () => {});\n// @clause end\n')
        write(self.dir, 'out/whole.js', '// @clause greet\nwhole();\n// @clause end\n')
        accepted(self.dir)

    def test_a_clause_lists_its_code_and_the_code_of_its_test(self):
        code, out, _ = self.sor('markers', 'greet/hello')
        self.assertEqual(code, 0)
        self.assertIn('out/app.js:4-6  code  greet/hello', out)
        self.assertIn('out/greet.test.js:1-3  test  greet/test:hello', out)

    def test_a_clause_without_code_and_a_name_that_does_not_exist_say_so(self):
        replace_in(os.path.join(self.spec, 'greet.md'), '## Tests', '- **mute** - Says nothing.\n\n## Tests')
        self.assertEqual(self.sor('markers', 'greet/mute')[1].strip(), 'greet/mute has no code')
        code, out, _ = self.sor('markers', 'greet/nothing')
        self.assertEqual((code, out.strip()), (2, 'greet/nothing: no such item'))

    def test_a_part_lists_the_code_marked_with_the_part_itself(self):
        self.assertIn('out/whole.js:1-3  code  greet', self.sor('markers', 'greet')[1])

    def test_a_line_says_which_clauses_it_serves_with_their_words(self):
        code, out, _ = self.sor('markers', 'out/app.js:5')
        self.assertEqual(code, 0)
        self.assertIn('out/app.js:4-6  code', out)
        self.assertIn('- **hello** - The page says {text: Hello}.', out)

    def test_a_line_in_wiring_names_the_glue_and_a_part_is_described_by_its_why(self):
        self.assertIn('glue:out/app.js', self.sor('markers', 'out/app.js:2')[1])
        self.assertIn('greet  (greet.md) — Says hello.', self.sor('markers', 'out/whole.js:2')[1])

    def test_a_line_in_no_region_exits_two(self):
        write(self.dir, 'out/app.js', APP + '// outside\n')
        code, out, _ = self.sor('markers', 'out/app.js:10')
        self.assertEqual((code, out.strip()), (2, 'out/app.js:10 is in no @clause region'))

    def test_a_table_row_is_described_by_its_id_and_its_text(self):
        self.project({'bodies': BODIES})
        write(self.dir, 'out/rows.js', 'const mars = 5;  // @clause bodies/planets/Mars\n')
        out = self.sor('markers', 'out/rows.js:1')[1]
        self.assertIn('bodies/planets/Mars  | Mars | 5 |', out)

    def test_the_json_of_one_clause_says_whether_it_exists_and_where_its_code_is(self):
        code, out, _ = self.sor('markers', '--json', 'greet/hello')
        data = json.loads(out)
        self.assertEqual((code, data['id'], data['exists']), (0, 'greet/hello', True))
        self.assertEqual(data['regions'][0]['file'], 'out/app.js')
        code, out, _ = self.sor('markers', '--json', 'greet/nothing')
        self.assertEqual((code, json.loads(out)['exists']), (2, False))


class TestShowCommand(Flow):
    """`sor show`: the clauses with their code underneath."""

    def test_a_name_that_does_not_exist_exits_two(self):
        self.greet_project()
        code, out, _ = self.sor('show', 'greet/nothing')
        self.assertEqual((code, out.strip()), (2, 'greet/nothing: no such part or item'))

    def test_a_clause_shows_its_words_its_code_and_then_its_test_with_the_test_code(self):
        self.greet_project()
        write(self.dir, 'out/greet.test.js', '// @clause test greet/hello\nit("says hello", () => {});\n// @clause end\n')
        out = self.sor('show', 'greet/hello')[1]
        self.assertIn('# Greet  (greet.md)', out)
        self.assertIn('> out/app.js:4-6', out)
        self.assertIn('| console.log("Hello");', out)
        self.assertIn('- **hello** - says hello.', out)
        self.assertIn('> out/greet.test.js:1-3', out)

    def test_a_part_shows_every_item_with_its_code_under_it_and_the_code_of_the_whole_part_last(self):
        self.greet_project()
        write(self.dir, 'out/whole.js', '// @clause greet\nwhole();\n// @clause end\n')
        out = self.sor('show', 'greet')[1]
        self.assertLess(out.index('The page says {text: Hello}'), out.index('| console.log("Hello");'))
        self.assertIn('## Code for the whole part', out)
        self.assertLess(out.index('## Code for the whole part'), out.index('| whole();'))

    def test_code_shared_by_two_clauses_is_shown_once_and_the_second_time_points_back(self):
        self.project({'pair': PAIR})
        write(self.dir, 'out/app.js', PAIR_APP)
        out = self.sor('show', 'pair')[1]
        self.assertIn('> out/app.js:1-3  (also pair/b)', out)
        self.assertIn('> out/app.js:1-3  (shown above)', out)
        self.assertEqual(out.count('| console.log("A", "B");'), 1)

    def test_the_root_is_shown_by_any_of_its_names_or_by_a_dot(self):
        self.greet_project()
        for name in ('ROOT', 'SPECOFRECORD', '.'):
            with self.subTest(name=name):
                code, out, _ = self.sor('show', name)
                self.assertEqual(code, 0)
                self.assertIn('# Demo', out)

    def test_a_table_row_shows_the_item_it_belongs_to_and_the_code_of_the_row(self):
        self.project({'bodies': BODIES})
        write(self.dir, 'out/rows.js', 'const mars = 5;  // @clause bodies/planets/Mars\n')
        out = self.sor('show', 'bodies/planets/Mars')[1]
        self.assertIn('# Bodies  (bodies.md)', out)
        self.assertIn('> out/rows.js:1', out)


class TestTheLockKeepsItsRules(Flow):
    """What `sor lock` refuses, and the notes `sor status` makes, when code is shared or a table changed."""

    def pair_locked(self):
        self.project({'pair': PAIR})
        write(self.dir, 'out/app.js', PAIR_APP)
        accepted(self.dir)

    def change_a(self):
        replace_in(os.path.join(self.spec, 'pair.md'), '{text: A}', '{text: Ay}')
        replace_in(os.path.join(self.dir, 'out', 'app.js'), '"A", "B"', '"Ay", "B"')

    def test_code_shared_with_a_changed_clause_is_for_review_and_says_which_test_must_pass_again(self):
        self.pair_locked()
        self.change_a()
        out = self.sor('status')[1]
        self.assertRegex(out, r'changed\s+pair/a')
        self.assertRegex(out, r'shared\s+pair/b\s+code changed with pair/a; its test pair/test:b must pass again')

    def test_a_scoped_lock_takes_the_clause_that_shares_the_code_and_says_so(self):
        self.pair_locked()
        self.change_a()
        results = write(self.dir, 'r.json', json.dumps({'pair/test:a': 'pass', 'pair/test:b': 'pass'}))
        code, out, _ = self.sor('lock', 'pair/a', '--results', results)
        self.assertEqual(code, 0, out)
        self.assertIn('locking with them (they share code): pair/b', out)

    def test_the_test_of_a_clause_that_shares_the_code_must_pass_and_allow_incomplete_does_not_change_that(self):
        self.pair_locked()
        self.change_a()
        only_a = write(self.dir, 'r.json', json.dumps({'pair/test:a': 'pass'}))
        for extra in ([], ['--allow-incomplete']):
            with self.subTest(extra=extra):
                code, out, _ = self.sor('lock', 'pair/a', '--results', only_a, *extra)
                self.assertEqual(code, 2, out)
                self.assertIn('shared  pair/b  its code changed with another clause, so pair/test:b must pass '
                              '(--allow-incomplete does not cover this)', out)

    def test_confirming_a_manual_test_outside_what_is_locked_is_refused_and_so_is_confirming_a_test_that_is_not_manual(self):
        self.project({'pair': doc('Pair', 'Two clauses.', rules=['- **a** - A.', '- **b** - B.'],
                                  tests=['- **a** - says a.', '  manual: by eye', '- **b** - says b.', '  manual: by eye'])})
        accepted(self.dir)
        code, out, _ = self.sor('lock', 'pair/a', '--confirm', 'pair/test:b')
        self.assertEqual(code, 2)
        self.assertIn('--confirm: pair/test:b is outside the clauses being locked', out)
        self.project({'pair': doc('Pair', 'Two clauses.', rules=['- **a** - A.'], tests=['- **a** - says a.', '  expect: ok'])})
        accepted(self.dir)
        code, out, _ = self.sor('lock', '--all', '--confirm', 'pair/test:a', '--allow-incomplete')
        self.assertEqual(code, 2)
        self.assertIn('--confirm: pair/test:a is not a manual test', out)

    def test_a_changed_row_of_a_table_says_whether_its_code_was_updated_and_then_that_it_was(self):
        self.project({'bodies': BODIES})
        write(self.dir, 'out/app.js', BODIES_APP)
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'bodies.md'), '| Mars | 5 |', '| Mars | 6 |')
        out = self.sor('status')[1]
        self.assertRegex(out, r'changed\s+bodies/planets/Mars\s+values: size · code not updated yet \(in bodies/planets\)')
        replace_in(os.path.join(self.dir, 'out', 'app.js'), '[5, 12]', '[6, 12]')
        out = self.sor('status')[1]
        self.assertRegex(out, r'changed\s+bodies/planets\s+rows changed: Mars · code updated')
        self.assertNotIn('drift', out)

    def test_code_a_person_writes_by_hand_is_noted_with_the_anchors_it_changed_not_called_drift(self):
        self.project({'hand': doc('Hand', 'By hand.', header=['Source: code at src/'],
                                  rules=['- **run** - It runs.', '  code: src/a.js#run', '- **walk** - It walks.'],
                                  tests=['- **run** - runs.', '  expect: ok'])})
        write(self.dir, 'src/a.js', 'function run() {\n  return 1;\n}\n')
        write(self.dir, 'src/b.js', '// @clause hand/walk\nfunction walk() {}\n// @clause end\n')
        accepted(self.dir)
        replace_in(os.path.join(self.dir, 'src', 'a.js'), 'return 1', 'return 2')
        replace_in(os.path.join(self.dir, 'src', 'b.js'), 'walk() {}', 'walk() { return 1; }')
        out = self.sor('status')[1]
        self.assertRegex(out, r'code-changed\s+hand/run\s+its code changed \(src/a\.js#run\): check the clause still holds')
        self.assertRegex(out, r'code-changed\s+hand/walk\s+hand-written code')
        self.assertNotIn('drift', out)

    def test_a_scoped_lock_does_not_absorb_a_change_nobody_has_locked_yet(self):
        self.project({'cam': doc('Camera', 'It looks.', rules=['- **zoom** - Zoom goes to {max: 6x}.', '- **pinch** - Pinch goes as far as {zoom.max}.'])})
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'cam.md'), '{max: 6x}', '{max: 8x}')
        replace_in(os.path.join(self.spec, 'cam.md'), 'goes as far as', 'goes as far as exactly')
        self.assertEqual(self.sor('lock', 'cam/pinch')[0], 0)
        out = self.sor('status')[1]
        self.assertRegex(out, r'stale\s+cam/pinch\s+refers to cam/zoom\.max \(changed\)')
        self.assertRegex(out, r'changed\s+cam/zoom')


class TestClaimRefusals(Flow):
    def test_the_lock_names_the_claim_you_made_under_another_name_in_this_session(self):
        self.greet_project()
        env = {'CLAUDE_CODE_SESSION_ID': 'S1'}
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'alice', **env)[0], 0)
        code, out, _ = self.sor('lock', 'greet/hello', '--as', 'bob', **env)
        self.assertEqual(code, 2)
        self.assertIn('you made these claims in this session under another name: pass --as alice', out)

    def test_release_needs_to_know_what_to_release_and_who_you_are(self):
        self.greet_project()
        code, _, err = self.sor('release')
        self.assertEqual((code, 'name the clauses, or --all' in err), (2, True))
        code, _, err = self.sor('release', 'greet/hello')
        self.assertEqual(code, 2)
        self.assertIn('say who you are', err)

    def test_releasing_one_clause_keeps_the_others_you_claimed(self):
        self.greet_project()
        self.assertEqual(self.sor('claim', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual(self.sor('claim', 'greet/bye', '--as', 'alice')[0], 0)
        self.assertEqual(self.sor('release', 'greet/hello', '--as', 'alice')[0], 0)
        self.assertEqual([c['asked'] for c in self.claims_file()], [['greet/bye']])


class TestWhatTheGuardSays(Flow):
    def test_a_file_written_whole_is_judged_like_an_edit(self):
        self.greet_project()
        text = read(self.app).replace('"Hello"', '"Hi"')
        said = reason(hook.pre_edit({'tool_name': 'Write', 'tool_input': {'file_path': self.app, 'content': text}}))
        self.assertIn('greet/hello', said)
        self.assertIsNone(hook.pre_edit({'tool_name': 'Write', 'tool_input': {'file_path': self.app, 'content': read(self.app)}}))

    def test_code_that_serves_two_clauses_names_both_and_where_to_change_one_of_them(self):
        self.project({'pair': PAIR})
        write(self.dir, 'out/app.js', PAIR_APP)
        accepted(self.dir)
        said = reason(hook.pre_edit(edit(self.app, '"A", "B"', '"X", "B"')))
        self.assertIn('serves `pair/a`, `pair/b`: change one of **a** in sor/pair.md, **b** in sor/pair.md first', said)

    def test_code_that_serves_a_table_row_or_a_part_says_where_that_is(self):
        self.project({'bodies': BODIES})
        write(self.dir, 'out/rows.js', 'const mars = 5;  // @clause bodies/planets/Mars\n')
        write(self.dir, 'out/whole.js', '// @clause bodies\nwhole();\n// @clause end\n')
        accepted(self.dir)
        said = reason(hook.pre_edit(edit(os.path.join(self.dir, 'out', 'rows.js'), 'mars = 5', 'mars = 6')))
        self.assertIn('change the row **Mars** of **planets** in sor/bodies.md first', said)
        said = reason(hook.pre_edit(edit(os.path.join(self.dir, 'out', 'whole.js'), 'whole()', 'whole(1)')))
        self.assertIn('change sor/bodies.md first', said)


if __name__ == '__main__':
    unittest.main()
