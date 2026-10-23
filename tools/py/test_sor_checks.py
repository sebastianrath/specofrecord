"""Tests for what `sor check`, `sor status` and `sor lock` tell people: the lock refusal that names the tests and
the way out, the pending tests in `sor status`, the note for a test nothing will run, the item count, a section heading
written twice, the words limit of one item, and the reference errors that say what was found and what was meant.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only, no browser. The two real projects are only read.
"""
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                            # noqa: E402  (its helpers only)
from sorlib import lint, model, testrun            # noqa: E402
from sorlib import lock as lockfile                # noqa: E402
from sorlib.markers import Scan                    # noqa: E402
from sorlib.model import Project                   # noqa: E402
from test_sor_flows import Flow, accepted, replace_in   # noqa: E402

doc, write, read = base.doc, base.write, base.read

WEB = doc('Web', 'Where the viewer runs.', rules=['- **path** - the page is {path: out/index.html}.'],
          contract=['- gives **probes** - members of the page.', '  read: time', '  do: step(seconds)'])


def core(n=12, steps=('  do: step()', '  expect: ok')):
    """A part `core` with n rules r01 ... and a test for each; the tests have these steps."""
    rules = [f'- **r{i:02}** - rule number {i}.' for i in range(1, n + 1)]
    tests = [f'- **r{i:02}** - proves r{i:02}.' + ''.join('\n' + s for s in steps) for i in range(1, n + 1)]
    return doc('Core', 'The core of the engine.', rules=rules, tests=tests)


def bullet(words, name='long', lead='- '):
    """A bullet of exactly this many words, the name counted."""
    return f'{lead}**{name}** - ' + ' '.join(['word'] * (words - 1))


class TestTheLockRefusalNamesTheTests(Flow):
    def test_it_names_the_first_ten_and_counts_the_rest(self):
        self.project({'core': core(12)})
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 2)
        self.assertIn('12 test(s) did not pass (0 failed, 12 not run)', out)
        for i in range(1, 11):
            self.assertIn(f'core/test:r{i:02}', out)
        self.assertNotIn('core/test:r11', out)
        self.assertIn('and 2 more', out)
        self.assertFalse(os.path.exists(os.path.join(self.spec, 'sor-lock.json')))
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)   # the way out that was always there

    def test_ten_or_fewer_are_all_named_and_say_nothing_about_more(self):
        self.project({'core': core(10)})
        out = self.sor('lock', '--all')[1]
        self.assertIn('core/test:r10', out)
        self.assertNotIn(' more', out)

    def test_without_a_web_target_it_says_what_to_do_instead(self):
        self.project({'core': core(2)})
        out = self.sor('lock', '--all')[1]
        self.assertIn('no web target', out)
        for way in ('`manual:`', '`--results F`', '--allow-incomplete'):
            self.assertIn(way, out)
        self.assertNotIn('@clause test', out)   # with no web target the lock does not need the mark: --results F is enough
        self.assertIn('{"core/test:r01": "pass"}', out)

    def test_with_a_web_target_it_points_at_running_the_tests(self):
        self.project({'core': core(2), 'targets/web': WEB})
        out = self.sor('lock', '--all')[1]
        self.assertIn('`sor lock --run-tests`', out)
        self.assertIn('`@clause test <id>`', out)   # with a web target the mark is what makes a test EXTERNAL
        self.assertNotIn('no web target', out)

    def test_a_failed_test_is_named_as_failed_and_comes_first(self):
        self.project({'core': core(3)})
        results = write(self.dir, 'results.json', json.dumps({'core/test:r03': 'fail', 'core/test:r02': 'pass'}))
        code, out, _ = self.sor('lock', '--all', '--results', results)
        self.assertEqual(code, 2)
        self.assertIn('2 test(s) did not pass (1 failed, 1 not run): core/test:r03 (failed), core/test:r01', out)
        self.assertIn('Fix the failed ones first', out)


class TestStatusSeesThePendingTests(Flow):
    def status(self):
        return json.loads(self.sor('status', '--json')[1])

    def test_before_the_first_lock_every_test_with_steps_is_pending_but_none_had_not_passed(self):
        self.project({'core': core(3)})
        data = self.status()
        self.assertEqual(data['tests_pending'], ['core/test:r01', 'core/test:r02', 'core/test:r03'])
        self.assertEqual(data['tests_not_passed'], [])
        self.assertEqual(self.sor('status', '--json')[0], 1)   # work pending, as it was

    def test_a_manual_test_needs_no_result_so_it_is_not_pending(self):
        self.project({'core': core(2, steps=('  manual: a person looks',))})
        self.assertEqual(self.status()['tests_pending'], [])

    def test_the_plain_status_says_a_lock_is_refused_and_what_to_do(self):
        self.project({'core': core(12)})
        code, out, _ = self.sor('status')
        self.assertEqual(code, 1)
        self.assertIn('tests (12) — no passing result yet, so locking them is refused: core/test:r01', out)
        self.assertIn('and 2 more', out)
        self.assertIn('`manual:`', out)

    def test_a_locked_project_where_every_test_passed_has_none_pending(self):
        self.project({'core': core(2)})
        accepted(self.dir)
        data = self.status()
        self.assertEqual((data['tests_pending'], data['findings']), ([], []))
        self.assertNotIn('tests (', self.sor('status')[1])

    def test_a_changed_clause_makes_its_test_pending_again(self):
        self.project({'core': core(2)})
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'core.md'), 'rule number 1.', 'rule number one.')
        self.assertEqual(self.status()['tests_pending'], ['core/test:r01'])

    def test_a_changed_test_is_pending(self):
        self.project({'core': core(2)})
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'core.md'), 'proves r02.', 'proves r02 again.')
        self.assertEqual(self.status()['tests_pending'], ['core/test:r02'])

    def test_a_change_to_a_part_itself_makes_all_its_tests_pending(self):
        self.project({'core': core(2), 'other': doc('Other', 'Another part.', rules=['- **o** - o.'], tests=['- **o** - o.', '  expect: ok'])})
        accepted(self.dir)
        replace_in(os.path.join(self.spec, 'core.md'), 'The core of the engine.', 'The heart of the engine.')
        data = self.status()
        self.assertEqual([f['key'] for f in data['findings']], ['core'])
        self.assertEqual(data['tests_pending'], ['core/test:r01', 'core/test:r02'])

    def test_a_test_locked_as_not_passed_is_pending_too(self):
        self.project({'core': core(2)})
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        data = self.status()
        self.assertEqual(data['tests_not_passed'], ['core/test:r01', 'core/test:r02'])
        self.assertEqual(data['tests_pending'], data['tests_not_passed'])
        self.assertIn('2 test(s) had not passed at the last lock', self.sor('status')[1])   # the old line stays

    def test_the_real_projects_say_nothing_of_it_while_their_tests_passed(self):
        for path in base.real_projects():
            with self.subTest(project=os.path.relpath(path, base.REPO)):
                data = json.loads(base.run_sor(path, 'status', '--json')[1])
                self.assertIsInstance(data['tests_pending'], list)
                if not data['findings'] and not data['tests_not_passed']:   # the owner may be in the middle of a change
                    self.assertEqual(data['tests_pending'], [])
                    self.assertNotIn('tests (', base.run_sor(path, 'status')[1])


class TestATestNothingWillRun(Flow):
    def notes(self, **parts):
        project = self.project(parts)
        return [n for n in lint.notes(project) if n.kind == 'never run']

    def test_a_project_without_a_web_target_gets_one_note_per_part_naming_the_tests(self):
        found = self.notes(core=core(7), other=core(1))
        self.assertEqual(len(found), 2)
        note = next(n for n in found if n.text.startswith('7 test(s) of core'))
        for name in ('core/test:r01', 'core/test:r05'):
            self.assertIn(name, note.text)
        self.assertIn('and 2 more', note.text)
        self.assertIn('manual:', note.text)
        self.assertIn('@clause test', note.text)
        self.assertEqual(note.where, 'core.md:' + str(Project(self.dir).items['core/test:r01'].lineno))

    def test_each_of_the_four_kinds_of_line_makes_a_test_a_candidate(self):
        for step in ('  do: step()', '  expect: ok', '  each: size in 800x600', '  measure: frame-time p95 over 600 frames ≤ 16 ms'):
            with self.subTest(step=step):
                self.assertEqual(len(self.notes(core=core(1, steps=(step,)))), 1)

    def test_it_is_a_note_and_never_a_problem_and_the_exit_code_stays(self):
        self.project({'core': core(1)})
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertIn('never run', out)
        self.assertIn('0 problem(s)', out)
        self.assertEqual(self.sor('check', '--strict')[0], 2)

    def test_a_manual_test_is_silent(self):
        self.assertEqual(len(self.notes(core=core(2))), 1)
        self.assertEqual(self.notes(core=core(2, steps=('  manual: a person looks',))), [])
        self.assertEqual(self.notes(core=core(2, steps=('  do: step()', '  manual: a person looks'))), [])

    def test_a_test_with_no_steps_is_silent(self):
        self.assertEqual(len(self.notes(core=core(2))), 1)
        self.assertEqual(self.notes(core=core(2, steps=('  bug: #12',))), [])

    def test_a_web_project_is_silent(self):
        self.assertEqual(len(self.notes(core=core(2))), 1)
        self.assertEqual(self.notes(core=core(2), **{'targets/web': WEB}), [])

    def test_a_test_written_in_the_projects_own_framework_is_silent(self):
        project = self.project({'core': core(2)})
        write(self.dir, 'test/core.test.js', '// @clause test core/r01\nexpect(1).toBe(1);\n// @clause end\n')
        found = [n for n in lint.notes(project) if n.kind == 'never run']
        self.assertEqual(len(found), 1)   # r02 has no code
        self.assertIn('core/test:r02', found[0].text)
        self.assertNotIn('core/test:r01', found[0].text)
        self.assertEqual(self.sor('check')[0], 0)

    def test_the_markers_are_read_only_when_there_is_something_to_ask(self):
        project = self.project({'core': core(2, steps=('  manual: a person looks',))})
        with mock.patch.object(lint, 'Scan', side_effect=AssertionError('read the code for nothing')):
            self.assertEqual([n for n in lint.notes(project) if n.kind == 'never run'], [])

    def test_a_scan_that_was_read_already_is_used(self):
        project = self.project({'core': core(2)})
        scan = Scan(project)
        with mock.patch.object(lint, 'Scan', side_effect=AssertionError('read the code twice')):
            self.assertEqual([n.kind for n in lint.notes(project, scan)], ['never run'])

    def test_a_test_in_a_tests_file_counts_as_a_test_of_its_part(self):
        self.project({'core': doc('Core', 'The core.', rules=['- **a** - A.'])})
        write(self.dir, 'sor/core.tests.md', '## Tests\n- **a** - proves a.\n  expect: ok\n')
        found = [n for n in lint.notes(Project(self.dir)) if n.kind == 'never run']
        self.assertEqual([n.where for n in found], ['core.tests.md:2'])

    def test_the_solar_system_example_has_a_web_target_and_no_such_note(self):
        for path in base.real_projects():
            project = Project(path)
            with self.subTest(project=os.path.relpath(path, base.REPO)):
                if project.has_web_target():
                    self.assertEqual([n for n in lint.notes(project) if n.kind == 'never run'], [])
        self.assertTrue(any(Project(p).has_web_target() for p in base.real_projects()))

    def test_having_a_web_target_means_what_sor_test_means_by_it(self):
        for path in base.real_projects():
            project = Project(path)
            self.assertEqual(project.has_web_target(), bool(testrun.web_targets(project)), path)
        self.project({'core': core(1), 'targets/web': WEB})
        self.assertTrue(Project(self.dir).has_web_target())
        self.assertTrue(testrun.web_targets(Project(self.dir)))
        write(self.dir, 'sor/targets/web.md', WEB.replace('out/index.html', 'out/index.txt'))
        self.assertFalse(Project(self.dir).has_web_target())
        self.assertFalse(testrun.web_targets(Project(self.dir)))


class TestTheItemCountIsPerSection(Flow):
    def thing(self, rules, contract=()):
        return self.project({'thing': doc('Thing', rules=rules, contract=contract)})

    def test_a_name_used_in_two_sections_counts_once_in_each(self):
        project = self.thing([f'- **r{i}** - rule {i}.' for i in range(1, 8)], ['- gives **r3** - the same name as a rule.'])
        counts = lint.bullet_counts(project.parts['thing'])
        self.assertEqual((counts['Rules'], counts['Contract']), (7, 1))
        self.assertEqual([n for n in lint.notes(project) if n.kind == 'too long'], [])
        self.assertEqual([p.kind for p in project.check()], ['duplicate'])

    def test_the_same_name_twice_in_one_section_still_counts_both(self):
        project = self.thing([f'- **r{i}** - rule {i}.' for i in range(1, 7)] + ['- **r1** - once more.'], ['- gives **r2** - and another.'])
        counts = lint.bullet_counts(project.parts['thing'])
        self.assertEqual((counts['Rules'], counts['Contract']), (7, 1))

    def test_the_eighth_bullet_is_still_one_too_many(self):
        project = self.thing([f'- **r{i}** - rule {i}.' for i in range(1, 8)], ['- gives **r3** - same.', '- gives **r1** - same.'])
        found = [n for n in lint.notes(project) if n.kind == 'too long']
        self.assertEqual(found, [])
        project = self.thing([f'- **r{i}** - rule {i}.' for i in range(1, 8)] + ['- **r3** - same.'])
        self.assertIn('Rules has 8 items', [n for n in lint.notes(project) if n.kind == 'too long'][0].text)

    def test_the_tests_of_a_tests_file_are_counted_as_tests(self):
        self.project({'core': doc('Core', 'The core.', rules=['- **a** - A.'], contract=['- gives **a** - the same name.'],
                                  tests=['- **a** - proves a.', '  expect: ok'])})
        write(self.dir, 'sor/core.tests.md', '## Tests\n- **a-again** - proves a.\n  proves: {a}\n  expect: ok\n')
        counts = lint.bullet_counts(Project(self.dir).parts['core'])
        self.assertEqual((counts['Rules'], counts['Contract'], counts['Tests']), (1, 1, 2))

    def test_sor_parts_counts_the_same_way(self):
        project = self.thing([f'- **r{i}** - rule {i}.' for i in range(1, 8)], ['- gives **r3** - the same name as a rule.'])
        info = next(d for d in json.loads(base.run_sor(project.root, 'parts', '--json')[1]) if d['id'] == 'thing')
        self.assertEqual((info['bullets']['rules'], info['bullets']['contract']), (7, 1))


class TestASectionHeadingWrittenTwice(Flow):
    TWICE = '# T\nWhy: it is here.\n\n## Approach\n- **a** - A.\n\n## Approach\n- **b** - B.\n'

    def found(self, text, name='t'):
        self.project({name: text})
        return [p for p in Project(self.dir).check() if p.kind == 'heading']

    def test_two_approach_headings_are_a_problem_with_both_line_numbers(self):
        (problem,) = self.found(self.TWICE)
        self.assertEqual(problem.where, 't.md:7')
        self.assertIn('lines 4 and 7', problem.text)
        self.assertIn('## Approach', problem.text)

    def test_check_fails_on_it(self):
        self.project({'t': self.TWICE})
        code, out, _ = self.sor('check')
        self.assertEqual(code, 2)
        self.assertIn('heading', out)

    def test_the_words_are_compared_without_regard_to_case_and_spacing(self):
        self.assertEqual(len(self.found(self.TWICE.replace('## Approach\n- **b', '##  approach \n- **b'))), 1)

    def test_a_third_heading_is_reported_against_the_first(self):
        (first, second) = self.found(self.TWICE + '\n## Approach\n- **c** - C.\n')
        self.assertIn('lines 4 and 7', first.text)
        self.assertIn('lines 4 and 10', second.text)

    def test_two_headings_that_only_mean_the_same_section_are_not_a_problem(self):
        text = '# T\nWhy: it is here.\n\n## Rules\n- **a** - A.\n\n## Must\n- **b** - B.\n\n## Edge cases\n- **c** - C.\n\n## Open points\n- **d** - D.\n'
        self.assertEqual(len(self.found(self.TWICE)), 1)
        self.assertEqual(self.found(text), [])

    def test_a_heading_inside_an_example_is_not_counted(self):
        text = '# T\nWhy: it is here.\n\n## Approach\n- **a** - A.\n\n```\n## Approach\n```\n'
        self.assertEqual(len(self.found(self.TWICE)), 1)
        self.assertEqual(self.found(text), [])

    def test_a_tests_file_with_a_heading_twice_is_reported_in_the_tests_file(self):
        self.project({'t': doc('T', rules=['- **a** - A.'], tests=['- **a** - proves a.', '  expect: ok'])})
        write(self.dir, 'sor/t.tests.md', '## Tests\n- **a-two** - proves a.\n  proves: {a}\n  expect: ok\n\n## Tests\n- **a-three** - proves a.\n  proves: {a}\n  expect: ok\n')
        found = [p for p in Project(self.dir).check() if p.kind == 'heading']
        self.assertEqual([p.where for p in found], ['t.tests.md:6'])

    def test_the_real_projects_have_none(self):
        self.assertEqual(len(self.found(self.TWICE)), 1)   # the check is there to find them
        for path in base.real_projects():
            with self.subTest(project=os.path.relpath(path, base.REPO)):
                self.assertEqual([p for p in Project(path).check() if p.kind == 'heading'], [])


class TestTheWordsOfOneItem(Flow):
    def notes(self, rules=(), approach=(), contract=(), tests=()):
        project = self.project({'thing': doc('Thing', rules=rules, approach=approach, contract=contract, tests=tests)})
        return [n for n in lint.notes(project) if n.kind == 'too long' and ' words ' in n.text]

    def test_the_limit_is_a_constant_next_to_the_others(self):
        self.assertGreater(lint.LIMIT_WORDS, 0)
        self.assertGreater(lint.LIMIT_WORDS, 40)   # the median rule is a third of it

    def test_one_word_over_the_limit_is_a_note_and_the_limit_itself_is_not(self):
        self.assertEqual(self.notes([bullet(lint.LIMIT_WORDS)]), [])
        (note,) = self.notes([bullet(lint.LIMIT_WORDS + 1)])
        self.assertEqual(note.kind, 'too long')
        self.assertIn(f'thing/long: {lint.LIMIT_WORDS + 1} words (at most {lint.LIMIT_WORDS})', note.text)
        self.assertEqual(note.where, 'thing.md:5')

    def test_it_applies_to_every_section_but_the_tests(self):
        for section in ('rules', 'approach', 'contract'):
            with self.subTest(section=section):
                self.assertEqual(len(self.notes(**{section: [bullet(lint.LIMIT_WORDS + 1)]})), 1)
        self.assertEqual(self.notes(tests=[bullet(lint.LIMIT_WORDS + 40, 'long'), '  expect: ok']), [])

    def test_the_lines_under_a_bullet_belong_to_it(self):
        half = lint.LIMIT_WORDS // 2 + 1
        (note,) = self.notes([bullet(half) + '\n  ' + ' '.join(['more'] * half)])
        self.assertIn(f'{2 * half} words', note.text)

    def test_a_table_an_open_question_and_a_code_anchor_are_no_words_of_the_item(self):
        lines = [bullet(lint.LIMIT_WORDS), '  open: ' + ' '.join(['why'] * 50), '  code: src/a.py#long',
                 '', '  | name | size |', '  |---|---|'] + [f'  | planet-{i} | {i} |' for i in range(60)]
        self.assertEqual(self.notes(['\n'.join(lines)]), [])

    def test_each_bullet_counts_alone_so_a_needs_item_of_several_lines_is_not_one_long_item(self):
        parts = {f'p{i}': doc(f'P{i}', contract=[f'- gives **g{i}** - g.']) for i in range(4)}
        needs = [f'- needs {{p{i}/g{i}}} - ' + ' '.join(['because'] * (lint.LIMIT_WORDS // 2)) for i in range(4)]
        project = self.project(dict(parts, thing=doc('Thing', contract=needs)))
        self.assertEqual([n for n in lint.notes(project) if ' words ' in n.text], [])

    def test_two_long_bullets_are_two_notes_each_at_its_own_line(self):
        found = self.notes([bullet(lint.LIMIT_WORDS + 1, 'one'), bullet(lint.LIMIT_WORDS + 1, 'two')])
        self.assertEqual([n.where for n in found], ['thing.md:5', 'thing.md:6'])

    def test_a_bullet_nobody_named_yet_is_quoted_instead_of_named(self):
        (note,) = self.notes(['- ' + ' '.join(['wordy'] * (lint.LIMIT_WORDS + 1))])
        self.assertTrue(note.text.startswith('"wordy wordy'), note.text)

    def test_it_is_a_note_that_never_blocks_a_lock(self):
        self.project({'thing': doc('Thing', rules=[bullet(lint.LIMIT_WORDS + 1)])})
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertIn('words (at most', out)
        self.assertEqual(self.sor('check', '--strict')[0], 2)
        self.assertEqual(self.sor('lock', '--all')[0], 0)


class TestReferenceErrorsHelp(Flow):
    def problems(self, kind=None, **parts):
        self.project(parts)
        return [p for p in Project(self.dir).check() if kind is None or p.kind == kind]

    ENGINE = {'core': doc('Core', 'The core.', rules=['- **c** - c.']),
              'core/ecs': doc('Ecs', 'Entities.', contract=['- gives **spawn** - makes one.', '- gives **despawn** - removes one.'])}

    def test_a_needs_line_naming_a_part_lists_what_the_part_gives(self):
        (p,) = self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs}'])))
        self.assertIn('{core/ecs} is a part, not a `gives` item', p.text)
        self.assertIn('{core/ecs/spawn}, {core/ecs/despawn}', p.text)

    def test_a_part_that_gives_nothing_says_so(self):
        (p,) = self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core}'])))
        self.assertIn('{core} is a part', p.text)
        self.assertIn('gives nothing yet', p.text)

    def test_a_needs_line_naming_a_rule_says_where_it_is_and_what_the_part_gives(self):
        (p,) = self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs/spawn}, {core/c}'])))
        self.assertTrue(p.text.startswith('{core/c} is not a `gives` item: it is in Rules of core'), p.text)

    def test_a_rule_of_a_part_that_gives_something_names_what_it_gives(self):
        parts = dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs/spawn}']))
        parts['core/ecs'] = doc('Ecs', 'Entities.', rules=['- **x** - x.'], contract=['- gives **spawn** - makes one.'])
        parts['game'] = doc('Game', 'G.', contract=['- needs {core/ecs/x}'])
        (p,) = self.problems('needs', **parts)
        self.assertIn('core/ecs gives {core/ecs/spawn}', p.text)

    def test_a_needs_line_naming_a_table_row_or_a_value_says_which(self):
        parts = dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs/t/Mars}', '- needs {core/ecs/spawn.v}']))
        parts['core/ecs'] = doc('Ecs', 'E.', contract=['- gives **spawn** - makes one {v: 3 s}.',
                                                      '- gives **t** - a table:', '', '| k | v |', '|---|---|', '| Mars | 5 |'])
        texts = [p.text for p in self.problems('needs', **parts)]
        self.assertEqual(len(texts), 2, texts)
        self.assertIn('table row', texts[0])
        self.assertIn('is a value', texts[1])

    def test_the_same_wrong_target_named_twice_is_reported_once_at_its_first_line(self):
        found = self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=[
            '- needs {core/ecs/spawn}', '- needs {core/ecs}', '- needs {core/ecs} - again'])))
        self.assertEqual([p.where for p in found], ['game.md:6'])

    def test_each_wrong_needs_line_is_reported_at_its_own_line(self):
        (p,) = self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs/spawn}', '- needs {core/ecs}'])))
        self.assertEqual(p.where, 'game.md:6')

    def test_a_needs_line_that_names_a_gives_item_is_fine(self):
        self.assertEqual(len(self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs}'])))), 1)
        self.assertEqual(self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs/spawn}']))), [])
        self.assertIn('is a part', self.problems('needs', **dict(self.ENGINE, game=doc('Game', 'G.', contract=['- needs {core/ecs}'])))[0].text)

    def test_a_broken_reference_says_which_part_exists_and_suggests_the_nearest_id(self):
        (p,) = self.problems('broken', **dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - makes {core/spawn}.'])))
        self.assertTrue(p.text.startswith('{core/spawn} names no item, row, value or part'), p.text)
        self.assertIn('the part `core` exists but has no item `spawn`', p.text)
        self.assertIn('did you mean {core/ecs/spawn}?', p.text)
        self.assertEqual(p.where, 'game.md:5')

    def test_a_misspelled_id_gets_the_closest_spelling(self):
        (p,) = self.problems('broken', **dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - {core/ecs/spwan}.'])))
        self.assertIn('did you mean {core/ecs/spawn}', p.text)

    def test_a_reference_that_resembles_nothing_suggests_nothing(self):
        (near,) = self.problems('broken', **dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - {core/ecs/spawm}.'])))
        (far,) = self.problems('broken', **dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - {zzzzqq}.'])))
        self.assertIn('did you mean', near.text)
        self.assertTrue(far.text.startswith('{zzzzqq} names no item'), far.text)
        self.assertNotIn('did you mean', far.text)

    def test_a_missing_value_lists_the_values_the_item_has(self):
        parts = {'z': doc('Z', 'Z.', rules=['- **zoom** - zoom between {min: 1x} and {max: 6x}.', '- **look** - {zoom.mx}.'])}
        (p,) = self.problems('broken', **parts)
        self.assertIn('{zoom.mx} names no value: `z/zoom` has the values max, min', p.text)

    def test_only_an_id_that_resolves_from_where_it_is_written_is_suggested(self):
        self.project(dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - {spawn}.'])))
        project = Project(self.dir)
        self.assertEqual(project.suggest('game', 'spawn'), ['core/ecs/spawn'])
        with mock.patch.object(Project, 'resolve', return_value=['somewhere/else']):
            self.assertEqual(project.suggest('game', 'spawn'), [])

    def test_at_most_three_ids_are_suggested_and_the_ones_that_start_alike_come_first(self):
        parts = {name: doc(name.title(), 'P.', contract=['- gives **spawn** - makes one.'])
                 for name in ('core/ecs', 'render/particles', 'audio', 'physics', 'ai')}
        parts.update({'core': doc('Core', 'C.'), 'render': doc('Render', 'R.'), 'game': doc('Game', 'G.', rules=['- **g** - {core/spawn}.'])})
        self.project(parts)
        project = Project(self.dir)
        near = project.suggest('game', 'core/spawn')
        self.assertEqual(len(near), 3)
        self.assertEqual(near[0], 'core/ecs/spawn')   # the longer id of another part would come first by length alone

    def test_a_misspelled_word_brings_its_best_id_only(self):
        self.project({**{f'p{i}': doc('P', 'P.', contract=['- gives **spawn** - makes one.']) for i in range(4)},
                      'game': doc('Game', 'G.', rules=['- **g** - {p0/spwan}.'])})
        self.assertEqual(Project(self.dir).suggest('game', 'p0/spwan'), ['p0/spawn'])

    def test_the_kind_of_a_broken_and_an_ambiguous_reference_is_what_it_was(self):
        (broken,) = self.problems(None, game=doc('Game', 'G.', rules=['- **g** - {nowhere}.']))
        self.assertEqual(broken.kind, 'broken')
        parts = {'a': doc('A', 'A.', rules=['- **x** - x.']), 'a/b': doc('B', 'B.', rules=['- **x** - x.', '- **y** - {x}.'])}
        (amb,) = [p for p in self.problems(None, **parts) if p.kind.startswith('ambiguous')]
        self.assertEqual(amb.kind, "ambiguous ['a/b/x', 'a/x']")
        self.assertIn('{x} could mean {a/b/x} or {a/x}', amb.text)

    def test_the_lock_and_the_hooks_do_not_pay_for_the_suggestions(self):
        self.project(dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - {core/spawn}.'])))
        project = Project(self.dir)
        with mock.patch.object(model.difflib, 'get_close_matches', side_effect=AssertionError('slow')):
            lockfile.snapshot(project, Scan(project))
            self.assertEqual(project.resolved_refs(project.items['game/g'])[1][0].text, '{core/spawn}')

    def test_the_candidates_are_built_once(self):
        self.project(dict(self.ENGINE, game=doc('Game', 'G.', rules=['- **g** - {core/spawn}.', '- **h** - {core/despwan}.'])))
        project = Project(self.dir)
        self.assertEqual(len([p for p in project.check() if p.kind == 'broken']), 2)
        self.assertIs(project.known_ids(), project.known_ids())

    def test_the_names_a_reference_can_mean_leave_out_tests_needs_lines_and_drafts(self):
        project = self.project({'z': doc('Z', 'Z.', rules=['- **zoom** - {min: 1x}.', '- a draft nobody named.'], contract=['- needs {z/zoom}'],
                                         tests=['- **zoom** - proves it.', '  expect: ok'])})
        self.assertEqual(project.known_ids(), ['out-of-scope', 'z', 'z/zoom', 'z/zoom.min'])

    def test_a_name_used_twice_says_where_the_first_one_is(self):
        text = doc('Win', rules=['- **window** - one.', '- **other** - x.'], contract=['- gives **window** - again.'])
        self.project({'win': text})
        (p,) = [p for p in Project(self.dir).check() if p.kind == 'duplicate']
        self.assertEqual(p.where, 'win.md:9')
        self.assertIn('**window** is named twice (the first is at line 5, in Rules)', p.text)

    def test_a_name_twice_in_one_section_does_not_name_the_section(self):
        self.project({'win': doc('Win', rules=['- **window** - one.', '- **window** - two.'])})
        (p,) = [p for p in Project(self.dir).check() if p.kind == 'duplicate']
        self.assertIn('(the first is at line 5)', p.text)

    def test_a_test_in_both_files_says_where_the_first_one_is(self):
        self.project({'t': doc('T', rules=['- **a** - A.'], tests=['- **a** - proves a.', '  expect: ok'])})
        write(self.dir, 'sor/t.tests.md', '## Tests\n- **a** - proves a.\n  expect: ok\n')
        (p,) = [p for p in Project(self.dir).check() if p.kind == 'duplicate']
        self.assertIn('is already a test in t.md (line 8)', p.text)

    def test_a_part_and_an_item_with_one_id_say_which_is_which(self):
        parts = {'scene': doc('Scene', 'S.', rules=['- **modes** - the modes.']), 'scene/modes': doc('Modes', 'M.', rules=['- **m** - m.'])}
        (p,) = self.problems('collision', **parts)
        self.assertEqual(p.where, 'scene/modes.md')
        self.assertEqual(p.text, '"scene/modes" names both a part (scene/modes.md) and an item of scene.md: rename one of them')

    def test_it_says_the_same_whichever_was_found_first(self):
        text = Project.collision('a/b', ('part', 'a/b.md'), ('item', 'a.md'))
        self.assertEqual(text, Project.collision('a/b', ('item', 'a.md'), ('part', 'a/b.md')))
        self.assertIn('a part (a/b.md) and an item of a.md', text)

    def test_two_items_with_one_id_are_named_as_two_items(self):
        parts = {'a': doc('A', 'A.', rules=['- **b/c** - one.']), 'a/b': doc('B', 'B.', rules=['- **c** - two.'])}
        (p,) = self.problems('collision', **parts)
        self.assertEqual(p.text, '"a/b/c" names two items, in a.md and a/b.md: rename one of them')

    def test_the_listing_helper_names_ten_then_the_rest(self):
        self.assertEqual(model.listed(['a', 'b']), 'a, b')
        self.assertEqual(model.listed(str(i) for i in range(12)), '0, 1, 2, 3, 4, 5, 6, 7, 8, 9 and 2 more')


if __name__ == '__main__':
    unittest.main()


class TestReferencesInTableCells(Flow):
    """A reference in a table cell is a reference like any other (SPEC §4): it must resolve, and its item is flagged when the target changes. A question (`open:`) may still name what is not decided yet."""

    def part(self, cell, extra=()):
        rules = ['- **a** - A {n: 3}.', '- **limits** - The limits:', '', '  | Name | Limit |', '  |---|---|', f'  | one | {cell} |', *extra]
        return doc('Bodies', 'The bodies.', rules=rules, tests=['- **a** - ok.', '  manual: by hand'])

    def problems(self, cell, extra=(), other=None):
        self.project({'bodies': self.part(cell, extra), **(other or {})})
        return [(p.kind, p.text) for p in Project(self.dir).check()]

    def test_a_cell_that_names_nothing_is_a_problem_with_its_line(self):
        found = self.problems('{nosuch.value}')
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0][0], 'broken')
        self.assertIn('{nosuch.value} names no item, row, value or part', found[0][1])
        where = [p.where for p in Project(self.dir).check()]
        self.assertEqual(where, ['bodies.md:10'])

    def test_a_cell_that_resolves_is_no_problem_and_a_dependency_of_its_item(self):
        self.assertEqual(self.problems('{a.n}'), [])
        item = Project(self.dir).items['bodies/limits']
        self.assertEqual([r for _, r in item.refs], ['a.n'])

    def stale_after_the_target_changes(self, cell):
        self.project({'bodies': self.part(cell)})
        accepted(self.dir)
        replace_in(os.path.join(self.dir, 'sor', 'bodies.md'), '{n: 3}', '{n: 4}')
        return self.sor('status')[1]

    def test_a_changed_target_flags_the_item_that_has_the_cell_for_review(self):
        self.assertRegex(self.stale_after_the_target_changes('{a.n}'), r'stale\s+bodies/limits\s+refers to bodies/a\.n')

    def test_an_alias_written_in_a_cell_flags_the_item_that_holds_the_table(self):
        self.assertRegex(self.stale_after_the_target_changes('{days: = a.n}'), r'stale\s+bodies/limits\s+refers to bodies/a\.n')

    def test_a_cell_with_no_reference_is_not_flagged(self):
        self.assertNotIn('bodies/limits', self.stale_after_the_target_changes('3 days'))

    def test_a_cell_that_could_mean_two_things_is_ambiguous(self):
        # the name is an item of this part and of the root: found at two levels, which SPEC §4 makes an error
        self.project({'bodies': self.part('{a}')}, root_text=doc('Demo', 'A project.', rules=['- **a** - The root has an a.']))
        found = [(p.kind, p.text) for p in Project(self.dir).check()]
        self.assertTrue(any(k.startswith('ambiguous') and '{a} could mean' in text for k, text in found), found)

    def test_an_alias_value_in_a_cell_is_checked_too(self):
        found = self.problems('{days: = nosuch.thing}')
        self.assertEqual([k for k, _ in found], ['broken'], found)
        self.assertIn('{nosuch.thing} names no item, row, value or part', found[0][1])

    def test_an_alias_in_a_cell_that_resolves_is_no_problem(self):
        self.assertEqual(self.problems('{days: = a.n}'), [])

    def test_the_summary_counts_the_references_it_examined(self):
        self.project({'bodies': self.part('{a.n}')})
        self.assertRegex(self.sor('check')[1], r'2 parts, 1 references,')   # the one in the cell counts

    def test_braces_in_code_in_a_cell_are_plain_text(self):
        self.assertEqual(self.problems('`{x, y}`'), [])

    def test_a_question_may_name_something_not_decided_yet(self):
        self.assertEqual(self.problems('{a.n}', extra=['  open: should {no-such-thing} be used here?']), [])

    def test_the_lock_waits_for_a_broken_cell(self):
        self.problems('{nosuch.value}')
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 2)
        self.assertIn('{nosuch.value}', out)


class TestTheSameValueInTwoParts(Flow):
    """A `{name: value}` that another part defines with the same name and the same text is one value written twice: a note
    at each of them, never a problem."""

    def part(self, *rules, tests=()):
        return doc('P', 'A part.', rules=list(rules), tests=list(tests))

    def found(self, parts, *args):
        self.project(parts)
        code, out, _ = self.sor('check', *args)
        return code, [m.groups() for m in (re.match(r'\s*value twice\s+(\S+)\s+(.*)$', line) for line in out.splitlines()) if m]

    def test_each_definition_gets_a_note_that_names_the_others(self):
        code, notes = self.found({'a': self.part('- **fast** - Takes {limit: 2 seconds}.'),
                                  'b': self.part('- **slow** - Takes {limit: 2 seconds}.')})
        self.assertEqual((code, [n[0] for n in notes]), (0, ['a.md:5', 'b.md:5']))
        self.assertIn('{limit: 2 seconds} is also defined with the same value in b/slow', notes[0][1])
        self.assertIn('{limit: 2 seconds} is also defined with the same value in a/fast', notes[1][1])
        self.assertIn('(`{b/slow.limit}`)', notes[0][1])
        self.assertIn('rename them so the names say what they are', notes[0][1])

    def test_it_is_a_note_and_strict_makes_it_fail(self):
        self.found({'a': self.part('- **x** - {n: 1}.'), 'b': self.part('- **y** - {n: 1}.')})
        self.assertEqual(self.sor('check')[0], 0)
        self.assertEqual(self.sor('check', '--strict')[0], 2)

    def test_case_and_spacing_do_not_make_two_values_different(self):
        _, notes = self.found({'a': self.part('- **x** - {n: 2 Seconds}.'), 'b': self.part('- **y** - {n:  2   seconds}.')})
        self.assertEqual(len(notes), 2)

    def test_with_three_parts_only_the_ones_that_agree_are_noted(self):
        _, notes = self.found({'a': self.part('- **x** - {n: 1}.'), 'b': self.part('- **y** - {n: 1}.'),
                               'c': self.part('- **z** - {n: 9}.')})
        self.assertEqual([n[0] for n in notes], ['a.md:5', 'b.md:5'])
        self.assertNotIn('c/z', notes[0][1])

    def test_the_root_and_a_child_count_as_two_parts(self):
        self.project({'a': self.part('- **x** - {n: 1}.')}, root_text=doc('Demo', 'A project.', rules=['- **r** - {n: 1}.']))
        _, out, _ = self.sor('check')
        self.assertEqual(len(re.findall(r'value twice', out)), 2)

    def test_different_texts_one_part_tests_cells_and_aliases_are_not_copies(self):
        table = ['- **t** - Sizes:', '', '| Name | Cost |', '|------|------|', '| x | {n: 1} |']
        cases = {
            'the same name with other texts': {'a': self.part('- **x** - {n: 1}.'), 'b': self.part('- **y** - {n: 2}.')},
            'two items of one part': {'a': self.part('- **x** - {n: 1}.', '- **y** - {n: 1}.')},
            'tests restate numbers on purpose': {'a': self.part('- **x** - {n: 1}.', tests=['- **x** - is {n: 1}.', '  manual: by hand']),
                                                 'b': self.part('- **y** - {m: 5}.', tests=['- **y** - is {n: 1}.', '  manual: by hand'])},
            'an alias refers, it does not define': {'a': self.part('- **x** - {n: 1}.'), 'b': self.part('- **y** - {n: = a/x.n}.')},
            'a cell is not a definition': {'a': self.part('- **x** - {n: 1}.'), 'b': self.part(*table)},
        }
        for what, parts in cases.items():
            with self.subTest(what=what):
                self.assertEqual(self.found(parts)[1], [])

    def test_a_check_for_one_part_shows_its_own_note(self):
        parts = {'a': self.part('- **x** - {n: 1}.'), 'b': self.part('- **y** - {n: 1}.'), 'c': self.part('- **z** - {m: 3}.')}
        self.assertEqual([n[0] for n in self.found(parts, 'a')[1]], ['a.md:5'])
        self.assertEqual([n[0] for n in self.found(parts, 'b')[1]], ['b.md:5'])
        self.assertEqual(self.found(parts, 'c')[1], [])

    def test_the_real_projects_have_none(self):
        self.assertEqual(len(self.found({'a': self.part('- **x** - {n: 1}.'), 'b': self.part('- **y** - {n: 1}.')})[1]), 2)
        for path in base.real_projects():
            with self.subTest(project=os.path.relpath(path, base.REPO)):
                self.assertEqual([n for n in lint.notes(Project(path)) if n.kind == 'value twice'], [])
