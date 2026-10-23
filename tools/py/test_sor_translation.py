"""Tests for how a test's lines become JavaScript (SPEC §8): what each line is turned into, and the messages a test
that is written wrong gets. Nothing here needs a browser: the JavaScript is only built and read, never run.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only, temporary folders only.
"""
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                           # noqa: E402  (its helpers only)
from sorlib import testrun                       # noqa: E402
from sorlib.model import Project                 # noqa: E402

doc, write = base.doc, base.write



def target(actions='step(seconds), slider(v), resize(w, h), setPaused(on)'):
    probes = ['- gives **probes** - members of window.__probe.', '  read: time, speed, paused, errors', f'  do: {actions}', '  metrics: fps']
    return doc('Web', 'The page.', rules=['- **path** - The page is {path: out/index.html}.'], contract=probes,
               tests=['- **path** - The page opens.', '  expect: count(errors) = 0'])


class Translation(base.Case):
    """A part `cam` with a few values, a target with probes, and one test whose lines each case writes."""

    RULES = ['- **zoom** - Zoom goes to {max: 6x}.', '- **loopy** - Loops: {self: = loopy.self}.', '- **bars** - Bars: {top: 10}, {room: 2}.']

    def build(self, lines, actions=None):
        self.project({'targets/web': target() if actions is None else target(actions),
                      'cam': doc('Camera', 'It looks.', rules=self.RULES, tests=['- **zoom** - the test.'] + list(lines))})
        write(self.dir, 'out/index.html', '<html></html>')
        project = Project(self.dir)
        web = testrun.web_targets(project)[0]
        return testrun.Test(project, web, project.items['cam/test:zoom'])

    def js(self, *lines, **kw):
        return self.build(lines, **kw).js()

    def error(self, *lines, **kw):
        t = self.build(lines, **kw)
        with self.assertRaises(testrun.TestError) as caught:
            t.js()
            t.measures()
        return str(caught.exception)


class TestWhatLinesBecome(Translation):
    def test_actions_become_calls_of_probes_in_the_order_written(self):
        js = self.js('  do: slider(100) · step(1)', '  expect: speed = 1')
        self.assertLess(js.index('A("slider", 100)'), js.index('A("step", 1)'))

    def test_remember_keeps_a_reading_and_unchanged_compares_with_it(self):
        js = self.js('  do: remember speed · step(1)', '  expect: speed unchanged')
        self.assertIn('M["speed"] = clone(R("speed"))', js)
        self.assertIn('same(a, b)', js)

    def test_changed_by_compares_the_difference_with_a_bound_or_a_tolerance(self):
        self.assertIn('a <= b', self.js('  do: remember time', '  expect: time changed by ≤ 5'))
        self.assertIn('a >= b', self.js('  do: remember time', '  expect: time changed by ≥ 5'))
        self.assertIn('a < b', self.js('  do: remember time', '  expect: time changed by < 5'))
        self.assertIn('a > b', self.js('  do: remember time', '  expect: time changed by > 5'))
        self.assertIn('near(a, b, 1)', self.js('  do: remember time', '  expect: time changed by 365 ± 1'))
        self.assertIn('near(a, b, Math.abs(365) * 0.01)', self.js('  do: remember time', '  expect: time changed by 365 ± 1%'))

    def test_a_dotted_reading_is_a_field_of_the_remembered_one(self):
        js = self.js('  do: remember time', '  expect: time.x unchanged')
        self.assertIn('F(M["time"], "x")', js)

    def test_a_result_is_kept_for_later_lines_and_an_action_may_give_one(self):
        js = self.js('  do: t = time · id = step(1)', '  expect: t = 1')
        self.assertIn('V["t"] = R("time")', js)
        self.assertIn('V["id"] = A("step", 1)', js)

    def test_each_size_runs_the_test_once_per_size_after_resizing(self):
        js = self.js('  each: size in 1280x720, 800x600', '  expect: speed = 1')
        self.assertIn('[[1280, 720], [800, 600]]', js)
        self.assertIn('A("resize", w, h)', js)

    def test_each_name_in_values_and_n_rounds_repeat_the_test(self):
        js = self.js('  each: n in 1, 2.5, a', '  expect: speed = n')
        self.assertIn('[1, 2.5, "a"]', js)
        self.assertIn('V["n"] = x', js)
        self.assertIn('for (let round = 0; round < 3; round++)', self.js('  each: 3 rounds', '  expect: speed = 1'))

    def test_the_comparisons_each_have_their_own_check(self):
        self.assertIn('check(near(a, b, 0.5)', self.js('  expect: speed = 1 ± 0.5'))
        self.assertIn('check(near(a, b, Math.abs(1) * 0.1)', self.js('  expect: speed ≈ 1 ± 10%'))
        self.assertIn('check(same(a, b)', self.js('  expect: speed is "fast"'))
        self.assertIn('check(has(a, b)', self.js('  expect: speed contains "fa"'))
        for op, js_op in (('<', '<'), ('≤', '<='), ('>', '>'), ('≥', '>=')):
            self.assertIn(f'check(a {js_op} b', self.js(f'  expect: speed {op} 1'), op)

    def test_a_value_of_a_clause_is_written_as_the_number_or_the_text_it_holds(self):
        self.assertIn('b = 6', self.js('  expect: speed = {zoom.max}'))
        self.assertIn('b = 10', self.js('  expect: speed = {bars.top}'))

    def test_values_may_be_added_and_subtracted_on_the_right_but_not_invented(self):
        self.assertIn('(10 + 2)', self.js('  expect: speed = {bars.top} + {bars.room}'))
        self.assertIn('(10 - 2)', self.js('  expect: speed = {bars.top} - {bars.room}'))
        self.assertIn('(10 + -2)', self.js('  expect: speed = {bars.top} -2'))

    def test_a_read_probe_may_take_arguments_and_fields(self):
        self.assertIn('F(R("time"), "x")', self.js('  expect: time.x > 0'))

    def test_a_test_that_only_measures_has_no_javascript(self):
        t = self.build(['  measure: clause-coverage ≥ 90'])
        self.assertIsNone(t.js())
        self.assertEqual(t.measures(), [('clause-coverage', '≥', 90.0)])


class TestWhatAWrongTestSays(Translation):
    CASES = [
        (['  expect: ok'], 'cannot read `expect: ok`'),
        (['  expect: speed = {nosuch}'], '{nosuch} does not resolve to one value'),
        (['  expect: speed = {zoom}'], '{zoom} is not a value (write {item.value})'),
        (['  expect: speed = {loopy.self}'], '{loopy.self} refers to itself'),
        (['  do: nothing(1)'], '`nothing` is not an action probe of targets/web'),
        (['  expect: nothing = 1'], '`nothing` is not a read probe of targets/web'),
        (['  each: size in 12', '  expect: speed = 1'], '`12` is not a size like 1280x720'),
        (['  each: nonsense', '  expect: speed = 1'], 'cannot read `each: nonsense`'),
        (['  do: remember speed', '  expect: speed = 1 ± abc'], 'a tolerance is a number or a percentage, not `abc`'),
        (['  expect: speed unchanged'], '`speed` is compared with an earlier reading, but nothing was remembered'),
        (['  bug: P-1'], 'the test has no `do:`, `expect:` or `measure:` lines'),
        (['  do: slider(1', '  expect: speed = 1'], 'cannot read `slider(1`: expected "," or ")"'),
        (['  do: slider(1) 2', '  expect: speed = 1'], 'cannot read `slider(1) 2`'),
        (['  expect: time. = 1'], 'a field name must follow "."'),
        (['  expect: speed = *'], 'cannot read `*`'),
        (['  do: t = time x', '  expect: speed = 1'], 'cannot read `time x`'),
        (['  measure: nonsense'], 'cannot read `measure: nonsense`'),
        (['  measure: bogus ≥ 5'], '`bogus` is not a metric of targets/web'),
        (['  measure: clause-coverage ≥ "abc"'], '`measure: clause-coverage ≥ "abc"` must compare with a number'),
    ]

    def test_each_mistake_gets_a_message_that_names_it(self):
        for lines, said in self.CASES:
            with self.subTest(lines=lines):
                self.assertIn(said, self.error(*lines))

    def test_each_size_needs_a_resize_probe_in_the_target(self):
        self.assertIn('`each: size` needs a resize action probe in targets/web',
                      self.error('  each: size in 1280x720', '  expect: speed = 1', actions='step(seconds)'))

    def test_generated_inputs_and_benchmarks_are_not_run_yet_and_say_so(self):
        with self.assertRaises(testrun.Unsupported) as caught:
            self.js('  each: 1000 × todos = randomTodos(50)', '  expect: speed = 1')
        self.assertIn('generated inputs', str(caught.exception))
        with self.assertRaises(testrun.Unsupported) as caught:
            self.build(['  measure: fps ≥ 30']).measures()
        self.assertIn('benchmarks (`measure: fps`) are not run yet', str(caught.exception))

    def test_a_target_without_probes_or_a_page_says_what_is_missing(self):
        bare = doc('Web', 'The page.', rules=['- **path** - The page is {path: out/index.html}.'], contract=['- gives **other** - x.'])
        self.project({'targets/web': bare, 'cam': doc('Camera', 'It looks.', rules=self.RULES)})
        with self.assertRaises(testrun.TestError) as caught:
            testrun.web_targets(Project(self.dir))
        self.assertIn('targets/web has no `gives **probes**` item', str(caught.exception))


class TestMeasuresInARun(Translation):
    """`measure: clause-coverage …` is decided in the run, from the results: what it says when it fails."""

    def run_it(self, line):
        self.build([line])
        with mock.patch.object(testrun, 'run_page', lambda t, s, ids, timeout: ([{'id': i, 'status': 'pass'} for i in ids], {})):
            results, summary = testrun.run(Project(self.dir))
        return results['cam/test:zoom']

    def test_a_coverage_below_the_bar_fails_and_says_by_how_much(self):
        got = self.run_it('  measure: clause-coverage ≥ 99')
        self.assertEqual(got['status'], 'fail')
        self.assertRegex(got['message'], r'clause-coverage is \d+\.\d%, want ≥ 99%')

    def test_a_coverage_that_holds_passes_with_the_number_it_measured(self):
        got = self.run_it('  measure: clause-coverage ≥ 0')
        self.assertEqual(got['status'], 'pass')
        self.assertRegex(got['message'], r'clause-coverage \d+%')

    def test_a_line_coverage_with_no_page_to_measure_says_nothing_was_measured(self):
        got = self.run_it('  measure: line-coverage ≥ 50')
        self.assertEqual((got['status'], got['message']), ('fail', 'line-coverage: nothing was measured'))

    def test_a_test_with_an_error_in_it_fails_without_stopping_the_others(self):
        self.build(['  expect: ok'])
        with mock.patch.object(testrun, 'run_page', lambda t, s, ids, timeout: ([{'id': i, 'status': 'pass'} for i in ids], {})):
            results, _ = testrun.run(Project(self.dir))
        self.assertEqual(results['cam/test:zoom']['status'], 'fail')
        self.assertIn('test error: cannot read `expect: ok`', results['cam/test:zoom']['message'])
        self.assertEqual(results['targets/web/test:path']['status'], 'pass')


class TestNamesOfTheTarget(base.Case):
    def test_a_name_list_is_read_with_its_arguments_and_blanks_left_out(self):
        self.assertEqual(testrun._names('step(seconds), slider(v) , , resize(w, h)'), ['step', 'slider', 'resize'])
        self.assertEqual(testrun._names(''), [])

    def test_a_probe_line_that_wraps_goes_on_with_the_field_above(self):
        wrapped = doc('Web', 'The page.', rules=['- **path** - The page is {path: out/index.html}.'],
                      contract=['- gives **probes** - x.', '  read: time,', '    speed', '  do: step(seconds)'])
        self.project({'targets/web': wrapped})
        web = testrun.web_targets(Project(self.dir))[0]
        self.assertEqual((web.reads, web.actions), ({'time', 'speed'}, {'step'}))


if __name__ == '__main__':
    unittest.main()
