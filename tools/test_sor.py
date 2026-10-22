"""Tests for the `sor` tool (Spec of Record): readability notes, `open:` questions, placeholders, `sor new`,
`sor parts`, `sor needs`, `sor changes`, the session-start hook, and a read-only run over the real projects.
The hooks, claims, lock, migrate and the rest are in test_sor_flows.py.

    cd <repo> && python3 -m unittest discover -s tools -p 'test_*.py' -v

Python 3.9, standard library only. No browser (`sor test` is never called), no network, no sleeps. Every
project built here lives in a temporary folder; the two real projects (examples/solar-system and
editors/vscode) are only read, and the tests prove that nothing in their `sor/` changed.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True   # importing sorlib must not leave .pyc files in the repository
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from sorlib import cli, hook, lint, views       # noqa: E402
from sorlib import lock as lockfile             # noqa: E402
from sorlib.invoke import CMD                   # noqa: E402
from sorlib.markers import Scan                 # noqa: E402
from sorlib.model import Item, Project          # noqa: E402

SOR = os.path.join(HERE, 'sor.py')
SUMMARY = re.compile(r'^\d+ parts, \d+ references, \d+ code regions; 0 problem\(s\)$')
SUMMARY_ANY = re.compile(r'^\d+ parts, \d+ references, \d+ code regions; \d+ problem\(s\)$')   # for the owner's live work


# --- helpers ------------------------------------------------------------------------------------------

def write(root, rel, text):
    """Writes root/rel (rel uses `/`), making folders as needed."""
    path = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf8', newline='\n') as fh:
        fh.write(text)
    return path


def doc(title, why='It is here for a reason.', rules=(), approach=(), contract=(), tests=(), header=()):
    """The text of a part file. Each section is a list of lines; an empty section is left out."""
    out = [f'# {title}', f'Why: {why}', *header, '']
    for heading, lines in (('Rules', rules), ('Approach', approach), ('Contract', contract), ('Tests', tests)):
        if lines:
            out += [f'## {heading}'] + list(lines) + ['']
    return '\n'.join(out)


ROOT_DOC = doc('Demo', 'A project the tests use.', rules=['- **out-of-scope** - everything else.'])


def make_project(root, parts=None, root_text=None):
    """root/sor/SPECOFRECORD.md plus one file per entry of parts ({'render': text, 'render/CLAUSES': text})."""
    write(root, 'sor/SPECOFRECORD.md', ROOT_DOC if root_text is None else root_text)
    for pid, text in (parts or {}).items():
        write(root, f'sor/{pid}.md', text)
    return root


def run_process(project, *args):
    """Runs `python3 tools/sor.py -C <project> ARGS` as a program: (exit code, stdout, stderr)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', NO_COLOR='1')
    for name in ('CLAUDE_CODE_SESSION_ID', 'SOR_AGENT', 'SOR_ENFORCE_CLAIMS'):
        env.pop(name, None)
    done = subprocess.run([sys.executable, SOR, '-C', project, *args], cwd=REPO, env=env,
                          capture_output=True, text=True, encoding='utf8')
    return done.returncode, done.stdout, done.stderr


def same_in_javascript(project, args, when):
    """With SOR_COMPARE_JS set: the project through the JavaScript tool and the Python tool (`test_sor_js`), before and after every command
    a test runs, so that the reader in tools/js meets every state this suite makes. Fails the test that made a state they read differently."""
    if not os.path.isdir(os.path.join(project, 'sor')):
        return
    import test_sor_js
    found = test_sor_js.compare_with_javascript(project, fresh=True)
    if found:
        raise AssertionError(f'the JavaScript tool reads {project} otherwise {when} `sor {" ".join(args)}`:\n' + '\n'.join(found))


def run_sor(project, *args):
    """The same command through sorlib.cli.main in this process (argument parsing, dispatch and exit code
    included, only the start-up of a new Python left out): (exit code, stdout, stderr). A program started
    for every call costs 80 ms, and this suite makes a hundred."""
    if os.environ.get('SOR_COMPARE_JS'):
        same_in_javascript(project, args, 'before')
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(['-C', project, *args])
        except SystemExit as e:   # argparse's usage errors, and "no sor/SPECOFRECORD.md under ..."
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                print(e.code, file=sys.stderr)
    if os.environ.get('SOR_COMPARE_JS'):
        same_in_javascript(project, args, 'after')
    return code, out.getvalue(), err.getvalue()


def run_hook(which, payload):
    """Runs `python3 tools/sor.py hook WHICH` with the payload on stdin: (exit code, stdout, stderr)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    done = subprocess.run([sys.executable, SOR, 'hook', which], cwd=REPO, env=env, input=json.dumps(payload),
                          capture_output=True, text=True, encoding='utf8')
    return done.returncode, done.stdout, done.stderr


def run_view(fn, **kw):
    """Calls a views.cmd_* function in this process: (exit code, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = fn(argparse.Namespace(**kw))
    return code, out.getvalue()


def read(path):
    with open(path, encoding='utf8') as fh:
        return fh.read()


def tree(root):
    """{path under root: file bytes, or None for a folder}: all there is, to prove nothing was written."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for d in dirs:
            out[os.path.relpath(os.path.join(dirpath, d), root)] = None
        for f in files:
            p = os.path.join(dirpath, f)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, root)] = fh.read()
    return out


def fingerprint(project):
    """{path under sor/: sha256}: every file there, hidden ones and the lock included."""
    out = {}
    spec = os.path.join(project, 'sor')
    for dirpath, _dirs, files in os.walk(spec):
        for f in files:
            p = os.path.join(dirpath, f)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, spec)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def sha12(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()[:12]


def kinds(problems):
    return sorted({p.kind for p in problems})


def notes_of(project, kind):
    return [n for n in lint.notes(project) if n.kind == kind]


def lock_now(project_dir):
    """Writes the lock for the files as they are (what `sor lock --all` accepts)."""
    project = Project(project_dir)
    lockfile.write(project, lockfile.snapshot(project, Scan(project)))
    return project


class Case(unittest.TestCase):
    """A test with its own temporary folder, self.dir, removed afterwards."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)

    def project(self, parts=None, root_text=None, folder=None):
        root = self.dir if folder is None else os.path.join(self.dir, folder)
        make_project(root, parts, root_text)
        return Project(root)

    def assert_clean(self, project):
        self.assertEqual([str(p) for p in project.check()], [])


# --- A. readability notes -----------------------------------------------------------------------------

GIVES = {'world': ['new', 'update'],
         'input': ['new', 'refresh', 'closed'],
         'rendering': ['new', 'draw-world', 'close']}
NEEDED = ['world/new', 'input/new', 'rendering/new', 'input/refresh', 'input/closed', 'world/update',
          'rendering/draw-world', 'rendering/close']
PROVIDES = ['- gives **start** - starts a game.', '- gives **step** - runs one frame.', '- gives **stop** - ends it.']


def providers():
    return {pid: doc(pid.title(), f'{pid} is used by the game.',
                     contract=[f'- gives **{n}** - the {n} call.' for n in names])
            for pid, names in GIVES.items()}


def game(needs, rules=(), approach=()):
    return doc('Game', 'The game ties the parts together.', rules=rules, approach=approach,
               contract=PROVIDES + needs)


NEEDS_ONE_PER_LINE = [f'- needs {{{t}}}' for t in NEEDED]
NEEDS_GROUPED = ['- needs {world/new}, {world/update} - the world',
                 '- needs {input/new}, {input/refresh}, {input/closed} - the input',
                 '- needs {rendering/new}, {rendering/draw-world}, {rendering/close} - the screen']


def game_project(case, needs, folder=None):
    return case.project(dict(providers(), game=game(needs)), folder=folder)


def bullets(n, prefix='rule'):
    return [f'- **{prefix}-{i}** - number {i}.' for i in range(1, n + 1)]


def padded(lines_above_tests):
    """A part with exactly this many lines above `## Tests`."""
    top = ['# Pad', 'Why: padding.', '', '## Rules', '- **pad** - the first line']
    lines = top + ['  and more words'] * (lines_above_tests - len(top))
    return '\n'.join(lines + ['## Tests', '- **pad** - proves it.', '  expect: ok', ''])


class TestContractBulletCount(Case):
    def test_eight_needs_lines_make_eleven_bullets_in_a_part_of_four_items(self):
        project = game_project(self, NEEDS_ONE_PER_LINE)
        part = project.parts['game']
        self.assert_clean(project)
        self.assertEqual(len(part.items), 4)   # three gives and one `needs` item that holds all eight lines
        self.assertEqual(lint.bullet_counts(part)['Contract'], 11)

    def test_eleven_bullets_in_the_contract_give_one_too_long_note_naming_contract_and_eleven(self):
        project = game_project(self, NEEDS_ONE_PER_LINE)
        found = notes_of(project, 'too long')
        self.assertEqual(len(found), 1)
        self.assertIn('Contract', found[0].text)
        self.assertIn('11', found[0].text)
        self.assertTrue(found[0].where.startswith('game.md:'))

    def test_the_same_contract_grouped_into_three_needs_bullets_gives_no_note(self):
        project = game_project(self, NEEDS_GROUPED)
        self.assert_clean(project)
        self.assertEqual(lint.bullet_counts(project.parts['game'])['Contract'], 6)
        self.assertEqual(notes_of(project, 'too long'), [])

    def test_the_providers_that_only_give_have_no_notes(self):
        self.assertEqual(lint.notes(game_project(self, NEEDS_GROUPED)), [])

    def test_ungrouped_and_grouped_needs_state_the_same_references(self):
        a = game_project(self, NEEDS_ONE_PER_LINE, folder='a')
        b = game_project(self, NEEDS_GROUPED, folder='b')
        refs = lambda p: sorted(r for _, r in p.parts['game'].items['needs'].refs)
        self.assertEqual(refs(a), refs(b))
        self.assertEqual(refs(a), sorted(NEEDED))


class TestItemLimits(Case):
    SECTIONS = ('rules', 'approach', 'contract')

    def test_seven_bullets_in_a_section_give_no_note(self):
        for section in self.SECTIONS:
            with self.subTest(section=section):
                project = self.project({'thing': doc('Thing', **{section: bullets(7)})})
                self.assertEqual(notes_of(project, 'too long'), [])

    def test_eight_bullets_in_a_section_give_a_note_naming_the_section_and_the_count(self):
        for section in self.SECTIONS:
            with self.subTest(section=section):
                project = self.project({'thing': doc('Thing', **{section: bullets(8)})})
                found = notes_of(project, 'too long')
                self.assertEqual(len(found), 1)
                self.assertIn(section.title(), found[0].text)
                self.assertIn('8 items', found[0].text)

    def test_a_table_under_a_bullet_counts_as_one_item(self):
        for indent in ('', '  '):
            with self.subTest(indent=repr(indent)):
                table = [indent + '| name | days |', indent + '|---|---|'] + \
                        [f'{indent}| planet-{i} | {i} |' for i in range(12)]
                project = self.project({'thing': doc('Thing', rules=bullets(6) + ['- **planets** - the planets.'] + table)})
                self.assertEqual(lint.bullet_counts(project.parts['thing'])['Rules'], 7)
                self.assertEqual(notes_of(project, 'too long'), [])

    def test_the_tests_section_is_exempt_from_the_item_cap(self):
        tests = [f'- **rule-{i}** - proves rule {i}.' for i in range(1, 8)]
        tests += [f'- **extra-{i}** - a fixed bug.\n  bug: #{i}' for i in range(1, 4)]
        project = self.project({'thing': doc('Thing', rules=bullets(7), tests=tests)})
        self.assert_clean(project)
        self.assertEqual(lint.bullet_counts(project.parts['thing'])['Tests'], 10)
        self.assertEqual(notes_of(project, 'too long'), [])


class TestScreenLimit(Case):
    def test_forty_lines_above_the_tests_give_no_screen_note(self):
        project = self.project({'pad': padded(40)})
        self.assertEqual(project.parts['pad'].headings['Tests'], 41)
        self.assertEqual(notes_of(project, 'screen'), [])

    def test_forty_one_lines_above_the_tests_give_a_screen_note(self):
        found = notes_of(self.project({'pad': padded(41)}), 'screen')
        self.assertEqual(len(found), 1)
        self.assertIn('41 lines', found[0].text)
        self.assertTrue(found[0].where.startswith('pad.md:'))

    def test_a_part_without_tests_counts_all_its_lines(self):
        lines = ['# Pad', 'Why: padding.', '', '## Rules', '- **pad** - the first line']
        for total, expected in ((40, 0), (41, 1)):
            with self.subTest(lines=total):
                text = '\n'.join(lines + ['  and more words'] * (total - len(lines))) + '\n'
                self.assertEqual(len(notes_of(self.project({'pad': text}), 'screen')), expected)

    def test_lines_in_the_tests_section_are_not_counted(self):
        text = padded(40).rstrip('\n') + '\n' + '  expect: more\n' * 60
        self.assertEqual(notes_of(self.project({'pad': text}), 'screen'), [])


class TestLongTests(Case):
    BASE = ['- **limits** - zoom stays between {min: 0.3x} and {max: 6x}.']

    def long_test(self, test_lines, tests_file=False):
        """A zoom part with this test, written in zoom.md or in zoom.tests.md."""
        if not tests_file:
            return self.project({'zoom': doc('Zoom', rules=self.BASE, tests=test_lines)})
        self.project({'zoom': doc('Zoom', rules=self.BASE)})
        write(self.dir, 'sor/zoom.tests.md', '## Tests\n' + '\n'.join(test_lines) + '\n')
        return Project(self.dir)

    def test_a_test_of_six_lines_gives_a_long_test_note(self):
        project = self.long_test(['- **limits** - proves it.'] + ['  expect: zoom = 6x'] * 5)
        found = notes_of(project, 'long test')
        self.assertEqual(len(found), 1)
        self.assertIn('6 lines', found[0].text)
        self.assertIn('zoom/test:limits', found[0].text)
        self.assertTrue(found[0].where.startswith('zoom.md:'))

    def test_a_test_of_five_lines_gives_no_note(self):
        project = self.long_test(['- **limits** - proves it.'] + ['  expect: zoom = 6x'] * 4)
        self.assertEqual(notes_of(project, 'long test'), [])

    def test_blank_lines_in_a_test_are_not_counted(self):
        project = self.long_test(['- **limits** - proves it.', '', '  expect: a', '', '  expect: b', '  expect: c', '  expect: d'])
        self.assertEqual(notes_of(project, 'long test'), [])

    def test_a_name_line_and_a_ten_row_table_count_as_two_lines(self):
        table = ['  | size | zoom |', '  |---|---|'] + [f'  | {i}x | {i} |' for i in range(10)]
        project = self.long_test(['- **limits** - proves it.'] + table)
        self.assertEqual(notes_of(project, 'long test'), [])

    def test_a_table_counts_as_one_line_and_not_as_none(self):
        table = ['  | size | zoom |', '  |---|---|', '  | 1x | 1 |']
        over = self.long_test(['- **limits** - proves it.'] + ['  expect: a'] * 4 + table)
        self.assertEqual(len(notes_of(over, 'long test')), 1)   # 1 + 4 + 1 table = 6
        fits = self.long_test(['- **limits** - proves it.'] + ['  expect: a'] * 3 + table)
        self.assertEqual(notes_of(fits, 'long test'), [])       # 1 + 3 + 1 table = 5

    def test_a_long_test_from_a_tests_file_names_that_file(self):
        project = self.long_test(['- **limits** - proves it.'] + ['  expect: zoom = 6x'] * 5, tests_file=True)
        found = notes_of(project, 'long test')
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].where.startswith('zoom.tests.md:'), found[0].where)
        self.assertEqual(found[0].where, 'zoom.tests.md:2')

    def test_a_long_rule_is_not_a_long_test(self):
        rules = ['- **limits** - zoom stays inside.'] + ['  more words'] * 8
        self.assertEqual(notes_of(self.project({'zoom': doc('Zoom', rules=rules)}), 'long test'), [])


class TestLooseText(Case):
    """Text in a section that is not part of an item is read by nobody: it is not locked and a change to it goes
    unnoticed. `sor check` says so in a note, because a loose sentence is easy to write by accident."""

    def part(self, lines):
        header = ['# Moon', 'Why: the moon.', '', '## Rules', '- **orbit** - The moon circles the earth.', '', '## Tests']
        return self.project({'moon': '\n'.join(header + lines) + '\n'})

    def loose(self, project):
        return [n for n in lint.notes(project) if n.kind == 'loose text']

    def test_a_plain_sentence_in_tests_is_a_note_that_says_how_to_make_it_a_test(self):
        project = self.part(['Test that the moon circles around.'])
        found = self.loose(project)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].where, 'moon.md:8')
        self.assertIn('not locked', found[0].text)
        self.assertIn('make it a test', found[0].text)
        self.assertEqual([p for p in project.check()], [])

    def test_a_note_never_fails_check_but_strict_does(self):
        project = self.part(['Test that the moon circles around.'])
        code, out, _ = run_sor(project.root, 'check')
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r'loose text\s+moon\.md:8')
        self.assertEqual(run_sor(project.root, 'check', '--strict')[0], 2)

    def test_a_loose_sentence_in_rules_is_a_note_too_and_says_a_bullet_not_a_test(self):
        project = self.project({'moon': '# Moon\nWhy: the moon.\n\n## Rules\nIt circles.\n- **moon** - Circles.\n'})
        found = self.loose(project)
        self.assertEqual(len(found), 1)
        self.assertIn('make it a bullet', found[0].text)

    def test_a_line_that_continues_a_bullet_without_indent_is_loose_and_the_note_says_to_indent(self):
        project = self.part(['- **orbit** - the moon circles', 'around the earth.'])
        found = self.loose(project)
        self.assertEqual([n.where for n in found], ['moon.md:9'])
        self.assertIn('indent it', found[0].text)

    def test_what_belongs_to_an_item_or_is_only_structure_is_not_loose(self):
        project = self.part(['- **orbit** - the moon circles around.', '  expect: ok', '  and a longer reason', '',
                             '| a | b |', '|---|---|', '| 1 | 2 |', '<!-- one line -->', '<!--', 'many lines', '-->',
                             '```', 'plain text in a fence', '```', '### a deeper heading', '---', ''])
        self.assertEqual(self.loose(project), [])

    def test_a_table_right_under_a_bullet_is_not_loose(self):
        project = self.project({'moon': '# Moon\nWhy: the moon.\n\n## Rules\n- **orbit** - Where it is:\n| a | b |\n|---|---|\n| 1 | 2 |\n'})
        self.assertEqual(self.loose(project), [])

    def test_loose_text_in_a_tests_file_is_reported_in_that_file(self):
        self.project({'moon': '# Moon\nWhy: the moon.\n\n## Rules\n- **moon** - Circles.\n'})
        write(self.dir, 'sor/moon.tests.md', '## Tests\n- **moon** - it circles.\n  expect: ok\nTest the phases too.\n')
        found = self.loose(Project(self.dir))
        self.assertEqual([n.where for n in found], ['moon.tests.md:4'])

    def test_a_second_sentence_under_the_title_is_loose_and_a_wrapped_why_is_the_usual_case(self):
        project = self.project({'moon': '# Moon\nWhy: the moon, which circles\nthe earth.\n\n## Rules\n- **orbit** - Circles.\n'})
        found = self.loose(project)
        self.assertEqual([n.where for n in found], ['moon.md:3'])
        self.assertIn('join it to the Why line', found[0].text)

    def test_the_header_with_a_title_a_why_settings_and_comments_has_no_loose_text(self):
        project = self.project({'moon': '# Moon\nWhy: the moon.\nOwner: sebastian. Run: open out/index.html\n\n<!-- a comment -->\n\n## Rules\n- **orbit** - Circles.\n'})
        self.assertEqual(self.loose(project), [])

    def test_a_marker_cannot_point_at_a_bullet_nobody_has_named(self):
        project = self.part(['- test that the moon circles around.'])
        draft = [k for k in project.items if '/test:~' in k][0]
        for ident in (draft, draft.replace('test:', '')):
            write(self.dir, 'test/a.test.js', f'// @clause test {ident}\nit("x", () => {{}});\n// @clause end\n')
            said = [str(p) for p in Scan(Project(self.dir)).problems if p.kind == 'marker']
            self.assertEqual(len(said), 1, ident)
            self.assertIn('nobody has named yet', said[0])
            self.assertIn('name it first', said[0])

    def test_a_marker_cannot_point_at_an_unnamed_rule_either(self):
        project = self.project({'moon': '# Moon\nWhy: the moon.\n\n## Rules\n- It circles the earth.\n'})
        draft = [k for k in project.items if '/~' in k][0]
        write(self.dir, 'out/app.js', f'// @clause {draft}\nfunction m() {{}}\n// @clause end\n')
        self.assertTrue(any('nobody has named yet' in p.text for p in Scan(Project(self.dir)).problems if p.kind == 'marker'))

    def test_an_unnamed_test_that_starts_with_a_minus_keeps_it_in_the_message(self):
        project = self.part(['- -5 degrees is too cold.'])
        found = [p for p in project.check() if p.kind == 'unnamed test']
        self.assertIn('"-5 degrees is too cold."', found[0].text)

    def test_the_files_sor_new_writes_have_no_loose_text(self):
        self.assertEqual(run_sor(self.dir, 'new', '--root')[0], 0)
        self.assertEqual(run_sor(self.dir, 'new', 'render')[0], 0)
        self.assertEqual(self.loose(Project(self.dir)), [])

    def test_a_bullet_without_a_name_in_tests_is_a_problem_that_says_how_to_name_it(self):
        project = self.part(['- test that the moon circles around.'])
        found = [p for p in project.check() if p.kind == 'unnamed test']
        self.assertEqual(len(found), 1)
        self.assertIn('has no name yet', found[0].text)
        self.assertIn('start the bullet with the name of the rule it proves', found[0].text)
        self.assertIn('test that the moon circles around', found[0].text)
        self.assertNotIn('~', found[0].text)
        self.assertEqual([p.kind for p in project.check() if p.kind == 'orphan test'], [])

    def test_an_unnamed_test_that_says_what_it_proves_is_fine(self):
        project = self.part(['- test that the moon circles around.', '  proves: {orbit}', '  expect: ok'])
        self.assertEqual([p.kind for p in project.check()], [])

    def test_a_named_test_that_proves_nothing_still_gets_the_old_message(self):
        project = self.part(['- **phases** - the moon has phases.'])
        self.assertEqual([p.kind for p in project.check()], ['orphan test'])


class TestNotesAndTheExitCode(Case):
    def test_notes_never_make_check_fail(self):
        project = game_project(self, NEEDS_ONE_PER_LINE)
        code, out, _ = run_process(project.root, 'check')
        self.assertEqual(code, 0, out)
        self.assertIn('notes (1)', out)
        self.assertRegex(out, r'too long\s+game\.md:\d+\s+Contract has 11 items')

    def test_strict_check_exits_two_when_there_is_a_note(self):
        project = game_project(self, NEEDS_ONE_PER_LINE)
        code, out, _ = run_process(project.root, 'check', '--strict')
        self.assertEqual(code, 2, out)

    def test_strict_check_exits_zero_when_there_is_no_note(self):
        project = game_project(self, NEEDS_GROUPED)
        code, out, _ = run_process(project.root, 'check', '--strict')
        self.assertEqual(code, 0, out)
        self.assertNotIn('notes (', out)

    def test_the_summary_line_is_the_same_with_and_without_notes(self):
        a = game_project(self, NEEDS_ONE_PER_LINE, folder='noisy')
        b = game_project(self, NEEDS_GROUPED, folder='quiet')
        first_a = run_process(a.root, 'check')[1].splitlines()[0]
        first_b = run_process(b.root, 'check')[1].splitlines()[0]
        self.assertRegex(first_a, SUMMARY)
        self.assertEqual(first_a, first_b)
        self.assertEqual(first_a, '5 parts, 8 references, 0 code regions; 0 problem(s)')

    def test_a_problem_still_fails_check_without_strict(self):
        project = self.project({'broken': doc('Broken', rules=['- **a** - needs {nowhere}.'])})
        code, out, _ = run_sor(project.root, 'check')
        self.assertEqual(code, 2, out)
        self.assertIn('; 1 problem(s)', out)


# --- B. open: questions -------------------------------------------------------------------------------

def zoom_with(*under_limits, tests=()):
    """A zoom part whose `limits` rule is followed by these lines; another rule refers to `limits`."""
    return doc('Zoom', 'How far the picture can be zoomed.',
               rules=['- **limits** - zoom stays between {min: 0.3x} and {max: 6x}.', *under_limits,
                      '- **step** - one wheel notch zooms by {factor: 10%}.',
                      '- **fit** - the picture fits inside {limits}.'],
               tests=list(tests))


def snapshot_of(project_dir):
    project = Project(project_dir)
    return lockfile.snapshot(project, Scan(project))


class TestOpenQuestions(Case):
    def pair(self, *under_limits):
        """(project with the lines, same project without them)."""
        a = self.project({'zoom': zoom_with(*under_limits)}, folder='with')
        b = self.project({'zoom': zoom_with()}, folder='without')
        return a, b

    def limits(self, project):
        return project.parts['zoom'].items['limits']

    def test_an_open_line_is_a_question_of_its_item(self):
        a, _ = self.pair('  open: is 6x the right upper limit?')
        item = self.limits(a)
        self.assertEqual([q for _, q in item.opens], ['is 6x the right upper limit?'])
        self.assertEqual(item.opens[0][0], item.lineno + 1)

    def test_an_open_line_is_not_part_of_the_text(self):
        a, b = self.pair('  open: is 6x the right upper limit?')
        self.assertNotIn('open:', self.limits(a).text())
        self.assertEqual(self.limits(a).text(), self.limits(b).text())

    def test_an_open_line_leaves_every_lock_entry_identical(self):
        a, b = self.pair('  open: is 6x the right upper limit?')
        self.assertEqual(snapshot_of(a.root), snapshot_of(b.root))

    def test_a_wrapped_question_is_one_question(self):
        a, _ = self.pair('  open: is 6x', '    the right upper limit', '    for a phone?')
        item = self.limits(a)
        self.assertEqual([q for _, q in item.opens], ['is 6x the right upper limit for a phone?'])
        self.assertEqual(len(item.open_lines), 3)

    def test_a_wrapped_question_leaves_every_lock_entry_identical(self):
        a, b = self.pair('  open: is 6x', '    the right upper limit', '    for a phone?')
        self.assertEqual(snapshot_of(a.root), snapshot_of(b.root))

    def test_a_because_line_after_an_open_line_is_still_text(self):
        a, _ = self.pair('  open: is 6x the right upper limit?', '  because: the budget says so')
        item = self.limits(a)
        self.assertEqual(len(item.opens), 1)
        self.assertIn('because: the budget says so', item.text())
        self.assertNotIn('is 6x', item.text())

    def test_the_text_with_a_because_line_matches_the_same_item_without_the_question(self):
        a = self.project({'zoom': zoom_with('  open: q?', '  because: the budget says so')}, folder='with')
        b = self.project({'zoom': zoom_with('  because: the budget says so')}, folder='without')
        self.assertEqual(snapshot_of(a.root), snapshot_of(b.root))

    def test_table_rows_after_an_open_line_still_belong_to_the_item(self):
        table = ['  | size | zoom |', '  | phone | 3x |', '  | desk | 6x |']
        a = self.project({'zoom': zoom_with('  open: is 6x too much?', *table)}, folder='with')
        b = self.project({'zoom': zoom_with(*table)}, folder='without')
        item = self.limits(a)
        self.assertEqual(list(item.rows), ['phone', 'desk'])
        self.assertEqual(len(item.opens), 1)
        self.assertTrue(item.text().endswith('rows: phone, desk'))
        self.assertIn('zoom/limits/phone', a.items)
        self.assertEqual(snapshot_of(a.root), snapshot_of(b.root))

    def test_a_blank_line_ends_a_wrapped_question(self):
        a, _ = self.pair('  open: first half', '    second half', '', '    not part of the question')
        item = self.limits(a)
        self.assertEqual([q for _, q in item.opens], ['first half second half'])
        self.assertIn('not part of the question', item.text())

    def test_a_capital_open_is_a_question_too(self):
        for word in ('Open', 'OPEN'):
            with self.subTest(word=word):
                a, b = self.pair(f'  {word}: is 6x the right upper limit?')
                self.assertEqual(len(self.limits(a).opens), 1)
                self.assertEqual(snapshot_of(a.root), snapshot_of(b.root))

    def test_an_open_line_with_no_question_is_still_listed(self):
        a, _ = self.pair('  open:')
        self.assertEqual([q for _, q in self.limits(a).opens], [''])
        self.assertEqual([n.text for n in notes_of(a, 'open')], ['zoom/limits:'])

    def test_an_open_line_in_a_test_is_an_ordinary_line(self):
        tests = ['- **limits** - zooming stays inside the limits.', '  open: this is not a question', '  expect: zoom = 6x']
        project = self.project({'zoom': zoom_with(tests=tests)})
        test = project.parts['zoom'].items['test:limits']
        self.assertEqual(test.opens, [])
        self.assertIn('open: this is not a question', test.text())
        self.assertEqual(notes_of(project, 'open'), [])

    def test_a_reference_inside_a_question_is_no_reference_of_the_item(self):
        a, b = self.pair('  open: should {no-such-thing} be used here?')
        self.assertEqual(self.limits(a).refs, [])
        self.assertEqual([p.kind for p in a.check()], [])   # no `broken` problem
        count = lambda p: sum(len(i.refs) for i in p.all_items())
        self.assertEqual(count(a), count(b))

    def test_a_reference_outside_a_question_is_still_broken(self):
        a, _ = self.pair('  because: of {no-such-thing}')
        self.assertEqual([p.kind for p in a.check()], ['broken'])

    def test_check_lists_the_question_as_an_open_note_and_exits_zero(self):
        a, _ = self.pair('  open: is 6x the right upper limit?')
        code, out, _ = run_process(a.root, 'check')
        self.assertEqual(code, 0, out)
        self.assertRegex(out.splitlines()[0], SUMMARY)
        self.assertIn('notes (1)', out)
        self.assertRegex(out, r'(?m)^\s+open\s+zoom\.md:\d+\s+zoom/limits: is 6x the right upper limit\?$')

    def test_strict_check_fails_on_an_open_question(self):
        a, _ = self.pair('  open: is 6x the right upper limit?')
        self.assertEqual(run_sor(a.root, 'check', '--strict')[0], 2)

    def test_check_with_and_without_the_question_has_the_same_summary_line(self):
        a, b = self.pair('  open: is 6x the right upper limit?')
        self.assertEqual(run_sor(a.root, 'check')[1].splitlines()[0], run_sor(b.root, 'check')[1].splitlines()[0])

    def test_every_question_of_a_part_is_counted_by_sor_parts(self):
        a, _ = self.pair('  open: first?', '  open: second?')
        info = json.loads(run_sor(a.root, 'parts', '--json')[1])
        self.assertEqual({i['id']: i['open'] for i in info}, {'ROOT': 0, 'zoom': 2})


# --- C. placeholders ----------------------------------------------------------------------------------

class TestPlaceholders(Case):
    def placeholders(self, project):
        return [p for p in project.check() if p.kind == 'placeholder']

    def test_a_placeholder_on_an_item_line_is_a_problem(self):
        project = self.project({'a': doc('A', rules=['- **x** - <fill in: what must be true>.'])})
        found = self.placeholders(project)
        self.assertEqual([p.where for p in found], ['a.md:5'])
        self.assertTrue(found[0].text.startswith('unfilled template text: '))

    def test_a_placeholder_on_the_why_line_is_a_problem(self):
        project = self.project({'a': doc('A', why='<fill in: one sentence>', rules=['- **x** - fine.'])})
        self.assertEqual([p.where for p in self.placeholders(project)], ['a.md:2'])

    def test_a_placeholder_in_a_tests_file_is_a_problem(self):
        project = self.project({'a': doc('A', rules=['- **x** - fine.'])})
        write(self.dir, 'sor/a.tests.md', '## Tests\n- **x** - proves it.\n  expect: <fill in: the result>\n')
        found = self.placeholders(Project(self.dir))
        self.assertEqual([p.where for p in found], ['a.tests.md:3'])

    def test_check_exits_two_for_a_placeholder(self):
        project = self.project({'a': doc('A', rules=['- **x** - <fill in: what must be true>.'])})
        code, out, _ = run_process(project.root, 'check')
        self.assertEqual(code, 2, out)
        self.assertRegex(out, r'placeholder\s+a\.md:5')
        self.assertIn('; 1 problem(s)', out)

    def test_a_placeholder_inside_backticks_is_an_example_and_no_problem(self):
        project = self.project({'a': doc('A', rules=['- **x** - write `<fill in: what>` where a person writes.'])})
        self.assertEqual(self.placeholders(project), [])
        self.assertEqual(run_sor(project.root, 'check')[0], 0)

    def test_a_placeholder_inside_a_fenced_block_is_an_example_and_no_problem(self):
        rule = ['- **x** - the template looks like this:', '  ```', '  <fill in: name>', '  ```']
        project = self.project({'a': doc('A', rules=rule)})
        self.assertEqual(self.placeholders(project), [])
        self.assertEqual(run_sor(project.root, 'check')[0], 0)

    def test_text_after_a_closed_fence_counts_again(self):
        rule = ['- **x** - the template looks like this:', '  ```', '  <fill in: name>', '  ```',
                '  and then <fill in: more>']
        found = self.placeholders(self.project({'a': doc('A', rules=rule)}))
        self.assertEqual([p.where for p in found], ['a.md:9'])

    def test_a_placeholder_next_to_backticked_text_is_still_a_problem(self):
        rule = ['- **x** - use `<fill in: a>` or <fill in: b>.']
        self.assertEqual(len(self.placeholders(self.project({'a': doc('A', rules=rule)}))), 1)

    def test_a_placeholder_in_one_part_blocks_nothing_in_another(self):
        project = self.project({'a': doc('A', rules=['- **x** - <fill in: what>.']),
                                'b': doc('B', rules=['- **y** - all filled in.'], tests=['- **y** - proves it.', '  expect: ok'])})
        found = project.check()
        self.assertEqual(kinds(found), ['placeholder'])
        self.assertTrue(all(p.where.startswith('a.md:') for p in found), [str(p) for p in found])
        code, out, _ = run_sor(project.root, 'check')
        self.assertIn('; 1 problem(s)', out)
        self.assertEqual(code, 2)


# --- D. sor new ---------------------------------------------------------------------------------------

def fill_in(text):
    """Every <fill in: ...> replaced by real words; `name` the same everywhere, so a test finds its rule."""
    return re.sub(r'<fill in: [^>]*>', 'plain real words', text.replace('<fill in: name>', 'speed'))


def md_files(root):
    spec = os.path.join(root, 'sor')
    return sorted(os.path.join(d, f) for d, _, fs in os.walk(spec) for f in fs if f.endswith('.md'))


class TestNewCommand(Case):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.dir, 'my-game')
        os.makedirs(self.proj)

    def new(self, *args, via=run_sor):
        code, out, err = via(self.proj, 'new', *args)
        self.assertEqual(code, 0, out + err)
        return out

    def test_a_child_goes_in_a_folder_beside_the_file_of_its_part(self):
        make_project(self.proj, {'render': doc('Render')})
        out = self.new('render/culling')
        self.assertIn('wrote sor/render/culling.md', out)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, 'sor', 'render.md')), 'the part keeps its file')
        self.assertEqual(sorted(Project(self.proj).parts), ['', 'render', 'render/culling'])

    def test_a_part_whose_children_already_sit_in_a_folder_gets_its_file_beside_the_folder(self):
        make_project(self.proj, {'render/culling': doc('Culling')})
        out = self.new('render')
        self.assertIn('wrote sor/render.md', out)
        self.assertEqual(sorted(Project(self.proj).parts), ['', 'render', 'render/culling'])

    def only_placeholders(self):
        found = Project(self.proj).check()
        self.assertEqual(kinds(found), ['placeholder'], [str(p) for p in found])
        return found

    def test_new_root_writes_the_root_file_and_leaves_only_placeholders_to_fill_in(self):
        out = self.new('--root')
        self.assertIn('wrote sor/SPECOFRECORD.md', out)
        text = read(os.path.join(self.proj, 'sor', 'SPECOFRECORD.md'))
        self.assertTrue(text.startswith('# My game\nWhy: <fill in:'))
        self.only_placeholders()

    def test_new_part_adds_a_part_with_only_placeholders_to_fill_in(self):
        self.new('--root')
        self.new('render')
        self.only_placeholders()
        self.assertIn('render', Project(self.proj).parts)

    def test_new_part_with_a_dash_titles_it_with_spaces(self):
        self.new('--root')
        self.new('render-queue')
        self.only_placeholders()
        self.assertEqual(Project(self.proj).parts['render-queue'].title, 'Render queue')

    def test_new_part_inside_a_folder_writes_the_file_in_that_folder(self):
        self.new('--root')
        out = self.new('targets/web')
        self.assertIn('wrote sor/targets/web.md', out)
        self.only_placeholders()
        self.assertEqual(Project(self.proj).parts['targets/web'].title, 'Web')

    def test_a_project_with_every_placeholder_filled_in_has_no_problem_left(self):
        for args in (['--root'], ['render'], ['render-queue'], ['targets/web']):
            self.new(*args, via=run_process)
        for path in md_files(self.proj):
            text = read(path)
            with open(path, 'w', encoding='utf8', newline='\n') as fh:
                fh.write(fill_in(text))
        self.assertEqual([str(p) for p in Project(self.proj).check()], [])
        code, out, _ = run_process(self.proj, 'check')
        self.assertEqual(code, 0, out)
        self.assertRegex(out.splitlines()[0], SUMMARY)

    def test_a_part_that_misses_a_placeholder_is_not_an_orphan_test_or_a_missing_why(self):
        self.new('--root')
        self.new('render')
        problems = Project(self.proj).check()
        self.assertFalse([p for p in problems if p.kind in ('orphan test', 'header', 'duplicate', 'broken')])

    def test_why_text_goes_on_the_why_line_and_leaves_no_placeholder_there(self):
        self.new('--root', '--why', 'A tiny game engine.')
        self.new('render', '--why', 'Draws the world.')
        for rel, why in (('SPECOFRECORD', 'A tiny game engine.'), ('render', 'Draws the world.')):
            lines = read(os.path.join(self.proj, 'sor', rel + '.md')).splitlines()
            self.assertEqual(lines[1], f'Why: {why}')
        self.assertFalse([p for p in self.only_placeholders() if p.where.endswith(':2')])
        self.assertTrue(self.only_placeholders())   # the rule and test placeholders are still there

    def test_why_text_has_its_spaces_and_line_breaks_tidied(self):
        self.new('--root', '--why', '  A   tiny\ngame   engine. ')
        lines = read(os.path.join(self.proj, 'sor', 'SPECOFRECORD.md')).splitlines()
        self.assertEqual(lines[1], 'Why: A tiny game engine.')

    def test_why_text_with_braces_is_written_as_it_is(self):
        self.new('--root', '--why', 'Shapes like {x, y} and {title}.')
        lines = read(os.path.join(self.proj, 'sor', 'SPECOFRECORD.md')).splitlines()
        self.assertEqual(lines[1], 'Why: Shapes like {x, y} and {title}.')

    def test_hint_comments_are_one_line_html_comments_without_braces_or_placeholders(self):
        self.new('--root')
        self.new('render')
        for path in md_files(self.proj):
            comments = [l for l in read(path).splitlines() if l.startswith('<!--')]
            self.assertTrue(comments, path)
            for line in comments:
                self.assertTrue(line.endswith('-->'), line)
                self.assertFalse(set('{}') & set(line), line)
                self.assertNotIn('<fill in', line)

    def test_hint_comments_create_no_items_and_no_text(self):
        self.new('--root')
        self.new('render')
        bare = os.path.join(self.dir, 'bare')
        for path in md_files(self.proj):
            lines = read(path).splitlines()
            rel = os.path.relpath(path, self.proj).replace(os.sep, '/')
            write(bare, rel, '\n'.join(l for l in lines if not l.startswith('<!--')) + '\n')
        with_comments, without = Project(self.proj), Project(bare)

        def outline(project):
            return {pid: (p.title, dict(p.header), sorted(p.headings),
                          [(i.name, i.section, i.kind, i.text(), [r for _, r in i.refs], dict(i.values))
                           for i in p.items.values()])
                    for pid, p in project.parts.items()}

        self.assertEqual(outline(with_comments), outline(without))
        self.assertEqual(lockfile.snapshot(with_comments, Scan(with_comments)), lockfile.snapshot(without, Scan(without)))
        problems = lambda p: sorted((x.kind, x.text) for x in p.check())
        self.assertEqual(problems(with_comments), problems(without))

    def test_new_never_overwrites_what_is_there(self):
        self.new('--root')
        self.new('render')
        path = os.path.join(self.proj, 'sor', 'render.md')
        with open(path, 'a', encoding='utf8') as fh:
            fh.write('- **mine** - written by a person.\n')
        before = tree(self.proj)
        code, out, _ = run_sor(self.proj, 'new', 'render')
        self.assertEqual(code, 2)
        self.assertIn('already exists', out)
        self.assertEqual(tree(self.proj), before)


class TestNewRefusals(Case):
    """Each refusal exits 2, says why, and writes nothing (not even an empty folder)."""

    def new(self, **kw):
        return run_view(views.cmd_new, root=self.dir, part=kw.get('part'), make_root=kw.get('make_root', False),
                        why=kw.get('why'))

    def refuse(self, phrase, **kw):
        before = tree(self.dir)
        code, out = self.new(**kw)
        self.assertEqual(code, 2, out)
        self.assertIn(phrase, out)
        self.assertEqual(tree(self.dir), before, 'something was written')

    def test_a_part_whose_file_exists_is_refused(self):
        make_project(self.dir, {'render': doc('Render')})
        self.refuse('already exists', part='render')

    def test_a_part_whose_folder_exists_is_refused(self):
        make_project(self.dir, {'render/CLAUSES': doc('Render')})
        self.refuse('already exists as', part='render')

    def test_a_part_named_like_an_existing_item_is_refused(self):
        # `year` is a rule of the root: a part `year` would make `sor check` report a collision
        make_project(self.dir, root_text=doc('Demo', rules=['- **year** - Earth takes {days: 365 days} to go round.']))
        self.refuse('already the id of an item', part='year')

    def test_a_mistyped_project_folder_is_refused_and_not_created(self):
        missing = os.path.join(self.dir, 'typo', 'game')
        code, out = run_view(views.cmd_new, root=missing, part=None, make_root=True, why=None)
        self.assertEqual(code, 2, out)
        self.assertIn('no such folder', out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'typo')), 'a stray folder was created')

    def test_a_part_without_a_project_is_refused(self):
        self.refuse('no project here', part='render')

    def test_a_second_root_is_refused(self):
        make_project(self.dir)
        self.refuse('already exists', make_root=True)

    def test_an_invalid_part_id_is_refused(self):
        make_project(self.dir)
        for bad in ('Render', 'a_b', '1abc', 'a//b', '/a', 'a/', 'a b', 'a.b', 'caf\u00e9'):
            with self.subTest(id=bad):
                self.refuse('not a part id', part=bad)

    def test_an_invalid_part_id_is_refused_even_with_no_project(self):
        self.refuse('not a part id', part='Render')

    def test_a_part_and_root_together_are_refused(self):
        make_project(self.dir)
        self.refuse('not both', part='render', make_root=True)

    def test_neither_a_part_nor_root_is_refused(self):
        make_project(self.dir)
        self.refuse('give a PART', part=None, make_root=False)

    def test_the_refusal_reaches_the_command_line_as_exit_code_two(self):
        code, out, _ = run_process(self.dir, 'new', 'Render')
        self.assertEqual(code, 2)
        self.assertIn('not a part id', out)
        self.assertEqual(os.listdir(self.dir), [])


# --- E. sor parts, sor needs, sor changes -------------------------------------------------------------

class TestPartsView(Case):
    KEYS = {'id', 'title', 'why', 'owner', 'source', 'rel', 'bullets', 'gives', 'open'}

    def test_parts_json_is_a_list_of_parts_with_the_documented_keys(self):
        project = game_project(self, NEEDS_GROUPED)
        code, out, _ = run_process(project.root, 'parts', '--json')
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIsInstance(data, list)
        self.assertEqual([d['id'] for d in data], ['ROOT', 'game', 'input', 'rendering', 'world'])
        for d in data:
            self.assertEqual(set(d), self.KEYS)

    def test_parts_come_in_id_order_with_the_root_first(self):
        project = self.project({'ui-kit': doc('Kit'), 'ui/CLAUSES': doc('Ui'), 'a': doc('A'), 'targets/web': doc('Web')})
        ids = [d['id'] for d in json.loads(run_sor(project.root, 'parts', '--json')[1])]
        self.assertEqual(ids, ['ROOT', 'a', 'targets/web', 'ui', 'ui-kit'])

    def test_the_root_prints_as_root_and_comes_first(self):
        project = game_project(self, NEEDS_GROUPED)
        code, out, _ = run_sor(project.root, 'parts')
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('ROOT'))
        self.assertEqual(json.loads(run_sor(project.root, 'parts', '--json')[1])[0]['id'], 'ROOT')

    def test_the_bullet_counts_equal_the_linters(self):
        project = game_project(self, NEEDS_ONE_PER_LINE)
        for d in json.loads(run_sor(project.root, 'parts', '--json')[1]):
            part = project.parts['' if d['id'] == 'ROOT' else d['id']]
            self.assertEqual(d['bullets'], {k.lower(): n for k, n in lint.bullet_counts(part).items()})
        game_info = [d for d in json.loads(run_sor(project.root, 'parts', '--json')[1]) if d['id'] == 'game'][0]
        self.assertEqual(game_info['bullets']['contract'], 11)
        self.assertEqual(game_info['gives'], ['start', 'step', 'stop'])

    def test_why_title_owner_and_source_are_read_from_the_header(self):
        text = ('# Engine\nWhy: Runs the physics.\nOwner: sam\nSource: code at src/engine/\n\n'
                '## Rules\n- **fast** - it is fast.\n')
        other = '# Other\nWhy: Hand written.\nCode: src/other (by hand)\n\n## Rules\n- **ok** - fine.\n'
        project = self.project({'engine': text, 'other': other})
        info = {d['id']: d for d in json.loads(run_sor(project.root, 'parts', '--json')[1])}
        self.assertEqual((info['engine']['title'], info['engine']['why'], info['engine']['owner']),
                         ('Engine', 'Runs the physics.', 'sam'))
        self.assertEqual(info['engine']['source'], 'code at src/engine/')
        self.assertEqual(info['engine']['rel'], 'engine.md')
        self.assertEqual(info['other']['source'], 'code at src/other')
        self.assertIsNone(info['other']['owner'])
        self.assertIsNone(info['ROOT']['source'])

    def test_text_output_ends_with_the_number_of_parts(self):
        project = game_project(self, NEEDS_GROUPED)
        self.assertEqual(run_sor(project.root, 'parts')[1].splitlines()[-1], '5 parts')

    def test_text_output_says_part_for_exactly_one(self):
        project = self.project()
        self.assertEqual(run_sor(project.root, 'parts')[1].splitlines()[-1], '1 part')

    def test_text_output_shows_each_why(self):
        project = game_project(self, NEEDS_GROUPED)
        out = run_sor(project.root, 'parts')[1]
        self.assertIn('The game ties the parts together.', out)
        self.assertIn('gives start, step, stop', out)

    def test_parts_changes_no_file(self):
        project = game_project(self, NEEDS_GROUPED)
        before = tree(self.dir)
        run_sor(project.root, 'parts')
        run_sor(project.root, 'parts', '--json')
        self.assertEqual(tree(self.dir), before)


REFS_ROOT = doc('Refs', 'A project that shows what needs counts.', header=['Design: design/tokens.json'],
                rules=['- **year** - an orbit takes {days: 365 days}.'],
                approach=['- **parts** - {game} is the game, {world}, {input} and {rendering} are what it uses.'])
TOKENS = {'planet': {'mars': {'$value': '#c1440e', '$type': 'color'}}}
REFS_RULES = ['- **speed** - the game runs at {fps: 60 frames per second}.',
              '- **tint** - the planet is drawn in {design/planet/mars}.',
              '- **length** - a year lasts {year}.']
REFS_APPROACH = ['- **frame** - each frame calls {input/refresh}, {world/update} and {rendering/draw-world}.',
                 '- **setup** - startup calls {world/new}, {input/new} and {rendering/new}.',
                 '- **end** - shutdown calls {input/closed} and {rendering/close}; the loop lives in {loop/tick}.']


class TestNeedsView(Case):
    def setUp(self):
        super().setUp()
        parts = dict(providers())
        parts['game/CLAUSES'] = doc('Game', 'The game ties the parts together.', rules=REFS_RULES,
                                    approach=REFS_APPROACH, contract=PROVIDES)
        parts['game/loop'] = doc('Loop', 'The loop of the game.',
                                 rules=['- **tick** - one tick runs a frame.', '- **pace** - ticks follow {speed}.'])
        make_project(self.dir, parts, root_text=REFS_ROOT)
        write(self.dir, 'design/tokens.json', json.dumps(TOKENS))   # the design export sits next to sor/
        self.project_ = Project(self.dir)

    def needs(self, *args):
        code, out, _ = run_sor(self.dir, 'needs', *args)
        return code, out

    def needs_json(self, part):
        code, out = self.needs(part, '--json')
        self.assertEqual(code, 0, out)
        return json.loads(out)[0]['needs']

    def test_the_fixture_is_a_clean_project(self):
        self.assertEqual([str(p) for p in self.project_.check()], [])

    def test_a_part_with_only_references_needs_all_eight_targets_none_of_them_declared(self):
        rows = self.needs_json('game')
        self.assertEqual(sorted(r['target'] for r in rows), sorted(NEEDED))
        self.assertTrue(all(r['gives'] and r['kind'] == 'gives' for r in rows))
        self.assertFalse(any(r['declared'] for r in rows))
        self.assertEqual({r['part'] for r in rows}, {'world', 'input', 'rendering'})

    def test_every_need_says_which_items_refer_to_it(self):
        rows = {r['target']: r['from'] for r in self.needs_json('game')}
        self.assertEqual(rows['world/update'], ['game/frame'])
        self.assertEqual(rows['rendering/close'], ['game/end'])

    def test_text_output_lists_the_targets_and_shows_no_declared_column(self):
        code, out = self.needs('game')
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], 'game needs:')
        for target in NEEDED:
            self.assertIn('{' + target + '}', out)
        self.assertNotIn('declared', out)

    def test_an_explicit_needs_bullet_marks_its_targets_declared(self):
        content = read(os.path.join(self.dir, 'sor', 'game', 'CLAUSES.md')).rstrip('\n')   # its last section is Contract
        write(self.dir, 'sor/game/CLAUSES.md', content + '\n- needs {world/new}, {world/update} - the world\n')
        rows = self.needs_json('game')
        self.assertEqual(sorted(r['target'] for r in rows if r['declared']), ['world/new', 'world/update'])
        self.assertEqual(len(rows), 8)
        self.assertIn('declared', self.needs('game')[1])

    def test_a_word_of_the_root_is_not_a_need(self):
        self.assertNotIn('year', {r['target'] for r in self.needs_json('game')})

    def test_a_word_of_the_parent_is_not_a_need(self):
        self.assertEqual(self.needs_json('game/loop'), [])
        self.assertIn('game/loop needs nothing from other parts', self.needs('game/loop')[1])

    def test_a_child_part_and_its_items_are_not_needs(self):
        targets = {r['target'] for r in self.needs_json('game')}
        self.assertNotIn('game/loop/tick', targets)
        self.assertFalse([t for t in targets if t.startswith('game/')])

    def test_a_design_token_is_not_a_need(self):
        self.assertFalse([r for r in self.needs_json('game') if r['target'].startswith('design')])

    def test_the_root_part_needs_nothing(self):
        self.assertEqual(self.needs_json('ROOT'), [])
        code, out = self.needs('ROOT')
        self.assertEqual(code, 0)
        self.assertIn('ROOT needs nothing from other parts', out)

    def test_a_whole_sibling_part_is_a_need_of_kind_part(self):
        write(self.dir, 'sor/world.md', doc('World', 'The world.', rules=['- **fine** - ok with {input}.'],
                                                 contract=['- gives **new** - n.', '- gives **update** - u.']))
        rows = self.needs_json('world')
        self.assertEqual([(r['target'], r['kind'], r['gives']) for r in rows], [('input', 'part', False)])

    def test_a_need_that_is_no_gives_item_is_marked_so(self):
        write(self.dir, 'sor/world.md', doc('World', 'The world.', rules=['- **fine** - ok with {input/new}.'],
                                                 contract=['- gives **new** - n.', '- gives **update** - u.']))
        write(self.dir, 'sor/input.md', doc('Input', 'Reads input.', rules=['- **new** - a rule, not a promise.']))
        rows = self.needs_json('world')
        self.assertEqual([(r['target'], r['kind'], r['gives']) for r in rows], [('input/new', 'rules', False)])
        self.assertIn('not a gives', self.needs('world')[1])

    def test_a_value_of_a_gives_item_is_a_need_of_that_gives_and_a_needs_bullet_declares_it(self):
        world = doc('World', 'The world.', contract=['- gives **new** - makes a world at {fps: 60 frames per second}.'])
        speed = ['- **speed** - runs at {world/new.fps}.']
        plain = self.project({'world': world, 'game': doc('Game', rules=speed)}, folder='plain')
        rows = json.loads(run_sor(plain.root, 'needs', 'game', '--json')[1])[0]['needs']
        self.assertEqual([(r['target'], r['kind'], r['gives'], r['declared']) for r in rows],
                         [('world/new.fps', 'gives', True, False)])
        said = self.project({'world': world, 'game': doc('Game', rules=speed, contract=['- needs {world/new} - the world'])},
                            folder='said')
        rows = json.loads(run_sor(said.root, 'needs', 'game', '--json')[1])[0]['needs']
        self.assertEqual([(r['target'], r['declared']) for r in rows], [('world/new', True), ('world/new.fps', True)])

    def test_without_a_part_only_parts_that_need_something_are_listed(self):
        code, out = self.needs()
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], '1 part needs something')
        data = json.loads(self.needs('--json')[1])
        self.assertEqual([d['id'] for d in data], ['game'])

    def test_the_design_export_is_a_part_that_sor_parts_marks_as_generated(self):
        out = run_sor(self.dir, 'parts')[1]
        self.assertIn('generated from design/tokens.json', out)
        self.assertIn('design', [d['id'] for d in json.loads(run_sor(self.dir, 'parts', '--json')[1])])

    def test_an_unknown_part_exits_two(self):
        code, out, _ = run_process(self.dir, 'needs', 'nope')
        self.assertEqual(code, 2)
        self.assertIn('nope: no such part', out)

    def test_an_item_is_not_a_part(self):
        code, out = self.needs('game/speed')
        self.assertEqual(code, 2)
        self.assertIn('no such part', out)

    def test_needs_json_parses_without_a_part_too(self):
        data = json.loads(self.needs('--json')[1])
        self.assertIsInstance(data, list)
        for entry in data:
            self.assertEqual(set(entry), {'id', 'needs'})
            for row in entry['needs']:
                self.assertEqual(set(row), {'part', 'target', 'kind', 'gives', 'declared', 'from'})

    def test_a_project_where_nothing_refers_across_parts_says_so(self):
        project = self.project({'a': doc('A', rules=['- **x** - fine.'])}, folder='plain')
        self.assertEqual(run_sor(project.root, 'needs')[1].strip(), 'no part needs anything from another')

    def test_needs_changes_no_file(self):
        before = tree(self.dir)
        self.needs()
        self.needs('game', '--json')
        self.assertEqual(tree(self.dir), before)


ZOOM_RULES = ['- **limits** - zoom stays between {min: 0.3x} and {max: 6x}.',
              '- **step** - one wheel notch zooms by {factor: 10%}.',
              '- **center** - zoom keeps the point under the cursor fixed.',
              '- **old-zoom** - retired: replaced by the limits rule.']


class TestChangesView(Case):
    def changes(self, project_dir=None, *args):
        code, out, err = run_sor(project_dir or self.dir, 'changes', *args)
        self.assertEqual(code, 0, out + err)
        return out

    def changes_json(self):
        return json.loads(self.changes(self.dir, '--json'))

    def locked_zoom(self):
        make_project(self.dir, {'zoom': doc('Zoom', 'How far the picture can be zoomed.', rules=ZOOM_RULES)})
        lock_now(self.dir)

    def edit_zoom(self, rules, tests=()):
        write(self.dir, 'sor/zoom.md', doc('Zoom', 'How far the picture can be zoomed.', rules=rules, tests=list(tests)))

    def ids(self, data, group):
        return [r['id'] for r in data[group]]

    def test_before_any_lock_the_text_says_no_lock_yet(self):
        make_project(self.dir, {'zoom': doc('Zoom', rules=ZOOM_RULES)})
        code, out, _ = run_process(self.dir, 'changes')
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], 'no lock yet: everything is new')
        self.assertIn('`sor lock` accepts the current state.', out)
        self.assertIn('Added (', out)

    def test_before_any_lock_json_says_not_locked(self):
        make_project(self.dir, {'zoom': doc('Zoom', rules=ZOOM_RULES)})
        data = self.changes_json()
        self.assertFalse(data['locked'])
        self.assertGreater(data['counts']['added'], 0)

    def test_nothing_pending_right_after_a_lock(self):
        make_project(self.dir, {'zoom': doc('Zoom', rules=ZOOM_RULES[:3])})
        lock_now(self.dir)
        self.assertEqual(self.changes().strip(), 'nothing pending')
        data = self.changes_json()
        self.assertTrue(data['locked'])
        self.assertEqual(data['counts'], {'added': 0, 'changed': 0, 'removed': 0, 'fixes': 0, 'retired': 0})

    def test_added_changed_removed_fixes_and_retired_hold_exactly_their_items(self):
        self.locked_zoom()
        rules = [ZOOM_RULES[0],
                 '- **step** - one wheel notch zooms by {factor: 5%}.',      # changed
                 '- **snap** - zoom snaps to whole percents.',               # added
                 ZOOM_RULES[3]]                                              # `center` is gone: removed
        tests = ['- **limits** - zooming forever stays inside the limits.', '  expect: zoom = {limits.max}', '  bug: #7']
        self.edit_zoom(rules, tests)
        data = self.changes_json()
        self.assertEqual(self.ids(data, 'added'), ['zoom/snap'])
        self.assertEqual(self.ids(data, 'changed'), ['zoom/step'])
        self.assertEqual(self.ids(data, 'removed'), ['zoom/center'])
        self.assertEqual(self.ids(data, 'fixes'), ['zoom/test:limits'])
        self.assertEqual(data['fixes'][0]['bug'], ['#7'])
        self.assertEqual(self.ids(data, 'retired'), ['zoom/old-zoom'])
        self.assertEqual(data['counts'], {'added': 1, 'changed': 1, 'removed': 1, 'fixes': 1, 'retired': 1})

    def test_a_fix_is_not_repeated_under_added(self):
        self.locked_zoom()
        self.edit_zoom(ZOOM_RULES, ['- **limits** - zooming forever stays inside the limits.', '  expect: zoom = 6x', '  bug: #7'])
        data = self.changes_json()
        self.assertEqual(self.ids(data, 'fixes'), ['zoom/test:limits'])
        self.assertEqual(data['added'], [])

    def test_a_new_test_without_bug_is_added_and_no_fix(self):
        self.locked_zoom()
        self.edit_zoom(ZOOM_RULES, ['- **limits** - zooming stays inside the limits.', '  expect: zoom = 6x'])
        data = self.changes_json()
        self.assertEqual(self.ids(data, 'added'), ['zoom/test:limits'])
        self.assertEqual(data['fixes'], [])

    def test_the_text_groups_each_item_under_its_title(self):
        self.locked_zoom()
        self.edit_zoom([ZOOM_RULES[0], '- **step** - one wheel notch zooms by {factor: 5%}.',
                        '- **snap** - zoom snaps to whole percents.', ZOOM_RULES[3]],
                       ['- **limits** - zooming stays inside the limits.', '  expect: zoom = 6x', '  bug: #7'])
        out = self.changes()
        order = [out.index(t) for t in ('Added (1)', 'Changed (1)', 'Removed (1)', 'Fixes (1)', 'Retired (1)')]
        self.assertEqual(order, sorted(order))
        self.assertIn('  - zoom/snap', out)
        self.assertIn('  - zoom/step', out)
        self.assertIn('  - zoom/center', out)
        self.assertIn('  - zoom/test:limits', out)
        self.assertIn('(bug: #7)', out)
        self.assertIn('  - zoom/old-zoom \u2014 replaced by the limits rule.', out)

    def test_a_test_with_a_bug_line_that_changes_is_a_fix_and_not_a_change(self):
        make_project(self.dir, {'zoom': doc('Zoom', 'How far the picture can be zoomed.', rules=ZOOM_RULES, tests=[
            '- **limits** - zooming stays inside the limits.', '  expect: zoom = 6x', '  bug: #7'])})
        lock_now(self.dir)
        self.edit_zoom(ZOOM_RULES, ['- **limits** - zooming stays inside the limits.', '  expect: zoom = 5x', '  bug: #7'])
        data = self.changes_json()
        self.assertEqual(self.ids(data, 'fixes'), ['zoom/test:limits'])
        self.assertEqual((data['added'], data['changed']), ([], []))

    def test_an_item_retired_after_the_lock_is_changed_and_retired(self):
        self.locked_zoom()
        self.edit_zoom([ZOOM_RULES[0], ZOOM_RULES[1], '- **center** - retired: the cursor point is not kept.', ZOOM_RULES[3]])
        data = self.changes_json()
        self.assertEqual(self.ids(data, 'changed'), ['zoom/center'])
        self.assertEqual(sorted(self.ids(data, 'retired')), ['zoom/center', 'zoom/old-zoom'])

    def test_an_item_added_already_retired_is_added_and_retired(self):
        self.locked_zoom()
        self.edit_zoom(ZOOM_RULES + ['- **old-step** - retired: replaced by {step}.'])
        data = self.changes_json()
        self.assertEqual(self.ids(data, 'added'), ['zoom/old-step'])
        self.assertIn('zoom/old-step', self.ids(data, 'retired'))

    def test_retired_in_backticks_is_an_example_and_no_retirement(self):
        make_project(self.dir, {'zoom': doc('Zoom', rules=['- **x** - write `retired: why` to retire a rule.'])})
        lock_now(self.dir)
        self.assertEqual(self.changes_json()['retired'], [])

    def test_an_open_question_is_no_change(self):
        self.locked_zoom()
        self.edit_zoom([ZOOM_RULES[0], '  open: is 6x the right upper limit?', *ZOOM_RULES[1:]])
        self.assertEqual(self.changes().strip().splitlines()[0], 'Retired (1)')
        self.assertEqual(self.changes_json()['counts'], {'added': 0, 'changed': 0, 'removed': 0, 'fixes': 0, 'retired': 1})

    def test_json_has_locked_counts_and_the_five_groups(self):
        self.locked_zoom()
        data = self.changes_json()
        self.assertEqual(set(data), {'locked', 'counts', 'added', 'changed', 'removed', 'fixes', 'retired'})
        self.assertEqual({k: len(data[k]) for k in data['counts']}, data['counts'])

    def test_changes_changes_no_file(self):
        self.locked_zoom()
        self.edit_zoom(ZOOM_RULES[:2])
        before = tree(self.dir)
        self.changes()
        self.changes(self.dir, '--json')
        self.assertEqual(tree(self.dir), before)


# --- F. the session-start hook ------------------------------------------------------------------------

def context(payload_cwd):
    out = hook.session_start({'cwd': payload_cwd})
    return None if out is None else out['hookSpecificOutput']['additionalContext']


def parts_line(ctx):
    lines = [l for l in ctx.splitlines() if l.startswith('Parts: ')]
    assert len(lines) == 1, ctx
    return lines[0]


class TestSessionStartHook(Case):
    def baseline(self):
        """The note of a project that has a root file only: the old note, with no part to list."""
        other = os.path.join(self.dir, 'baseline')
        make_project(other)
        note = context(other)
        self.assertNotIn('Parts:', note)
        return note

    def test_a_project_with_parts_gets_the_old_note_and_a_parts_line(self):
        note = self.baseline()
        make_project(self.dir, {'render': doc('Render', 'Draws the world.'), 'input': doc('Input', 'Reads keys.')})
        ctx = context(self.dir)
        self.assertTrue(ctx.startswith(note + '\nParts: '), ctx)
        self.assertEqual(len(ctx.splitlines()), len(note.splitlines()) + 1)
        self.assertIn('This project keeps its specification as clauses in sor/', ctx)
        self.assertIn(f'`{CMD} status`', ctx)

    def test_the_index_has_the_ids_sorted_without_the_root_and_each_why(self):
        make_project(self.dir, {'render': doc('Render', 'Draws the world.'), 'input': doc('Input', 'Reads keys.'),
                                'targets/web': doc('Web', 'The page.'), 'audio': doc('Audio', 'Plays sounds.'),
                                'ui-kit': doc('Kit', 'Widgets.'), 'ui/CLAUSES': doc('Ui', 'The screen.')})
        line = parts_line(context(self.dir))
        # by id, not by file name: ui-kit.md comes before ui/CLAUSES.md on disk, but `ui` is the shorter id
        self.assertEqual(line, 'Parts: audio - Plays sounds.; input - Reads keys.; render - Draws the world.; '
                               'targets/web - The page.; ui - The screen.; ui-kit - Widgets.')
        self.assertNotIn('CLAUSES', line)

    def test_a_part_without_a_why_is_listed_by_its_title_and_one_without_a_title_by_its_id(self):
        make_project(self.dir, {'plain': '# Plain title\n\n## Rules\n- **a** - x.\n', 'bare': '## Rules\n- **a** - x.\n'})
        self.assertEqual(parts_line(context(self.dir)), 'Parts: bare; plain - Plain title')

    def test_a_why_of_sixty_characters_is_kept_and_a_longer_one_is_cut_to_sixty(self):
        sixty, longer = 'w' * 60, ('long ' * 20).strip()
        make_project(self.dir, {'exact': doc('E', sixty), 'over': doc('O', 'w' * 61), 'words': doc('W', longer)})
        entries = dict(e.split(' - ', 1) for e in parts_line(context(self.dir))[len('Parts: '):].split('; '))
        self.assertEqual(entries['exact'], sixty)
        self.assertEqual(entries['over'], 'w' * 59 + '\u2026')
        self.assertLessEqual(len(entries['words']), 60)
        self.assertTrue(entries['words'].endswith('\u2026'))

    def test_a_hundred_and_fifty_parts_end_with_how_many_more_and_stay_within_the_limit(self):
        parts = {}
        for i in range(1, 151):
            why = f'Part number {i} does its job' if i % 3 else ('this part has a very long reason ' * 4).strip()
            parts[f'part-{i}'] = doc(f'Part {i}', why)
        make_project(self.dir, parts)
        line = parts_line(context(self.dir))
        tail = re.search(r'(?:; )?\.\.\. and (\d+) more: run `[^`]+`$', line)
        self.assertIsNotNone(tail, line[-80:])
        self.assertIn(f'`{CMD} parts`', tail.group(0))
        entries = line[len('Parts: '):tail.start()].split('; ')
        ids = [e.split(' - ', 1)[0] for e in entries]
        self.assertLessEqual(len(line), 1200)
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(ids, sorted(parts)[:len(ids)])        # the first ones, in id order: part-1, part-10, part-100 ...
        self.assertEqual(len(entries) + int(tail.group(1)), 150)
        self.assertGreater(int(tail.group(1)), 0)
        self.assertGreater(len(entries), 5)
        for entry in entries:
            self.assertLessEqual(len(entry.split(' - ', 1)[1]), 60)

    def test_a_small_project_lists_every_part_and_no_tail(self):
        make_project(self.dir, {f'p{i:02d}': doc(f'P{i}', f'Part {i}.') for i in range(30)})
        line = parts_line(context(self.dir))
        self.assertNotIn('more', line)
        self.assertEqual(line.count('; ') + 1, 30)

    def test_a_file_that_cannot_be_decoded_gives_the_old_note_alone(self):
        note = self.baseline()
        make_project(self.dir, {'render': doc('Render', 'Draws the world.')})
        with open(os.path.join(self.dir, 'sor', 'bad.md'), 'wb') as fh:
            fh.write(b'# Bad\n\xff\xfe\x00 not utf-8\n')
        self.assertEqual(context(self.dir), note)

    def test_a_file_that_cannot_be_opened_gives_the_old_note_alone(self):
        note = self.baseline()
        make_project(self.dir, {'render': doc('Render', 'Draws the world.')})
        path = write(self.dir, 'sor/locked.md', '# Locked\nWhy: nobody can read me.\n')
        os.chmod(path, 0)
        try:
            if os.access(path, os.R_OK):
                self.skipTest('this user can read files with no permission at all')
            self.assertEqual(context(self.dir), note)
        finally:
            os.chmod(path, 0o644)

    def test_a_folder_that_is_no_project_gets_no_note_at_all(self):
        empty = os.path.join(self.dir, 'nothing-here')
        os.makedirs(empty)
        self.assertIsNone(hook.session_start({'cwd': empty}))

    def test_the_result_keeps_the_shape_claude_code_reads(self):
        make_project(self.dir, {'render': doc('Render', 'Draws the world.')})
        out = hook.session_start({'cwd': self.dir})
        self.assertEqual(set(out), {'hookSpecificOutput'})
        self.assertEqual(set(out['hookSpecificOutput']), {'hookEventName', 'additionalContext'})
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertIsInstance(out['hookSpecificOutput']['additionalContext'], str)
        json.dumps(out, ensure_ascii=False)   # and it can be written out

    def test_a_session_started_in_a_subfolder_finds_the_project(self):
        make_project(self.dir, {'render': doc('Render', 'Draws the world.')})
        sub = os.path.join(self.dir, 'src', 'deep')
        os.makedirs(sub)
        self.assertIn('Parts: render - Draws the world.', context(sub))

    def test_the_command_line_prints_the_same_json(self):
        make_project(self.dir, {'render': doc('Render', 'Draws the world.')})
        code, out, err = run_hook('session-start', {'cwd': self.dir})
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out), hook.session_start({'cwd': self.dir}))

    def test_the_command_line_prints_nothing_outside_a_project(self):
        empty = os.path.join(self.dir, 'nothing-here')
        os.makedirs(empty)
        self.assertEqual(run_hook('session-start', {'cwd': empty}), (0, '', ''))


# --- G. the real projects, read only ------------------------------------------------------------------

REAL = ('examples/solar-system', 'editors/vscode')


def real_projects():
    found = [os.path.join(REPO, *rel.split('/')) for rel in REAL]
    projects = [p for p in found if os.path.isfile(os.path.join(p, 'sor', 'SPECOFRECORD.md'))]
    assert len(projects) == len(REAL), f'the real projects are not where the tests look: found {projects}'
    return projects


def legacy_text(item):
    """The text an item had before `open:` existed: its non-row lines, then its row names."""
    out = [t for _, t in item.lines if not Item._is_row(t)]
    if item.rows:
        out.append('rows: ' + ', '.join(item.rows))
    return '\n'.join(out)


class TestRealProjects(unittest.TestCase):
    """examples/solar-system and editors/vscode, read only. They are the owner's work in progress: nothing here
    asserts what their clauses say, only that the tool reads them cleanly and writes nothing."""

    def setUp(self):
        self.projects = real_projects()
        if not self.projects:
            self.skipTest('the real projects are not in this checkout')

    def test_check_prints_its_summary_line_in_the_format_the_tools_read(self):
        """Whether the owner's work in progress has problems is not the tool's business: only the format and the
        exit code's meaning (0 clean, 2 problems) are asserted, so this stays green while the specs are edited."""
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                code, out, err = run_process(path, 'check')
                self.assertIn(code, (0, 2), out + err)
                self.assertTrue(any(SUMMARY_ANY.match(line) for line in out.splitlines()), out)
                if code == 0:
                    self.assertTrue(any(SUMMARY.match(line) for line in out.splitlines()), out)

    def test_status_json_has_the_documented_keys(self):
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                code, out, err = run_process(path, 'status', '--json')
                self.assertIn(code, (0, 1, 2), err)   # 1 is work pending: the owner may be in the middle of a change
                data = json.loads(out)
                for key in ('locked', 'problems', 'findings', 'tests_not_passed', 'claims'):
                    self.assertIn(key, data)

    def test_the_json_views_parse_and_exit_zero(self):
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                for args in (('markers', '--json'), ('parts', '--json'), ('needs', '--json'), ('changes', '--json')):
                    code, out, err = run_process(path, *args)
                    self.assertEqual(code, 0, f'{args}: {out}{err}')
                    json.loads(out)

    def test_markers_show_and_the_text_views_run(self):
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                for args in (('markers',), ('show', 'ROOT'), ('parts',), ('needs',), ('changes',)):
                    code, out, err = run_sor(path, *args)
                    self.assertEqual(code, 0, f'{args}: {out}{err}')
                    self.assertTrue(out.strip(), args)

    def test_no_command_changes_a_file_in_clauses(self):
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                before = fingerprint(path)
                self.assertIn('sor-lock.json', before)
                for args in (('check',), ('check', '--strict'), ('status',), ('status', '--json'), ('markers',),
                             ('markers', '--json'), ('parts',), ('parts', '--json'), ('needs',), ('needs', '--json'),
                             ('changes',), ('changes', '--json'), ('show', 'ROOT')):
                    run_sor(path, *args)
                hook.session_start({'cwd': path})
                self.assertEqual(fingerprint(path), before)

    def test_session_start_lists_the_parts_of_every_real_project(self):
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                project = Project(path)
                ctx = context(path)
                self.assertLessEqual(len(parts_line(ctx)), 1200)
                for pid in sorted(p for p in project.parts if p)[:3]:
                    self.assertIn(pid, ctx)

    def test_the_text_of_every_existing_item_is_what_it_was_before_open_lines_existed(self):
        """Every item of the real projects without an `open:` question hashes as it did before `open:` existed.

        The text is its non-row lines, then its row names. An item the owner has given an `open:` line is
        skipped: its text is meant to differ, and TestOpenQuestions proves that case in a temporary project."""
        checked = 0
        for path in self.projects:
            with self.subTest(project=os.path.relpath(path, REPO)):
                project = Project(path)
                snap = lockfile.snapshot(project, Scan(project))
                for item in project.all_items():
                    if item.opens:
                        continue
                    self.assertEqual(item.text(), legacy_text(item), item.id)
                    self.assertEqual(snap[item.id]['text'], sha12(legacy_text(item)), item.id)
                    checked += 1
        self.assertGreater(checked, 20)


if __name__ == '__main__':
    unittest.main()
