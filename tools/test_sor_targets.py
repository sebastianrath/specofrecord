"""Tests for how code is shared between targets (SPEC §9, §10): which target a file belongs to, the problems with how targets
share paths, the `targetName` of a region in `sor markers --json`, and the note that says a target lacks code another one has.
Nothing here changes the lock.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. Every project lives in a temporary folder.
"""
import json
import os
import shutil
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import test_sor as base                      # noqa: E402
import test_sor_flows as flows               # noqa: E402
from sorlib import lock as lockfile          # noqa: E402
from sorlib.markers import Scan             # noqa: E402
from sorlib.model import Project             # noqa: E402

doc, write, read = base.doc, base.write, base.read


def target(name, *paths, why='Where the code of one language lives.'):
    return doc(name.title(), why, rules=[f'- **code{i}** - The code is under {{path: {p}}}.' for i, p in enumerate(paths)])


class TwoTargets(flows.Flow):
    """greet/hello and greet/bye, with code in src_py/ (a target) and src_ts/ (another)."""
    PY = '# @clause greet/hello\nHELLO = "Hello"\n# @clause end\n'
    TS = '// @clause greet/hello\nexport const HELLO = "Hello";\n// @clause end\n'
    TARGETS = {'targets/py': target('py', 'src_py/'), 'targets/ts': target('ts', 'src_ts/')}

    def build(self, targets=None, extra=None, rules=None):
        shutil.rmtree(os.path.join(self.dir, 'sor'), ignore_errors=True)   # the spec only; the code files stay
        parts = dict(self.TARGETS if targets is None else targets)
        parts['greet'] = doc('Greet', 'Says hello.', rules=rules or ['- **hello** - The greeting is "Hello".',
                                                                    '- **bye** - The farewell is "Bye".'])
        parts.update(extra or {})
        self.project(parts)

    def setUp(self):
        super().setUp()
        self.build()
        write(self.dir, 'src_py/greet.py', self.PY)
        write(self.dir, 'src_ts/greet.ts', self.TS)

    def project_(self):
        return Project(self.dir)

    def problems(self, kind=None):
        project = self.project_()
        found = project.check() + Scan(project).problems
        return [p for p in found if kind is None or p.kind == kind]


class TestWhichTargetAFileBelongsTo(TwoTargets):
    def test_the_target_whose_path_is_the_longest_prefix(self):
        project = self.project_()
        self.assertEqual(project.target_names(), ['py', 'ts'])
        for rel, want in (('src_py/greet.py', 'py'), ('src_ts/a/b/greet.ts', 'ts'), ('src_py', 'py'), ('src_pyx/greet.py', None),
                          ('src/greet.py', None), ('README.md', None)):
            with self.subTest(rel):
                self.assertEqual(project.target_of(rel), want)

    def test_a_target_may_have_several_paths_and_a_deeper_path_of_another_target_wins(self):
        self.build({'targets/web': target('web', 'out/index.html', 'test/'), 'targets/py': target('py', 'src/'),
                    'targets/ts': target('ts', 'src/ts/')})
        project = self.project_()
        for rel, want in (('out/index.html', 'web'), ('test/a.test.js', 'web'), ('src/a.py', 'py'), ('src/ts/a.ts', 'ts')):
            with self.subTest(rel):
                self.assertEqual(project.target_of(rel), want)
        self.assertEqual(self.problems('target'), [])

    def test_the_path_dot_is_the_whole_project_and_loses_to_any_deeper_path(self):
        self.build({'targets/all': target('all', '.'), 'targets/ts': target('ts', 'src_ts/')})
        project = self.project_()
        for rel, want in (('src_py/greet.py', 'all'), ('README.md', 'all'), ('src_ts/greet.ts', 'ts')):
            with self.subTest(rel):
                self.assertEqual(project.target_of(rel), want)
        self.assertEqual(self.problems('target'), [])

    def test_a_part_inside_a_target_adds_its_paths_to_that_target(self):
        self.build(extra={'targets/py/tests': target('tests', 'src_py/tests/')})
        self.assertEqual(self.project_().target_of('src_py/tests/a.py'), 'py')

    def test_a_project_without_targets_has_none(self):
        self.build(targets={})
        project = self.project_()
        self.assertEqual((project.target_names(), project.target_of('src_py/greet.py')), ([], None))


class TestProblemsWithHowTargetsShareCode(TwoTargets):
    def test_two_targets_naming_the_same_path_is_a_problem_and_no_file_belongs_to_either(self):
        self.build({'targets/py': target('py', 'src/'), 'targets/ts': target('ts', 'src/')})
        found = self.problems('target')
        self.assertEqual(len(found), 1)
        self.assertIn('src is named by target py', found[0].text)
        self.assertIn('and by ts', found[0].text)
        self.assertIsNone(self.project_().target_of('src/a.py'))

    def test_one_target_naming_a_path_twice_is_no_problem(self):
        self.build({'targets/py': target('py', 'src_py/', 'src_py')})
        self.assertEqual(self.problems('target'), [])

    def test_a_target_may_not_be_named_like_a_key_prefix(self):
        for name in ('glue', 'test', 'ROOT'):
            with self.subTest(name):
                self.build({f'targets/{name}': target(name, 'src_x/'), 'targets/ts': target('ts', 'src_ts/')})
                found = self.problems('target')
                self.assertTrue(any(f'"{name}" is a reserved name' in p.text for p in found), found)

    def test_hand_written_code_in_no_target_is_a_problem_only_with_two_targets_or_more(self):
        hand = doc('Tools', 'Hand written.', header=['Source: code at tools/'])
        self.build(extra={'tools': hand})
        self.assertTrue(any('hand-written code at tools' in p.text for p in self.problems('target')))
        self.build(targets={'targets/py': target('py', 'src_py/')}, extra={'tools': hand})
        self.assertEqual(self.problems('target'), [])
        inside = doc('Tools', 'Hand written.', header=['Source: code at src_py/tools/'])
        self.build(extra={'tools': inside})
        self.assertEqual(self.problems('target'), [])

    def test_an_environment_named_like_a_target_is_a_problem_only_with_two_targets_or_more(self):
        tests = ['- **hello** - says hello.', '  expect: ok', '  runs on: py']
        self.build(extra={'greet': doc('Greet', 'Says hello.', rules=['- **hello** - The greeting is "Hello".'], tests=tests)})
        found = self.problems('runs on')
        self.assertEqual(len(found), 1)
        self.assertIn('"py" is a target', found[0].text)
        self.build(targets={'targets/py': target('py', 'src_py/')},
                   extra={'greet': doc('Greet', 'Says hello.', rules=['- **hello** - The greeting is "Hello".'], tests=tests)})
        self.assertEqual(self.problems('runs on'), [])

    def test_a_part_name_may_not_start_with_the_character_of_the_lock_marker(self):
        self.build(extra={'*odd': doc('Odd', 'A part whose name starts with the marker character.')})
        self.assertTrue(any(p.kind == 'name' for p in self.problems()))

    def test_none_of_this_is_reported_for_a_project_with_one_target(self):
        self.build(targets={'targets/py': target('py', 'src_py/')})
        self.assertEqual(self.problems('target'), [])
        self.assertEqual(self.sor('check')[0], 0)

    def test_the_two_real_projects_have_no_such_problem(self):
        for rel in ('examples/solar-system', 'editors/vscode'):
            project = Project(os.path.join(REPO, rel))
            with self.subTest(rel):
                self.assertEqual([p for p in project.check() if p.kind in ('target', 'name', 'runs on')], [])


class TestTheTargetOfARegionInTheIndex(TwoTargets):
    def regions(self):
        code, out, _ = self.sor('markers', '--json')
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        return data, {r['file']: r for r in data['regions']}

    def test_every_region_says_its_target_and_the_version_stays_2(self):
        data, by_file = self.regions()
        self.assertEqual(data['version'], 2)
        self.assertEqual((by_file['src_py/greet.py']['targetName'], by_file['src_ts/greet.ts']['targetName']), ('py', 'ts'))

    def test_code_in_no_target_has_none_and_a_project_without_targets_has_none_everywhere(self):
        write(self.dir, 'other/x.py', 'BYE = "Bye"\n')
        spec = read(os.path.join(self.spec, 'greet.md'))
        write(self.dir, 'sor/greet.md', spec.replace('- **bye** - The farewell is "Bye".',
                                                     '- **bye** - The farewell is "Bye".\n  code: other/x.py#BYE'))
        self.assertIsNone(self.regions()[1]['other/x.py']['targetName'])    # an anchor can point outside every target
        self.build(targets={})
        self.assertEqual({r['targetName'] for r in self.regions()[0]['regions']}, {None})

    def test_an_anchor_region_keeps_its_own_target_field_and_gets_a_target_name(self):
        spec = read(os.path.join(self.spec, 'greet.md'))
        write(self.dir, 'sor/greet.md', spec.replace('- **bye** - The farewell is "Bye".',
                                                     '- **bye** - The farewell is "Bye".\n  code: src_ts/greet.ts#HELLO'))
        anchor = [r for r in self.regions()[0]['regions'] if r['kind'] == 'anchor']
        self.assertEqual([(r['target'], r['targetName']) for r in anchor], [('src_ts/greet.ts#HELLO', 'ts')])


class TestTheNoteThatATargetLacksCode(TwoTargets):
    def notes(self):
        return [p for p in self.notes_() if p.kind == 'no code for target']

    def notes_(self):
        from sorlib import lint
        project = self.project_()
        return lint.notes(project, Scan(project))

    def test_it_names_the_target_and_the_clauses_that_have_code_somewhere_else(self):
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        self.assertEqual([(p.where, p.text) for p in self.notes()],
                         [('targets/ts.md:1', '1 clause(s) have code in py but none in ts: greet/bye')])
        write(self.dir, 'src_ts/bye.ts', '// @clause greet/bye\nexport const BYE = "Bye";\n// @clause end\n')
        self.assertEqual(self.notes(), [])

    def test_a_clause_with_code_in_both_a_clause_with_none_and_glue_and_tests_are_not_reported(self):
        write(self.dir, 'src_py/glue.py', '# @clause glue\nX = 1\n# @clause end\n')
        self.assertEqual(self.notes(), [])

    def test_test_code_in_one_target_is_not_a_clause_the_other_lacks(self):
        self.build(extra={'greet': doc('Greet', 'Says hello.', rules=['- **hello** - The greeting is "Hello".'],
                                       tests=['- **hello** - says hello.', '  manual: look'])})
        write(self.dir, 'src_py/test_greet.py', '# @clause test greet/hello\ndef test_hello():\n    pass\n# @clause end\n')
        project = self.project_()
        scan = Scan(project)
        self.assertTrue([r for r in scan.regions if r.kind == 'test'])
        self.assertEqual(self.notes(), [])

    def test_it_is_a_note_apart_from_the_problems_and_never_changes_the_exit_code(self):
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        code, out, _ = self.sor('check')
        self.assertEqual(code, 0, out)
        self.assertIn('no code for target', out)
        self.assertEqual(self.sor('check', '--strict')[0], 2)

    def test_it_says_nothing_for_a_project_with_one_target(self):
        self.build(targets={'targets/py': target('py', 'src_py/')})
        write(self.dir, 'src_py/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')
        self.assertEqual(self.notes(), [])
        from sorlib import lint
        project = self.project_()
        self.assertEqual(lint.no_code_for_target(project, Scan(project)), [])   # not by the caller's guard alone

    def test_code_in_no_target_is_not_counted_for_any(self):
        self.build(extra={'tools': doc('Tools', 'Hand written.', header=['Source: code at tools/'])})
        write(self.dir, 'tools/bye.py', '# @clause greet/bye\nBYE = "Bye"\n# @clause end\n')   # code, but in neither target
        scan = Scan(self.project_())
        self.assertEqual([r.file for r in scan.regions if 'greet/bye' in r.keys], ['tools/bye.py'])
        self.assertIsNone(self.project_().target_of('tools/bye.py'))
        self.assertEqual(self.notes(), [])


class TestTheLockDoesNotChange(TwoTargets):
    def test_two_targets_give_one_entry_per_clause_and_no_marker(self):
        self.assertEqual(self.sor('lock', '--all', '--allow-incomplete')[0], 0)
        keys = set(json.loads(flows.lock_bytes(self.dir)))
        self.assertFalse([k for k in keys if '@' in k or k.startswith('*')])
        self.assertEqual(keys, set(lockfile.snapshot(Project(self.dir), Scan(Project(self.dir)))))
        self.assertNotIn(b'*format', flows.lock_bytes(self.dir))
        self.assertEqual(lockfile.read(Project(self.dir))['greet/hello']['code'],
                         Scan(Project(self.dir)).code_hashes()['greet/hello'])   # one code hash for the clause, from both languages


if __name__ == '__main__':
    unittest.main()
