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
from .model import Problem, has_spec, split_lines

# A marker is `@clause` after a comment starter (SPEC §10). A starter is a run (`;; @clause`, `/// @clause`), so the marker is the
# whole line and not "code, then a line marker". Every file has these; a type adds its own (`LANGUAGES`) and a target may declare more.
BASE_STARTERS = (r'//+', r'#+', r'/\*+', r'<!--', r'-{2,}', r';+')
EXTRA_STARTERS = {'%': r'%+', '!': r'!+', "'": r"'+", '(*': r'\(\*+', 'rem': r'^\s*(?:(?i:rem)\b|::)'}
MARKER_CLOSERS = re.compile(r'(\*/|-->|\*\))\s*$')   # a comment that closes on the line is not an id
_MARKERS = {}


def marker_regex(extras=()):
    """The regex that finds a marker in a line, for the extra starters of a file. Group 1 is what follows `@clause`."""
    key = tuple(dict.fromkeys(extras))
    if key not in _MARKERS:
        alts = list(BASE_STARTERS) + [EXTRA_STARTERS.get(s) or re.escape(s) + re.escape(s[-1]) + '*' for s in key]
        _MARKERS[key] = re.compile('(?:' + '|'.join(alts) + r')\s*@clause\b(.*)$')
    return _MARKERS[key]


def _split_marker(m, line):
    """(the code before the marker, the words after `@clause`) of a line, from the match of `marker_regex`."""
    return line[:m.start()].rstrip(), MARKER_CLOSERS.sub('', m.group(1)).split()


def parse_marker(rel, line, starters=()):
    """(the code before the marker, the words after `@clause`) of a line of the file at this path that holds a marker, else None.
    `starters`: what the file's target declares besides the starters of its type."""
    m = marker_regex(starters_of(rel) + tuple(starters)).search(line)
    return None if m is None else _split_marker(m, line)

SKIP_DIRS = {'node_modules', '__pycache__', 'venv'}   # and every folder whose name starts with a dot (.git, .venv, .claude)
MAX_BYTES = 2_000_000


class Region:
    def __init__(self, file, start, kind, ids):
        self.file, self.start, self.kind, self.ids = file, start, kind, ids
        self.end = None
        self.lines = []
        self.keys = []   # lock keys after checking: item/row/part ids, test ids, or glue:<file>
        self._normalized = {}

    def normalized(self, style):
        """This region's code as the lock sees it under a style (see `normalized`), worked out once: a clause's hash and the hash of
        each of its targets both need it. The lines do not change once the scan is made."""
        if style not in self._normalized:
            self._normalized[style] = normalized(self.lines, style)
        return self._normalized[style]

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


def scan_text(rel, text, starters=()):
    """Regions, problems and unmarked line numbers of one file. `starters`: the comment starters its target declares."""
    regions, problems, unmarked = [], [], []
    cur, whole = None, None
    lines = split_lines(text)
    mark = marker_regex(starters_of(rel) + tuple(starters))
    for n, line in enumerate(lines, 1):
        m = mark.search(line)
        if not m:
            if cur is not None:
                cur.lines.append(line.rstrip())
            elif line.strip():
                unmarked.append(n)
            continue
        code, words = _split_marker(m, line)
        head = words[0] if words else ''
        if code:
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
        whole.lines = [l.rstrip() for l in lines if not mark.search(l)]
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
# `--` ends in a symbol character only in Haskell, where `-->` is an operator and a line that starts with one continues an
# expression. `{-#` is a pragma, and a block comment that closes and then goes on with code is code.
DASH_COMMENT = re.compile(r'^(--+(?![!#$%&*+./<=>?@\\^|~:]).*|/\*(?:(?!\*/).)*\*/|\{-(?!#)(?:(?!-\}).)*-\})$')
# A comment that changes what the interpreter does is code: a Python coding cookie (`# -*- coding: latin-1 -*-`) changes how the
# file is read, and so does Ruby's `# frozen_string_literal: true`.
MAGIC = re.compile(r'^#.*(?:coding[:=]|frozen_string_literal:|shareable_constant_value:)')

# How a file's code is normalized follows its type (SPEC §11). A style is written `family[-keep][+kinds]`.
#   family   which lines are comments: c (`//`, `/* */`, `<!-- -->`), hash (`#`), dash (`--`, `/* */`, `{- -}`), python (`#`, and the
#            nesting of statements counts), or safe (none: a comment is code).
#   -keep    indentation counts: each line carries its indentation as written, less what all the kept lines start with, and spaces
#            are not collapsed. safe means -keep.
#   +kinds   the multi-line strings the type has, whose lines are text and never a comment: tick (`` ` ``), rawtick (the same where a
#            backslash is just a backslash: Go), triple (`"""`), triple1 (`'''`).
# A file of a type that is not listed gets `safe`, which hides nothing but blank lines and trailing spaces. One row per kind of file:
# its extensions, its style, and the comment starters (besides the ones every file has) that a marker may be written after.
LANGUAGES = [
    ('py pyi pyw pyx pxd pxi bzl bazel star sky', 'python', ''),
    ('sh bash zsh ksh fish rb rake gemspec pl pm r toml ex exs jl ps1 psm1 tf tfvars cmake nix tcl cr awk', 'hash', ''),
    ('sql lua vhd vhdl ada adb ads', 'dash', ''),
    ('hs elm purs idr', 'dash-keep', ''),
    ('nim nims coffee', 'hash-keep', ''),
    ('js jsx mjs cjs ts tsx mts cts', 'c+tick', ''),
    ('go', 'c+rawtick', ''),
    ('java kt kts swift cs', 'c+triple', ''),
    ('dart groovy gradle', 'c+triple+triple1', ''),
    ('scala sc', 'c-keep+triple', ''),
    ('fs fsx fsi', 'c-keep', '(*'),
    ('sass styl', 'c-keep', ''),
    ('c h cc cpp cxx c++ h++ hh hpp hxx cppm ixx inl ipp tpp ino mm rs php zig sol proto thrift prisma dts dtsi d v sv svh '
     'glsl vert frag comp geom tesc tese mesh task rgen rchit rmiss rahit rint rcall hlsl hlsli wgsl slang metal cu cuh cl '
     'html htm xhtml css scss less vue svelte astro erb cshtml razor jsp asp aspx hbs mustache twig ejs liquid mdx '
     'xml svg xsd xsl xslt xaml plist csproj fsproj vbproj props targets resx wsdl rss storyboard xib '
     'json jsonc json5', 'c', ''),
    ('graphql gql', 'hash', ''),
    ('m', 'c', '%'),                       # Objective-C, or MATLAB
    ('pas pp', 'c', '(*'),
    ('erl hrl tex sty', 'safe', '%'),
    ('f f90 f95 f03 f08 for ftn', 'safe', '!'),
    ('vb vbs bas', 'safe', "'"),
    ('bat cmd', 'safe', 'rem'),
    ('ml mli mll mly', 'safe', '(*'),
]
# Files known by their name, not their extension.
LANGUAGES_BY_NAME = {'dockerfile': 'hash', 'containerfile': 'hash', 'rakefile': 'hash', 'gemfile': 'hash', 'vagrantfile': 'hash',
                     'cmakelists.txt': 'hash'}
# ... and by the name exactly as written: a script called `build` is a shell script, `BUILD` is Bazel's.
LANGUAGES_BY_EXACT_NAME = {'BUILD': 'python', 'WORKSPACE': 'python'}
DEFAULT_STYLE = 'safe'
STYLES = {ext: (style, starters) for exts, style, starters in LANGUAGES for ext in exts.split()}
FAMILIES = ('c', 'hash', 'dash', 'python', 'safe')
KINDS = ('tick', 'rawtick', 'triple', 'triple1')


def _language(rel):
    """(style, extra marker starters) of the file at this project-relative path."""
    exact = os.path.basename(rel)
    name = exact.lower()
    if exact in LANGUAGES_BY_EXACT_NAME:
        return LANGUAGES_BY_EXACT_NAME[exact], ''
    if name in LANGUAGES_BY_NAME:
        return LANGUAGES_BY_NAME[name], ''
    return STYLES.get(name.rpartition('.')[2], (DEFAULT_STYLE, '')) if '.' in name else (DEFAULT_STYLE, '')


def starters_of(rel):
    """The comment starters, besides the ones every file has, that a marker may follow in the file at this path (its type's)."""
    return tuple(_language(rel)[1].split())


def style_of(rel):
    """The normalization style of the file at this project-relative path (see the table above); `safe` for a type not listed."""
    return _language(rel)[0]


def _collapse(t):
    """One space for every run of spaces outside quotes; what is inside quotes stays as written."""
    return ''.join(part if i % 2 else re.sub(r'[ \t]+', ' ', part) for i, part in enumerate(QUOTED.split(t)))


def _lead(rest):
    """How indentation reads in a hash: the number of spaces (`3`), or, when it holds a tab or another whitespace character, the
    indentation itself with each of those written as `\\u` and its code point in four hex digits at least (`  \\u0009`), so that a
    tab is never the same as eight spaces."""
    if not rest.strip(' '):
        return str(len(rest))
    return ''.join(c if c == ' ' else f'\\u{ord(c):04x}' for c in rest)


def _indented(kept, keep):
    """The texts of the kept lines [(line, text)], each led by its indentation when indentation counts (`3:foo`): the indentation as
    written, less the characters all the kept lines start with, so that moving the whole piece of code is not a change."""
    if not keep:
        return [text for _, text in kept]
    lead = [line[:len(line) - len(line.lstrip())] for line, _ in kept]
    base = len(os.path.commonprefix(lead))
    return [f'{_lead(ws[base:])}:{text}' for ws, (_, text) in zip(lead, kept)]


def normalized(lines, style='c'):
    """Code as the lock sees it: no blank lines, no comment-only lines, no indentation, and one
    space for every run of spaces outside quotes. Text inside quotes and everything else stays
    exactly as written, so re-indenting and re-spacing is not a change but a new word is.
    `style` (see `LANGUAGES`) says which lines are comments, whether indentation counts, and which multi-line strings there are."""
    base, *kinds = style.split('+')
    family = base[:-5] if base.endswith('-keep') else base
    if family not in FAMILIES or any(k not in KINDS for k in kinds) or (kinds and family != 'c'):
        raise ValueError(f'unknown normalization style {style!r}')    # a typo must not switch a protection off in silence
    if family == 'python':
        return _python_normalized(lines)
    keep = family == 'safe' or base.endswith('-keep')
    if family == 'hash':
        return _hash_normalized(lines, keep)
    comment = {'c': COMMENT_LINE, 'dash': DASH_COMMENT}.get(family)
    inside = _inside_strings(lines, kinds) if kinds else ()
    kept = []
    for i, line in enumerate(lines):
        t = line.strip()
        if not t or (comment is not None and comment.match(t) and not (inside and inside[i])):
            continue
        kept.append((line, t if keep else _collapse(t)))
    return '\n'.join(_indented(kept, keep))


_LEX = re.compile(r'//|/\*|`|"""|\'\'\'|"|\'')
_CLOSERS = {}


def _after_closer(line, i, quote, escapes=True):
    """The index just after the next `quote` at or after i, where a backslash makes the next character no closer (unless `escapes`
    is false); -1 when the line has none."""
    if not escapes:
        j = line.find(quote, i)
        return -1 if j < 0 else j + len(quote)
    if quote not in _CLOSERS:
        _CLOSERS[quote] = re.compile(r'\\|' + re.escape(quote))
    while True:
        m = _CLOSERS[quote].search(line, i)
        if m is None:
            return -1
        if m.group() != '\\':
            return m.end()
        i = m.end() + 1


def _inside_strings(lines, kinds):
    """For each line, whether it starts inside a multi-line string (so it is text, and a line that looks like a comment is not one).
    `kinds`: tick, rawtick, triple, triple1 (see `LANGUAGES`). Comments are skipped, `//` to the end of the line and `/* */` over lines,
    before a quote is looked for, and a quote that closes on its line is a string of one line. Wrongly inside keeps comment lines,
    which only gives a false alarm. Wrongly outside hides a change, and the tracker catches the one case it can see: a region that
    ends inside a string or a comment has lost its place, so none of its lines is dropped. An even number of strays still gets through."""
    opens = {'`': 'tick' in kinds or 'rawtick' in kinds, '"""': 'triple' in kinds, "'''": 'triple1' in kinds}
    escapes = 'rawtick' not in kinds
    out, state = [], None   # state: None, 'block' (inside /* */), or the closer of the multi-line string that is open
    for line in lines:
        out.append(state not in (None, 'block'))
        i, n = 0, len(line)
        while i < n:
            if state == 'block':
                j = line.find('*/', i)
                if j < 0:
                    break
                state, i = None, j + 2
            elif state is not None:
                j = _after_closer(line, i, state, escapes or state != '`')
                if j < 0:
                    break
                state, i = None, j
            else:
                m = _LEX.search(line, i)
                if m is None:
                    break
                tok, i = m.group(), m.end()
                if tok == '//':
                    break
                if tok == '/*':
                    j = line.find('*/', i)
                    if j < 0:
                        state = 'block'
                        break
                    i = j + 2
                    continue
                if tok in ('"""', "'''") and not opens[tok]:
                    tok, i = tok[0], m.start() + 1     # an empty string, then whatever follows
                j = _after_closer(line, i, tok, escapes or tok != '`')
                if tok in opens and opens[tok]:
                    if j < 0:
                        state = tok
                        break
                    i = j
                elif tok in ('"', "'") and j >= 0:
                    i = j                              # a string of one line (an unclosed quote is an apostrophe)
    if state is not None:
        # A region does not end inside a string or a comment, so the tracker lost its place (a lone backtick in JSX text, say). Every
        # line is then kept as text, which can only give a false alarm; reading on would trust a parity that is wrong.
        return [True] * len(lines)
    return out


def _is_comment(t):
    """Whether a stripped line of a `#` language is a comment of its own (a magic comment is not)."""
    return bool(HASH_COMMENT.match(t)) and not MAGIC.match(t)


def _python_normalized(lines):
    """Python code without layout but with its nesting: comment-only lines and blank lines are gone, spaces are collapsed, and
    every line that starts a statement carries its depth (`2:return x`), counted in levels, not in columns, so changing 2 spaces
    to 4 everywhere is not a change and moving a line into a loop is. Lines that continue a statement (inside brackets, after a
    backslash, inside a multi-line string) carry no depth. A `#` line inside a multi-line string is text, not a comment."""
    out, levels = [], _Levels()
    stack, depth, continued = (), 0, False
    for line in lines:
        t = line.strip()
        if stack:
            if t:
                out.append(_collapse(t))
        elif t and not _is_comment(t):
            text = _collapse(t)
            if depth == 0 and not continued:
                width = len(line[:len(line) - len(line.lstrip())].expandtabs(8))
                text = f'{levels.of(width)}:{text}'
            out.append(text)
        stack, depth, continued = _python_state(line, stack, depth)
    return '\n'.join(out)


class _Levels:
    """The depth of the statements of a piece of code, counted from the first one. A piece of code is often not a whole file: it
    may start inside a method and go on with a line of the class around it, so the depth can go below the first line's (-1)."""

    def __init__(self):
        self.stack = []   # the columns of the open levels, increasing
        self.below = 0    # how many levels under the first line's there have been

    def of(self, width):
        """The level of a statement that starts at this column: deeper than the line before opens a level, shallower closes levels
        down to the column it matches, and shallower than every open level is a new level below them all."""
        stack = self.stack
        if not stack or width > stack[-1]:
            stack.append(width)
        else:
            while len(stack) > 1 and width < stack[-1]:
                stack.pop()
            if width > stack[-1]:    # a dedent that matches no level there was: a new one
                stack.append(width)
            elif width < stack[-1]:  # shallower than all of them: the piece began inside a block
                stack[:] = [width]
                self.below += 1
        return len(stack) - 1 - self.below


_PY_OPEN = re.compile(r'[\'"#()\[\]{}]')
_PY_CLOSE = {q: re.compile(r'\\|' + re.escape(q)) for q in ('"', "'", '"""', "'''")}
_PY_FIELD = re.compile(r'[\'"#()\[\]{}:]')   # what matters inside the code of an f-string's replacement field
_PY_SPEC = re.compile(r'[{}]')                 # and inside its format spec
_PY_LITERAL = {}                                # (quote) -> what matters in the text of an f-string


def _literal(quote):
    if quote not in _PY_LITERAL:
        _PY_LITERAL[quote] = re.compile(r'\\|\{\{|\}\}|\{|\}|' + re.escape(quote))
    return _PY_LITERAL[quote]


def _open_string(line, j):
    """(frame, length of the opening quotes) of the string whose quote is at line[j]. A frame is ('s', quote) for a string and
    ('f', quote, raw) for an f-string or a template string (`t"..."`, Python 3.14), which have code in them the same way. The prefix
    is read back from the quote, and the end of a name such as `if` in `if"x"` or `not` in `not"x"` is not a prefix."""
    q = line[j]
    quote = q * 3 if line.startswith(q * 3, j) else q
    k = j
    while k > 0 and j - k < 2 and line[k - 1] in 'rRbBuUfFtT':
        k -= 1
    prefix = line[k:j].lower()
    if k > 0 and (line[k - 1].isalnum() or line[k - 1] == '_'):
        prefix = ''
    if 'f' in prefix or 't' in prefix:
        return ('f', quote, 'r' in prefix), len(quote)
    return ('s', quote), len(quote)


def _python_state(line, stack, depth):
    """(what is open, bracket depth, whether the statement goes on) after one line of Python. What is open is a tuple of frames, the
    innermost last: ('s', quote) a string, ('f', quote, raw) the text of an f-string, ('e', n) the code of one of its replacement
    fields with n brackets open in it, ('m',) its format spec. Since Python 3.12 the code of a field may use the quote of the f-string
    around it and span lines, so the end of an f-string is found by reading the fields, not by the next quote. A one-quote string or
    f-string text ends with its line unless a backslash goes on."""
    i, n, code_end = 0, len(line), len(line)
    stack = list(stack)
    while i < n:
        top = stack[-1] if stack else None
        if top is None:                     # code
            m = _PY_OPEN.search(line, i)
            if m is None:
                break
            c, i = m.group(), m.end()
            if c == '#':
                code_end = m.start()
                break
            if c in '\'"':
                frame, size = _open_string(line, m.start())
                stack.append(frame)
                i = m.start() + size
            else:
                depth = max(depth + (c in '([{') - (c in ')]}'), 0)
        elif top[0] == 's':                 # a string
            m = _PY_CLOSE[top[1]].search(line, i)
            if m is None:
                i = n
            elif m.group() == '\\':
                i = m.end() + 1             # the escaped character; past the end when the backslash ends the line
            else:
                i = m.end()
                stack.pop()
        elif top[0] == 'f':                 # the text of an f-string
            m = _literal(top[1]).search(line, i)
            if m is None:
                i = n
                continue
            g, i = m.group(), m.end()
            if g == '\\':
                nxt = line[i:i + 1]
                if not nxt:
                    i += 1                  # a backslash at the end of the line goes on
                elif top[2]:                # raw: a backslash only keeps a quote or a backslash from meaning anything
                    i += 1 if nxt in ('\\', top[1][0]) else 0
                elif nxt == 'N' and line.startswith('{', i + 1):    # \N{NAME}
                    close = line.find('}', i + 2)
                    i = n if close < 0 else close + 1
                elif nxt not in '{}':
                    i += 1
            elif g == '{':
                stack.append(('e', 0))
            elif g == top[1]:
                stack.pop()
        elif top[0] == 'e':                 # the code of a replacement field
            m = _PY_FIELD.search(line, i)
            if m is None:
                break
            c, j, i = m.group(), m.start(), m.end()
            if c == '#':
                break                       # a comment, to the end of the line
            if c in '\'"':
                frame, size = _open_string(line, j)
                stack.append(frame)
                i = j + size
            elif c in '([{':
                stack[-1] = ('e', top[1] + 1)
            elif c in ')]':
                stack[-1] = ('e', max(top[1] - 1, 0))
            elif c == '}':
                if top[1] > 0:
                    stack[-1] = ('e', top[1] - 1)
                else:
                    stack.pop()
            elif top[1] == 0:               # a colon outside brackets: the format spec begins
                stack[-1] = ('m',)
        else:                               # the format spec of a field
            m = _PY_SPEC.search(line, i)
            if m is None:
                break
            i = m.end()
            if m.group() == '{':
                stack.append(('e', 0))
            else:
                stack.pop()
    if stack and stack[-1][0] in 'sf' and len(stack[-1][1]) == 1 and i <= n:   # the text of a one-quote string ends with its line
        stack.pop()
    return tuple(stack), depth, not stack and line[:code_end].rstrip().endswith('\\')


HEREDOC = re.compile(r'<<[-~]?[ \t]*(?:"([^"]+)"|\'([^\']+)\'|\\?([A-Za-z_][A-Za-z0-9_]*))')


def _hash_normalized(lines, keep=False):
    """Code of a `#` language (shell, Ruby, Perl, R, TOML) without layout: comment-only lines and blank lines are gone and spaces are
    collapsed. A `#` line inside a string or a here-document is text, not a comment, so what is open at the end of a line is tracked.
    `keep`: indentation counts (see `normalized`), and spaces are not collapsed."""
    kept, open_ = [], None
    for line in lines:
        t = line.strip()
        if open_ is None and (not t or _is_comment(t)):
            continue
        if t:
            kept.append((line, t if keep else _collapse(t)))
        open_ = _hash_state(line, open_)
    return '\n'.join(_indented(kept, keep))


def _hash_state(line, open_):
    """What a line of a `#` language leaves open: None, the quote of a string that goes on (`"`, `'`, a backtick, or three of them),
    or ('heredoc', words) for the here-documents the line started, each ended by a line that is its word. A quote is taken as
    opened wherever one is found, so a doubtful line leaves a string open and keeps the comments after it: that can only make a
    comment edit count as a change, never hide a change to code."""
    if isinstance(open_, tuple):
        words = open_[1][1:] if line.strip() == open_[1][0] else open_[1]
        return ('heredoc', words) if words else None
    i, n, words = 0, len(line), []
    while i < n:
        if open_:
            if line[i] == '\\':
                i += 2
            elif line.startswith(open_, i):
                i, open_ = i + len(open_), None
            else:
                i += 1
        elif line[i] == '#' and (i == 0 or line[i - 1] in ' \t;&|('):
            break
        elif line[i] in '\'"`':
            open_ = line[i] * 3 if line.startswith(line[i] * 3, i) else line[i]
            i += len(open_)
        elif line.startswith('<<<', i):
            i += 3
        elif line.startswith('<<', i):
            m = HEREDOC.match(line, i)
            if m:
                words.append(m.group(1) or m.group(2) or m.group(3))
            i = m.end() if m else i + 2
        else:
            i += 1
    return open_ if open_ or not words else ('heredoc', tuple(words))


def code_hash(regions, legacy=False):
    """The hash of the code of these regions: in file and line order, each region normalized by the rule of its file (`legacy`: the
    C-family rule for all), joined by a line that holds a NUL, then SHA-256, the first 12 hex digits. `vectors/hashing.json` pins it."""
    parts = [r.normalized('c' if legacy else style_of(r.file)) for r in sorted(regions, key=lambda r: (r.file, r.start))]
    return hashlib.sha256('\n\x00\n'.join(parts).encode('utf8')).hexdigest()[:12]


class Scan:
    """Every region under the project's code roots, checked against the project's ids."""

    def __init__(self, project, overrides=None):
        """overrides: {path: text} read instead of the file on disk (or as a new file), so a
        change can be checked before it is written."""
        self.project = project
        self.regions, self.problems = [], []
        self._hashes = {}
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
                r.lines = [l.rstrip() for l in split_lines(text)[span[0] - 1:span[1]]]
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
        regions, problems, unmarked = scan_text(rel, text, self.project.comment_starters(rel))
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
        before the rule followed the file type, to recognise a lock written then (see `lock.old_rule_keys`).
        The regions do not change once the scan is made, so each of the two answers is worked out once."""
        if legacy not in self._hashes:
            by_key = {}
            for r in sorted(self.regions, key=lambda r: (r.file, r.start)):
                for k in r.keys:
                    by_key.setdefault(k, []).append(r)
            self._hashes[legacy] = {k: code_hash(rs, legacy) for k, rs in by_key.items()}
        return dict(self._hashes[legacy])

    def target_code_hashes(self):
        """key -> {target -> hash} of the code marked with it, one hash for the regions in each target's paths (`code_hash`). Code in
        no target's path is under the name `*`, which no target can have. Computed once, like `code_hashes`."""
        if 'targets' not in self._hashes:
            by_key = {}
            for r in sorted(self.regions, key=lambda r: (r.file, r.start)):
                target = self.project.target_of(r.file) or '*'
                for k in r.keys:
                    by_key.setdefault(k, {}).setdefault(target, []).append(r)
            self._hashes['targets'] = {k: {t: code_hash(rs) for t, rs in by_target.items()} for k, by_target in by_key.items()}
        return {k: dict(v) for k, v in self._hashes['targets'].items()}

    def at(self, file, line):
        file = file.replace('\\', '/')
        return [r for r in self.regions if r.file == file and r.contains(line)]
