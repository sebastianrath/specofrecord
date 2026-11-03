"""Readability notes (SPEC §13), open questions, and unfilled template text.

`notes` are advice: a section with too many items, an item with too many words, a part longer than a screen, a part with
too many child parts, a test that proves more than one thing, a test nothing will run, a question marked `open:`. They
are never problems and never change the lock.
`placeholders` are problems: template text nobody filled in (`sor check` reports them).
"""
import glob
import os
import re

from .markers import Scan
from .model import ANCHOR, CODE, SECTIONS, VDEF, Item, Problem, listed, split_lines, test_keyword

LIMIT_ITEMS = 7        # items in Rules, Approach or Contract (a table counts as one)
LIMIT_SCREEN = 40      # lines above `## Tests`
LIMIT_TEST_LINES = 5   # non-blank lines in one test
LIMIT_WORDS = 80       # words in one bullet of Rules, Approach or Contract (its indented lines too; tables, `open:` and `code:` lines not)
LIMIT_CHILDREN = 12    # parts directly under one part (under the root: the top-level parts)
LIMIT_REGION_CLAUSES = 7   # clauses named by one `@clause` marker: they are claimed and locked together
SENTINEL = '<fill in'  # what a template writes where a person has to write


def bullet_counts(part):
    """{'Rules': n, 'Approach': n, 'Contract': n, 'Tests': n}: the bullets in each section of a part.
    A bullet is a `- ` line at the start of a line, named or not, counted in the section it is written in (a name used
    twice makes one item, but its two bullets still belong to their own sections); a table under a bullet is not one,
    and every `- needs` line counts although they all make up one item. The items a design export makes up are not bullets."""
    counts = dict.fromkeys(SECTIONS, 0)
    for item in part.items.values():
        for section, n in item.bullets.items():
            counts[section] += n
    return counts


def child_counts(project):
    """{part id: how many parts are directly under it}, the root being ''. A folder that only groups parts is no part and
    gets no count; the part made from a design export is nobody's child."""
    counts = {}
    for pid, part in project.parts.items():
        if pid and part.path.endswith('.md'):
            parent = pid.rpartition('/')[0]
            counts[parent] = counts.get(parent, 0) + 1
    return counts


def bullet_words(item):
    """[(line, words, text)] for each bullet of an item: the bullet with its indented lines. A table, an `open:` question and a
    `code:` line are not words of the item; a word is a piece of text between spaces that has a letter or a digit in it."""
    found = []
    for n, t in item.lines:
        if t.startswith('- '):
            found.append([n, t[2:].strip()])
        elif found and t.strip() and not t.strip().startswith('|') and n not in item.open_lines and not ANCHOR.match(t):
            found[-1][1] += ' ' + t.strip()
    return [(n, sum(1 for w in text.split() if any(c.isalnum() for c in w)), text) for n, text in found]


def _first_bullet(part, section):
    """The line of a section's first item, for a section that has no heading of its own."""
    return min((i.lineno for i in part.items.values() if i.section == section and i.kind != 'design'), default=1)


def _order(note):
    path, _, line = note.where.rpartition(':')
    return (path, int(line) if line.isdigit() else 0, note.kind, note.text)


def _steps(test):
    """The keywords of a test's lines: {'do', 'expect', 'manual', ...}."""
    return {kw[0] for _, t in test.lines[1:] for kw in [test_keyword(t)] if kw}


def notes(project, scan=None):
    """Readability notes and open questions as Problems of the kinds 'too long', 'too wide', 'screen',
    'long test', 'never run', 'loose text', 'value twice' and 'open'. They are advice: callers show them apart from the problems.
    scan: the code markers, which tell a test written in the project's own framework (`@clause test`) from one nobody
    runs; they are read only when a project without a web target has a test with steps."""
    out = []
    web = project.has_web_target()
    for pid, n in child_counts(project).items():
        if n > LIMIT_CHILDREN and pid in project.parts:
            under = f'`{pid}`' if pid else 'the root'
            out.append(Problem('too wide', f'{project.parts[pid].rel}:1',
                               f'{n} parts sit directly under {under} (at most {LIMIT_CHILDREN}): group related ones under a part '
                               f'of their own, as `{pid + "/" if pid else ""}<group>/<name>` (SPEC §13)'))
    for r in (scan.regions if scan is not None else []):   # a region that serves many clauses ties them together (SPEC §13)
        if r.kind not in ('code', 'file', 'line'):   # glue and test regions name no clause of their own
            continue
        n = len(set(r.ids))
        if n > LIMIT_REGION_CLAUSES:
            out.append(Problem('wide region', f'{r.file}:{r.start}',
                               f'this code region serves {n} clauses (at most {LIMIT_REGION_CLAUSES}): they are claimed and locked together, so '
                               'split the code into regions, one per clause where it can be done (SPEC §13)'))
    for part in project.parts.values():
        counts = bullet_counts(part)
        for section in ('Rules', 'Approach', 'Contract'):
            if counts[section] > LIMIT_ITEMS:
                line = part.headings.get(section) or _first_bullet(part, section)
                out.append(Problem('too long', f'{part.rel}:{line}',
                                   f'{section} has {counts[section]} items (at most {LIMIT_ITEMS}): '
                                   'split it into child parts (SPEC §13)'))
        tests_at = part.headings.get('Tests')
        above = tests_at - 1 if tests_at else part.nlines
        if above > LIMIT_SCREEN:
            out.append(Problem('screen', f'{part.rel}:{tests_at or part.nlines}',
                               f'{above} lines above the tests (a screen is {LIMIT_SCREEN}): '
                               'shorten it or split it into child parts (SPEC §13)'))
        for file, n, section, text in part.loose:
            if section is None:
                how = ('the header holds the title, a `Why:` sentence on one line and settings, and reads nothing else: '
                       'join it to the Why line, or make it a bullet in a section')
            else:
                how = (f'make it {"a test" if section == "Tests" else "a bullet"} (`- **name** — …`), or indent it '
                       'under the item it continues')
            out.append(Problem('loose text', f'{file}:{n}', f'"{text[:50]}" is not an item, so it is not locked and a change to it '
                                                            f'goes unnoticed: {how}'))
        idle = [] if web else [t for t in part.items.values() if t.is_test and 'manual' not in _steps(t)
                               and _steps(t) & {'do', 'expect', 'each', 'measure'}]
        if idle:
            scan = scan or Scan(project)
            idle = [t for t in idle if not scan.regions_for(t.id)]   # code marked `@clause test` runs in its own framework
        left_to_ci = [t for t in idle if t.runs_on()]
        idle = [t for t in idle if not t.runs_on()]
        if left_to_ci:   # `manual:` is no way out for these: a CI job has to run them
            out.append(Problem('never run', f'{left_to_ci[0].file}:{left_to_ci[0].lineno}',
                               f'{len(left_to_ci)} test(s) of {part.key} say `runs on:` but have do:, expect:, each: or measure: '
                               f'lines that nothing will run ({listed((t.id for t in left_to_ci), 5)}): the project has no web '
                               "target, so `sor test` has no runner for them. Write them in the project's own framework, mark "
                               'their code `@clause test <id>`, and have the CI job report them with `sor evidence`'))
        if idle:
            out.append(Problem('never run', f'{idle[0].file}:{idle[0].lineno}',
                               f'{len(idle)} test(s) of {part.key} have do:, expect:, each: or measure: lines that nothing will '
                               f'run ({listed((t.id for t in idle), 5)}): the project has no web target, so `sor test` has no '
                               "runner for them. Add a `manual:` line saying what a person checks by hand, or write the test in "
                               "the project's own framework and mark its code `@clause test <id>`"))
        for item in part.items.values():
            # a table counts as one line, like everywhere in §13
            lines = sum(1 for _, t in item.lines if t.strip() and not t.strip().startswith('|'))
            lines += 1 if any(t.strip().startswith('|') for _, t in item.lines) else 0
            if item.is_test and lines > LIMIT_TEST_LINES:
                out.append(Problem('long test', f'{item.file}:{item.lineno}',
                                   f'{item.id}: {lines} lines (at most {LIMIT_TEST_LINES}); '
                                   'split it so each test proves one thing'))
            for n, words, text in ([] if item.is_test else bullet_words(item)):
                if words > LIMIT_WORDS:
                    name = f'"{text[:40]}…"' if item.draft else item.id
                    out.append(Problem('too long', f'{item.file}:{n}', f'{name}: {words} words (at most {LIMIT_WORDS}): '
                                                                       'say it shorter, or split it into two items (SPEC §13)'))
            for n, question in item.opens:
                out.append(Problem('open', f'{part.rel}:{n}', f'{item.id}: {question}'.rstrip()))
    out += value_twice(project)
    if len(project.target_names()) >= 2:
        out += no_code_for_target(project, scan or Scan(project))
    # The markers are read only when there is something to ask: a text that says where its code is, or a lock to compare with.
    if any(WHERE_CODE.search(_item_text(item)[0]) for part in project.parts.values() for item in part.items.values()
           if not item.is_test):
        scan = scan or Scan(project)
        out += code_location_sentences(project, scan)
    from . import lock as lockfile   # lazily: lock reads the markers, not the notes
    try:
        old = lockfile.read(project)
    except lockfile.LockFormatError:   # `sor check` works without a lock it cannot read (a newer format, a merge conflict, damage)
        old = {}
    if old:   # a clause is new or changed only against a lock
        keys = new_or_changed_items(project, old)
        out += code_waived(project, keys)
        if keys:
            scan = scan or Scan(project)
            out += no_code_yet(project, scan, keys)
    return sorted(out, key=_order)


def no_code_for_target(project, scan):
    """One note for each target that has no code for clauses another target has code for: `N clauses have code in py but none in
    ts`. It says nothing for a clause with no code at all (a rule such as `out-of-scope` has none anywhere), nothing in a project with
    one target, where every clause that has code has it there, and nothing about a target that does not apply to the clause (`Targets:`
    on its part). Code in no target is not counted for any."""
    names = project.target_names()
    where = scan.targets_with_code()   # clause key -> the targets that have code for it
    applies = {k: set(project.targets_applying_to(k)) for k in where}
    out = []
    for name in names:
        lacking = sorted(k for k, have in where.items() if name not in have and name in applies[k])
        if lacking:
            part = next(p for n, _, p in project.target_paths() if n == name)
            others = sorted({t for k in lacking for t in where[k]})
            out.append(Problem('no code for target', f'{part.rel}:1',
                               f'{len(lacking)} clause(s) have code in {", ".join(others)} but none in {name}: {listed(lacking, 5)}'))
    return out


def code_none_problems(project, scan):
    """A problem for a clause that says `code: none` and has code marked for it: it cannot be both, and a `code: none` that stays
    after the code is written would hide the clause from the checks that ask for code."""
    coded = {k for r in scan.regions if r.kind != 'test' for k in r.keys if not k.startswith('glue:')}
    out = []
    for item in project.items.values():
        if isinstance(item, Item) and item.no_code and ({item.id} | {r.id for r in item.rows.values()}) & coded:
            out.append(Problem('code none', f'{item.file}:{item.lineno}',
                               f'{item.id} says `code: none` but code is marked for it: remove the line, or take the markers away'))
    return out


def code_waived(project, keys):
    """One note per part for the clauses among `keys` (new or changed since the last lock) that say `code: none`: the one way to
    lock a clause with no code under `Require: code`, shown once so that a reviewer sees each exception when it is made."""
    by_part = {}
    for key in sorted(keys):
        item = project.items.get(key)
        if isinstance(item, Item) and item.no_code and not item.is_test and item.kind not in ('design', 'needs') and not item.draft:
            by_part.setdefault(item.part.key, []).append(item)
    out = []
    for part_key, items in by_part.items():
        first = min(items, key=lambda i: i.lineno)
        out.append(Problem('code waived', f'{first.file}:{first.lineno}',
                           f'{len(items)} clause(s) of {part_key} are new or changed and say `code: none`: '
                           f'{listed(sorted(i.id for i in items), 5)}. They are meant to have no code: check that is true'))
    return out


def new_or_changed_items(project, old):
    """The ids of the clauses (not tests) that the lock does not have, or has with another text: what `sor status` calls new or
    changed, found from the text hashes alone, so `sor check` does not work out the code of every clause."""
    from .lock import h   # lazily, like the lock itself in `notes`
    keys = []
    for part in project.parts.values():
        for item in part.items.values():
            if not item.is_test and (old.get(item.id) or {}).get('text') != h(item.text()):
                keys.append(item.id)
    return keys


def no_code_yet(project, scan, keys):
    """One note per part for the clauses among `keys` (new or changed since the last lock) that have no code at all, in any
    target: nothing in `sor check`, `sor status` or `sor lock` says so otherwise, because a clause without code is allowed (a
    rule such as `out-of-scope` has none) and the per-target note counts only a target that lacks code another has. It shows
    once, when the clause is new or changed; locking it (with no code) acknowledges it. Code that is not glue or a test, in a
    region or named by a `code:` line that resolves (its region), counts."""
    coded = {k for r in scan.regions if r.kind != 'test' for k in r.keys if not k.startswith('glue:')}
    by_part = {}
    for key in sorted(keys):
        item = project.items.get(key)
        if not isinstance(item, Item) or item.is_test or item.kind in ('design', 'needs') or item.draft or item.no_code:
            continue   # `code: none` says the clause is meant to have none; a `needs` line is no clause
        if not ({item.id} | {r.id for r in item.rows.values()}) & coded:
            by_part.setdefault(item.part.key, []).append(item)
    out = []
    for part_key, items in by_part.items():
        first = min(items, key=lambda i: i.lineno)
        out.append(Problem('no code', f'{first.file}:{first.lineno}',
                           f'{len(items)} clause(s) of {part_key} are new or changed and have no code in any target: '
                           f'{listed(sorted(i.id for i in items), 5)}. Mark their code `@clause <id>`, or lock them as they are if '
                           'they are meant to have none (a rule, a constraint)'))
    return out


# "Its code is ...", "The code is ...", "Their code is ...", "the code is marked ...": a sentence that says where the code is.
WHERE_CODE = re.compile(r'\b(?:[Ii]ts|[Tt]heir|[Tt]he) code (?:is|lives|sits)\b|\bcode is marked\b')
CODE_PATH = re.compile(r'`([^`\s]+\.[A-Za-z0-9]{1,5})`')
SENTENCE_END = re.compile(r'(?<![Ee]\.g)(?<![Ii]\.e)(?<=[a-z0-9`)])\.(?=\s+[A-Z`(]|\s*$)')


def _item_text(item):
    """The item's lines as one text, and where each line starts in it: a sentence may wrap onto the next line."""
    parts, starts, at = [], [], 0
    for n, text in item.lines:
        starts.append((at, n))
        parts.append(text.strip())
        at += len(parts[-1]) + 1
    return ' '.join(parts), starts


def _line_at(starts, offset):
    return [n for at, n in starts if at <= offset][-1]


def code_location_sentences(project, scan):
    """A note for an item whose text says where its code is and names a file that has code regions but none for this item.
    The place is written twice, in the text and in the `@clause` markers, and nothing else compares them, so one of them goes
    stale when code moves or a unit puts its code in another clause's region. `sor show <id>` prints the places from the
    markers: the sentence is better left out."""
    files = {}
    for r in scan.regions:
        if r.kind != 'test':
            files.setdefault(r.file, set()).update(r.keys)
    by_name = {}
    for f in files:
        by_name.setdefault(os.path.basename(f), []).append(f)
    out = []
    for part in project.parts.values():
        for item in part.items.values():
            if item.is_test:
                continue
            keys = {item.id} | {r.id for r in item.rows.values()}
            text, starts = _item_text(item)
            for m in WHERE_CODE.finditer(text):
                sentence = text[m.start():]
                end = SENTENCE_END.search(sentence)
                sentence = sentence[:end.end()] if end else sentence
                named = set()
                for path in CODE_PATH.findall(sentence):
                    plain = path[2:] if path.startswith('./') else path
                    for f in by_name.get(os.path.basename(path), []):
                        if f == plain or f.endswith('/' + plain):
                            named.add(f)
                wrong = sorted(f for f in named if not keys & files[f])
                if wrong:
                    out.append(Problem('code location', f'{item.file}:{_line_at(starts, m.start())}',
                                       f'{item.id} says its code is in {listed(wrong, 3)}, but the markers put none of its code '
                                       'there: `sor show` prints where it is, so leave the place out of the text, or fix whichever is wrong'))
    return out


def value_twice(project):
    """A note at every `{name: value}` that another part defines with the same name and the same text: one value written
    twice, so a change to one copy misses the other. Left out: tests (they restate numbers on purpose), table cells and
    `{v: = x}` aliases (those refer, they do not define), generated parts, and the same name with different texts (a
    generic `max` or a glossary's `term` is not a copy of anything)."""
    seen = {}   # (name, text) -> [(part id, item, line)]
    for part in project.parts.values():
        if not part.path.endswith('.md'):
            continue
        for item in part.items.values():
            if item.is_test:
                continue
            for name, value in item.values.items():
                if value.startswith('='):
                    continue
                line = next((n for n, t in item.lines if not t.strip().startswith('|')
                             and any(k == name for k, _ in VDEF.findall(CODE.sub('', t)))), item.lineno)
                seen.setdefault((name, ' '.join(value.lower().split())), []).append((part.id, item, line))
    out = []
    for (name, _), places in seen.items():
        if len({pid for pid, _, _ in places}) < 2:
            continue
        for pid, item, line in places:
            others = [o for o in places if o[0] != pid]
            where = ', '.join(o[1].id for o in others[:4]) + (f' and {len(others) - 4} more' if len(others) > 4 else '')
            out.append(Problem('value twice', f'{item.file}:{line}',
                               f'{{{name}: {item.values[name]}}} is also defined with the same value in {where}: keep one '
                               f'definition and refer to it from the others (`{{{others[0][1].id}.{name}}}`), or, if they are '
                               'different quantities, rename them so the names say what they are (SPEC §13)'))
    return out


def placeholders(project):
    """A problem for every line of every spec file that still holds template text (`<fill in ...>`).
    Lines inside ``` blocks and text inside `backticks` are examples, not unfilled text."""
    found = []
    for path in sorted(glob.glob(os.path.join(project.spec_dir, '**', '*.md'), recursive=True)):
        rel = os.path.relpath(path, project.spec_dir).replace(os.sep, '/')
        with open(path, encoding='utf8') as fh:
            lines = split_lines(fh.read())
        fenced = False
        for n, raw in enumerate(lines, 1):
            if raw.lstrip().startswith('```'):
                fenced = not fenced
            elif not fenced and SENTINEL in CODE.sub('', raw):
                found.append(Problem('placeholder', f'{rel}:{n}', 'unfilled template text: ' + raw.strip()[:80]))
    return found
