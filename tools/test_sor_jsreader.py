"""The JavaScript reader (tools/js/sor.js: `markers --json`, `status --json`, `parts --json`) against the Python tool, which is the reference.

The extension runs the JavaScript one and never Python, so what it prints has to be what the Python tool prints, field for field. These tests
put a project in about sixty states and compare the three answers, make a lock the tool refuses and compare the message, run the two real
projects of this repository, and call the command line the way an editor does. `SOR_COMPARE_JS=1` runs the whole suite and does the first kind
for every state any test builds (see test_sor_js.py).

Skipped, with a message, when there is no `node`. Python 3.9, standard library only. Node 16 or later.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_js as js                     # noqa: E402

NODE, GIT = js.NODE, shutil.which('git')
SOR_JS = os.path.join(HERE, 'js', 'sor.js')

GREET_PY = ('# @clause glue\nimport os\n# @clause end\n'
            '# @clause greet/hello greet/shares\nHELLO = "Hello"\n# @clause end\n'
            '# @clause greet/bye\n# says goodbye\nBYE = "Bye"  # \U0001F600 café\n# @clause end\n'
            '# @clause test greet/bye\ndef test_bye():\n    pass\n# @clause end\n'
            '# @clause greet/pairs\nPAIRS = {\n    "a": 1,\n}\n# @clause end\n')
GREET_TS = ('// @clause greet/hello greet/shares\nexport const HELLO = "Hello";\n// @clause end\n'
            '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n'
            '// @clause greet/pairs\nexport const PAIRS = {a: 1};\n// @clause end\n')
LIB_PY = 'def helper(x):\n    return x + 1\n\n\ndef other():\n    return 2\n'
PART_PY = '# @clause greet\nPART = 1\n# @clause end\n'
GREET_RULES = ['- **hello** - The greeting is "Hello" {size: 3}.',
               '- **bye** - The farewell is "Bye", as long as {hello.size} says. \U0001F600 `code \U0001F600` {big: 4}',
               '- **shares** - Shares the code of hello.',
               '- **pairs** - The pairs:', '', '| Name | Value |', '|------|-------|', '| a    | 1     |', '| b    | {n: 2} |',
               '- **uses** - Uses {hello} and {pairs/b.value}.',
               '- **alias** - The same size: {same: = hello.size}.']
GREET_TESTS = ['- **hello** - looks right.', '  manual: look',
               '- **bye** - looks right.', '  expect: the farewell is shown',      # needs a result at the lock
               '- **shares** - looks right.', '  runs on: linux',                   # left to CI
               '- **uses** - checks {hello.size}', '  expect: {hello.size} = 3', '  manual: look']
PASS = {'greet/test:bye': 'pass'}


def target_doc(name, folder):
    return base.doc(name.title(), 'Where the code of one language lives.', rules=[f'- **code** - The code is under {{path: {folder}}}.'])


def build_project(d, targets=True):
    """A project with two targets, values and an alias, a table, references, tests of every kind, a hand-written part, glue, code for a part,
    and characters from beyond the first plane."""
    header = 'Targets: py, ts\n' if targets else ''
    base.write(d, 'sor/SPECOFRECORD.md', f'# Demo\n\nWhy: A demo with \U0001F600 in it.\n{header}\n## Rules\n- **r** - x.\n')
    base.write(d, 'sor/targets/py.md', target_doc('py', 'src_py/'))
    base.write(d, 'sor/targets/ts.md', target_doc('ts', 'src_ts/'))
    base.write(d, 'sor/greet.md', base.doc('Greet', 'Says hello \U0001F600.', rules=GREET_RULES, tests=GREET_TESTS))
    base.write(d, 'sor/hand.md', base.doc('Hand', 'Written by hand.', header=['Source: code at src_py/lib.py'] + (['Targets: py'] if targets else []),
                                          rules=['- **lib** - The helper adds one.', '  code: src_py/lib.py#helper']))
    base.write(d, 'src_py/greet.py', GREET_PY)
    base.write(d, 'src_py/lib.py', LIB_PY)
    base.write(d, 'src_py/part.py', PART_PY)
    base.write(d, 'src_ts/greet.ts', GREET_TS)


def edit(d, rel, old, new):
    path = os.path.join(d, *rel.split('/'))
    text = base.read(path)
    assert old in text, (rel, old)
    base.write(d, rel, text.replace(old, new, 1))


def sor(d, *args):
    code, out, err = base.run_sor(d, *args)
    assert code == 0, (args, out, err)


def lock_file(d):
    return os.path.join(d, 'sor', 'sor-lock.json')


def change_lock(d, fn):
    with open(lock_file(d), encoding='utf8') as fh:
        data = json.load(fh)
    fn(data)
    base.write(d, 'sor/sor-lock.json', json.dumps(data, indent=1))


def git(d, *args, **env):
    dates = {'GIT_AUTHOR_DATE': '2026-10-17T10:00:00', 'GIT_COMMITTER_DATE': '2026-10-17T10:00:00'}
    done = subprocess.run(['git', '-c', 'user.name=Ada Lovelace', '-c', 'user.email=ada@example.org', '-C', d, *args], capture_output=True, text=True,
                          env=dict(os.environ, **dict(dates, **env)))
    assert done.returncode == 0, done.stderr
    return done.stdout


def committed(d):
    git(d, 'init', '-q')
    git(d, 'add', '-A')
    git(d, 'commit', '-q', '-m', 'locked')


def reworded(d):
    edit(d, 'sor/greet.md', 'The greeting is "Hello"', 'The greeting is "Hi"')


def rebuilt_in_py(d):
    reworded(d)
    edit(d, 'src_py/greet.py', '"Hello"', '"Hi"')


def left_behind(d):
    rebuilt_in_py(d)
    sor(d, 'lock', 'greet/hello', '--allow-behind', 'ts')


def a_clause_locked_without_code(d):
    edit(d, 'sor/greet.md', '## Tests', '- **extra** - More.\n\n## Tests')
    sor(d, 'lock', 'greet/extra', '--allow-behind', 'py,ts')


def drift(d):
    edit(d, 'src_py/greet.py', '"Bye"', '"Ciao"')


def drift_committed(d):
    drift(d)
    git(d, 'commit', '-q', '-a', '-m', 'ciao', GIT_AUTHOR_NAME='Grace Hopper', GIT_AUTHOR_EMAIL='grace@example.org',
        GIT_AUTHOR_DATE='2026-10-19T09:30:00', GIT_COMMITTER_DATE='2026-10-19T09:30:00')


MANY = 22   # more drifted clauses than the blame is asked for (blame.annotate asks for 20)


def many_clauses(d):
    rules = ''.join(f'- **c{i:02}** - Clause number {i}.\n' for i in range(MANY))
    edit(d, 'sor/greet.md', '## Tests', rules + '\n## Tests')
    base.write(d, 'src_py/many.py', ''.join(f'# @clause greet/c{i:02}\nC{i} = {i}\n# @clause end\n' for i in range(MANY)))


def many_drift(d):
    base.write(d, 'src_py/many.py', ''.join(f'# @clause greet/c{i:02}\nC{i} = {i + 1}\n# @clause end\n' for i in range(MANY)))


def a_test_first(d):
    edit(d, 'sor/greet.md', '- **uses** - checks {hello.size}', '- **again** - checks it again\n  proves: {hello}\n  manual: look\n- **uses** - checks {hello.size}')
    edit(d, 'src_py/greet.py', '"Hello"', '"Yo"')
    edit(d, 'src_ts/greet.ts', '"Hello"', '"Yo"')


def shared_with_a_new_clause(d):
    edit(d, 'sor/greet.md', '## Tests', '- **extra** - More.\n\n## Tests')
    edit(d, 'src_py/greet.py', '# @clause greet/hello greet/shares\nHELLO = "Hello"', '# @clause greet/hello greet/shares greet/extra\nHELLO = "Yo"')


def old_rule_hashes(d):
    """The lock as a sor wrote it before the hash followed the file type: the code of each clause under the rule every file followed then."""
    from sorlib.markers import Scan
    from sorlib.model import Project
    scan = Scan(Project(d))
    legacy, now = scan.code_hashes(legacy=True), scan.code_hashes()
    assert any(legacy[k] != now[k] for k in now), 'the fixture should have code that the two rules hash differently'
    change_lock(d, lambda data: [e.__setitem__('code', legacy[k]) for k, e in data.items() if k in legacy and 'code' in e])


def lock_without(d, *names):
    change_lock(d, lambda data: [data.pop(n, None) for n in names])


def write_lock(d, text):
    base.write(d, 'sor/sor-lock.json', text)


def old_root_key(d):
    change_lock(d, lambda data: data.__setitem__('CLAUSES', data.pop('ROOT')))


def old_lock_name(d):
    os.rename(lock_file(d), os.path.join(d, 'sor', 'clauses-lock.json'))


def empty_targets(d):
    change_lock(d, lambda data: data['greet/hello'].update(targets={}))


# name -> what a state is made of: `targets` (False: the project says no targets), `before` (changes before the lock), `results` (what the tests that
# need a result get), `flags` (more arguments of the lock), `git` (the project is committed after the lock), `after` (changes after it)
S = dict
STATES = {
    'nothing changed': S(),
    'a clause reworded': S(after=reworded),
    'reworded and rebuilt in one language': S(after=rebuilt_in_py),
    'a value changed (and the alias that follows it)': S(after=lambda d: edit(d, 'sor/greet.md', '{size: 3}', '{size: 5}')),
    'a value that is only referenced': S(after=lambda d: edit(d, 'sor/greet.md', '{n: 2}', '{n: 9}')),
    'code edited in both languages': S(after=lambda d: (edit(d, 'src_py/greet.py', '"Bye"', '"Ciao"'), edit(d, 'src_ts/greet.ts', '"Bye"', '"Ciao"'))),
    'code edited in one language': S(after=lambda d: edit(d, 'src_ts/greet.ts', '"Bye"', '"Ciao"')),
    'a region shared by two clauses, one reworded': S(after=lambda d: (edit(d, 'src_py/greet.py', '"Hello"', '"Yo"'),
                                                                       edit(d, 'sor/greet.md', 'Shares the code', 'Shares all the code'))),
    'a clause removed': S(after=lambda d: edit(d, 'sor/greet.md', '- **uses** - Uses {hello} and {pairs/b.value}.\n', '')),
    'a clause added': S(after=lambda d: edit(d, 'sor/greet.md', '## Tests', '- **extra** - More.\n\n## Tests')),
    'a clause added with code': S(after=lambda d: (edit(d, 'sor/greet.md', '## Tests', '- **extra** - More.\n\n## Tests'),
                                                   base.write(d, 'src_py/extra.py', '# @clause greet/extra\nX = 1\n# @clause end\n'))),
    'a row changed': S(after=lambda d: edit(d, 'sor/greet.md', '| a    | 1     |', '| a    | 7     |')),
    'a row changed and the code of its table': S(after=lambda d: (edit(d, 'sor/greet.md', '| a    | 1     |', '| a    | 7     |'),
                                                                  edit(d, 'src_py/greet.py', '"a": 1', '"a": 7'), edit(d, 'src_ts/greet.ts', '{a: 1}', '{a: 7}'))),
    'a row that had no code of its own gets some': S(after=lambda d: base.write(d, 'src_py/greet.py', base.read(os.path.join(d, 'src_py', 'greet.py')) + 'PAIRS_B = 2  # @clause greet/pairs/b\n')),
    'a row removed': S(after=lambda d: edit(d, 'sor/greet.md', '| b    | {n: 2} |\n', '')),
    'a row added': S(after=lambda d: edit(d, 'sor/greet.md', '| b    | {n: 2} |', '| b    | {n: 2} |\n| c    | 3 |')),
    'glue changed': S(after=lambda d: edit(d, 'src_py/greet.py', 'import os', 'import sys')),
    'the code of a part changed': S(after=lambda d: edit(d, 'src_py/part.py', 'PART = 1', 'PART = 2')),
    'hand-written code changed': S(after=lambda d: edit(d, 'src_py/lib.py', 'return x + 1', 'return x + 2')),
    'a hand-written function moved': S(after=lambda d: base.write(d, 'src_py/lib.py', '# first\n' + LIB_PY)),
    'a test and its code changed': S(after=lambda d: (edit(d, 'sor/greet.md', '- **hello** - looks right.', '- **hello** - looks very right.'),
                                                      edit(d, 'src_py/greet.py', '"Hello"', '"Yo"'), edit(d, 'src_ts/greet.ts', '"Hello"', '"Yo"'))),
    'an alias item reworded while the value it follows moves': S(after=lambda d: (edit(d, 'sor/greet.md', '{size: 3}', '{size: 5}'),
                                                                                  edit(d, 'sor/greet.md', 'The same size:', 'The very same size:'))),
    'an alias item reworded, the value it follows not moved': S(after=lambda d: edit(d, 'sor/greet.md', 'The same size:', 'The very same size:')),
    'a region of a clause with a test that needs a result is shared with a new one': S(after=lambda d: (
        edit(d, 'sor/greet.md', '## Tests', '- **extra** - More.\n\n## Tests'),
        edit(d, 'src_py/greet.py', '# @clause greet/bye\n# says goodbye\nBYE = "Bye"', '# @clause greet/bye greet/extra\n# says goodbye\nBYE = "Ciao"'))),
    'a test is added first, then the code': S(after=a_test_first),
    'a region shared with a clause that is new': S(after=shared_with_a_new_clause),
    'a test that needs a result is reworded': S(after=lambda d: edit(d, 'sor/greet.md', 'the farewell is shown', 'the farewell shows')),
    'a test that did not pass at the last lock': S(results={'greet/test:bye': 'fail'}, flags=['--allow-incomplete']),
    'its code changed, to fix it': S(results={'greet/test:bye': 'fail'}, flags=['--allow-incomplete'],
                                     after=lambda d: edit(d, 'src_py/greet.py', '"Bye"', '"Ciao"')),
    'characters from beyond the first plane in code': S(after=lambda d: edit(d, 'src_py/greet.py', '\U0001F600 café', '\U0001F600 café ✓ \U0001D431')),
    'a region of code removed': S(after=lambda d: base.write(d, 'src_py/greet.py', GREET_PY.replace('# @clause greet/pairs\nPAIRS = {\n    "a": 1,\n}\n# @clause end\n', ''))),
    'markers that name nothing': S(after=lambda d: base.write(d, 'src_py/bad.py', '# @clause nothing/here\nX = 1\n# @clause end\n# @clause greet/hello\n')),
    'code outside any region': S(after=lambda d: base.write(d, 'src_py/loose.py', 'X = 1\n')),
    'a part removed': S(after=lambda d: os.remove(os.path.join(d, 'sor', 'hand.md'))),
    'a part added': S(after=lambda d: base.write(d, 'sor/more.md', base.doc('More', 'More.', rules=['- **m** - m.']))),
    'a target dropped': S(after=lambda d: edit(d, 'sor/SPECOFRECORD.md', 'Targets: py, ts', 'Targets: py')),
    'targets given up': S(after=lambda d: edit(d, 'sor/SPECOFRECORD.md', 'Targets: py, ts\n', '')),
    'no targets at all, code edited': S(targets=False, after=drift),
    'no targets at all, a clause reworded and rebuilt': S(targets=False, after=rebuilt_in_py),
    'no targets at all, a clause reworded': S(targets=False, after=reworded),
    'an open question': S(after=lambda d: edit(d, 'sor/greet.md', '"Hello" {size: 3}.', '"Hello" {size: 3}.\n  open: which language?')),
    'no lock yet': S(after=lambda d: os.remove(lock_file(d))),
    'spec files with CRLF': S(after=lambda d: base.write(d, 'sor/greet.md', base.read(os.path.join(d, 'sor', 'greet.md')).replace('\n', '\r\n'))),
    'a clause left behind in one language': S(after=left_behind),
    'the language that was behind is being rebuilt': S(after=lambda d: (left_behind(d), edit(d, 'src_ts/greet.ts', '"Hello"', '"Hi"'))),
    'a clause locked without code that now has some': S(before=a_clause_locked_without_code,
                                                       after=lambda d: base.write(d, 'src_py/extra.py', '# @clause greet/extra\nX = 1\n# @clause end\n')),
    'a lock whose hashes were made before the rule followed the file type': S(targets=False, after=old_rule_hashes),
    'a clause left behind in one language, and the code of the other one edited': S(after=lambda d: (left_behind(d), edit(d, 'src_py/greet.py', '"Hi"', '"Hey"'))),
    'a row gets code of its own and the code of its table changes': S(after=lambda d: (
        base.write(d, 'src_py/greet.py', base.read(os.path.join(d, 'src_py', 'greet.py')) + 'PAIRS_B = 2  # @clause greet/pairs/b\n'),
        edit(d, 'src_py/greet.py', '"a": 1', '"a": 9'))),
    'a lock written before the root was called ROOT': S(after=old_root_key),
    'a lock under its old file name': S(after=old_lock_name),
    'a lock with nothing in it': S(after=lambda d: write_lock(d, '{}')),
    'a lock with one entry': S(after=lambda d: write_lock(d, '{"greet": {"kind": "part", "text": "x"}}')),
    'a lock entry with no targets in it': S(after=empty_targets),
    'a lock that holds only what an older sor wrote': S(after=lambda d: change_lock(d, lambda data: [data.pop(k) for k in list(data) if k.startswith('greet/hello@')])),
    'a lock from a newer sor': S(after=lambda d: write_lock(d, '{"*format": 99}')),
    'a lock whose format is no number': S(after=lambda d: write_lock(d, '{"*format": "three"}')),
    'a lock whose format is zero': S(after=lambda d: write_lock(d, '{"*format": 0}')),
    'a lock whose format is true': S(after=lambda d: write_lock(d, '{"*format": true}')),
    'a damaged lock': S(after=lambda d: write_lock(d, '{"greet": ')),
    'a claim held': S(after=lambda d: sor(d, 'claim', 'greet/hello', '--as', 'someone')),
    'drift in git, not committed': S(git=True, after=drift),
    'drift in git, committed by someone': S(git=True, after=drift_committed),
    'more drifted clauses than the blame is asked for': S(git=True, before=many_clauses, after=many_drift),
    'hand-written code changed in git': S(git=True, after=lambda d: edit(d, 'src_py/lib.py', 'return x + 1', 'return x + 2')),
    'drift in git, the code of a clause in two files': S(git=True, after=lambda d: (drift(d), edit(d, 'src_ts/greet.ts', '"Bye"', '"Ciao"'))),
}
MARKS_AND_IDS = ['src_py/greet.py:5', 'src_py/greet.py:99', 'greet/hello', 'greet', 'ROOT', 'nothing', 'src_py/lib.py:2', 'greet/bye', 'greet/pairs/a',
                 'src_ts/greet.ts:2', 'src_py/part.py:2', 'greet/alias', 'greet/test:bye']
WANTED_STATUSES = {'new', 'changed', 'removed', 'stale', 'drift', 'behind', 'built', 'shared', 'fixing', 'glue', 'code-changed'}


def locked_state(d, state):
    build_project(d, state.get('targets', True))
    if state.get('before'):
        state['before'](d)
    base.write(d, 'results.json', json.dumps(state.get('results', PASS)))
    sor(d, 'lock', '--all', '--allow-behind', 'py,ts', '--results', os.path.join(d, 'results.json'), *state.get('flags', []))
    if state.get('git'):
        committed(d)
    if state.get('after'):
        state['after'](d)


@unittest.skipUnless(NODE, 'node is not installed, so the JavaScript reader (tools/js) was not run')
class TestTheJavaScriptReader(unittest.TestCase):
    def test_it_reads_a_project_in_every_state_the_way_the_python_tool_does(self):
        met, fields = set(), set()
        for name, state in STATES.items():
            if state.get('git') and not GIT:
                continue
            with tempfile.TemporaryDirectory() as d:
                with self.subTest(state=name):
                    locked_state(d, state)
                    self.assertEqual(js.compare_with_javascript(d, MARKS_AND_IDS), [])
                    status = js.python_json(d, ['status', '--json']) or {}
                    met |= {f['status'] for f in status.get('findings', [])}
                    fields |= {k for k, v in status.items() if v} | {f'finding.{k}' for f in status.get('findings', []) for k in f}
        self.assertEqual(sorted(WANTED_STATUSES - met), [], 'the states should include every kind of finding')
        want = {'locked', 'findings', 'tests_not_passed', 'tests_pending', 'tests_deferred', 'claims', 'finding.detail', 'finding.where'}
        want |= {'finding.by'} if GIT else set()
        self.assertEqual(sorted(want - fields), [], 'the states should fill every part of the answer')

    def test_it_refuses_a_lock_it_cannot_read_with_the_message_of_the_python_tool(self):
        for name in ('a lock from a newer sor', 'a lock whose format is no number', 'a lock whose format is zero', 'a lock whose format is true'):
            with tempfile.TemporaryDirectory() as d, self.subTest(state=name):
                locked_state(d, STATES[name])
                python = subprocess.run([sys.executable, os.path.join(HERE, 'sor.py'), '-C', d, 'status', '--json'], capture_output=True, text=True, encoding='utf8')
                node = subprocess.run([NODE, SOR_JS, '-C', d, 'status', '--json'], capture_output=True, text=True, encoding='utf8')
                self.assertEqual((node.returncode, node.stdout, node.stderr), (python.returncode, python.stdout, python.stderr))
                self.assertEqual(node.returncode, 2)
                self.assertIn('lock format', node.stderr)

    def test_it_reads_the_two_projects_of_this_repository_the_way_the_python_tool_does(self):
        for rel in ('examples/solar-system', 'editors/vscode'):
            self.assertEqual(js.compare_with_javascript(os.path.join(REPO, *rel.split('/')), ['out/index.html:30', 'bodies/planets', 'ROOT']), [], rel)

    def run_js(self, *args):
        done = subprocess.run([NODE, SOR_JS, *args], capture_output=True, text=True, encoding='utf8')
        return done.returncode, done.stdout, done.stderr

    def test_its_command_line_is_read_the_way_an_editor_calls_it(self):
        with tempfile.TemporaryDirectory() as d:
            build_project(d)
            where = os.path.join(d, 'sor')   # the spec folder itself is also a project folder
            answers = {json.dumps(self.run_js(*args)) for args in (['-C', d, 'parts', '--json'], [f'-C{d}', 'parts', '--json'], ['parts', '-C', d, '--json'],
                                                                  ['--json', 'parts', '-C', where])}
            self.assertEqual(len(answers), 1)
            code, out, _ = self.run_js('-C', d, 'parts', '--json')
            self.assertEqual((code, [p['id'] for p in json.loads(out)]), (0, ['ROOT', 'greet', 'hand', 'targets/py', 'targets/ts']))
            code, out, _ = self.run_js('-C', d, 'markers', '--json', 'greet/hello')
            self.assertEqual((code, json.loads(out)['exists']), (0, True))
            # everything else is the Python tool's, and says so; a project that is not there, or an option nobody knows, is an error
            for args in ([], ['-C', d], ['-C', d, 'status'], ['-C', d, 'check', '--json'], ['-C', d, 'parts', '--json', 'greet'], ['-C', d, 'status', '--json', 'x'],
                         ['-C', d, 'parts', '--json', '--tree'], ['-C'], ['-C', d, 'markers', '--json', '--nothing']):
                with self.subTest(args=args):
                    code, out, err = self.run_js(*args)
                    self.assertEqual((code, out), (2, ''))
                    self.assertIn('usage: sor.js', err)
            code, out, err = self.run_js('-C', os.path.join(d, 'nowhere'), 'status', '--json')
            self.assertEqual((code, out), (2, ''))
            self.assertRegex(err, r'^sor: no sor/SPECOFRECORD.md under ')
            for flag in ('-h', '--help'):
                code, out, err = self.run_js(flag)
                self.assertEqual((code, err), (0, ''))
                self.assertIn('usage: sor.js', out)

    def test_it_never_writes_to_the_project(self):
        with tempfile.TemporaryDirectory() as d:
            locked_state(d, STATES['a clause reworded'])
            sor(d, 'claim', 'greet/hello', '--as', 'someone')
            before = base.tree(d)
            for args in (['markers', '--json'], ['status', '--json'], ['parts', '--json'], ['markers', '--json', 'src_py/greet.py:3']):
                self.assertEqual(self.run_js('-C', d, *args)[0], 0)
            self.assertEqual(base.tree(d), before)


if __name__ == '__main__':
    unittest.main()
