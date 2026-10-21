"""Tests for `runs on:`, the test line that leaves a test to the CI jobs that provide an environment: the line itself, the
lock state it gives (`deferred`), the fingerprint, the evidence a job writes and `sor verify`, the gate over them.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. No browser, no network. Every project lives in a temporary folder.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import evidence, testrun          # noqa: E402
from sorlib.markers import Scan               # noqa: E402
from sorlib.model import Project, parse_runs_on   # noqa: E402

doc, write, read = base.doc, base.write, base.read


class TestTheRunsOnLine(unittest.TestCase):
    def test_commas_separate_environments_and_a_plus_joins_names_one_machine_must_have(self):
        sets, err = parse_runs_on('Windows, macos , linux+DB, windows')
        self.assertIsNone(err)
        self.assertEqual(sets, [('windows',), ('macos',), ('linux', 'db')])

    def test_an_empty_list_or_a_name_that_is_not_safe_in_a_file_name_is_an_error(self):
        for text in ('', ' , ', 'win dows', '../x', 'linux+', 'a/b', '-x'):
            with self.subTest(text=text):
                self.assertIsNotNone(parse_runs_on(text)[1])


class Deferred(flows.Flow):
    """greet/hello and greet/bye; a test that says `runs on:` is left to CI."""
    HELLO = ['- **hello** - says hello.', '  expect: ok']
    BYE = ['- **bye** - says bye.', '  expect: ok']

    def greet(self, hello=None, bye=None, rules=None):
        rules = rules or ['- **hello** - The page says {text: Hello}.', '- **bye** - The page says {text: Bye}.']
        tests = (self.HELLO if hello is None else hello) + (self.BYE if bye is None else bye)
        self.project({'greet': doc('Greet', 'Says hello.', rules=rules, tests=tests)})
        write(self.dir, 'out/app.js', flows.APP)

    def entries(self):
        return json.loads(flows.lock_bytes(self.dir))

    def status_json(self):
        code, out, _ = self.sor('status', '--json')
        return json.loads(out)


class TestAChecked(Deferred):
    def test_a_runs_on_line_in_a_clause_or_next_to_manual_or_with_a_bad_name_is_a_problem(self):
        cases = {
            'manual': dict(hello=['- **hello** - looks right.', '  manual: look at it', '  runs on: linux']),
            'a bad name': dict(hello=self.HELLO + ['  runs on: win dows']),
            'an empty list': dict(hello=self.HELLO + ['  runs on:']),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.greet(**kw)
                code, out, _ = self.sor('check')
                self.assertEqual(code, 2, out)
                self.assertIn('runs on', out)

    def test_a_runs_on_line_under_anything_but_a_test_is_plain_text(self):
        # a rule may say where something runs; before `runs on:` existed that was just prose, and it must stay valid
        self.greet(rules=['- **hello** - The page says {text: Hello}.', '  runs on: macOS 14 and Linux',
                          '- **bye** - The page says {text: Bye}.'])
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertNotIn('runs on  ', out)
        self.assertEqual(Project(self.dir).items['greet/hello'].runs_on(), [])

    def test_a_good_line_is_no_problem_and_a_wrapped_one_reads_as_one(self):
        self.greet(hello=self.HELLO + ['  runs on: linux,', '    windows+gpu'])
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        item = Project(self.dir).items['greet/test:hello']
        self.assertEqual(item.runs_on(), [('linux',), ('windows', 'gpu')])


class TestLockingADeferredTest(Deferred):
    def test_a_deferred_test_is_recorded_as_deferred_and_never_blocks_the_lock(self):
        self.greet(hello=self.HELLO + ['  runs on: linux, windows'], bye=['- **bye** - says bye.', '  manual: look'])
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.entries()['greet/test:hello']['result'], 'deferred')
        self.assertIn('1 deferred to CI', out)
        code, out, _ = self.sor('status')
        self.assertIn('tests deferred (1)', out)
        self.assertNotIn('no passing result', out)

    def test_status_lists_the_deferred_tests_apart_from_the_ones_that_wait_for_a_result(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'])
        self.sor('lock', '--all', '--allow-incomplete')
        data = self.status_json()
        self.assertEqual(data['tests_deferred'], ['greet/test:hello'])
        self.assertNotIn('greet/test:hello', data['tests_pending'] + data['tests_not_passed'])
        self.assertIn('greet/test:bye', data['tests_not_passed'])

    def test_the_other_tests_still_block_the_lock_and_the_message_names_only_them(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'])
        code, out, _ = self.sor('lock', '--all')
        self.assertEqual(code, 2)
        self.assertIn('greet/test:bye', out)
        self.assertNotIn('greet/test:hello', out)

    def test_a_result_given_for_a_deferred_test_is_not_recorded_and_says_so(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'])
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass', 'greet/test:bye': 'pass'}))
        code, out, _ = self.sor('lock', '--all', '--results', results)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.entries()['greet/test:hello']['result'], 'deferred')
        self.assertEqual(self.entries()['greet/test:bye']['result'], 'pass')
        self.assertIn('not recorded in the lock', out)

    def test_a_deferred_test_does_not_hold_back_a_change_to_code_it_shares(self):
        # SPEC §16: a clause whose code changed with another one needs its own test to pass again. A test CI proves
        # settles that for the lock, or a project that defers tests could never lock a shared region.
        write(self.dir, 'out/app.js', '// @clause greet/hello greet/bye\nconsole.log("both");\n// @clause end\n')
        self.greet(hello=self.HELLO + ['  runs on: linux'], bye=self.BYE + ['  runs on: linux'])
        write(self.dir, 'out/app.js', '// @clause greet/hello greet/bye\nconsole.log("both");\n// @clause end\n')
        self.assertEqual(self.sor('lock', '--all')[0], 0)
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')
        write(self.dir, 'out/app.js', '// @clause greet/hello greet/bye\nconsole.log("both again");\n// @clause end\n')
        code, out, _ = self.sor('lock', 'greet/hello')
        self.assertEqual(code, 0, out)
        self.assertNotIn('must pass', out)

    def test_a_lock_names_the_tests_that_just_became_deferred_and_only_once(self):
        # one line is all it takes to leave a test to CI, so the lock says which tests that is
        results = write(self.dir, 'results.json', json.dumps({'greet/test:hello': 'pass', 'greet/test:bye': 'pass'}))
        self.greet()
        self.assertEqual(self.sor('lock', '--all', '--results', results)[0], 0)
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '- **hello** - says hello.\n  expect: ok',
                         '- **hello** - says hello.\n  expect: ok\n  runs on: linux')
        code, out, _ = self.sor('lock', '--all', '--results', results)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r'now left to CI.*greet/test:hello')
        self.assertNotIn('greet/test:bye', out.split('now left to CI')[1].split('\n')[0])
        out = self.sor('lock', '--all', '--results', results)[1]
        self.assertNotIn('now left to CI', out)

    def test_the_lock_stays_the_same_bytes_whatever_runs_where(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'], bye=['- **bye** - says bye.', '  manual: look'])
        self.sor('lock', '--all')
        first = flows.lock_bytes(self.dir)
        self.sor('lock', '--all')
        self.assertEqual(flows.lock_bytes(self.dir), first)
        self.assertNotIn(b'linux', first)


class Gate(Deferred):
    """Jobs write evidence, `sor verify` is the gate over it."""
    KEY = 'greet/test:hello'

    def setUp(self):
        super().setUp()
        self.greet(hello=self.HELLO + ['  runs on: linux, windows'])
        self.n = 0

    def job(self, name, provides, status='pass', key=None, out=None):
        """Runs `sor evidence` for a job that says `status` about a test; returns (exit code, output)."""
        self.n += 1
        results = write(self.dir, f'r{self.n}.json', json.dumps({key or self.KEY: status}))
        out = out or os.path.join(self.dir, 'evidence', f'{name}.json')
        code, text, _ = self.sor('evidence', '--job', name, '--provides', provides, '--results', results, '--out', out)
        return code, text

    def verify(self, *args):
        code, out, _ = self.sor('verify', *args)
        return code, out

    def fingerprint(self):
        project = Project(self.dir)
        return evidence.fingerprints(project, Scan(project))[self.KEY]


class TestWritingEvidence(Gate):
    def test_a_job_keeps_only_the_tests_that_say_runs_on_and_name_what_it_provides(self):
        results = write(self.dir, 'r.json', json.dumps({self.KEY: 'pass', 'greet/test:bye': 'pass'}))
        out = os.path.join(self.dir, 'ev', 'linux.json')
        code, text, _ = self.sor('evidence', '--job', 'linux-ci', '--provides', 'Linux,db', '--results', results, '--out', out)
        self.assertEqual(code, 0, text)
        with open(out, encoding='utf8') as fh:
            data = json.load(fh)
        self.assertEqual(data, {'job': 'linux-ci', 'provides': ['db', 'linux'],
                                'results': {self.KEY: {'fingerprint': self.fingerprint(), 'status': 'pass'}}})
        self.assertIn('do not say `runs on:`', text)

    def test_a_job_that_provides_none_of_the_environments_writes_no_result_and_says_so(self):
        code, text = self.job('mac', 'macos')
        self.assertEqual(code, 0, text)
        self.assertIn('provides none of their environments', text)
        with open(os.path.join(self.dir, 'evidence', 'mac.json'), encoding='utf8') as fh:
            self.assertEqual(json.load(fh)['results'], {})

    def test_the_file_has_the_same_bytes_every_time(self):
        self.job('linux', 'linux')
        path = os.path.join(self.dir, 'evidence', 'linux.json')
        first = read(path)
        self.job('linux', 'linux')
        self.assertEqual(read(path), first)

    def test_a_job_name_that_could_leave_the_folder_a_result_for_a_non_test_and_a_wrong_status_are_refused(self):
        for name, kw in (('../x', {}), ('ok', {'key': 'greet/nothing'}), ('ok', {'status': 'passed'})):
            with self.subTest(name=name, kw=kw):
                code, text = self.job(name, 'linux', out=os.path.join(self.dir, 'o.json'), **kw)
                self.assertEqual(code, 2, text)
                self.assertIn('refused', text)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'o.json')))

    def test_provides_must_name_something_and_every_entry_must_be_a_name(self):
        code, text = self.job('ok', '')
        self.assertEqual(code, 2)
        self.assertIn('names at least one environment', text)
        code, text = self.job('ok', 'linux,,db')      # `runs on: linux,,db` is a problem, so this is one too
        self.assertEqual(code, 2)
        self.assertIn('an empty name', text)

    def test_a_results_file_may_hold_tests_that_are_not_kept_whatever_their_status(self):
        results = write(self.dir, 'r.json', json.dumps({self.KEY: 'pass', 'greet/test:bye': 'skipped'}))
        code, text, _ = self.sor('evidence', '--job', 'linux', '--provides', 'linux', '--results', results)
        self.assertEqual(code, 0, text)
        self.assertIn('do not say `runs on:`', text)

    def test_a_status_that_is_no_result_is_still_refused_for_a_test_that_is_kept(self):
        code, text = self.job('linux', 'linux', status='skipped')
        self.assertEqual(code, 2)
        self.assertIn('is not a result', text)

    def test_a_windows_device_name_is_not_a_job(self):
        for name in ('con', 'nul', 'com1', 'LPT3', 'aux.x'):
            with self.subTest(name):
                self.assertEqual(self.job(name, 'linux', out=os.path.join(self.dir, 'o.json'))[0], 2)
        self.assertEqual(self.job('console', 'linux')[0], 0)

    def test_nothing_is_left_behind_when_the_write_fails(self):
        out = os.path.join(self.dir, 'ev', 'x.json')
        with mock.patch.object(evidence.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                evidence.write(out, {'job': 'x', 'provides': ['linux'], 'results': {}})
        self.assertEqual(os.listdir(os.path.join(self.dir, 'ev')), [])


class TestTheFingerprint(Gate):
    def test_it_follows_the_test_the_clause_it_proves_and_its_code_and_nothing_else(self):
        before = self.fingerprint()
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Bye}', '{text: Ciao}')      # another clause
        self.assertEqual(self.fingerprint(), before)
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hi}')      # the clause it proves
        changed = self.fingerprint()
        self.assertNotEqual(changed, before)
        flows.replace_in(self.app, 'console.log("Hello")', 'console.log("Hi")')                     # its code
        self.assertNotEqual(self.fingerprint(), changed)

    def test_it_covers_a_clause_the_test_proves_without_being_named_after_it(self):
        # the test is named after `bye` but proves `hello` through `proves:`; a manual test's check would miss hello's code
        self.greet(hello=self.HELLO, bye=['- **bye** - says bye.', '  expect: ok', '  proves: {hello}', '  runs on: linux'])
        key = 'greet/test:bye'
        project = Project(self.dir)
        before = evidence.fingerprints(project, Scan(project))[key]
        flows.replace_in(self.app, 'console.log("Hello")', 'console.log("Hi")')
        project = Project(self.dir)
        self.assertNotEqual(evidence.fingerprints(project, Scan(project))[key], before)

    def test_it_covers_the_rows_and_values_of_the_clause(self):
        rules = ['- **hello** - The page says {text: Hello}.', '- **bye** - The page says {text: Bye}.']
        self.greet(hello=self.HELLO + ['  runs on: linux'], rules=rules)
        before = self.fingerprint()
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '{text: Hello}', '{text: Hello, text2: x}')
        self.assertNotEqual(self.fingerprint(), before)


class TestTheFingerprintOfRowsAndTheTestsOwnTable(Gate):
    ROWS = ['- **hello** - The page says its text in every language.', '  | lang | text |', '  | en | Hello |', '  | fr | Salut |']
    CODE = '// @clause greet/hello\nconsole.log("Hello");\n// @clause end\nconsole.log("Salut");  // @clause greet/hello/fr\n'

    def test_it_covers_code_marked_with_a_row_of_the_clause_it_proves(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'], rules=self.ROWS)
        write(self.dir, 'out/app.js', self.CODE)
        before = self.fingerprint()
        write(self.dir, 'out/app.js', self.CODE.replace('Salut', 'Salut!'))
        self.assertNotEqual(self.fingerprint(), before)

    def test_it_covers_the_rows_of_the_test_itself(self):
        self.greet(hello=self.HELLO + ['  runs on: linux', '  | size | zoom |', '  | phone | 3x |'])
        before = self.fingerprint()
        flows.replace_in(os.path.join(self.spec, 'greet.md'), '| phone | 3x |', '| phone | 4x |')
        self.assertNotEqual(self.fingerprint(), before)


class TestEvidenceFromAResultsFileThatIsNotResults(Gate):
    def test_json_null_is_refused_like_any_other_wrong_shape(self):
        results = write(self.dir, 'null.json', 'null')
        code, text, err = self.sor('evidence', '--job', 'linux', '--provides', 'linux', '--results', results)
        self.assertEqual((code, err), (2, ''))
        self.assertIn('evidence refused', text)
        self.assertIn('as `sor test --out` writes it', text)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'evidence')))

    def test_a_missing_file_is_refused_and_not_a_crash(self):
        code, text, err = self.sor('evidence', '--job', 'linux', '--provides', 'linux', '--results', os.path.join(self.dir, 'nope.json'))
        self.assertEqual((code, err), (2, ''))
        self.assertIn('cannot read', text)


class TestStrengthRunsTheTestsAsTestDoes(Deferred):
    def test_the_environments_a_run_provides_and_all_reach_the_run_strength_makes(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'])
        seen = []

        def fake_run(project, only=None, timeout=90, confirmed=(), provides=None, everything=False):
            seen.append((provides, everything))
            return {}, {}

        with mock.patch.object(testrun, 'run', fake_run), mock.patch.object(testrun, 'web_targets', return_value=[object()]):
            self.sor('test', '--strength', '--provides', 'linux')
            self.sor('test', '--strength', '--all')
            self.sor('test', '--strength')
        self.assertEqual(seen, [(frozenset({'linux'}), False), (frozenset(), True), (frozenset(), False)])


class TestTheEvidenceFormat(Gate):
    """Format 1 has no marker and keeps its bytes. Format 2 adds the commit and the run the job saw."""

    def written(self, name='linux-ci', provides='linux', *flags):
        results = write(self.dir, 'r.json', json.dumps({self.KEY: 'pass'}))
        out = os.path.join(self.dir, 'evidence', name + '.json')
        code, text, err = self.sor('evidence', '--job', name, '--provides', provides, '--results', results, '--out', out, *flags)
        return code, text + err, out

    def by_hand(self, name, **extra):
        data = {'job': name, 'provides': ['linux'], 'results': {self.KEY: {'fingerprint': self.fingerprint(), 'status': 'pass'}}}
        data.update(extra)
        return write(self.dir, f'evidence/{name}.json', json.dumps(data))

    def test_a_job_that_gives_no_commit_and_no_run_writes_format_1_without_a_marker(self):
        code, text, out = self.written()
        self.assertEqual(code, 0, text)
        self.assertEqual(set(json.loads(read(out))), {'job', 'provides', 'results'})
        self.assertNotIn('"format"', read(out))

    def test_a_commit_and_a_run_make_it_format_2_with_the_same_bytes_every_time(self):
        code, text, out = self.written('linux-ci', 'linux', '--commit', 'ABC1234', '--run', 'ci-7')
        self.assertEqual(code, 0, text)
        data = json.loads(read(out))
        self.assertEqual((data['format'], data['from']), (2, {'commit': 'abc1234', 'run': 'ci-7'}))
        first = read(out)
        self.written('linux-ci', 'linux', '--commit', 'abc1234', '--run', 'ci-7')
        self.assertEqual(read(out), first)

    def test_either_one_alone_is_enough(self):
        for flags, want in ((('--commit', 'abc1234'), {'commit': 'abc1234'}), (('--run', 'build.42'), {'run': 'build.42'})):
            with self.subTest(flags):
                self.assertEqual(json.loads(read(self.written('j', 'linux', *flags)[2]))['from'], want)

    def test_a_commit_or_run_that_is_not_a_token_is_refused_and_nothing_is_written(self):
        for flags in (('--commit', 'xyz'), ('--commit', 'abc'), ('--commit', 'abc123g'), ('--run', '../x'), ('--run', 'a b'), ('--run', '')):
            with self.subTest(flags):
                code, text, out = self.written('linux-ci', 'linux', *flags)
                self.assertEqual(code, 2, text)
                self.assertIn('evidence refused', text)
                self.assertFalse(os.path.exists(out))

    def test_the_gate_reads_both_formats_together_and_names_the_commit_in_text_and_json(self):
        self.written('linux-ci', 'linux')
        self.written('win-ci', 'windows', '--commit', 'abc1234def5678', '--run', 'ci-7')
        code, out = self.verify()
        self.assertEqual(code, 0, out)
        self.assertIn('win-ci (commit abc1234def56, run ci-7)', out)
        self.assertNotIn('linux-ci (', out)
        data = json.loads(self.verify('--json')[1])
        self.assertEqual(data['sources'], {'win-ci': {'commit': 'abc1234def5678', 'run': 'ci-7'}})

    def test_a_long_run_id_is_shown_whole_and_only_the_commit_is_cut(self):
        run = '1234567890123456'
        self.written('win-ci', 'windows', '--commit', 'a' * 40, '--run', run)
        self.written('linux-ci', 'linux')
        out = self.verify()[1]
        self.assertIn(f'commit {"a" * 12}, run {run})', out)
        self.assertNotIn('a' * 13, out)

    def test_a_format_this_tool_does_not_read_is_refused_with_a_message_to_update(self):
        self.by_hand('linux-ci', format=evidence.FORMAT + 1, **{'from': {'run': 'ci-7'}})
        code, out = self.verify()
        self.assertEqual(code, 2, out)
        self.assertIn(f'evidence in format {evidence.FORMAT + 1}', out)
        self.assertIn('Update sor', out)

    def test_a_marker_that_is_no_whole_number_from_1_up_is_refused(self):
        for value in ('2', 0, -1, 1.5, True, None, [2]):
            with self.subTest(value):
                shutil_target = self.by_hand('linux-ci', format=value, **{'from': {'run': 'ci-7'}})
                code, out = self.verify()
                self.assertEqual(code, 2, out)
                self.assertIn('not an evidence format number', out)
                os.remove(shutil_target)

    def test_the_keys_have_to_fit_the_format(self):
        cases = {
            'format 2 without from': dict(format=2),
            'format 2 with an empty from': dict(format=2, **{'from': {}}),
            'format 1 written out, with a from': dict(format=1, **{'from': {'run': 'ci-7'}}),
            'a from with a key it does not know': dict(format=2, **{'from': {'branch': 'main'}}),
            'a from with a commit that is not hexadecimal': dict(format=2, **{'from': {'commit': 'main'}}),
            'a from with a run that is not text': dict(format=2, **{'from': {'run': 7}}),
        }
        for name, extra in cases.items():
            with self.subTest(name):
                path = self.by_hand('linux-ci', **extra)
                self.assertEqual(self.verify()[0], 2, name)
                os.remove(path)

    def test_format_1_may_say_so_and_is_read_the_same(self):
        self.by_hand('linux-ci', format=1)
        self.assertEqual(self.verify()[0], 1)    # linux proven, windows still missing: the file itself is fine

    def test_a_format_2_file_has_a_key_a_tool_from_before_the_number_does_not_know(self):
        # that tool reads exactly {job, provides, results}, so it refuses a format 2 file loudly instead of reading it wrongly
        data = json.loads(read(self.written('linux-ci', 'linux', '--run', 'ci-7')[2]))
        self.assertNotEqual(set(data), {'job', 'provides', 'results'})


class TestTheGate(Gate):
    def test_every_environment_with_a_current_pass_is_proven(self):
        self.job('linux-ci', 'linux')
        self.job('win-ci', 'windows')
        code, out = self.verify()
        self.assertEqual(code, 0, out)
        self.assertIn('1 deferred test(s): 1 proven, 0 not', out)
        self.assertIn('linux-ci', out)

    def test_a_missing_environment_fails_and_is_named(self):
        self.job('linux-ci', 'linux')
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertRegex(out, r'windows\s+MISSING')

    def test_no_evidence_at_all_fails_with_every_environment_missing(self):
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(out.count('MISSING'), 2)

    def test_a_result_for_an_older_clause_or_code_is_stale(self):
        self.job('linux-ci', 'linux')
        self.job('win-ci', 'windows')
        flows.replace_in(self.app, 'console.log("Hello")', 'console.log("Hi")')
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(out.count('STALE'), 2)

    def test_a_current_failure_is_not_averaged_away_by_another_job_that_passed(self):
        self.job('linux-a', 'linux', 'pass')
        self.job('linux-b', 'linux', 'fail')
        self.job('win-ci', 'windows')
        code, out = self.verify()
        self.assertEqual(code, 1)
        self.assertRegex(out, r'linux\s+FAILED\s+linux-b')

    def test_a_plus_needs_one_machine_with_every_name(self):
        self.greet(hello=self.HELLO + ['  runs on: linux+db'])
        self.job('only-linux', 'linux')
        self.job('only-db', 'db')
        self.assertEqual(self.verify()[0], 1)
        self.job('both', 'linux,db')
        code, out = self.verify()
        self.assertEqual(code, 0, out)

    def test_evidence_files_are_read_from_the_paths_given_instead_of_the_default_folder(self):
        self.job('linux-ci', 'linux', out=os.path.join(self.dir, 'elsewhere', 'a.json'))
        self.job('win-ci', 'windows', out=os.path.join(self.dir, 'elsewhere', 'b.json'))
        self.assertEqual(self.verify()[0], 1)    # nothing in evidence/
        self.assertEqual(self.verify(os.path.join(self.dir, 'elsewhere'))[0], 0)

    def test_an_evidence_file_that_cannot_be_trusted_makes_the_gate_refuse_with_exit_2(self):
        folder = os.path.join(self.dir, 'evidence')
        good = {'job': 'a', 'provides': ['linux'], 'results': {self.KEY: {'fingerprint': '0' * 12, 'status': 'pass'}}}
        cases = {
            'not json': 'nope',
            'extra key': dict(good, extra=1),
            'a wrong status': dict(good, results={self.KEY: {'fingerprint': '0' * 12, 'status': 'passed'}}),
            'a bad hash': dict(good, results={self.KEY: {'fingerprint': 'xyz', 'status': 'pass'}}),
            'an unsafe job': dict(good, job='../a'),
            'a bad provides': dict(good, provides=['Linux!']),
        }
        for name, content in cases.items():
            with self.subTest(name):
                write(self.dir, 'evidence/a.json', content if isinstance(content, str) else json.dumps(content))
                code, out = self.verify()
                self.assertEqual(code, 2, out)
                self.assertIn('a.json', out)
        write(self.dir, 'evidence/a.json', json.dumps(good))
        write(self.dir, 'evidence/b.json', json.dumps(good))
        code, out = self.verify()
        self.assertEqual(code, 2)
        self.assertIn('also in', out)
        self.assertTrue(os.path.isdir(folder))

    def test_an_evidence_file_whose_job_is_not_a_string_is_refused_not_a_crash(self):
        for job in (5, True, ['a'], None, 0):
            with self.subTest(repr(job)):
                write(self.dir, 'evidence/a.json', json.dumps({'job': job, 'provides': ['linux'], 'results': {}}))
                code, out = self.verify()
                self.assertEqual(code, 2, out)
                self.assertIn('is not a job name', out)

    def test_artifacts_in_their_own_subfolders_are_found(self):
        # a download of several CI artifacts makes one folder for each
        self.job('linux-ci', 'linux', out=os.path.join(self.dir, 'artifacts', 'linux', 'linux-ci.json'))
        self.job('win-ci', 'windows', out=os.path.join(self.dir, 'artifacts', 'windows', 'win-ci.json'))
        code, out = self.verify(os.path.join(self.dir, 'artifacts'))
        self.assertEqual(code, 0, out)

    def test_the_gate_says_when_it_found_no_evidence_file(self):
        os.makedirs(os.path.join(self.dir, 'artifacts'))
        code, out = self.verify(os.path.join(self.dir, 'artifacts'))
        self.assertEqual(code, 1)
        self.assertIn('no evidence files', out)

    def test_the_gate_refuses_while_a_runs_on_line_is_wrong(self):
        self.greet(hello=self.HELLO + ['  runs on: win dows'])
        code, out = self.verify()
        self.assertEqual(code, 2)
        self.assertIn('runs on', out)

    def test_results_for_tests_that_stopped_saying_runs_on_are_ignored_and_named(self):
        self.job('linux-ci', 'linux')
        self.greet()
        code, out = self.verify()
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to verify', out)
        self.assertIn(self.KEY, out)

    def test_json_says_the_same_as_the_text(self):
        self.job('linux-ci', 'linux')
        code, out = self.verify('--json')
        data = json.loads(out)
        self.assertEqual((code, data['ok']), (1, False))
        self.assertEqual([e['status'] for e in data['tests'][0]['environments']], ['pass', 'missing'])


class TestRunningWithEnvironments(flows.Flow):
    """`sor test` with the browser replaced: the page passes every test it is asked for."""

    def setUp(self):
        super().setUp()
        rules = ['- **quick** - Errors stay at zero.', '- **slow** - Errors stay at zero on the real database.']
        tests = ['- **quick** - the page has no errors.', '  expect: count(errors) = 0',
                 '- **slow** - the page has no errors on the real database.', '  expect: count(errors) = 0',
                 '  runs on: linux, windows+gpu']
        self.project({'targets/web': flows.TARGET, 'lim': doc('Limits', 'How many errors.', rules=rules, tests=tests)})
        write(self.dir, 'out/index.html', flows.PAGE)

    def ask(self, *args):
        """(code, output, the test ids asked of the page)"""
        asked = []

        def page(target, script, ids, timeout):
            asked.extend(ids)
            return [{'id': i, 'status': 'pass'} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            code, out, err = self.sor(*args)
        return code, out + err, asked

    def test_a_plain_run_leaves_a_deferred_test_to_ci_and_says_so(self):
        code, out, asked = self.ask('test')
        self.assertEqual(code, 0, out)
        self.assertIn('lim/test:quick', asked)
        self.assertNotIn('lim/test:slow', asked)
        self.assertRegex(out, r'DEFER\s+lim/test:slow\s+runs on linux, windows\+gpu')
        self.assertIn('1 deferred to CI', out)

    def test_a_run_that_provides_one_of_the_environments_runs_the_test(self):
        for provides, runs in (('linux', True), ('Linux, db', True), ('windows', False), ('windows,gpu', True), ('macos', False)):
            with self.subTest(provides):
                asked = self.ask('test', '--provides', provides)[2]
                self.assertEqual('lim/test:slow' in asked, runs)

    def test_all_runs_every_deferred_test_whatever_it_names(self):
        self.assertIn('lim/test:slow', self.ask('test', '--all')[2])

    def test_naming_the_test_runs_it_but_naming_its_part_does_not(self):
        self.assertIn('lim/test:slow', self.ask('test', 'lim/test:slow')[2])
        self.assertNotIn('lim/test:slow', self.ask('test', 'lim')[2])

    def test_a_lock_with_run_tests_records_the_deferred_test_as_deferred_and_the_others_as_passed(self):
        code, out, asked = self.ask('lock', '--all', '--run-tests')
        self.assertEqual(code, 0, out)
        self.assertNotIn('lim/test:slow', asked)
        entries = json.loads(flows.lock_bytes(self.dir))
        self.assertEqual((entries['lim/test:slow']['result'], entries['lim/test:quick']['result']), ('deferred', 'pass'))

    def test_out_holds_results_for_what_ran_and_nothing_for_the_rest(self):
        out = os.path.join(self.dir, 'r.json')
        self.ask('test', '--out', out)
        with open(out, encoding='utf8') as fh:
            data = json.load(fh)
        self.assertEqual(data.get('lim/test:quick'), 'pass')
        self.assertNotIn('lim/test:slow', data)

    def test_a_bad_provides_is_refused(self):
        code, out, _ = self.ask('test', '--provides', 'lin ux')
        self.assertEqual(code, 2)
        self.assertIn('--provides', out)

    def test_the_whole_chain_from_a_job_to_the_gate(self):
        # a job runs what it provides, writes evidence from the results `sor test --out` wrote, and the gate reads it
        results = os.path.join(self.dir, 'r.json')
        self.ask('test', '--provides', 'linux', '--out', results)
        self.assertEqual(self.sor('evidence', '--job', 'linux-ci', '--provides', 'linux', '--results', results)[0], 0)
        code, out, _ = self.sor('verify')
        self.assertEqual(code, 1)
        self.assertRegex(out, r'linux\s+ok\s+linux-ci')
        self.assertRegex(out, r'windows\+gpu\s+MISSING')
        self.ask('test', '--provides', 'windows,gpu', '--out', results)
        self.assertEqual(self.sor('evidence', '--job', 'win-ci', '--provides', 'windows,gpu', '--results', results)[0], 0)
        self.assertEqual(self.sor('verify')[0], 0)


class TestAnExternalTestLeftToCi(flows.Flow):
    """The hour-long database test: written in the project's own framework, so `sor test` shows it as EXTERNAL. It says `runs on:`,
    so no lock waits for a result of it."""

    def setUp(self):
        super().setUp()
        tests = ['- **limit** - the cap holds.', '  expect: count(errors) = {limit.max}',
                 '- **replica** - errors stay below the cap on the real database.', '  proves: {limit}', '  runs on: linux+db']
        self.project({'targets/web': flows.TARGET_WITH_TEST_CODE,
                      'lim': doc('Limits', 'How many errors.', rules=['- **limit** - At most {max: 5} errors.'], tests=tests)})
        write(self.dir, 'out/index.html', flows.PAGE)
        write(self.dir, 'test/replica.test.js', '// @clause test lim/replica\nit("replica", () => {});\n// @clause end\n')

    def lock(self, *args):
        def page(target, script, ids, timeout):
            return [{'id': i, 'status': 'pass'} for i in ids], {}

        with mock.patch.object(testrun, 'run_page', page):
            return self.sor('lock', '--all', *args)

    def test_the_lock_does_not_wait_for_it_and_records_it_as_deferred(self):
        code, out, _ = self.lock('--run-tests')
        self.assertEqual(code, 0, out)
        self.assertNotIn('EXTERNAL', out.replace('DEFER', ''))
        entries = json.loads(flows.lock_bytes(self.dir))
        self.assertEqual(entries['lim/test:replica']['result'], 'deferred')
        self.assertEqual(entries['lim/test:limit']['result'], 'pass')

    def test_a_results_file_for_it_is_not_taken_into_the_lock_and_says_so(self):
        results = write(self.dir, 'framework.json', json.dumps({'lim/test:replica': 'pass'}))
        code, out, _ = self.lock('--run-tests', '--results', results)
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(flows.lock_bytes(self.dir))['lim/test:replica']['result'], 'deferred')

    def test_the_job_that_has_both_names_proves_it_through_evidence(self):
        self.lock('--run-tests')
        results = write(self.dir, 'framework.json', json.dumps({'lim/test:replica': 'pass'}))
        self.assertEqual(self.sor('evidence', '--job', 'db', '--provides', 'linux,db', '--results', results)[0], 0)
        self.assertEqual(self.sor('verify')[0], 0)


class TestListingTests(Deferred):
    """`sor test --list` runs nothing, so it works in a project with no web target at all."""

    def test_it_lists_what_a_run_would_run_and_what_it_leaves_to_ci_without_a_browser(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'], bye=['- **bye** - says bye.', '  manual: look'])
        with mock.patch.object(testrun, 'find_chrome', side_effect=AssertionError('a browser was asked for')):
            code, out, _ = self.sor('test', '--list')
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r'DEFER\s+greet/test:hello\s+runs on linux')
        self.assertRegex(out, r'MANUAL\s+greet/test:bye')
        self.assertIn('0 to run, 1 left to CI, 1 manual', out)
        code, out, _ = self.sor('test', '--list', '--provides', 'linux')
        self.assertRegex(out, r'RUN\s+greet/test:hello')

    def test_json_gives_the_environments_the_fingerprint_and_whether_your_own_framework_runs_it(self):
        self.greet(hello=['- **hello** - the greeting holds.', '  proves: {hello}', '  runs on: linux, windows+gpu'])
        write(self.dir, 'test/hello.test.js', '// @clause test greet/hello\nit("hello", () => {});\n// @clause end\n')
        write(self.dir, 'sor/targets/web.md', doc('Web', 'Where it runs.', rules=['- **test-code** - Hand-written tests are in {path: test/}.']))
        code, out, _ = self.sor('test', '--list', '--json')
        row = next(t for t in json.loads(out)['tests'] if t['id'] == 'greet/test:hello')
        self.assertEqual(row['runs_on'], [['linux'], ['windows', 'gpu']])
        self.assertTrue(row['external'])
        self.assertFalse(row['selected'])
        project = Project(self.dir)
        self.assertEqual(row['fingerprint'], evidence.fingerprints(project, Scan(project))['greet/test:hello'])

    def test_external_means_what_sor_test_means_a_stepless_test_with_marked_code(self):
        self.greet(hello=['- **hello** - the greeting holds.', '  proves: {hello}', '  runs on: linux'])
        row = next(t for t in json.loads(self.sor('test', '--list', '--json')[1])['tests'] if t['id'] == 'greet/test:hello')
        self.assertFalse(row['external'])        # no code is marked `@clause test`: `sor test` would fail it, not leave it to a framework
        write(self.dir, 'test/hello.test.js', '// @clause test greet/hello\nit("hello", () => {});\n// @clause end\n')
        write(self.dir, 'sor/targets/web.md', doc('Web', 'Where it runs.', rules=['- **test-code** - Hand-written tests are in {path: test/}.']))
        row = next(t for t in json.loads(self.sor('test', '--list', '--json')[1])['tests'] if t['id'] == 'greet/test:hello')
        self.assertTrue(row['external'])

    def test_a_name_that_matches_no_test_is_still_an_error(self):
        self.greet()
        self.assertEqual(self.sor('test', '--list', 'greet/nothing')[0], 2)


class TestTheUsageList(unittest.TestCase):
    def test_sor_help_names_the_commands_that_run_on_and_evidence_add(self):
        from sorlib import cli
        for words in ('sor test --list', 'sor evidence --job', 'sor verify'):
            self.assertIn(words, cli.__doc__)


class TestTheNeverRunNote(Deferred):
    def test_a_deferred_test_nothing_can_run_is_told_to_use_a_framework_and_evidence_not_manual(self):
        self.greet(hello=self.HELLO + ['  runs on: linux'])
        out = self.sor('check')[1]
        self.assertIn('say `runs on:` but have do:', out)
        self.assertIn('`sor evidence`', out)
        self.assertNotIn('Add a `manual:` line', out.split('greet/test:bye')[0])   # the advice for hello does not offer it

    def test_a_test_that_does_not_say_runs_on_keeps_the_old_note(self):
        self.greet()
        out = self.sor('check')[1]
        self.assertIn('Add a `manual:` line', out)
        self.assertNotIn('say `runs on:`', out)


if __name__ == '__main__':
    unittest.main()
