"""Reads a spec folder (sor/) into parts, items, table rows and values (SPEC §1-3), and resolves
{references} by looking outward from where they are written (SPEC §4)."""
import difflib
import glob
import os
import re

ITEM = re.compile(r'^- (?:(gives|owns|offers|provides|exports|stores) )?\*\*([^*]+)\*\*')
NEEDS = re.compile(r'^- (?:needs|uses|requires|depends on)\b')
CONTRACT_WORD = {'offers': 'gives', 'provides': 'gives', 'exports': 'gives', 'stores': 'owns'}
VDEF = re.compile(r'\{([A-Za-z][\w-]*):\s*([^{}]+)\}')
REF = re.compile(r'\{([^{}:\s][^{}:]*)\}')
BAD_VDEF = re.compile(r'\{[^{}\s]+:[^\s][^{}]*\}')
CODE = re.compile(r'`[^`]*`')
HEADER = re.compile(r'^(Why|Owner|Source|Run|Code|Design):\s*(.*)$')
SETTING = re.compile(r'(?:^|\.\s+|\s+·\s+)(Why|Owner|Source|Run|Code|Design):\s*')
SECTION = re.compile(r'^## (.+?)\s*$')
SECTIONS = ('Rules', 'Approach', 'Contract', 'Tests')
# Headings a person may write, and the section each one means (SPEC §15, the plain format). A heading the
# table does not know is read as rules.
SECTION_WORDS = {
    'Rules': ('rules', 'must', 'requirements', 'behaviour', 'behavior', 'what'),
    'Approach': ('approach', 'notes', 'how', 'how it works', 'design', 'why', 'decisions', 'ideas'),
    'Contract': ('contract', 'interface', 'api'),
    'Tests': ('tests', 'checks', 'examples', 'acceptance', 'proof'),
}


RESERVED_TARGETS = ('glue', 'test', 'ROOT')   # a target may not have a name that a lock key starts with

LINE_BREAK = re.compile(r'\r\n|\r|\n')


def split_lines(text):
    """The lines of a text, numbered the way an editor numbers them: a line ends at \\n, \\r\\n or \\r and nowhere else.
    `str.splitlines` also splits at a form feed, a vertical tab and the Unicode separators, which would give every
    line after one a number no editor shows."""
    lines = LINE_BREAK.split(text)
    if lines and not lines[-1]:
        lines.pop()
    return lines


def section_of(heading):
    h = heading.strip().lower()
    for canonical, words in SECTION_WORDS.items():
        if h in words:
            return canonical
    return 'Rules'


def unnamed(text):
    """The name of a bullet nobody named yet: stable while its words stay the same."""
    import hashlib
    return '~' + hashlib.sha1(' '.join(text.split()).encode('utf8')).hexdigest()[:6]
# The spec folder and the lock file of a project. A lock called clauses-lock.json, from before the rename, is still read
# and is replaced by sor-lock.json the next time the lock is written.
SPEC_DIR, LOCK_FILE, LEGACY_LOCK_FILE = 'sor', 'sor-lock.json', 'clauses-lock.json'
# The own file of every part is SPECOFRECORD.md: the root's is sor/SPECOFRECORD.md, a folder part's is sor/screen/SPECOFRECORD.md.
# CLAUSES.md is the older name of these files, still read. The root part has three names for the same thing:
#   ROOT          its id, in commands, output and as its key in the lock file (an older lock says CLAUSES: read as ROOT)
#   SPECOFRECORD  the name of its file (without .md)
#   CLAUSES       its older file name and key
ROOT, PART_FILE_NAME, LEGACY_FILE_NAME = 'ROOT', 'SPECOFRECORD', 'CLAUSES'
ROOT_FILE_NAME = PART_FILE_NAME
FOLDER_FILE_NAME = PART_FILE_NAME
LEGACY_ROOT_KEY = LEGACY_FILE_NAME
ROOT_ALIASES = frozenset({ROOT, PART_FILE_NAME, LEGACY_FILE_NAME})   # what `sor claim X`, `sor lock X` and `sor show X` take for the root


def part_files(folder):
    """The own files of a part that exist in a folder: SPECOFRECORD.md, and the older CLAUSES.md."""
    return [os.path.join(folder, n + '.md') for n in (PART_FILE_NAME, LEGACY_FILE_NAME)
            if os.path.isfile(os.path.join(folder, n + '.md'))]


def root_files(spec_dir):
    """The root files that exist in a spec folder: sor/SPECOFRECORD.md, and the older sor/CLAUSES.md."""
    return part_files(spec_dir)


def has_spec(project_root):
    """Whether this folder holds a project: sor/SPECOFRECORD.md (or the older sor/CLAUSES.md)."""
    return bool(root_files(os.path.join(project_root, SPEC_DIR)))


ANCHOR = re.compile(r'^\s+code:\s*(\S+)\s*$')   # an item's code anchor, see anchors.py
OPEN = re.compile(r'^\s+open:\s*(.*?)\s*$', re.I)   # an open question about an item; not part of its text


# Words a test line may start with, and the keyword each one means (SPEC §15, the plain format).
TEST_WORDS = {'each': 'each', 'do': 'do', 'given': 'do', 'when': 'do', 'expect': 'expect',
              'then': 'expect', 'should': 'expect', 'shows': 'expect', 'measure': 'measure',
              'manual': 'manual', 'by eye': 'manual', 'by hand': 'manual', 'sign-off': 'manual',
              'bug': 'bug', 'fixes': 'bug', 'regression': 'bug', 'proves': 'proves', 'runs on': 'runs_on'}
TEST_LINE = re.compile(r'^\s+(' + '|'.join(sorted(TEST_WORDS, key=len, reverse=True)) + r'):\s*(.*)$', re.I)


def test_keyword(line):
    """(keyword, rest) for an indented test line such as `  then: zoom = 6x`, else None."""
    m = TEST_LINE.match(line)
    return (TEST_WORDS[m.group(1).lower()], m.group(2).strip()) if m else None


ENV_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]*$')   # what an environment is called: also safe to use in a file name


def parse_runs_on(text):
    """([tuple of names], error) for the words after `runs on:`, in the order they were written. A comma separates the
    environments a test must pass in, a plus joins the names one machine must provide together: `windows, macos,
    linux+db` is three environments, the last one on a machine that has both `linux` and `db`. Names are lowercase
    letters, digits, dots, dashes and underscores. The error is None, or says what is wrong."""
    if not text.strip():
        return [], 'name the environments after `runs on:`, for example `runs on: linux, windows`'
    out = []
    for entry in text.split(','):
        names = [n.strip().lower() for n in entry.split('+')]
        bad = [n for n in names if not ENV_NAME.match(n)]
        if bad:
            return [], (f'"{bad[0]}" is not an environment name: use lowercase letters, digits, dots, dashes and '
                        'underscores, with a comma between environments and a plus between names one machine must have')
        env = tuple(dict.fromkeys(names))
        if frozenset(env) not in [frozenset(e) for e in out]:
            out.append(env)
    return out, None


def join(pid, name):
    return f'{pid}/{name}' if pid else name


def listed(names, shown=10):
    """The first `shown` names, then "and N more": a long list in a sentence."""
    names = list(names)
    return ', '.join(names[:shown]) + (f' and {len(names) - shown} more' if len(names) > shown else '')


class Problem:
    def __init__(self, kind, where, text):
        self.kind, self.where, self.text = kind, where, text

    def __str__(self):
        return f'{self.kind:>10}  {self.where}  {self.text}'


class Row:
    def __init__(self, item, name, text, values):
        self.id = f'{item.id}/{name}'
        self.name, self.text, self.values = name, text, values


class Item:
    def __init__(self, part, name, section, kind, lineno):
        self.part, self.name, self.section, self.kind = part, name, section, kind
        self.id = join(part.id, name)
        self.file = part.rel   # the file its line numbers belong to: a test in <part>.tests.md is not in the part's own file
        self.lineno = lineno
        self.lines = []        # (lineno, text) of the bullet and its continuation lines
        self.bullets = dict.fromkeys(SECTIONS, 0)   # `- ` lines written for it, per section: a name used twice gathers both
        self.values = {}       # name -> text
        self.rows = {}         # first cell -> Row
        self.refs = []         # (lineno, reference text)
        self.anchors = []      # (lineno, 'path#name'): the code this item is about
        self.opens = []        # (lineno, question): `open:` lines; they stay out of text() and the lock
        self.open_lines = set()  # every line number that belongs to a question (it may wrap onto deeper-indented lines)
        self.draft = False     # a bullet nobody has named yet (its name starts with ~)

    @property
    def is_test(self):
        return self.kind == 'test'

    @property
    def target_name(self):
        """The item a test proves (its name without `test:`)."""
        return self.name[5:] if self.is_test else self.name

    def steps(self):
        """[(keyword, text)] of the keyword lines under the bullet; a line that wraps belongs to the keyword above it.
        `open:` questions are no part of it."""
        out = []
        for n, t in self.lines[1:]:
            if n in self.open_lines:
                continue
            kw = test_keyword(t)
            if kw:
                out.append(kw)
            elif out and t.strip():
                k, v = out[-1]
                out[-1] = (k, v + ' ' + t.strip())
        return out

    def runs_on(self):
        """The environments a test must pass in, one tuple of names for each, as written ([] for a test that runs anywhere).
        A test with any is deferred: a local run and a lock leave it to the jobs that provide those names."""
        if not self.is_test:
            return []
        out = []
        for k, v in self.steps():
            if k == 'runs_on':
                out += [e for e in parse_runs_on(v)[0] if frozenset(e) not in [frozenset(x) for x in out]]
        return out

    def text(self):
        """The item's own text: table rows are items of their own, so only their names count
        here (adding or removing a row changes the item, editing one does not). `open:` lines are
        left out: a question about an item is not a change to it."""
        lines = self.lines
        if self.open_lines:
            lines = [(n, t) for n, t in lines if n not in self.open_lines]
            while lines and not lines[-1][1].strip():
                lines.pop()
        out = [t for n, t in lines if not self._is_row(t)]
        if self.rows:
            out.append('rows: ' + ', '.join(self.rows))
        return '\n'.join(out)

    @staticmethod
    def _is_row(t):
        t = t.strip()
        return t.startswith('|') and not re.match(r'^\|[\s:|-]+\|$', t) and t != ''

    def finish(self):
        while self.lines and not self.lines[-1][1].strip():
            self.lines.pop()
        header = None
        asking = None   # the indent of the `open:` line whose question is still wrapping onto deeper lines
        for n, t in self.lines:
            clean = CODE.sub('', t)
            s = t.strip()
            if s.startswith('|'):
                asking = None
                if re.match(r'^\|[\s:|-]+\|$', s):
                    continue
                self.refs += [(n, ref.strip()) for ref in REF.findall(clean)]   # a cell refers like any other text: `{x}` and `{v: = x}`
                self.refs += [(n, val.strip()[1:].strip()) for _, val in VDEF.findall(clean) if val.strip().startswith('=')]
                cells = [c.strip() for c in s.strip('|').split('|')]
                if header is None:
                    header = [c.lower() for c in cells]
                    self.lines[self.lines.index((n, t))] = (n, '  ' + s)  # header is item text
                else:
                    vals = dict(zip(header[1:], cells[1:]))
                    self.rows[cells[0]] = Row(self, cells[0], s, vals)
                continue
            asked = None if self.is_test else OPEN.match(t)
            if asked:
                self.opens.append((n, asked.group(1)))
                self.open_lines.add(n)
                asking = len(t) - len(t.lstrip())
                continue
            if asking is not None and s and len(t) - len(t.lstrip()) > asking:
                n0, question = self.opens[-1]   # a wrapped question: deeper-indented lines right after it
                self.opens[-1] = (n0, (question + ' ' + s).strip())
                self.open_lines.add(n)
                continue
            asking = None
            anchor = ANCHOR.match(t)
            if anchor and not self.is_test:
                self.anchors.append((n, anchor.group(1)))
                continue
            for name, val in VDEF.findall(clean):
                self.values[name] = val.strip()
                if val.strip().startswith('='):
                    self.refs.append((n, val.strip()[1:].strip()))
            for ref in REF.findall(clean):
                self.refs.append((n, ref.strip()))
            for bad in BAD_VDEF.findall(clean):
                self.part.problems.append(Problem(
                    'malformed', f'{self.part.rel}:{n}', f'{bad}  (a value needs a space after the colon)'))


class Part:
    def __init__(self, pid, path, rel, root_key=ROOT):
        self.id, self.path, self.rel = pid, path, rel
        self.loose = []        # (file, lineno, section, text): text in a section that belongs to no item
        self.key = pid or root_key
        self.title = ''
        self.header = {}
        self.items = {}
        self.problems = []
        self.headings = {}     # section name -> line of its first `## ` heading
        self.nlines = 0        # lines in the file

    @property
    def source_code(self):
        """The folder or file a part's hand-written code lives in (`Source: code at <path>`, or
        `Code: <path> (by hand)`), or None."""
        m = re.match(r'code at\s+(\S+)', self.header.get('Source', ''))
        if not m:
            m = re.match(r'(\S+)\s*\(by hand\)', self.header.get('Code', ''))
        return m.group(1).rstrip('/') if m else None

    def face(self):
        """What other parts see when they refer to the whole part: its header and Contract."""
        out = [self.title] + [f'{k}: {v}' for k, v in sorted(self.header.items())]
        out += [i.text() for i in self.items.values() if i.section == 'Contract']
        return '\n'.join(out)


def part_id(root, f):
    rel = os.path.relpath(f, root)[:-3].replace(os.sep, '/')
    base, folder = os.path.basename(rel), os.path.dirname(rel)
    if base in (PART_FILE_NAME, LEGACY_FILE_NAME):   # a folder's own file (at the top: the root's)
        return folder
    return rel


def file_rank(path, spec_dir):
    """Which of two files claiming one part counts: `<id>.md` first, then a folder's `SPECOFRECORD.md`, then the older `CLAUSES.md`."""
    base = os.path.basename(path)
    if base == LEGACY_FILE_NAME + '.md':
        return 2
    if base == PART_FILE_NAME + '.md':
        return 0 if os.path.abspath(os.path.dirname(path)) == os.path.abspath(spec_dir) else 1
    return 0


def parse_part(root, path):
    rel = os.path.relpath(path, root).replace(os.sep, '/')
    part = Part(part_id(root, path), path, rel, ROOT)
    section, cur = None, None
    with open(path, encoding='utf8') as fh:
        lines = split_lines(fh.read())
    part.nlines = len(lines)
    fenced = commented = False   # inside a ``` block or an HTML comment: text there is not loose
    written = {}                 # heading words -> line of the first `## ` heading that used them
    for n, raw in enumerate(lines, 1):
        line = raw.rstrip()
        marked = fenced or commented
        if line.strip().startswith('```'):
            fenced = not fenced
            marked = True
        elif commented:
            commented = '-->' not in line
        elif line.strip().startswith('<!--'):
            commented = '-->' not in line
            marked = True
        h = SECTION.match(line)
        if h:
            section, cur = section_of(h.group(1)), None
            part.headings.setdefault(section, n)
            said = ' '.join(h.group(1).lower().split())
            if said in written and not marked:   # merged into the first one without a word (a heading in an example does not count)
                part.problems.append(Problem(
                    'heading', f'{rel}:{n}', f'`## {h.group(1)}` is written twice (lines {written[said]} and {n}): '
                                             'there is one such section, so put the bullets under the first heading'))
            elif not marked:
                written[said] = n
            continue
        if section is None and not line.startswith('- '):
            # the header: the title, settings, and the first sentence, which says why
            if line.startswith('# ') and not part.title:
                part.title = line[2:].strip()
            elif SETTING.search(line) and SETTING.match(line):
                pieces = SETTING.split(line)
                for k, v in zip(pieces[1::2], pieces[2::2]):
                    part.header[k] = v.strip()
            elif line.strip() and part.title and 'Why' not in part.header:
                part.header['Why'] = line.strip()
            elif line.strip().startswith('|') and cur is not None:
                cur.lines.append((n, line))   # a table right under a bullet belongs to it
            elif line.strip() and not marked and not line.startswith('#') and not re.fullmatch(r'[-*_=\s]+', line):
                part.loose.append((rel, n, None, line.strip()))   # more prose under the title: nobody reads it
            continue
        if section is None:
            section = 'Rules'   # bullets right under the title are rules
        if line.startswith('- '):
            m = ITEM.match(line)
            if m:
                name = m.group(2).strip()
                word = CONTRACT_WORD.get(m.group(1), m.group(1))
                kind = 'test' if section == 'Tests' else (word or section.lower())
                if section == 'Tests':
                    name = 'test:' + name
                if name in part.items:
                    first = part.items[name]
                    where = f'line {first.lineno}' + (f', in {first.section}' if first.section != section else '')
                    part.problems.append(Problem('duplicate', f'{rel}:{n}',
                                                 f'**{m.group(2)}** is named twice (the first is at {where}): rename one of them'))
                cur = part.items.setdefault(name, Item(part, name, section, kind, n))
            elif NEEDS.match(line) and section == 'Contract':
                cur = part.items.setdefault('needs', Item(part, 'needs', section, 'needs', n))
            else:
                # not named yet: a draft until tidy names it; its key follows its words
                name = unnamed(line[2:])
                if section == 'Tests':
                    name = 'test:' + name
                kind = 'test' if section == 'Tests' else section.lower()
                cur = part.items.setdefault(name, Item(part, name, section, kind, n))
                cur.draft = True
            cur.lines.append((n, line))
            cur.bullets[section] += 1
        elif cur is not None and (line == '' or line[0] in ' \t|'):
            cur.lines.append((n, line))
        elif line:
            if not marked and not line.startswith('#') and not re.fullmatch(r'[-*_=\s]+', line):
                part.loose.append((rel, n, section, line.strip()))
            cur = None
    if 'Why' not in part.header:
        part.problems.append(Problem('header', rel, 'the `Why:` line is missing'))
    for item in part.items.values():
        item.finish()
    return part


class Project:
    def __init__(self, root):
        """root: a project folder (holding sor/) or the spec folder itself."""
        root = os.path.abspath(root)
        if has_spec(root):   # a project folder; otherwise -C names the spec folder itself (a folder called `sor` may be either)
            root = os.path.join(root, SPEC_DIR)
        found = root_files(root)
        if not found:
            raise SystemExit(f'no {SPEC_DIR}/{ROOT_FILE_NAME}.md under {root}')
        if len(found) > 1:
            raise SystemExit(f'both {SPEC_DIR}/{PART_FILE_NAME}.md and {SPEC_DIR}/{LEGACY_FILE_NAME}.md exist under {root}: '
                             f'the root file is {PART_FILE_NAME}.md, so keep that one (merge {LEGACY_FILE_NAME}.md into it)')
        self.spec_dir = root
        self._proved_by = None   # item id -> ids of the tests that prove it, built on first use (with _named_after_nothing)
        self._known = None       # every id a reference can name, built on first use (for the "did you mean" of a broken one)
        self._by_tail = None     # the same ids by their last word, built with the first suggestion
        self.spec_name, self.root_key, self.lock_file = SPEC_DIR, ROOT, LOCK_FILE
        self.root = os.path.dirname(root)
        files = sorted(f for f in glob.glob(os.path.join(root, '**', '*.md'), recursive=True)
                       if not f.endswith('.tests.md'))
        # One file per part. A part is `<id>.md`; the root is SPECOFRECORD.md; the own file of a folder (`<id>/SPECOFRECORD.md`, or
        # the older `<id>/CLAUSES.md`) is still read. When two files claim one part, the first of those counts and the
        # others are a problem, named, instead of silently replacing each other.
        found = {}
        for f in files:
            p = parse_part(root, f)
            found.setdefault(p.id, []).append((file_rank(f, root), p))
        self.parts = {}
        for pid, claimants in found.items():
            claimants.sort(key=lambda c: c[0])
            keep = claimants[0][1]
            for _, other in claimants[1:]:
                keep.problems.append(Problem('layout', keep.rel, f'{other.rel} claims the same part `{pid or ROOT}` as {keep.rel}: '
                                             'keep one of the two files and merge the other into it'))
            self.parts[pid] = keep
        for f in sorted(glob.glob(os.path.join(root, '**', '*.tests.md'), recursive=True)):
            self._merge_tests(root, f)
        self._design()
        self.items = {}   # every item, row and value by id -> object
        for p in self.parts.values():
            for it in p.items.values():
                self.items[it.id] = it
                for r in it.rows.values():
                    self.items[r.id] = r

    def _design(self):
        """`Design: design/tokens.json` under the root title: the exported design becomes the part
        `design`. Each token group is an item and each token a row with a `value`
        (`{design/planet/mars}`, `{design/planet/mars.value}`); the SVG files in an `assets/` folder
        next to it are rows of the item `assets`. Changing the export changes these rows, so the
        clauses and code that refer to them are flagged like any other clause change."""
        import hashlib
        import json
        root_part = self.parts.get('')
        m = re.search(r'(\S+\.json)', (root_part.header.get('Design', '') if root_part else ''))
        if not m:
            return
        rel = m.group(1)
        path = os.path.join(self.root, rel)
        part = Part('design', path, rel)
        part.title = 'Design'
        part.header['Why'] = 'colors and pictures exported from the design file'
        self.parts['design'] = part
        try:
            with open(path, encoding='utf8') as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            root_part.problems.append(Problem('design', rel, f'cannot read the design export: {e}'))
            return

        def item(name):
            it = Item(part, name, 'Contract', 'design', 0)   # not a promise: it is not counted as a rule
            it.lines = [(0, f'- **{name}** — from {rel}')]
            part.items[name] = it
            return it

        for group, tokens in data.items():
            if group.startswith('$') or not isinstance(tokens, dict):
                continue
            it = item(group)
            for name, tok in tokens.items():
                if isinstance(tok, dict) and '$value' in tok:
                    value = str(tok['$value'])
                    it.rows[name] = Row(it, name, f'| {name} | {value} |', {'value': value})
        assets = os.path.join(os.path.dirname(path), 'assets')
        if os.path.isdir(assets):
            it = item('assets')
            for f in sorted(glob.glob(os.path.join(assets, '*.svg'))):
                name = os.path.splitext(os.path.basename(f))[0]
                with open(f, 'rb') as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()[:12]
                file_rel = os.path.relpath(f, self.root).replace(os.sep, '/')
                it.rows[name] = Row(it, name, f'| {name} | {file_rel} | {digest} |', {'file': file_rel})

    def _merge_tests(self, root, f):
        """`<part>.tests.md` holds more tests of the part (SPEC §13). A problem in it is reported in it, and
        what cannot be merged is a problem: a test named in both files (the first one counts), tests for a part
        that does not exist, anything but tests."""
        extra = parse_part(root, f)
        pid = part_id(root, f[:-9] + '.md')
        home = self.parts.get(pid)
        if home is None:
            if '' in self.parts:
                self.parts[''].problems.append(Problem(
                    'tests file', extra.rel, f'no part {pid or ROOT} for these tests: rename the file or add the part'))
            return
        home.problems += [p for p in extra.problems if p.kind != 'header']   # a tests file has no header, by design
        home.loose += extra.loose
        for k, it in extra.items.items():
            if not it.is_test:
                home.problems.append(Problem('misplaced', f'{extra.rel}:{it.lineno}',
                                             f'**{it.name}** is not a test: {extra.rel} holds only tests'))
            elif k in home.items:
                home.problems.append(Problem('duplicate', f'{extra.rel}:{it.lineno}',
                                             f'**{it.name[5:]}** is already a test in {home.rel} (line {home.items[k].lineno})'))
            else:
                it.part = home
                it.id = join(pid, it.name)
                home.items[k] = it

    @property
    def lock_path(self):
        return os.path.join(self.spec_dir, self.lock_file)

    @property
    def legacy_lock_path(self):
        return os.path.join(self.spec_dir, LEGACY_LOCK_FILE)

    def all_items(self):
        for p in self.parts.values():
            yield from p.items.values()

    def find(self, ident):
        """An id as written in a marker or on the command line → (kind, object) or None."""
        if ident in self.parts:
            return 'part', self.parts[ident]
        if ident in ROOT_ALIASES:   # the root part, under any of its names
            return 'part', self.parts['']
        if ident in self.items:
            o = self.items[ident]
            return ('row' if isinstance(o, Row) else 'item'), o
        return None

    # --- references (SPEC §4) ---------------------------------------------------------------
    def _in_part(self, pid, rest):
        """rest is `name`, `name.value`, `name/Row` or `name/Row.value` inside part pid."""
        path, _, val = rest.partition('.')
        segs = path.split('/')
        part = self.parts[pid]
        item = part.items.get(segs[0])
        if item is None:
            return None
        if len(segs) > 2:
            return None
        if len(segs) == 2:
            row = item.rows.get(segs[1])
            if row is None or (val and val not in row.values):
                return None
            return f'{row.id}.{val}' if val else row.id
        if val and val not in item.values:
            return None
        return f'{item.id}.{val}' if val else item.id

    def resolve(self, pid, ref):
        """All ids `ref`, written in part `pid`, can mean. Exactly one is a valid reference."""
        levels, p = [], pid
        while True:
            levels.append(p)
            if p == '':
                break
            p = os.path.dirname(p)
        path, _, val = ref.partition('.')
        segs = path.split('/')
        hits = []
        for level in levels:
            if level in self.parts:
                hit = self._in_part(level, ref)
                if hit:
                    hits.append(hit)
            for k in range(len(segs), 0, -1):
                sub = '/'.join(([level] if level else []) + segs[:k])
                if sub in self.parts and sub != level:
                    rest = '/'.join(segs[k:])
                    if rest:
                        hit = self._in_part(sub, rest + ('.' + val if val else ''))
                    elif val:
                        hit = None  # a part has no values of its own
                    else:
                        hit = sub
                    if hit:
                        hits.append(hit)
                    break
        return sorted(set(hits))

    def known_ids(self):
        """Every id a reference can name: parts, items, table rows and `item.value`s. Tests, `needs` lines and drafts
        are named by nothing."""
        if self._known is None:
            ids = {pid for pid in self.parts if pid}
            for it in self.all_items():
                if it.is_test or it.kind == 'needs' or it.draft:
                    continue
                ids.add(it.id)
                ids.update(f'{it.id}.{v}' for v in it.values)
                for row in it.rows.values():
                    ids.add(row.id)
                    ids.update(f'{row.id}.{v}' for v in row.values)
            self._known = sorted(ids)
        return self._known

    def suggest(self, pid, ref, limit=3):
        """Ids that a reference which resolves to nothing may have meant, nearest first: those that end in the same word
        (`core/spawn` → `core/ecs/spawn`), and when there are none, those that end in a word spelled almost like its last
        one. Only an id that `resolve` finds again from part pid."""
        if self._by_tail is None:
            self._by_tail = {}
            for i in self.known_ids():
                self._by_tail.setdefault(i.rpartition('/')[2], []).append(i)
        tail = ref.rpartition('/')[2]
        same = tail in self._by_tail
        out = []
        for word in [tail] if same else difflib.get_close_matches(tail, self._by_tail, n=limit, cutoff=0.6):
            # the ids that start like the reference first, the shorter first; of a word spelled differently, the best id only
            for i in sorted(self._by_tail[word], key=lambda i: (-len(os.path.commonprefix([ref, i])), len(i), i)):
                if self.resolve(pid, i) == [i]:
                    out.append(i)
                    if not same or len(out) == limit:
                        break
        return out

    def explain_broken(self, pid, ref):
        """What `sor check` says of a reference that names nothing: what was found on the way, and the nearest valid ids."""
        path, _, val = ref.partition('.')
        owner = self.resolve(pid, path) if val else []
        if len(owner) == 1:   # `hello.text`: hello is there, the value is not
            names = sorted(getattr(self.items.get(owner[0]), 'values', {}))
            return f'{{{ref}}} names no value: `{owner[0]}` has ' + (f'the values {", ".join(names)}' if names else 'no values')
        segs, found, p = path.split('/'), '', pid
        while not found:   # the longest leading run of words that names a part, looking outward as `resolve` does
            for k in range(len(segs) - 1, 0, -1):
                sub = '/'.join(([p] if p else []) + segs[:k])
                if sub in self.parts:
                    found = f' (the part `{sub}` exists but has no item `{"/".join(segs[k:])}`)'
                    break
            if p == '':
                break
            p = os.path.dirname(p)
        near = ['{' + i + '}' for i in self.suggest(pid, ref)]
        said = (', '.join(near[:-1]) + (' or ' if len(near) > 1 else '') + near[-1]) if near else ''
        return f'{{{ref}}} names no item, row, value or part{found}' + (f'; did you mean {said}?' if said else '')

    def resolved_refs(self, item, explain=False):
        """{target id} for an item's references that resolve; problems for those that don't. explain: the text of a
        broken one says what was found and what was probably meant. That takes time, so `check` asks for it and the
        lock and the hooks do not."""
        out, problems = set(), []
        for n, ref in item.refs:
            hits = self.resolve(item.part.id, ref)
            if len(hits) == 1:
                out.add(hits[0])
            else:
                problems.append(self.unresolved(item, n, ref, hits, explain))
        return out, problems

    def unresolved(self, item, n, ref, hits, explain=False):
        """The problem for a reference that does not find exactly one id: `hits` are the ids it finds."""
        if hits:
            return Problem(f'ambiguous {hits}', f'{item.file}:{n}',
                           f'{{{ref}}} could mean ' + ' or '.join('{' + h + '}' for h in hits)
                           + ': write the whole id of the one you mean')
        return Problem('broken', f'{item.file}:{n}', self.explain_broken(item.part.id, ref) if explain else '{' + ref + '}')

    def has_web_target(self):
        """Whether `sor test` has a page to run in: a `targets/` part whose Rules give a `path` ending in .html (the
        condition testrun.web_targets reads). Without one no test runs, but a `manual:` one or one in the project's
        own framework."""
        return any(p.id.startswith('targets/') and any(it.section == 'Rules' and it.values.get('path', '').endswith('.html')
                                                      for it in p.items.values())
                   for p in self.parts.values())

    def proof_links(self, test):
        """[(item id, how)]: what a test proves (SPEC §8). `how` is 'name' (the test is named after the item), 'refers'
        (an `expect:` or `measure:` line refers to the item, to one of its values or to one of its rows) or 'says' (a
        `proves:` line names it). References in `do:` and `each:` lines are inputs and prove nothing."""
        out = []
        target = test.part.items.get(test.target_name)
        if target is not None and not target.is_test:
            out.append((target.id, 'name'))
        word, words = None, {}
        for n, t in test.lines[1:]:
            kw = test_keyword(t)
            if kw:
                word = kw[0]
            words[n] = word   # a wrapped line belongs to the keyword above it
        for n, ref in test.refs:
            word = words.get(n)
            if word not in ('expect', 'measure', 'proves'):
                continue
            hits = self.resolve(test.part.id, ref)
            if len(hits) != 1:
                continue
            owner = hits[0]
            if owner not in self.items and '.' in owner:
                owner = owner.rpartition('.')[0]
            if isinstance(self.items.get(owner), Row):
                owner = owner.rsplit('/', 1)[0]
            o = self.items.get(owner)
            if isinstance(o, Item) and not o.is_test:
                out.append((owner, 'says' if word == 'proves' else 'refers'))
        return out

    def proves(self, test):
        """Ids of the items a test proves."""
        return {i for i, _ in self.proof_links(test)}

    def tests_of(self, item_id, regressions_only=False):
        """Ids (lock keys) of the tests that prove an item: the test named after it, then every other test that
        proves it by a reference in its `expect:` or `measure:` lines or by a `proves:` line. A bug fix may add such
        a test without touching the first. regressions_only: only the test named after the item, the tests named
        after nothing (split and bug tests, SPEC §8) and the tests that say `proves:` for it, not a test of another
        item that merely refers to it in passing."""
        if self._proved_by is None:
            self._proved_by, self._named_after_nothing, self._declared = {}, set(), {}
            for t in self.all_items():
                if t.is_test:
                    if t.part.items.get(t.target_name) is None:
                        self._named_after_nothing.add(t.id)
                    for i, how in self.proof_links(t):
                        if t.id not in self._proved_by.setdefault(i, []):
                            self._proved_by[i].append(t.id)
                        if how == 'says':
                            self._declared.setdefault(i, set()).add(t.id)
        own = join(item_id.rpartition('/')[0], 'test:' + item_id.rpartition('/')[2])
        others = [t for t in self._proved_by.get(item_id, []) if t != own]
        if regressions_only:
            others = [t for t in others if t in self._named_after_nothing or t in self._declared.get(item_id, ())]
        return [own] + others

    def check_test_lines(self, item):
        """Problems with the lines that say what a test proves (SPEC §8): a test named after nothing needs a `proves:`
        or `bug:` line, a `proves:` line names a clause, and `expect: {ref}` alone compares nothing."""
        out = []
        for n, t in item.lines[1:]:
            kw = test_keyword(t)
            where = f'{item.file}:{n}'
            if kw and kw[0] == 'proves':
                if not item.is_test:
                    out.append(Problem('proves', where, 'only a test proves something: put `proves:` in the Tests section'))
                    continue
                refs = REF.findall(CODE.sub('', t))
                if not refs:
                    out.append(Problem('proves', where, f'write what it proves as a reference: `proves: {{{item.target_name}}}`'))
                for ref in refs:
                    hits = self.resolve(item.part.id, ref.strip())
                    if len(hits) != 1:
                        continue   # broken or ambiguous: reported as a reference
                    o = self.items.get(hits[0])
                    if isinstance(o, Row):
                        o = self.items.get(hits[0].rsplit('/', 1)[0])
                    if o is None:
                        what = 'a part' if hits[0] in self.parts else 'a value'
                        out.append(Problem('proves', where, f'{{{ref}}} is {what}: name the clause that holds it'))
                    elif o.is_test or o.kind == 'needs':
                        out.append(Problem('proves', where, f'{{{ref}}} is not a clause a test can prove'))
            elif item.is_test and kw and kw[0] == 'expect' and re.fullmatch(r'\{[^{}]+\}', kw[1]):
                out.append(Problem('expect', where, f'`expect: {kw[1]}` compares nothing, so `sor test` cannot run it: '
                                                    f'say what the test proves with `proves: {kw[1]}` and add an expect that compares'))
        if item.is_test:
            first = next((n for n, t in item.lines[1:] if (test_keyword(t) or ('',))[0] == 'runs_on'), None)
            if first is not None:
                where = f'{item.file}:{first}'
                steps = item.steps()
                out += [Problem('runs on', where, err) for k, v in steps if k == 'runs_on'
                        for err in [parse_runs_on(v)[1]] if err]
                if any(k == 'manual' for k, _ in steps):
                    out.append(Problem('runs on', where, 'a manual test is never run by the tool, so it has no environment: '
                                                         'drop `runs on:` or `manual:`'))
        if item.is_test and item.target_name not in item.part.items:
            if not any(how == 'says' for _, how in self.proof_links(item)) \
                    and not any((test_keyword(t) or ('',))[0] == 'bug' for _, t in item.lines):
                if item.draft:
                    first = item.lines[0][1][2:].strip()
                    out.append(Problem('unnamed test', f'{item.file}:{item.lineno}',
                                       f'"{first[:50]}" has no name yet: start the bullet with the name of the rule it proves, '
                                       '`- **name** — …` (the AI does this when it tidies). If the name has to differ from the rule\'s, '
                                       'add `proves: {rule}` under it'))
                else:
                    out.append(Problem('orphan test', f'{item.file}:{item.lineno}',
                                       f'**{item.target_name}** proves no item: name it after one, or add `proves: {{item}}` '
                                       '(a test split off) or `bug:` (a regression test)'))
        return out

    def check(self):
        """Every problem in the spec files: format, references, orphan tests (SPEC §3-4, §8)."""
        problems = [pr for p in self.parts.values() for pr in p.problems]
        for item in self.all_items():
            problems += self.resolved_refs(item, explain=True)[1]
            problems += self.check_test_lines(item)
            if item.kind == 'needs':
                said = set()
                for n, ref in item.refs:
                    hits = self.resolve(item.part.id, ref)
                    if len(hits) == 1 and hits[0] not in said:
                        said.add(hits[0])
                        why = self.not_gives(hits[0])
                        if why:
                            problems.append(Problem('needs', f'{item.file}:{n}', why))
        keys = {}   # id -> (what it names, the file it is in)
        for p in self.parts.values():
            for k, what in [(p.key, 'part')] + [(i.id, 'item') for i in p.items.values()]:
                if k in keys:
                    problems.append(Problem('collision', p.rel, self.collision(k, keys[k], (what, p.rel))))
                keys[k] = (what, p.rel)
        from . import lint   # lint imports this module, so it is loaded only when needed
        return problems + self.target_problems() + lint.placeholders(self)

    @staticmethod
    def collision(key, first, second):
        """The text for an id that two things claim: (what, file) of each. A part and an item of another part are the
        usual pair: `scene/modes` is the file scene/modes.md and also a rule `modes` in scene.md."""
        by_kind = dict([first, second])
        if len(by_kind) == 2:
            return (f'"{key}" names both a part ({by_kind["part"]}) and an item of {by_kind["item"]}: '
                    'rename one of them')
        return f'"{key}" names two {first[0]}s, in {first[1]} and {second[1]}: rename one of them'

    def not_gives(self, target):
        """None when a `needs` line may name `target`; else why not, and what to name instead."""
        o = self.items.get(target)
        if isinstance(o, Item) and o.kind == 'gives':
            return None
        if isinstance(o, Row):
            return f'{{{target}}} is a table row, not a `gives` item: need the item it is in, if that is one'
        if o is None and target in self.parts:
            gives = [i.id for i in self.parts[target].items.values() if i.kind == 'gives']
            what = (f'It gives {listed("{" + g + "}" for g in gives)}: name what you need.' if gives
                    else 'It gives nothing yet: add `- gives **name** — …` to its Contract, then name that.')
            return f'{{{target}}} is a part, not a `gives` item. {what}'
        if o is None:   # `item.value`
            return f'{{{target}}} is a value, not a `gives` item: need the item that holds it, if that is one'
        gives = [i.id for i in o.part.items.values() if i.kind == 'gives']
        what = (f'{o.part.key} gives {listed("{" + g + "}" for g in gives)}' if gives
                else f'{o.part.key} gives nothing yet: make it a `gives` item in its Contract')
        return f'{{{target}}} is not a `gives` item: it is in {o.section} of {o.part.key}; {what}'

    def code_roots(self):
        """Where code lives: every `path` value a target declares, and every `Source: code at`."""
        roots = []
        for p in self.parts.values():
            if p.id.startswith('targets/'):
                for it in p.items.values():
                    if it.section == 'Rules' and 'path' in it.values:
                        roots.append(it.values['path'])
            if p.source_code:
                roots.append(p.source_code)
        return sorted(set(r.rstrip('/') for r in roots)) or ['.']

    def target_paths(self):
        """[(target name, path, the part that says so)] for every `path` a target declares, in part order. A target is the part
        `targets/<name>`; the parts inside it add paths to the same target. A target may have several (a page and a folder of tests)."""
        if getattr(self, '_target_paths', None) is None:
            self._target_paths = [(p.id.split('/')[1], it.values['path'].rstrip('/'), p)
                                  for p in self.parts.values() if p.id.startswith('targets/')
                                  for it in p.items.values() if it.section == 'Rules' and 'path' in it.values]
        return self._target_paths

    def target_names(self):
        """The names of the targets that declare a path, sorted."""
        return sorted({name for name, _, _ in self.target_paths()})

    def target_of(self, rel):
        """The target a file belongs to: the one whose path is the longest prefix of this project-relative path. None for a file
        in no target's path, and for a path two targets both name (`sor check` reports that)."""
        best, names = -1, []
        for name, path, _ in self.target_paths():
            if rel == path or rel.startswith(path + '/'):
                if len(path) > best:
                    best, names = len(path), [name]
                elif len(path) == best and name not in names:
                    names.append(name)
        return names[0] if len(names) == 1 else None

    def target_problems(self):
        """Problems with how targets share the code (SPEC §9): a name a lock key could start with, a path two targets both name,
        a hand-written area in no target (only where there are two targets or more, since with one there is nothing to choose
        between), and an environment named like a target."""
        out, owner, reserved = [], {}, set()   # owner: path -> (target, file that names it)
        for name, path, part in self.target_paths():
            if name in RESERVED_TARGETS and name not in reserved:
                reserved.add(name)
                out.append(Problem('target', part.rel, f'"{name}" is a reserved name: lock keys start with it; rename the target'))
            if path in owner and owner[path][0] != name:
                out.append(Problem('target', part.rel, f'{path} is named by target {owner[path][0]} ({owner[path][1]}) and by '
                                                       f'{name}: a path belongs to one target'))
            owner.setdefault(path, (name, part.rel))
        names = self.target_names()
        if len(names) >= 2:
            for p in self.parts.values():
                if p.source_code and not any(p.source_code == path or p.source_code.startswith(path + '/')
                                             for _, path, _ in self.target_paths()):
                    out.append(Problem('target', p.rel, f'the hand-written code at {p.source_code} is in no target\'s path: '
                                                        'the project has several targets, so say which one it belongs to by '
                                                        'putting it under that target\'s path'))
            for item in self.all_items():
                if item.is_test:
                    for env in sorted({n for e in item.runs_on() for n in e} & set(names)):
                        out.append(Problem('runs on', f'{item.file}:{item.lineno}',
                                           f'"{env}" is a target, so as an environment it would defer a test that runs here: '
                                           'give the environment another name'))
        for p in self.parts.values():
            if any(piece.startswith('*') for piece in p.id.split('/')):
                out.append(Problem('name', p.rel, 'a part name may not start with `*`: the lock marks its format with a key '
                                                  'that starts with it'))
        return out

    def hand_written(self):
        """Folders whose code is written by people: unmarked lines are allowed there."""
        return {p.source_code: p for p in self.parts.values() if p.source_code}
