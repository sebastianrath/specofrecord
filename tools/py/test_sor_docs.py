"""Tests that the documents agree with the tool and with each other.

    cd <repo> && python3 -m unittest discover -s tools/py -p 'test_*.py' -v

The ground truth, in this order: the code (`tools/py/sorlib`, asked directly), then SPEC.md, then the skill, then every
other document. A document may not contradict what comes before it. These tests read the repository's own files,
so they check shape and content, not wording:

  * every `sor` command, flag and `SOR_` variable a document names exists, and the flag belongs to that command;
  * every number a document gives for a limit equals the constant in the code, and the readability limits are
    stated once (SPEC §13 and the cheat sheet generated from SPEC), nowhere else;
  * the plugin has one name in its manifests, its install lines, its skill namespace and its folder;
  * a path a document names exists, and a section (§N) it cites exists;
  * the cheat sheet in the plugin is the one SPEC.md produces;
  * the workflow is written once, in the skill; CLAUDE.md imports it and AGENTS.md points to it.

Python 3.9, standard library only. Nothing is written.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from sorlib import claims, cli, hook, lint   # noqa: E402
from sorlib import lock as lockfile          # noqa: E402

SKILL_DIR = 'plugins/specofrecord/skills/specofrecord'
SKILL = SKILL_DIR + '/SKILL.md'
CHEAT = SKILL_DIR + '/reference/format-cheatsheet.md'
DOCS = {
    'AGENTS.md': 'AGENTS.md',
    'CLAUDE.md': 'CLAUDE.md',
    'README.md': 'README.md',
    'SKILL.md': SKILL,
    'format-cheatsheet.md': CHEAT,
    'new-project.md': SKILL_DIR + '/reference/new-project.md',
    'parallel-agents.md': SKILL_DIR + '/reference/parallel-agents.md',
    'plain-clauses.md': SKILL_DIR + '/reference/plain-clauses.md',
    'ci-evidence.md': SKILL_DIR + '/reference/ci-evidence.md',
    'plugin README.md': 'plugins/specofrecord/README.md',
    'SPEC.md': 'SPEC.md',
}
# programs other than `sor`, whose commands and flags appear in the same documents
OTHER_PROGRAMS = ('claude ', 'sh ', 'git ', 'python3 -m ', 'npm ', 'node ', 'cd ')
OTHER_FLAGS = {'--check', '--plugin-dir', '--repo'}   # sync-tools.sh, claude and gh, named on their own in prose
NOT_COMMANDS = {'init'}                     # "there is no `sor init`"


def read(rel):
    with open(os.path.join(REPO, *rel.split('/')), encoding='utf8') as fh:
        return fh.read()


def flat(text):
    """One line, single spaces: a sentence wrapped across lines is still one sentence."""
    return re.sub(r'\s+', ' ', text)


def spans(text):
    """(line, code) for every inline `code` span and every line of a fenced block."""
    out, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('```'):
            fenced = not fenced
        elif fenced:
            out.append((n, line.strip()))
        else:
            out += [(n, m) for m in re.findall(r'`([^`]+)`', line)]
    return out


def sor_commands():
    """{command: its flags}, from the tool's own parser."""
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {name: {o for act in p._actions for o in act.option_strings} | {'--help'} for name, p in sub.choices.items()}


class TestNamesInTheDocuments(unittest.TestCase):
    def test_every_command_and_flag_a_document_names_exists_and_belongs_together(self):
        commands = sor_commands()
        everything = set().union(*commands.values()) | {'-C'}
        call = re.compile(r'^(?:sor|python3? tools/(?:py/)?sor\.py)(?:\s+-C\s+\S+)?\s+([a-z][a-z-]*)\b')
        wrong = []
        for name, rel in DOCS.items():
            for n, span in spans(read(rel)):
                if span.startswith(OTHER_PROGRAMS):
                    continue
                flags = re.findall(r'(?<![\w-])(--[a-z][a-z-]*)', span)
                m = call.match(span)
                if m and m.group(1) not in NOT_COMMANDS:
                    cmd = m.group(1)
                    if cmd not in commands:
                        wrong.append(f'{name}:{n} `{span}`: no command `sor {cmd}`')
                    else:
                        wrong += [f'{name}:{n} `{span}`: `sor {cmd}` has no {f}' for f in flags if f not in commands[cmd]]
                else:
                    wrong += [f'{name}:{n} `{span}`: no flag {f} on any command' for f in flags
                              if f not in everything and f not in OTHER_FLAGS]
        self.assertEqual(wrong, [])

    def test_every_environment_variable_a_document_names_is_read_by_the_tool(self):
        source = ''
        # `test_sor.py` is here for SOR_COMPARE_JS, which makes the test suite compare the two tools (tools/js/README.md); no program reads it
        for path in glob.glob(os.path.join(HERE, 'sorlib', '*.py')) + [os.path.join(HERE, 'test_sor.py')]:
            with open(path, encoding='utf8') as fh:
                source += fh.read()
        known = set(re.findall(r'\bSOR_[A-Z_]+\b', source)) | {'SOR_' + n for n in re.findall(r"getenv\('([A-Z_]+)'\)", source)}
        self.assertGreaterEqual(len(known), 3)
        wrong = [f'{name}: {v}' for name, rel in DOCS.items() for v in sorted(set(re.findall(r'\bSOR_[A-Z_]+\b', read(rel))))
                 if v not in known]
        self.assertEqual(wrong, [])


class TestNumbersInTheDocuments(unittest.TestCase):
    LIMITS = {
        'items per section': (lint.LIMIT_ITEMS, r'at most (\d+) items|(\d+)-item cap'),
        'lines above the tests': (lint.LIMIT_SCREEN, r'(\d+) lines above|screen \((\d+) lines\)'),
        'lines per test': (lint.LIMIT_TEST_LINES, r'(\d+) lines per test|within (\d+) lines'),
        'words per item': (lint.LIMIT_WORDS, r'(\d+) words per item|within (\d+) words'),
        'child parts per part': (lint.LIMIT_CHILDREN, r'(\d+) child parts per part|at most (\d+) child parts'),
    }
    STATED = ('SPEC.md', 'format-cheatsheet.md')   # SPEC §13, and the cheat sheet generated from SPEC

    def numbers(self, doc, pattern):
        return [int(next(g for g in m.groups() if g)) for m in re.finditer(pattern, flat(read(DOCS[doc])), re.I)]

    def test_the_readability_limits_are_stated_in_spec_and_cheat_sheet_and_equal_the_code(self):
        for limit, (value, pattern) in self.LIMITS.items():
            for doc in self.STATED:
                found = self.numbers(doc, pattern)
                self.assertTrue(found, f'{doc} does not state the limit of {limit}')
                self.assertEqual(set(found), {value}, f'{doc}: {limit}')

    def test_no_other_document_repeats_the_limits(self):
        for limit, (_, pattern) in self.LIMITS.items():
            for doc in DOCS:
                if doc not in self.STATED:
                    self.assertEqual(self.numbers(doc, pattern), [], f'{doc} states the limit of {limit}: point to the cheat sheet')

    def test_no_source_file_states_a_limit_in_words(self):
        """The templates `sor new` writes must take the limit from the code, not repeat it."""
        wrong = []
        for path in glob.glob(os.path.join(HERE, 'sorlib', '*.py')):
            with open(path, encoding='utf8') as fh:
                text = flat(fh.read())
            for limit, (_, pattern) in self.LIMITS.items():
                if re.search(pattern, text, re.I):
                    wrong.append(f'{os.path.basename(path)} states the limit of {limit}')
        self.assertEqual(wrong, [])

    def test_the_times_and_sizes_spec_gives_are_the_ones_in_the_code(self):
        spec = flat(read('SPEC.md'))
        for what, value, pattern in (
                ('a claim lasts (minutes)', claims.DEFAULT_TTL // 60, r'default (\d+) minutes'),
                ('an expired claim is kept to tell its holder (hours)', claims.TOMBSTONE // 3600, r'kept for (\d+) hours'),
                ('a leftover mutex is broken after (seconds)', claims.STALE_LOCK, r'older than (\d+) s\b'),
                ('the parts index at session start (characters)', hook.INDEX_MAX, r'`Why:`, at most (\d+) characters'),
                ('the line about what is pending at session start (characters)', hook.PENDING_MAX, r'in a line of at most (\d+) characters')):
            found = [int(n) for n in re.findall(pattern, spec)]
            self.assertTrue(found, f'SPEC.md no longer says {what}')
            self.assertEqual(set(found), {value}, what)

    def test_the_lock_format_spec_gives_is_the_one_in_the_code(self):
        spec = flat(read('SPEC.md'))
        self.assertEqual({int(n) for n in re.findall(r'lock format described here is number (\d+)', spec)}, {lockfile.FORMAT})
        self.assertIn(f'`"{lockfile.FORMAT_KEY}": {lockfile.FORMAT}`', spec)

    def test_the_claim_lifetime_the_skill_documents_give_is_the_one_in_the_code(self):
        minutes = claims.DEFAULT_TTL // 60
        for doc, pattern in ((SKILL, r'It ends after (\d+) minutes without activity'),
                             (os.path.join(os.path.dirname(SKILL), 'reference', 'parallel-agents.md'),
                              r'Claims end after (\d+) minutes without activity|end after (\d+) min idle by default')):
            found = [int(n) for m in re.findall(pattern, flat(read(doc))) for n in (m if isinstance(m, tuple) else (m,)) if n]
            self.assertTrue(found, f'{doc} no longer says how long a claim lasts')
            self.assertEqual(set(found), {minutes}, doc)

    def test_the_skill_documents_say_who_sees_a_claim(self):
        # A skill that leaves this out sends an agent to a worktree to dodge collisions the claims already prevent. Where the claims file
        # is, and that a claim does not hold glue, are pinned in the claims tests (test_sor_claims.py, test_sor_flows.py).
        for doc in (SKILL, os.path.join(os.path.dirname(SKILL), 'reference', 'parallel-agents.md')):
            self.assertIn('do not see your claims; agents in the same folder see them', flat(read(doc)), doc)


class TestThePluginHasOneName(unittest.TestCase):
    def setUp(self):
        self.market = json.loads(read('.claude-plugin/marketplace.json'))
        self.entry = self.market['plugins'][0]
        self.folder = self.entry['source'].lstrip('./')
        self.plugin = json.loads(read(self.folder + '/.claude-plugin/plugin.json'))
        self.name, self.market_name = self.plugin['name'], self.market['name']

    def test_manifests_and_folder_agree(self):
        self.assertEqual(self.entry['name'], self.name)
        self.assertEqual(os.path.basename(self.folder), self.name)
        self.assertEqual(len(self.market['plugins']), 1)

    def test_every_install_line_names_the_plugin_and_the_marketplace(self):
        lines = 0
        for rel in ('plugins/specofrecord/README.md', 'index.html'):
            text = read(rel)
            if rel.endswith(('.htm', '.html')):
                text = re.sub(r'<[^>]+>', '', text)   # the commands are highlighted with <span>s: read the text
            for plugin, market in re.findall(r'/plugin install ([\w-]+)@([\w-]+)', text):
                lines += 1
                self.assertEqual((plugin, market), (self.name, self.market_name), rel)
            for repo in re.findall(r'/plugin marketplace add [\w.-]+/([\w-]+)', text):
                lines += 1
                self.assertEqual(repo, self.market_name, f'{rel}: the repository is named like the marketplace')
        self.assertGreaterEqual(lines, 3)

    def test_the_skill_namespace_and_the_folder_in_paths_use_the_same_name(self):
        for rel in ('tools/py/sorlib/hook.py', 'plugins/specofrecord/README.md'):
            found = re.findall(r'\b([a-z-]+):specofrecord\b', read(rel))
            self.assertTrue(found, rel)
            self.assertEqual(set(found), {self.name}, rel)
        for name, rel in DOCS.items():
            for folder in re.findall(r'plugins/([a-z-]+)/', read(rel)):
                self.assertEqual(folder, self.name, name)


class TestPathsAndSections(unittest.TestCase):
    def test_a_path_a_document_names_exists(self):
        repo_path = re.compile(r'^(?:tools|plugins|examples|editors|proposals|vectors)/[\w./-]+$')
        wrong = []
        for name, rel in DOCS.items():
            for n, span in spans(read(rel)):
                if repo_path.match(span):
                    target = span
                elif re.match(r'^reference/[\w.-]+\.md$', span):
                    target = SKILL_DIR + '/' + span
                elif span in ('SPEC.md', 'DECISIONS.md', 'AGENTS.md', 'CLAUDE.md'):
                    target = span
                else:
                    continue
                if not os.path.exists(os.path.join(REPO, *target.split('/'))):
                    wrong.append(f'{name}:{n} `{span}` does not exist')
        self.assertEqual(wrong, [])

    def test_a_section_a_document_cites_exists_in_spec(self):
        sections = {int(n) for n in re.findall(r'^## (\d+)\.', read('SPEC.md'), re.M)}
        self.assertEqual(sections, set(range(1, 17)))
        wrong = [f'{name}: §{n}' for name, rel in DOCS.items() for n in re.findall(r'§(\d+)', read(rel))
                 if int(n) not in sections]
        self.assertEqual(wrong, [])

    def test_the_cheat_sheet_in_the_plugin_is_the_one_spec_produces(self):
        """What sync-tools.sh generates: the lines of SPEC.md between '## Cheat sheet' and the next '---'."""
        lines = read('SPEC.md').splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith('## Cheat sheet'))
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == '---')
        body = '\n'.join(lines[start + 1:end])
        self.assertGreater(len(body), 2000)
        self.assertIn(body, read(CHEAT), 'run: sh plugins/sync-tools.sh')


class TestTheOldNameIsGone(unittest.TestCase):
    """The first name of the clauses (`fact`) is gone from code and live documents. Only git history keeps it."""
    OLD = re.compile(r'@fact\b|FACT_[A-Z]|\bfact[/.-]|FACT\.md|fact-lock|fact\.py|fact-coverage|factDir|\bfacts?-markdown|\.fact\b|runFact|openFact|(?-i:[a-z]Fact[A-Z]|\\bfact[A-Z])',
                     re.I)
    SCANNED = ('tools/py/sorlib', 'tools/py/sor.py', 'plugins/specofrecord', 'AGENTS.md', 'CLAUDE.md', 'SPEC.md', 'index.html',
               '.gitignore', 'editors/vscode/src', 'editors/vscode/sor', 'editors/vscode/test', 'editors/vscode/syntaxes',
               'editors/vscode/package.json', 'editors/vscode/README.md')

    def files(self):
        for entry in self.SCANNED:
            path = os.path.join(REPO, *entry.split('/'))
            if os.path.isfile(path):
                yield entry, path
            for dirpath, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ('node_modules', '__pycache__')]
                for name in names:
                    if name.endswith(('.py', '.md', '.json', '.js', '.sh', '.htm', '.html')) and not name.endswith('-lock.json'):
                        yield os.path.relpath(os.path.join(dirpath, name), REPO), os.path.join(dirpath, name)

    def test_every_scanned_path_exists(self):
        missing = [e for e in self.SCANNED if not os.path.exists(os.path.join(REPO, *e.split('/')))]
        self.assertEqual(missing, [], 'a path that is not there is scanned as nothing')

    def test_no_live_file_uses_the_old_name(self):
        found = []
        for rel, path in self.files():
            with open(path, encoding='utf8', errors='replace') as fh:
                for n, line in enumerate(fh, 1):
                    if self.OLD.search(line):
                        found.append(f'{rel}:{n}: {line.strip()[:100]}')
        self.assertEqual(found, [])


class TestTheWorkflowIsWrittenOnce(unittest.TestCase):
    """The workflow lives in the plugin's skill. CLAUDE.md imports it and AGENTS.md points to it; three copies had
    drifted within a day."""

    def test_claude_md_imports_the_skill_and_the_skill_exists(self):
        self.assertIn(f'\n@{SKILL}\n', read('CLAUDE.md'))
        self.assertTrue(os.path.isfile(os.path.join(REPO, SKILL)))

    def test_agents_md_points_to_the_skill(self):
        self.assertIn(f'`{SKILL}`', read('AGENTS.md'))

    def test_neither_file_carries_a_second_copy_of_the_command_table_or_the_steps(self):
        for name in ('CLAUDE.md', 'AGENTS.md'):
            text = read(name)
            self.assertNotIn('| Command | Does |', text, name)
            self.assertNotIn('A change asked in words', text, name)
            self.assertNotIn('When other agents work at the same time', text, name)

    def test_every_reference_file_is_linked_from_the_skill_and_every_link_exists(self):
        folder = os.path.join(REPO, *SKILL_DIR.split('/'), 'reference')
        files = {f for f in os.listdir(folder) if f.endswith('.md')}
        linked = set(re.findall(r'`reference/([\w.-]+\.md)`', read(SKILL)))
        self.assertEqual(files, linked, 'a reference file the skill does not link is never read; a link to nothing misleads')

    def test_the_skill_stays_a_short_overview(self):
        """Anthropic allows 500 lines; this skill keeps well under it (it was 148) so the everyday path stays readable."""
        lines = read(SKILL).splitlines()
        self.assertLess(len(lines), 130, 'move what applies only sometimes into a reference file')
        for name in ('new-project.md', 'parallel-agents.md', 'format-cheatsheet.md'):
            text = read(SKILL_DIR + '/reference/' + name)
            if len(text.splitlines()) > 100:
                self.assertIn('## Contents', text, f'{name} is over 100 lines: it needs a contents list')

    def test_the_skill_names_every_command_the_tool_has(self):
        skill = read(SKILL)
        missing = sorted(c for c in sor_commands() if c != 'hook' and f'sor {c}' not in skill)
        self.assertEqual(missing, [], 'commands the skill never mentions')

    # what the skill quotes from the tool's own output, as (the words in the skill, the words in the tool's source)
    QUOTED = (('Clauses come first', 'Clauses come first'),
              ('Someone else is working on this', 'Someone else is working on this'),
              ('Do not rewrite', 'Do not rewrite'),
              ('is written only by', 'is written only by'),
              ('REFUSED', 'REFUSED'),
              ('unnamed test', 'unnamed test'),
              ('loose text', 'loose text'),
              ('tests (N)', "tests ({"),   # the block `sor status` prints, with its count
              ('<fill in:', '<fill in:'))

    def test_the_output_the_skill_quotes_is_what_the_tool_prints(self):
        """A rename in the tool must not leave the skill telling the agent to look for words that no longer appear."""
        skill = flat(read(SKILL))
        source = ''.join(read('tools/py/sorlib/' + os.path.basename(f)) for f in sorted(glob.glob(os.path.join(REPO, 'tools', 'py', 'sorlib', '*.py'))))
        for in_skill, in_source in self.QUOTED:
            with self.subTest(quoted=in_skill):
                self.assertIn(in_skill, skill, 'the skill no longer quotes it: take it out of QUOTED')
                self.assertIn(in_source, source, 'the skill quotes words the tool no longer prints')

    def test_what_the_router_cues_on_is_explained_where_it_sends_the_agent(self):
        """The row for plain sentences names two things `sor check` says; the file it points to must cover both."""
        plain = flat(read(SKILL_DIR + '/reference/plain-clauses.md'))
        for cue in ('unnamed test', 'loose text'):
            with self.subTest(cue=cue):
                self.assertIn(f'`{cue}`', flat(read(SKILL)))
                self.assertIn(f'`{cue}`', plain, f'plain-clauses.md never mentions {cue}')


class TestTheLicenses(unittest.TestCase):
    """README.md says the spec is CC BY 4.0 and the toolset (tools, plugin, extension) is MIT."""

    def test_every_folder_the_readme_calls_mit_has_the_license_text_and_says_mit_in_its_manifest(self):
        for folder in ('tools', 'plugins/specofrecord', 'editors/vscode'):
            self.assertTrue(read(folder + '/LICENSE').startswith('MIT License'), folder)
        mit = read('LICENSE.md')
        for folder in ('tools', 'plugins/specofrecord', 'editors/vscode'):
            self.assertIn(read(folder + '/LICENSE').strip(), mit, folder + '/LICENSE is not the text in LICENSE.md')
        self.assertIn('CC BY 4.0', mit)
        self.assertIn('(LICENSE.md)', read('README.md'))
        self.assertEqual(json.loads(read('plugins/specofrecord/.claude-plugin/plugin.json')).get('license'), 'MIT')
        self.assertEqual(json.loads(read('editors/vscode/package.json')).get('license'), 'MIT')

    def test_the_plugin_readme_says_the_code_is_mit_and_never_that_no_license_is_chosen(self):
        readme = flat(read('plugins/specofrecord/README.md'))
        self.assertIn('The code in this plugin is MIT', readme)
        self.assertIn('CC BY 4.0', readme)
        self.assertNotIn('not been chosen', readme)


class TestNothingNamesTheOldLayout(unittest.TestCase):
    """The Python tool moved from tools/ to tools/py. A document, script or workflow of the repository that still names the old place sends a reader or a run
    to a path that is gone, or, in the dotted form `unittest tools.test_x`, to an import that fails. The plugin's own documents and the shipped copies keep
    the old layout on purpose (the plugin has no py level), so they are not listed. The command shown in a document is checked by TestNamesInTheDocuments,
    which accepts both forms; this is the test that tells them apart."""
    OLD = re.compile(r'tools/(?:sor\.py|sorlib|test_|coverage)|unittest tools\.|discover -s tools(?![/\w])')
    WORKFLOW_OLD = re.compile(r'unittest tools\.|discover -s tools(?![/\w])')   # the workflows also name the extension's copy, extension/tools/sorlib, on purpose
    FILES = ('CLAUDE.md', 'AGENTS.md', 'README.md', 'SPEC.md', 'LICENSE.md', 'index.html', 'vectors/README.md', 'vectors/make_hashing.py', 'tools/js/README.md',
             'examples/solar-system/design/README.md', '.claude/settings.json', '.claude/skills/run-specofrecord/SKILL.md', '.claude/skills/run-specofrecord/smoke.sh',
             '.coveragerc', '.gitignore', 'tools/py/coverage.sh', 'tools/py/coverage_site/sitecustomize.py')
    WORKFLOWS = ('.github/workflows/plugin.yml', '.github/workflows/vscode.yml')

    def test_no_document_script_or_workflow_names_the_old_places(self):
        found = []
        for files, pattern in ((self.FILES, self.OLD), (self.WORKFLOWS, self.WORKFLOW_OLD)):
            for rel in files:
                for number, line in enumerate(read(rel).split('\n'), 1):
                    found += [f'{rel}:{number} {m.group(0)}' for m in pattern.finditer(line)]
        self.assertEqual(found, [], 'the Python tool is in tools/py')

    def test_the_old_test_command_fails_and_says_where_the_tests_are(self):
        """`discover -s tools` finds no test in tools/py (it is no package), so without tools/test_sor_moved_to_py.py it would print `Ran 0 tests`, `OK`."""
        done = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py'], cwd=REPO, capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertNotEqual(done.returncode, 0, done.stderr)
        self.assertIn('discover -s tools/py', done.stderr)


if __name__ == '__main__':
    unittest.main()
