"""Views of a project that are printed and never stored, and the command that starts a part (SPEC §15).

    sor parts [--json] [--tree] [PART ...]  an index of every part: why, bullets per section, what it gives, open questions
    sor needs [PART] [--json]       what a part needs, derived from the {references} in its items
    sor changes [--json]            the changes pending since the last lock, in words
    sor new PART | --root [--why]   a skeleton part, or the root file, with <fill in: ...> where a person writes

The first three only read. Nothing is written into sor/, because every .md file there is a part.
"""
import glob
import json
import os
import re
import sys
import textwrap

from . import lock as lockfile
from . import lint
from .lint import bullet_counts
from .markers import Scan
from .model import CODE, FOLDER_FILE_NAME, ITEM, ROOT_FILE_NAME, SETTING, SPEC_DIR, Project, Row, has_spec, part_files, root_files, shown_path, test_keyword

WIDTH = 110   # the longest line these views print


def dump(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cut(text, width):
    """text cut to at most width characters, ending in … when it was longer."""
    return text if len(text) <= width else text[:width - 1].rstrip() + '…'


def dim(text):
    """Dimmed on a terminal, plain in a pipe or file (and when NO_COLOR is set)."""
    return f'\x1b[2m{text}\x1b[0m' if sys.stdout.isatty() and not os.environ.get('NO_COLOR') else text


def in_order(project):
    """Part ids: the root first, then by id."""
    return sorted(project.parts, key=lambda pid: (pid != '', pid))


def generated(part):
    """The part `design` is made from the design export, not from a spec file."""
    return not part.path.endswith('.md')


# --- sor parts ------------------------------------------------------------------------------------

def part_info(part):
    source = part.header.get('Source') or (f'code at {part.source_code}' if part.source_code else None)
    return {'id': part.key, 'title': part.title, 'why': part.header.get('Why', ''),
            'owner': part.header.get('Owner'), 'source': source, 'rel': part.rel,
            'bullets': {k.lower(): n for k, n in bullet_counts(part).items()},
            'gives': [i.name for i in part.items.values() if i.kind == 'gives'],
            'open': sum(len(i.opens) for i in part.items.values())}


def detail(info, room):
    """The dim line under a part: counts, what it gives, open questions, owner, where its code is."""
    counts = ' · '.join(f'{k} {n}' for k, n in info['bullets'].items())
    rest = [f'{info["open"]} open'] if info['open'] else []
    if info['owner']:
        rest.append(f'Owner: {info["owner"]}')
    if info['source'] and info['source'] != 'spec':
        rest.append(info['source'])
    gives = info['gives']
    line = ''
    for shown in range(len(gives), -1, -1):   # as many names as fit
        names = ', '.join(gives[:shown]) if shown else str(len(gives))
        more = f' +{len(gives) - shown} more' if 0 < shown < len(gives) else ''
        line = ' · '.join([counts] + ([f'gives {names}{more}'] if gives else []) + rest)
        if len(line) <= room:
            break
    return cut(line, room)


def tree_order(project):
    """The root first, then every part right after its parent: by the segments of its id, not by its characters
    (as text `a-b` sorts before `a/b`, which would split a part from its children)."""
    return sorted(project.parts, key=lambda pid: (pid != '', pid.split('/')))


def tree_label(pid, kids):
    """A part's name for the tree: indented by depth, only its last segment, and how many parts sit under it."""
    name = pid.rpartition('/')[2] if pid else 'ROOT'
    return '  ' * pid.count('/') + name + (f' ({kids[pid]})' if kids.get(pid) else '')


def cmd_parts(args, keep=None):
    """`keep` says which part ids to show (default: all): `sor parts audio` shows audio and the parts inside it."""
    project = Project(args.root)
    parts = [project.parts[pid] for pid in (tree_order(project) if args.tree else in_order(project)) if keep is None or keep(pid)]
    infos = [part_info(p) for p in parts]
    if args.json:
        dump(infos)
        return 0
    kids = lint.child_counts(project)
    labels = [tree_label(p.id, kids) if args.tree else i['id'] for p, i in zip(parts, infos)]
    idw = min(28, max((len(label) for label in labels), default=0))
    for part, info, label in zip(parts, infos, labels):
        print(cut(f'{label:<{idw}}  {info["why"] or info["title"]}', WIDTH))
        text = f'generated from {info["rel"]}' if generated(part) else detail(info, WIDTH - idw - 2)
        print(' ' * (idw + 2) + dim(text))
    print(f'{len(infos)} part{"" if len(infos) == 1 else "s"}')
    return 0


# --- sor needs ------------------------------------------------------------------------------------

def owners_of(project):
    """Item and row id -> the item it belongs to."""
    out = {}
    for item in project.all_items():
        out[item.id] = item
        for row in item.rows.values():
            out[row.id] = item
    return out


def origin(project, owners, target):
    """(part id, kind) of a resolved target: the part it lives in, and `part` or the kind of its item.
    A row or a value is of the kind of its item. Root items have ids without a prefix, so their part is ''."""
    if target in project.parts:
        return target, 'part'
    item = owners.get(target) or owners.get(target.rpartition('.')[0])
    return (item.part.id, item.kind) if item else ('', 'item')


def needs_of(project, owners, pid):
    """What part `pid` needs from other parts, found in the references of all its items (tests and an
    explicit `needs` item too). Leaves out its own part, its ancestors (words defined in the parent's
    files; the root is an ancestor of everything), its children (a part is made of them, it does not
    depend on them) and the generated part `design`."""
    part = project.parts[pid]
    declared = set()
    for item in part.items.values():
        if item.kind == 'needs':
            declared |= project.resolved_refs(item)[0]
    found = {}
    for item in part.items.values():
        for target in sorted(project.resolved_refs(item)[0]):
            tp, kind = origin(project, owners, target)
            # its own part, its ancestors (words it inherits), its children (it is made of them, not
            # dependent on them: the root's `parts` item and `Refined by`) and the design export are not needs
            if (tp == pid or tp == '' or pid.startswith(tp + '/') or pid == '' or tp.startswith(pid + '/')
                    or generated(project.parts[tp])):
                continue
            row = found.setdefault(target, {
                'part': tp, 'target': target, 'kind': kind, 'gives': kind == 'gives',
                'declared': any(target == d or target.startswith((d + '/', d + '.')) for d in declared),
                'from': []})
            row['from'].append(item.id)
    return sorted(found.values(), key=lambda r: (r['part'], r['target']))


def print_needs(name, rows):
    print(f'{name} needs:')
    label = {'gives': 'gives', 'part': 'part'}
    pw = max(len(r['part']) for r in rows)
    tw = max(len(r['target']) for r in rows) + 2
    kw = max(len(label.get(r['kind'], 'not a gives')) for r in rows)
    any_declared = any(r['declared'] for r in rows)
    for r in rows:
        target = '{' + r['target'] + '}'
        head = f'  {r["part"]:<{pw}}  {target:<{tw}}  {label.get(r["kind"], "not a gives"):<{kw}}  '
        if any_declared:
            head += f'{"declared" if r["declared"] else "":<8}  '
        print(textwrap.fill('— ' + ', '.join(r['from']), width=WIDTH, initial_indent=head,
                            subsequent_indent=' ' * len(head), break_long_words=False, break_on_hyphens=False))


def plural(n, one, many):
    return f'{n} {one if n == 1 else many}'


def cmd_needs(args):
    project = Project(args.root)
    owners = owners_of(project)
    if args.part is not None:
        found = project.find(args.part)
        if found is None or found[0] != 'part':
            print(f'{args.part}: no such part')
            return 2
        pids = [found[1].id]
    else:
        pids = in_order(project)
    result = [{'id': project.parts[pid].key, 'needs': needs_of(project, owners, pid)} for pid in pids]
    if args.part is None:
        result = [r for r in result if r['needs']]
    if args.json:
        dump(result)
        return 0
    for n, r in enumerate(result):
        if n:
            print()
        if r['needs']:
            print_needs(r['id'], r['needs'])
        else:
            print(f'{r["id"]} needs nothing from other parts')
    if args.part is None:
        if result:
            print()
        print(plural(len(result), 'part needs something', 'parts need something') if result
              else 'no part needs anything from another')
    return 0


# --- sor changes ----------------------------------------------------------------------------------

RETIRED = re.compile(r'\bretired:\s*(.*)', re.I)
PENDING = ('new', 'changed', 'removed')


def words(item):
    """The first line of an item's text without its `- **name** —` start, cut to 100 characters."""
    lines = [t for t in item.text().splitlines() if t.strip()]
    first = lines[0] if lines else ''
    m = ITEM.match(first)
    rest = first[m.end():] if m else first[2:] if first.startswith('- ') else first
    rest = re.sub(r'^\s*[—–:]\s*|^\s*-\s+', '', rest).strip()
    if not rest and len(lines) > 1:   # the name stands alone and its words follow on the next line
        rest = lines[1].strip()
    return cut(rest, 100)


def bugs_of(item):
    """The `bug:` texts of a test (`fixes:` and `regression:` count too)."""
    out = []
    for _, t in item.lines:
        kw = test_keyword(t)
        if kw and kw[0] == 'bug':
            out.append(kw[1])
    return out


def retired_in(item):
    """The words after `retired:` in an item's text: '' when nothing follows the marker, None when the
    item has no such marker. (`open:` lines are no part of the text.)"""
    for t in item.text().splitlines():
        masked = CODE.sub(lambda m: ' ' * len(m.group()), t)   # `retired:` inside backticks is an example
        m = RETIRED.search(masked)
        if m:
            return t[m.start(1):].strip()
    return None


def cmd_changes(args):
    project = Project(args.root)
    scan = Scan(project)
    old = lockfile.read(project)
    findings, _ = lockfile.status(project, scan, old)
    out = {'added': [], 'changed': [], 'removed': [], 'fixes': []}
    for f in findings:
        if f.status not in PENDING:
            continue
        found = project.find(f.key)
        if found:
            kind, o = found
            kind = 'test' if getattr(o, 'is_test', False) else kind
        else:   # removed: the lock still knows what it was; a marker with an id nobody wrote is no change of the spec
            kind, o = old.get(f.key, {}).get('kind'), None
        if kind not in ('part', 'item', 'row', 'test'):
            continue
        text = (f'part: {o.header.get("Why") or o.title}' if kind == 'part' else o.text if kind == 'row'
                else words(o)) if o else ''
        row = {'id': f.key, 'kind': kind, 'status': f.status, 'text': cut(text, 100)}
        bug = bugs_of(o) if kind == 'test' and f.status != 'removed' else []
        if bug:
            out['fixes'].append(dict(row, bug=bug))
        else:
            out[{'new': 'added'}.get(f.status, f.status)].append(row)
    out['retired'] = []
    for item in project.all_items():
        if item.kind != 'design':
            why = retired_in(item)
            if why is not None:
                out['retired'].append({'id': item.id, 'text': cut(why or words(item), 100)})
    if args.json:
        dump({'locked': bool(old), 'counts': {k: len(v) for k, v in out.items()}, **out})
        return 0
    if not old:
        print('no lock yet: everything is new')
    elif not any(out.values()):
        print('nothing pending')
        return 0
    for title, key in (('Added', 'added'), ('Changed', 'changed'), ('Removed', 'removed'),
                       ('Fixes', 'fixes'), ('Retired', 'retired')):
        rows = out[key]
        if not rows:
            continue
        print(f'{title} ({len(rows)})')
        if not old and key != 'retired':
            continue   # nothing is locked: counts say it all
        for r in rows:
            tail = f' — {r["text"]}' if r['text'] else ''
            if key == 'fixes':
                tail += f' (bug: {", ".join(r["bug"])})'
            print(f'  - {r["id"]}{tail}')
    if not old:
        print('`sor lock` accepts the current state.')
    return 0


# --- sor new --------------------------------------------------------------------------------------

PART_ID = re.compile(r'^[a-z][a-z0-9-]*(/[a-z][a-z0-9-]*)*$')
WHY = '<fill in: one sentence on why this part exists>'

# Hints are HTML comments at the start of a line, one line each, directly under their heading: they are
# not part of any item, hold no braces and no placeholder, so `sor check` reads them as nothing.
PART = '''# {title}
Why: {why}

## Rules
<!-- What must be true: goals, rules, numbers, budgets, words. If a user or a test could notice a change, it is a rule. At most {limit} items. -->
- **<fill in: name>** - <fill in: what must be true>.

## Approach
<!-- How it is built, and why that way. Put the reason on a "because:" line under the item. -->

## Contract
<!-- gives: what others may call. owns: data only this part changes. If another part would break when it changes, it belongs here. needs is optional: sor needs derives it. -->

## Tests
<!-- Name each test after the rule it proves. Lines: do:, expect:, bug: for a fixed bug, proves: for a second test of the same rule, manual: for a check by hand. -->
- **<fill in: name>** - <fill in: what the test shows>.
  expect: <fill in: the result>
'''

ROOT_FILE = '''# {title}
Why: {why}

## Rules
<!-- What must be true: goals, rules, numbers, budgets, words (speed, size, how easy it is to use). If a user or a test could notice a change, it is a rule. At most {limit} items. -->
- **out-of-scope** - <fill in: what the project will not do>.

## Approach
<!-- How it is built, and why that way. Put the reason on a "because:" line under the item. List the parts in "parts", one line each. -->
- **parts** - <fill in: the subsystems, one line each>.
'''


NOUN = {'Rules': 'rule', 'Approach': 'approach item', 'Contract': 'contract item'}   # what an item is called, by section


def title_of(name):
    """`render-queue` -> `Render queue`."""
    text = ' '.join(w for w in name.split('-') if w) or 'Project'
    return text[0].upper() + text[1:]


def skeleton(pid, project_dir, why=None):
    """The text `sor new` writes for the part `pid` ('' for the root, titled after the project folder). why is
    the sentence given to --why; without one the Why: line is a placeholder. The edit guard compares with this."""
    text, name = (PART, pid.rpartition('/')[2]) if pid else (ROOT_FILE, os.path.basename(project_dir))
    return text.format(title=title_of(name), why=' '.join((why or '').split()) or WHY, limit=lint.LIMIT_ITEMS)


def refuse(*lines):
    for line in lines:
        print(line)
    return 2


def named(project, ident):
    """Where the item or row `ident` is written, in words: `the rule **mixer** in audio.md`."""
    o = project.items[ident]
    if isinstance(o, Row):
        item = next(i for i in project.all_items() if o in i.rows.values())   # a row's name may hold a `/`
        return f'the row **{o.name}** of **{item.name}** in {item.file}'
    return f'the {NOUN.get(o.section, "item")} **{o.name}** in {o.file}'


def cmd_new(args):
    if bool(args.part) == bool(args.make_root):
        return refuse('new: give a PART or --root, not both' if args.part else
                      'new: give a PART (sor new render) or --root (the root file of a new project)')
    pid = args.part
    if pid and not PART_ID.match(pid):
        return refuse(f'{pid}: not a part id. Use lowercase words joined by `-`, and `/` to put one part inside '
                      'another, e.g. render or render/culling-queue')
    setting = SETTING.search(args.why or '')
    if setting:   # the reader takes "Owner: x" after a full stop as a setting of its own, not as part of the sentence
        return refuse(f'--why: "{setting.group(1)}:" in the sentence would be read as a setting of the part. '
                      'Reword it, and set the owner and the like in the file afterwards. Nothing was written.')
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):   # a mistyped -C must not leave a stray tree behind
        return refuse(f'{args.root}: no such folder. Create it first (or check the -C path): nothing written')
    if os.path.basename(root) == SPEC_DIR and root_files(root):
        root = os.path.dirname(root)   # -C was given the spec folder itself
    found = has_spec(root)
    spec = os.path.join(root, SPEC_DIR)
    rel_root = f'{SPEC_DIR}/{ROOT_FILE_NAME}.md'
    if args.make_root:
        if found:
            return refuse(f'{rel_root} already exists: nothing written')
        path = os.path.join(spec, ROOT_FILE_NAME + '.md')
    else:
        if not found:
            return refuse(f'no project here: run sor new --root first ({rel_root} is missing)')
        segs = pid.split('/')
        path = os.path.join(spec, *segs) + '.md'
        if os.path.isfile(path):
            return refuse(f'{SPEC_DIR}/{pid}.md already exists: nothing written')
        folder = os.path.join(spec, *segs)
        if part_files(folder):
            return refuse(f'{pid} already exists as {os.path.relpath(part_files(folder)[0], root).replace(os.sep, "/")}: nothing written')
        project = Project(root)
        if pid in project.items:   # `sor check` would call it a collision (a part and an item with one id)
            return refuse(f'{pid} is already the id of an item: {named(project, pid)}. Ids share one namespace.',
                          'Two ways out: choose another name for the part, or rename that item first and run this again.',
                          'Nothing was written.')
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'x', encoding='utf8', newline='\n') as fh:   # 'x': never overwrites, even in a race
            fh.write(skeleton(pid or '', root, args.why))
    except FileExistsError:
        return refuse(f'{shown_path(path, root)} already exists: nothing written')
    except OSError as e:
        return refuse(f'cannot write {shown_path(path, root)}: {e.strerror or e}')
    print(f'wrote {shown_path(path, root)}')
    print('next: replace every <fill in: ...> with real words; give the rule and its test the same name')
    print('then: run `sor check`, it lists what is left to fill in')
    return 0
