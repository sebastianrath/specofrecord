"""Finds `@clause` regions in code (SPEC §10) and checks them against the spec files.

    // @clause camera/limits camera/zoom-step   code for one or more clauses
    // @clause test camera/limits               test code for the test of camera/limits
    // @clause glue                             wiring that belongs to no single clause
    // @clause end                              closes the open region
    // @clause file physics/solver              the whole file (only for `Source: code` parts)
    { name: 'mars', size: 5 },  // @clause bodies/planets/Mars    one line, inside or outside a region

"""
import hashlib
import os
import re

from . import anchors
from .model import Problem, has_spec

MARK = re.compile(r'(?://|#|/\*|<!--|--|;)\s*@clause\b(.*)$')
SKIP_DIRS = {'node_modules', '__pycache__', 'venv'}   # and every folder whose name starts with a dot (.git, .venv, .claude)
MAX_BYTES = 2_000_000


class Region:
    def __init__(self, file, start, kind, ids):
        self.file, self.start, self.kind, self.ids = file, start, kind, ids
        self.end = None
        self.lines = []
        self.keys = []   # lock keys after checking: item/row/part ids, test ids, or glue:<file>

    @property
    def where(self):
        return f'{self.file}:{self.start}-{self.end}' if self.end else f'{self.file}:{self.start}'

    def contains(self, n):
        return self.start <= n <= (self.end or self.start)


def _ranges(nums):
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append((start, prev))
            start = prev = n
    if start is not None:
        out.append((start, prev))
    return out


def scan_text(rel, text):
    """Regions, problems and unmarked line numbers of one file."""
    regions, problems, unmarked = [], [], []
    cur, whole = None, None
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        m = MARK.search(line)
        if not m:
            if cur is not None:
                cur.lines.append(line.rstrip())
            elif line.strip():
                unmarked.append(n)
            continue
        words = re.sub(r'(\*/|-->)\s*$', '', m.group(1)).split()
        head = words[0] if words else ''
        code = line[:m.start()].rstrip()
        if code.strip():
            # a line marker: this one line belongs to the ids at its end (a table row, say),
            # not to the region around it
            r = Region(rel, n, 'line', words)
            r.end, r.lines = n, [code]
            if not words or head in ('end', 'glue', 'test', 'file'):
                problems.append(Problem('marker', f'{rel}:{n}', 'a line marker names the ids its line serves'))
            regions.append(r)
            continue
        if head == 'end':
            if cur is None:
                problems.append(Problem('marker', f'{rel}:{n}', '@clause end without an open region'))
            else:
                cur.end = n
                regions.append(cur)
                cur = None
            continue
        if cur is not None:
            problems.append(Problem('marker', f'{rel}:{n}',
                                    f'regions never nest: the region at line {cur.start} is still open'))
            cur.end = n - 1
            regions.append(cur)
            cur = None
        if head == 'file':
            whole = Region(rel, n, 'file', words[1:])
            continue
        if head == 'glue':
            cur = Region(rel, n, 'glue', [])
        elif head == 'test':
            cur = Region(rel, n, 'test', words[1:])
        else:
            cur = Region(rel, n, 'code', words)
        if cur.kind != 'glue' and not cur.ids:
            problems.append(Problem('marker', f'{rel}:{n}', '@clause needs at least one id'))
    if cur is not None:
        problems.append(Problem('marker', f'{rel}:{cur.start}', 'region is never closed with @clause end'))
        cur.end = len(lines)
        regions.append(cur)
    if whole is not None:
        whole.end = len(lines)
        whole.lines = [l.rstrip() for l in lines if not MARK.search(l)]
        regions.append(whole)
        unmarked = []
    return regions, problems, unmarked


def _files(project, root):
    path = os.path.join(project.root, root)
    if os.path.isfile(path):
        yield path
        return
    for dirpath, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')
                         and os.path.abspath(os.path.join(dirpath, d)) != project.spec_dir
                         and not has_spec(os.path.join(dirpath, d)))   # a folder with a project of its own is not ours
        for f in sorted(files):
            yield os.path.join(dirpath, f)


QUOTED = re.compile(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`)')
COMMENT_LINE = re.compile(r'^(//.*|/\*.*\*/|<!--.*-->)$')
HASH_COMMENT = re.compile(r'^#(?!!).*$')   # a `#!` line names the interpreter: that is code
DASH_COMMENT = re.compile(r'^--.*$')

# How a file's code is normalized follows its type. Whatever is not listed is read as C-family (`//`, `/* */`, `<!-- -->`;
# indentation never counts), which is how every file was read before the rule followed the file type, so those hashes
# are unchanged. In Python indentation is meaning: a line moved into a loop is a change.
STYLE_BY_EXTENSION = {
    **dict.fromkeys(('py', 'pyi', 'pyw'), 'python'),                      # `#` comments, indentation counts
    **dict.fromkeys(('sh', 'bash', 'zsh', 'rb', 'pl', 'r', 'toml'), 'hash'),   # `#` comments, indentation does not
    **dict.fromkeys(('sql', 'lua', 'hs'), 'dash'),                        # `--` comments
}


def style_of(rel):
    """The normalization style of the file at this project-relative path: c (the default), python, hash or dash."""
    name = os.path.basename(rel)
    return STYLE_BY_EXTENSION.get(name.rpartition('.')[2].lower(), 'c') if '.' in name else 'c'


def _collapse(t):
    """One space for every run of spaces outside quotes; what is inside quotes stays as written."""
    return ''.join(part if i % 2 else re.sub(r'[ \t]+', ' ', part) for i, part in enumerate(QUOTED.split(t)))


def normalized(lines, style='c'):
    """Code as the lock sees it: no blank lines, no comment-only lines, no indentation, and one
    space for every run of spaces outside quotes. Text inside quotes and everything else stays
    exactly as written, so re-indenting and re-spacing is not a change but a new word is.
    `style` (see `style_of`) says which lines are comments and, for Python, that the nesting of lines is kept."""
    if style == 'python':
        return _python_normalized(lines)
    comment = {'hash': HASH_COMMENT, 'dash': DASH_COMMENT}.get(style, COMMENT_LINE)
    out = []
    for line in lines:
        t = line.strip()
        if not t or comment.match(t):
            continue
        out.append(_collapse(t))
    return '\n'.join(out)


def _python_normalized(lines):
    """Python code without layout but with its nesting: comment-only lines and blank lines are gone, spaces are collapsed, and
    every line that starts a statement carries its depth (`2:return x`), counted in levels, not in columns, so changing 2 spaces
    to 4 everywhere is not a change and moving a line into a loop is. Lines that continue a statement (inside brackets, after a
    backslash, inside a multi-line string) carry no depth. A `#` line inside a multi-line string is text, not a comment."""
    out, stack = [], []
    triple, depth, continued = None, 0, False
    for line in lines:
        t = line.strip()
        if triple is not None:
            if t:
                out.append(_collapse(t))
        elif t and not HASH_COMMENT.match(t):
            text = _collapse(t)
            if depth == 0 and not continued:
                width = len(line[:len(line) - len(line.lstrip())].expandtabs(8))
                text = f'{_level(stack, width)}:{text}'
            out.append(text)
        triple, depth, continued = _python_state(line, triple, depth)
    return '\n'.join(out)


def _level(stack, width):
    """The depth of a statement that starts at this column, given the columns of the open levels (changed in place). A first line
    sets level 0; a deeper line opens a level; a shallower one closes levels down to the column it matches."""
    if not stack:
        stack.append(width)
    elif width > stack[-1]:
        stack.append(width)
    else:
        while len(stack) > 1 and width < stack[-1]:
            stack.pop()
        if width > stack[-1]:    # a dedent that matches no level there was: a new one
            stack.append(width)
        elif width < stack[-1]:  # shallower than the first line of a fragment: it becomes the first
            stack[:] = [width]
    return len(stack) - 1


def _python_state(line, triple, depth):
    """(open multi-line string or None, bracket depth, whether the statement goes on) after one line of Python."""
    i, n, code_end = 0, len(line), len(line)
    while i < n:
        c = line[i]
        if triple:
            if line.startswith(triple, i):
                i, triple = i + 3, None
            else:
                i += 2 if c == '\\' else 1
        elif c == '#':
            code_end = i
            break
        elif c in '\'"':
            if line.startswith(c * 3, i):
                triple, i = c * 3, i + 3
            else:
                j = i + 1
                while j < n and line[j] != c:
                    j += 2 if line[j] == '\\' else 1
                i = j + 1
        else:
            depth += (c in '([{') - (c in ')]}')
            depth = max(depth, 0)
            i += 1
    return triple, depth, triple is None and line[:code_end].rstrip().endswith('\\')


class Scan:
    """Every region under the project's code roots, checked against the project's ids."""

    def __init__(self, project, overrides=None):
        """overrides: {path: text} read instead of the file on disk (or as a new file), so a
        change can be checked before it is written."""
        self.project = project
        self.regions, self.problems = [], []
        self._hand = project.hand_written()
        self._explicit = project.code_roots() != ['.']
        overrides = {self.rel(p): t for p, t in (overrides or {}).items()}
        seen = set()
        for root in project.code_roots():
            for path in _files(project, root):
                rel = self.rel(path)
                if rel in seen:
                    continue
                seen.add(rel)
                if rel in overrides:
                    self._add(rel, overrides[rel])
                    continue
                if os.path.getsize(path) > MAX_BYTES:
                    continue
                try:
                    with open(path, encoding='utf8') as fh:
                        self._add(rel, fh.read())
                except (UnicodeDecodeError, OSError):
                    continue
        for rel, text in overrides.items():
            if rel not in seen and self.covers(rel):
                self._add(rel, text)
        self._anchor(overrides)

    def _anchor(self, overrides):
        """Regions for `code: path#name` lines: the named symbol's lines belong to the item."""
        for item in self.project.all_items():
            for n, target in item.anchors:
                where = f'{item.file}:{n}'
                path, name = anchors.split(target)
                rel = path.replace('\\', '/')
                if rel.startswith('./'):
                    rel = rel[2:]
                if rel in overrides:
                    text = overrides[rel]
                else:
                    try:
                        with open(os.path.join(self.project.root, rel), encoding='utf8') as fh:
                            text = fh.read()
                    except (OSError, UnicodeDecodeError):
                        self.problems.append(Problem('anchor', where, f'code: {target}: no such file'))
                        continue
                span = anchors.find(text, rel, name)
                if span is None:
                    self.problems.append(Problem('anchor', where, f'code: {target}: no "{name}" in {rel}'))
                    continue
                r = Region(rel, span[0], 'anchor', [item.id])
                r.end = span[1]
                r.lines = [l.rstrip() for l in text.splitlines()[span[0] - 1:span[1]]]
                r.keys = [item.id]
                r.target = target
                self.regions.append(r)

    def rel(self, path):
        return os.path.relpath(os.path.abspath(path), self.project.root).replace(os.sep, '/')

    def covers(self, rel):
        """Whether a file at this project-relative path is code the tool looks at."""
        if rel.startswith('../') or rel == self.project.spec_name or rel.startswith(self.project.spec_name + '/'):
            return False
        return any(r == '.' or rel == r or rel.startswith(r + '/') for r in self.project.code_roots())

    def by_hand(self, rel):
        return any(rel == h or rel.startswith(h + '/') for h in self._hand)

    def _add(self, rel, text):
        if not self._explicit and '@clause' not in text:
            return
        regions, problems, unmarked = scan_text(rel, text)
        self.problems += problems
        by_hand = self.by_hand(rel)
        if not by_hand:
            for a, b in _ranges(unmarked):
                where = f'{rel}:{a}' + (f'-{b}' if b != a else '')
                self.problems.append(Problem('unmarked', where, 'code outside any @clause region'))
        for r in regions:
            if r.kind == 'file' and not by_hand:
                self.problems.append(Problem('marker', f'{rel}:{r.start}',
                                             '@clause file is only for `Source: code` parts'))
            self._keys(r)
        self.regions += regions

    def _keys(self, r):
        p = self.project
        if r.kind == 'glue':
            r.keys = [f'glue:{r.file}']
            return
        for ident in r.ids:
            name = ident.rpartition('/')[2]
            if (name[5:] if name.startswith('test:') else name).startswith('~'):
                self.problems.append(Problem('marker', f'{r.file}:{r.start}',
                                             f'{ident} is a bullet nobody has named yet, and its id changes whenever its words do: '
                                             'name it first (`- **name** — …`), then point at the name'))
                continue
            if r.kind == 'test':
                part, _, name = ident.rpartition('/')
                key = ident if name.startswith('test:') else (f'{part}/test:{name}' if part else f'test:{name}')
                if key in p.items and p.items[key].is_test:
                    r.keys.append(key)
                else:
                    self.problems.append(Problem('marker', f'{r.file}:{r.start}', f'{ident} has no test'))
                continue
            found = p.find(ident)
            if found is None:
                self.problems.append(Problem('marker', f'{r.file}:{r.start}', f'{ident} is no item, row or part'))
            elif found[0] == 'item' and found[1].is_test:
                self.problems.append(Problem('marker', f'{r.file}:{r.start}',
                                             f'{ident} is a test: mark test code with @clause test'))
            else:
                r.keys.append(found[1].key if found[0] == 'part' else found[1].id)

    def regions_for(self, key):
        return [r for r in self.regions if key in r.keys]

    def has_own_rules(self):
        """Whether any file with code in it is of a type that is normalized in its own way (not as C-family)."""
        return any(style_of(r.file) != 'c' for r in self.regions)

    def code_hashes(self, legacy=False):
        """lock key -> hash of all code marked with it, in file and line order. The code is
        hashed without layout (see `normalized`), so reformatting is not drift. legacy: with the rule every file followed
        before the rule followed the file type, to recognise a lock written then (see `lock.old_rule_keys`)."""
        code = {}
        for r in sorted(self.regions, key=lambda r: (r.file, r.start)):
            style = 'c' if legacy else style_of(r.file)
            for k in r.keys:
                code.setdefault(k, []).append(normalized(r.lines, style))
        return {k: hashlib.sha256('\n\x00\n'.join(v).encode('utf8')).hexdigest()[:12]
                for k, v in code.items()}

    def at(self, file, line):
        file = file.replace('\\', '/')
        return [r for r in self.regions if r.file == file and r.contains(line)]
