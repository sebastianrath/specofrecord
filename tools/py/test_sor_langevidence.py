"""Tests for the evidence of a test that says `runs on:` in a project that says its targets (SPEC §8): a test with test code in some languages
takes a result for each (`greet/test:hello@py`), the fingerprint of a language covers the code of that language only, `sor evidence` and
`sor verify` read the results by the lock's rule, and a test with no test code per language is as it was.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
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
import test_sor_targets_lock as targeted     # noqa: E402
from sorlib import evidence                  # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

write, read = base.write, base.read
TEST = 'greet/test:hello'
PY_TEST = '# @clause test greet/hello\ndef test_hello():\n    assert HELLO\n{}# @clause end\n'
TS_TEST = '// @clause test greet/hello\ntest("hello", () => expect(HELLO));\n{}// @clause end\n'
TESTS = ['- **hello** - says hello.', '  expect: ok', '  runs on: linux, windows', '- **bye** - looks right.', '  manual: look']


class PerLanguage(targeted.Targeted):
    """greet/hello has code and test code in Python and in TypeScript, and its test says `runs on: linux, windows`."""

    def setUp(self):
        super().setUp()
        self.build(tests=TESTS)
        self.rebuild('py')
        self.rebuild('ts')
        self.write_test_py('')
        self.write_test_ts('')

    def rebuild(self, language, word='Hello'):
        write(self.dir, f'src_{language}/greet.{language}', (self.PY if language == 'py' else self.TS).replace('Hello', word))

    def write_test_py(self, more):
        write(self.dir, 'src_py/test_greet.py', PY_TEST.format(more))

    def write_test_ts(self, more):
        write(self.dir, 'src_ts/greet.test.ts', TS_TEST.format(more))

    def fingerprints(self):
        project = Project(self.dir)
        return evidence.fingerprints(project, Scan(project))

    def job(self, name, provides, results):
        path = write(self.dir, f'results-{name}.json', json.dumps(results))
        out = os.path.join(self.dir, 'evidence', f'{name}.json')
        code, text, _ = self.sor('evidence', '--job', name, '--provides', provides, '--results', path, '--out', out)
        return code, text

    def verify(self, *args):
        code, out, _ = self.sor('verify', '--json', *args)
        return code, json.loads(out)

    def statuses(self, data):
        return {r['id']: {'+'.join(e['needs']): e['status'] for e in r['environments']} for r in data['tests']}


class TestTheFingerprintOfALanguage(PerLanguage):
    def test_a_test_with_test_code_has_one_for_the_test_and_one_for_each_language(self):
        fps = self.fingerprints()
        self.assertEqual(sorted(k for k in fps if k.startswith(TEST)), [TEST, f'{TEST}@py', f'{TEST}@ts'])
        self.assertEqual(len({fps[TEST], fps[f'{TEST}@py'], fps[f'{TEST}@ts']}), 3)

    def test_code_in_python_makes_python_stale_and_leaves_typescript_current(self):
        before = self.fingerprints()
        self.rebuild('py', word='Hi')
        after = self.fingerprints()
        self.assertNotEqual(after[f'{TEST}@py'], before[f'{TEST}@py'])
        self.assertEqual(after[f'{TEST}@ts'], before[f'{TEST}@ts'])
        self.assertNotEqual(after[TEST], before[TEST])                    # the one for the test as a whole follows every language

    def test_test_code_in_typescript_makes_only_typescript_stale(self):
        before = self.fingerprints()
        self.write_test_ts('test("again", () => expect(HELLO));\n')
        after = self.fingerprints()
        self.assertNotEqual(after[f'{TEST}@ts'], before[f'{TEST}@ts'])
        self.assertEqual(after[f'{TEST}@py'], before[f'{TEST}@py'])

    def test_the_text_of_the_clause_makes_every_language_stale(self):
        before = self.fingerprints()
        self.change_clause()
        after = self.fingerprints()
        for key in (TEST, f'{TEST}@py', f'{TEST}@ts'):
            self.assertNotEqual(after[key], before[key], key)

    def test_the_text_of_the_test_makes_every_language_stale(self):
        before = self.fingerprints()
        base_replace = read(self.spec_file).replace('says hello.', 'says hello twice.')
        write(self.dir, 'sor/greet.md', base_replace)
        after = self.fingerprints()
        for key in (f'{TEST}@py', f'{TEST}@ts'):
            self.assertNotEqual(after[key], before[key], key)

    def test_a_test_with_no_test_code_per_language_has_the_one_it_always_had(self):
        os.remove(os.path.join(self.dir, 'src_py', 'test_greet.py'))      # the same spec, no test code
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))
        fps = self.fingerprints()
        self.assertEqual([k for k in fps if '@' in k], [])
        before = fps[TEST]
        self.rebuild('ts', word='Hi')
        self.assertNotEqual(self.fingerprints()[TEST], before)             # an edit in any language is an edit of what it proves

    ROWS = ['- **hello** - The greeting per language.', '  | lang | text |', '  | en | Hello |', '  | fr | Salut |', '- **bye** - looks right.']

    def test_the_code_of_a_row_of_a_proved_clause_counts_in_its_language_only(self):
        self.build(rules=self.ROWS, tests=TESTS)
        write(self.dir, 'src_py/greet.py', self.PY + 'FR = "Salut"  # @clause greet/hello/fr\n')
        write(self.dir, 'src_ts/greet.ts', self.TS + 'export const FR = "Salut";  // @clause greet/hello/fr\n')
        before = self.fingerprints()
        write(self.dir, 'src_ts/greet.ts', self.TS + 'export const FR = "Bonjour";  // @clause greet/hello/fr\n')
        after = self.fingerprints()
        self.assertNotEqual(after[f'{TEST}@ts'], before[f'{TEST}@ts'])
        self.assertEqual(after[f'{TEST}@py'], before[f'{TEST}@py'])

    def test_the_text_of_a_row_of_a_proved_clause_makes_every_language_stale(self):
        self.build(rules=self.ROWS, tests=TESTS)
        before = self.fingerprints()
        write(self.dir, 'sor/greet.md', read(self.spec_file).replace('| fr | Salut |', '| fr | Bonjour |'))
        after = self.fingerprints()
        for key in (f'{TEST}@py', f'{TEST}@ts'):
            self.assertNotEqual(after[key], before[key], key)


class TestTheListGivesTheFingerprintOfEachLanguage(PerLanguage):
    def rows(self, *args):
        code, out, _ = self.sor('test', '--list', '--json', *args)
        self.assertEqual(code, 0, out)
        return {r['id']: r for r in json.loads(out)['tests']}

    def test_a_test_with_test_code_in_two_languages_has_the_fingerprint_of_each_and_the_one_it_had(self):
        row = self.rows()[TEST]
        fps = self.fingerprints()
        self.assertEqual(row['fingerprints'], {'py': fps[f'{TEST}@py'], 'ts': fps[f'{TEST}@ts']})
        self.assertEqual(row['fingerprint'], fps[TEST])

    def test_a_test_with_no_test_code_per_language_has_only_the_one(self):
        os.remove(os.path.join(self.dir, 'src_py', 'test_greet.py'))
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))
        self.assertNotIn('fingerprints', self.rows()[TEST])

    def test_the_fingerprint_of_a_language_in_the_list_is_the_one_the_evidence_is_made_for(self):
        self.assertEqual(self.job('linux-ci', 'linux', {f'{TEST}@py': 'pass'})[0], 0)
        with open(os.path.join(self.dir, 'evidence', 'linux-ci.json'), encoding='utf8') as fh:
            written = json.load(fh)['results'][f'{TEST}@py']['fingerprint']
        self.assertEqual(self.rows()[TEST]['fingerprints']['py'], written)


class TestWritingEvidenceForALanguage(PerLanguage):
    def test_a_result_for_each_language_is_written_under_its_key_with_its_fingerprint(self):
        code, text = self.job('linux-ci', 'linux', {f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'})
        self.assertEqual(code, 0, text)
        with open(os.path.join(self.dir, 'evidence', 'linux-ci.json'), encoding='utf8') as fh:
            data = json.load(fh)
        fps = self.fingerprints()
        self.assertEqual(data['results'], {f'{TEST}@py': {'fingerprint': fps[f'{TEST}@py'], 'status': 'pass'},
                                           f'{TEST}@ts': {'fingerprint': fps[f'{TEST}@ts'], 'status': 'pass'}})

    def test_a_plain_result_is_refused_when_two_languages_have_test_code_and_the_keys_are_named(self):
        code, text = self.job('linux-ci', 'linux', {TEST: 'pass'})
        self.assertEqual(code, 2, text)
        self.assertIn(f'{TEST} has test code in py, ts: give a result for each, {TEST}@py, {TEST}@ts', text)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'evidence', 'linux-ci.json')))

    def test_a_language_with_no_test_code_is_refused(self):
        code, text = self.job('linux-ci', 'linux', {f'{TEST}@go': 'pass'})
        self.assertEqual(code, 2, text)
        self.assertIn(f'{TEST}@go: the test code of {TEST} is in py, ts, not in go', text)

    def test_a_plain_result_is_the_result_of_the_only_language_that_has_test_code(self):
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))
        code, text = self.job('linux-ci', 'linux', {TEST: 'pass'})
        self.assertEqual(code, 0, text)
        with open(os.path.join(self.dir, 'evidence', 'linux-ci.json'), encoding='utf8') as fh:
            self.assertEqual(list(json.load(fh)['results']), [f'{TEST}@py'])

    def test_a_language_of_a_test_with_no_test_code_per_language_is_refused(self):
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))
        os.remove(os.path.join(self.dir, 'src_py', 'test_greet.py'))
        code, text = self.job('linux-ci', 'linux', {f'{TEST}@py': 'pass'})
        self.assertEqual(code, 2, text)
        self.assertIn(f'{TEST} has no test code per language, so it has one result: {TEST}', text)
        self.assertEqual(self.job('linux-ci', 'linux', {TEST: 'pass'})[0], 0)

    def test_a_language_of_a_job_that_provides_none_of_the_environments_is_left_out(self):
        code, text = self.job('mac', 'macos', {f'{TEST}@py': 'pass'})
        self.assertEqual(code, 0, text)
        self.assertIn(f'{TEST}@py', text)


class TestTheGateOverLanguages(PerLanguage):
    def both(self, job='linux-ci', provides='linux'):
        self.assertEqual(self.job(job, provides, {f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'})[0], 0)

    def test_a_row_for_each_language_and_each_environment(self):
        code, data = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(data), {f'{TEST}@py': {'linux': 'missing', 'windows': 'missing'},
                                               f'{TEST}@ts': {'linux': 'missing', 'windows': 'missing'}})

    def test_every_language_in_every_environment_passes_the_gate(self):
        self.both('linux-ci', 'linux')
        self.both('windows-ci', 'windows')
        code, data = self.verify()
        self.assertEqual((code, data['ok']), (0, True))

    def test_one_language_missing_is_missing_and_the_other_is_proven(self):
        self.assertEqual(self.job('linux-ci', 'linux', {f'{TEST}@py': 'pass'})[0], 0)
        self.assertEqual(self.job('windows-ci', 'windows', {f'{TEST}@py': 'pass'})[0], 0)
        code, data = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(data), {f'{TEST}@py': {'linux': 'pass', 'windows': 'pass'},
                                               f'{TEST}@ts': {'linux': 'missing', 'windows': 'missing'}})

    def test_an_edit_in_one_language_makes_only_its_evidence_stale(self):
        self.both('linux-ci', 'linux')
        self.both('windows-ci', 'windows')
        self.rebuild('py', word='Hi')
        code, data = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(data), {f'{TEST}@py': {'linux': 'stale', 'windows': 'stale'},
                                               f'{TEST}@ts': {'linux': 'pass', 'windows': 'pass'}})

    def test_a_failure_in_one_language_is_a_failure_of_that_row_only(self):
        self.assertEqual(self.job('linux-ci', 'linux', {f'{TEST}@py': 'fail', f'{TEST}@ts': 'pass'})[0], 0)
        code, data = self.verify()
        self.assertEqual(self.statuses(data)[f'{TEST}@py']['linux'], 'fail')
        self.assertEqual(self.statuses(data)[f'{TEST}@ts']['linux'], 'pass')

    def test_the_text_output_names_the_languages(self):
        self.both('linux-ci', 'linux')
        code, out, _ = self.sor('verify')
        self.assertIn(f'{TEST}@py', out)
        self.assertIn(f'{TEST}@ts', out)
        self.assertIn('2 deferred test(s)', out)


class TestOneResultsFileForTheLockAndTheEvidence(PerLanguage):
    def test_the_lock_leaves_the_results_per_language_of_a_deferred_test_to_the_evidence(self):
        path = write(self.dir, 'results.json', json.dumps({f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'}))
        code, out, _ = self.sor('lock', '--all', '--results', path, '--allow-behind', 'ts')
        self.assertEqual(code, 0, out)
        self.assertIn(f'a result for {TEST}@py, {TEST}@ts is not recorded in the lock', out)
        self.assertNotIn('no test code per language', out)
        out_file = os.path.join(self.dir, 'evidence', 'ci.json')
        code, text, _ = self.sor('evidence', '--job', 'ci', '--provides', 'linux', '--results', path, '--out', out_file)
        self.assertEqual(code, 0, text)                                    # and the same file is what the job gives sor evidence
        with open(out_file, encoding='utf8') as fh:
            self.assertEqual(sorted(json.load(fh)['results']), [f'{TEST}@py', f'{TEST}@ts'])

    def test_a_language_that_has_no_test_code_is_ignored_too_for_a_test_left_to_ci(self):
        path = write(self.dir, 'results.json', json.dumps({f'{TEST}@go': 'pass'}))
        self.assertEqual(self.sor('lock', '--all', '--results', path, '--allow-behind', 'ts')[0], 0)


class TestTheGateHashesTheProjectOnce(PerLanguage):
    def test_the_functions_of_the_gate_read_the_snapshot_they_are_given(self):
        project = Project(self.dir)
        scan = Scan(project)
        with mock.patch.object(lockfile, 'snapshot', wraps=lockfile.snapshot) as snapshot:
            snap = lockfile.snapshot(project, scan)
            rows = evidence.verify(project, scan, [], snap)
            evidence.unknown(project, scan, [], snap)
            evidence.renamed(project, scan, [], snap)
            evidence.fingerprints(project, scan, None, snap)
        self.assertEqual(snapshot.call_count, 1)
        self.assertEqual([r['id'] for r in rows], [f'{TEST}@py', f'{TEST}@ts'])

    def test_sor_verify_takes_one_snapshot_for_the_evidence_and_one_for_the_checks_of_the_spec(self):
        with mock.patch.object(lockfile, 'snapshot', wraps=lockfile.snapshot) as snapshot:
            self.sor('verify')
        self.assertLessEqual(snapshot.call_count, 2)


class TestEvidenceFromBeforeTheTestTookALanguage(PerLanguage):
    """A job wrote a result for the test as one, before it had test code in two languages (or before the tool took one result for each)."""

    def old_evidence(self):
        fps = self.fingerprints()
        write(self.dir, 'evidence/old-job.json', json.dumps({'job': 'old-job', 'provides': ['linux', 'windows'],
                                                             'results': {TEST: {'fingerprint': fps[TEST], 'status': 'pass'}}}))

    def test_it_proves_nothing_and_the_gate_says_what_the_job_has_to_write(self):
        self.old_evidence()
        code, out, _ = self.sor('verify')
        self.assertEqual(code, 1, out)
        self.assertIn(f'note: old-job has a result for {TEST}, which now takes one result for each language ({TEST}@py, {TEST}@ts)', out)
        self.assertNotIn('no longer say', out)                              # it is not a test that vanished

    def test_the_json_names_it_apart_from_the_unknown_ones(self):
        self.old_evidence()
        code, data = self.verify()
        self.assertEqual(data['renamed'], [{'job': 'old-job', 'test': TEST, 'now': [f'{TEST}@py', f'{TEST}@ts']}])
        self.assertEqual(data['unknown'], [])

    def test_a_result_for_a_language_the_test_has_no_code_in_is_unknown(self):
        fps = self.fingerprints()
        write(self.dir, 'evidence/odd.json', json.dumps({'job': 'odd', 'provides': ['linux'],
                                                         'results': {f'{TEST}@go': {'fingerprint': fps[TEST], 'status': 'pass'}}}))
        code, data = self.verify()
        self.assertEqual(data['unknown'], [{'job': 'odd', 'test': f'{TEST}@go'}])
        self.assertNotIn('renamed', data)

    def test_a_result_for_a_language_of_the_test_is_not_unknown(self):
        self.both_jobs = self.job('linux-ci', 'linux', {f'{TEST}@py': 'pass', f'{TEST}@ts': 'pass'})
        code, data = self.verify()
        self.assertEqual(data['unknown'], [])
        self.assertNotIn('renamed', data)

    def test_a_test_with_no_test_code_per_language_keeps_its_bare_key(self):
        os.remove(os.path.join(self.dir, 'src_ts', 'greet.test.ts'))
        os.remove(os.path.join(self.dir, 'src_py', 'test_greet.py'))
        self.assertEqual(self.job('linux-ci', 'linux', {TEST: 'pass'})[0], 0)
        code, data = self.verify()
        self.assertEqual(self.statuses(data), {TEST: {'linux': 'pass', 'windows': 'missing'}})
        self.assertNotIn('renamed', data)                                   # a test that takes one result is not renamed


if __name__ == '__main__':
    unittest.main()
