"""The lock file, clauses-lock.json (SPEC §11), and the status it gives: what changed since the last lock, what
must be reviewed because something it refers to changed, and what code drifted from its clauses.

One entry per part, item, row, value and test:
    text    hash of its own text
    refs    {referenced id: that id's text hash} — any reference is a dependency
    code    hash of the code marked with it
    result  tests only: pass, fail, manual, deferred or none, as accepted by `sor lock`
            (deferred: the test says `runs on:`, so the CI jobs that provide those environments prove it, not this lock)
Sorted, one entry per line, no timestamps: identical input gives identical bytes.

The file has a format number. Format 1 has no marker, so a lock written before the number existed is format 1 and a project
that stays in format 1 keeps the same bytes. Format 2 opens the file with `"*format": 2` (no item, row, value, test or glue key
can start with `*`) and holds, for a clause with code in several targets, one line per target next to the clause's own:

    "greet/hello":    {"kind": "item", "refs": ..., "text": ...}
    "greet/hello@py": {"kind": "code", "of": "greet/hello", "target": "py", "code": ..., "built": ...}

`built` is the text hash of the clause the target's code was accepted for. In memory the lines are folded into the clause's
entry (`entry['targets'][target]`) and its `code` is the digest of its targets' code, so what compares the code of a clause goes
on working; `write` unfolds them again. A tool that reads a number it does not know stops and says to update itself.
"""
import glob
import hashlib
import json
import os
import shutil
import time

from .model import LEGACY_ROOT_KEY, Item, Problem, Row, listed, test_keyword



# What a test's entry may say. A lock refuses a test that is 'none' (not run) or 'fail'. The others are settled: it passed,
# a person looks at it (manual, checked), or it is left to the CI jobs that provide its environment (deferred).
SETTLED = ('pass', 'manual', 'checked', 'deferred')

FORMAT = 3                # the newest lock format this tool reads and writes
LINE_FIELDS = ('code', 'built')   # what a format 2 line holds; a line with more is format 3
LINE_KIND = 'code'        # the kind of a per-target line in the file
FORMAT_KEY = '*format'    # the marker of a format above 1: a scalar, so that a tool older than this one fails on it instead of dropping it


class LockFormatError(Exception):
    """The lock file is in a format this tool does not read."""


def h(s):
    return hashlib.sha256(s.encode('utf8')).hexdigest()[:12]


def snapshot(project, scan, lines=None):
    """The lock entries the files would produce right now. `lines`: whether a clause keeps its code per target (`targets`, and its
    `code` the digest of them) or in one joined hash; by default per target when the project says which targets its clauses apply
    to (`Project.targeted`)."""
    entries, text = {}, {}

    def put(key, kind, t):
        entries[key] = {'kind': kind, 'text': t}
        text[key] = t

    for p in project.parts.values():
        put(p.key, 'part', h(p.face()))
        for it in p.items.values():
            put(it.id, 'test' if it.is_test else 'item', h(it.text()))
            for r in it.rows.values():
                put(r.id, 'row', h(r.text))

    def value_hash(owner, name, val, guard):
        if val.startswith('='):  # an alias: it changes when the value it stands for changes
            target = owner_refs.get((owner.id, val[1:].strip()))
            if target and target not in guard:
                return h(val + '\x00' + value_text(target, guard | {target}))
        return h(val)

    values = {}
    owner_refs = {}
    for it in project.all_items():
        for n, ref in it.refs:
            hits = project.resolve(it.part.id, ref)
            if len(hits) == 1:
                owner_refs[(it.id, ref)] = hits[0]
                for r in it.rows.values():
                    owner_refs[(r.id, ref)] = hits[0]
        for name, val in it.values.items():
            values[f'{it.id}.{name}'] = (it, name, val)
        for r in it.rows.values():
            for name, val in r.values.items():
                values[f'{r.id}.{name}'] = (r, name, val)

    def value_text(key, guard):
        if key in values:
            owner, name, val = values[key]
            return value_hash(owner, name, val, guard)
        return text.get(key, '')

    for key in values:
        put(key, 'value', value_text(key, {key}))

    for it in project.all_items():
        targets = project.resolved_refs(it)[0]
        if targets:
            entries[it.id]['refs'] = {t: text.get(t, '') for t in sorted(targets)}
        if it.is_test:
            entries[it.id]['result'] = 'manual' if is_manual(it) else 'deferred' if it.runs_on() else 'none'
    per_target = scan.target_code_hashes() if (project.targeted() if lines is None else lines) else {}
    for key, c in scan.code_hashes().items():
        entry = entries.setdefault(key, {'kind': 'glue'})
        if key in per_target and entry['kind'] in ('item', 'row', 'part', 'test'):
            entry['targets'] = {t: {'code': code} for t, code in per_target[key].items()}
            entry['code'] = digest(entry['targets'])
            if entry['kind'] == 'test' and entry.get('result') == 'none':   # a manual test or one left to CI has no result to give
                for line in entry['targets'].values():
                    line['result'] = 'none'
        else:
            entry['code'] = c
    return entries


def conform(now, lock, scan):
    """`now` with each clause's code in the shape the lock keeps it, so that a clause is compared with itself and not with the other
    way of writing the same code: a lock made before the project said its targets keeps one joined hash, one made after keeps them
    per target. Only `code` and `targets` are touched, and `now` is changed in place."""
    per_target = None
    for key, a in now.items():
        b = lock.get(key)
        if not b or a.get('kind') not in ('item', 'row', 'part', 'test'):
            continue
        if b.get('targets') and not a.get('targets'):
            per_target = per_target if per_target is not None else scan.target_code_hashes()
            if key in per_target:
                a['targets'] = {t: {'code': code} for t, code in per_target[key].items()}
                a['code'] = digest(a['targets'])
        elif a.get('targets') and not b.get('targets'):
            del a['targets']
            a['code'] = scan.code_hashes()[key]     # the same regions as the per-target hashes, so the key is there
    return now


def without_built(entry):
    """An entry as it is compared when `built` does not count: a snapshot has no `built`, the lock has."""
    if not entry or not entry.get('targets'):
        return entry
    return dict(entry, targets={t: {'code': line.get('code')} for t, line in entry['targets'].items()})


def line_collisions(project, scan):
    """Problems for a clause whose per-target lock line `K@t` would be the key of something else: the lock could not tell them apart.
    Only a project that keeps its code per target has such lines."""
    if not project.targeted():
        return []
    entries = snapshot(project, scan)
    out = []
    for key, e in entries.items():
        for t in e.get('targets') or {}:
            if f'{key}@{t}' in entries:
                out.append(Problem('collision', key, f'{key}@{t} is also the name of something else, and it is the lock line for the code '
                                                    f'of {key} in {t}: rename one of them'))
    return out


def moved_targets(a, b):
    """The targets whose code is not the same in these two entries of a clause (both per target), sorted."""
    ta, tb = a.get('targets') or {}, b.get('targets') or {}
    return sorted(t for t in set(ta) | set(tb) if ta.get(t, {}).get('code') != tb.get(t, {}).get('code'))


def basis_of(project, entries, key):
    """What a language's `built` is compared with for one clause: its text hash, and for an item with a table also the text hash of each
    row that has no code of its own per target (the cells of a row are not in the item's text, and a table's code is usually marked with
    the item, so a changed cell is a change to that code). A row with lines of its own is behind on its own."""
    item = project.items.get(key)
    rows = sorted(r.id for r in item.rows.values() if r.id in entries and not entries[r.id].get('targets')) \
        if isinstance(item, Item) else []
    text = (entries.get(key) or {}).get('text')
    return h('\n'.join([text or ''] + [entries[r].get('text', '') for r in rows])) if rows else text


def bases(project, entries):
    """{key: `basis_of`} for the clauses that have code per target."""
    return {key: basis_of(project, entries, key) for key, e in entries.items() if e.get('targets')}


def lagging_targets(project, key, entry, owners, basis):
    """The targets of a locked clause that apply to it and whose code was accepted for an older text of the clause than the locked
    one (`built` is not the clause's `basis`): they are behind, and say that the clause was changed without their code."""
    applicable = project.targets_of_part(owners.get(key))
    return sorted(t for t, line in (entry.get('targets') or {}).items()
                  if t in applicable and line.get('built') != basis.get(key, entry.get('text')))


def unbuilt_targets(project, key, entry, owners):
    """The targets that apply to a locked clause and have no line in the lock: it was locked without code in them (`--allow-behind`), so
    code that arrives in one is the first code of that language and not a change to what was accepted."""
    applicable = project.targets_of_part(owners.get(key))
    return sorted(t for t in applicable if t not in (entry.get('targets') or {}))


def old_rule_keys(lock, scan):
    """{lock key: the hash it would have now} for entries whose code hash was made with the rule every file followed before the rule
    followed the file type (see `markers.style_of`) and whose code has not changed under that rule. They are not changes: the next
    `sor lock` (or `sor lock --rehash`) writes the new hash. Empty when no file has a rule of its own, which is every project
    whose code is C-family, HTML or of a type that is not listed."""
    if not lock or not getattr(scan, 'has_own_rules', lambda: False)():
        return {}
    new = scan.code_hashes()
    differ = [k for k, e in lock.items() if e.get('code') and not e.get('targets') and new.get(k) not in (None, e['code'])]
    if not differ:   # every hash agrees: the old rule need not be worked out
        return {}
    legacy = scan.code_hashes(legacy=True)
    return {k: new[k] for k in differ if legacy.get(k) == lock[k]['code']}


def upgrade(lock, scan):
    """The lock with the hashes of `old_rule_keys` replaced by the ones the code has now, so that what the old rule did not see
    as a change is not one. Anything the old rule did see as a change stays a change."""
    stale = old_rule_keys(lock, scan)
    return dict(lock, **{k: dict(lock[k], code=h) for k, h in stale.items()}) if stale else lock


def format_problem(project, path, number):
    """The refusal for a lock whose marker is `number`, or None when this tool reads it."""
    rel = os.path.relpath(path, project.root).replace(os.sep, '/')
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        return (f'{rel} has {FORMAT_KEY} {json.dumps(number)}, which is not a lock format number (a whole number from 1 up). '
                'The file may be damaged. Nothing was changed.')
    if number > FORMAT:
        return (f'{rel} is in lock format {number}, and this sor reads format {FORMAT} at most. Update sor, every copy of it '
                '(the project\'s tools, the plugin and the editor extension), and try again. Nothing was changed.')
    return None


def load(project):
    """(path, entries) of the lock there is, without its format marker. Raises LockFormatError for a format this tool does not
    read, so that nothing reads, and nothing rewrites, a lock it would misread."""
    path = existing_path(project)
    if not path:
        return None, {}
    with open(path, encoding='utf8') as fh:
        data = json.load(fh)
    if isinstance(data, dict) and FORMAT_KEY in data:
        problem = format_problem(project, path, data.pop(FORMAT_KEY))
        if problem:
            raise LockFormatError(problem)
    return path, data


def read(project):
    path, data = load(project)
    if not path:
        return {}
    # A lock written before the root was called ROOT keeps it under CLAUSES. Every reader sees ROOT, with the
    # same entry, so nothing counts as changed; the next lock writes it back under the new key.
    if LEGACY_ROOT_KEY in data and project.root_key not in data:
        data[project.root_key] = data.pop(LEGACY_ROOT_KEY)
    return fold(data)


def derived_result(targets):
    """The result of a test that keeps one per language (a line with `result`): `fail` if one failed, `pass` if all passed, else `none`. It is
    worked out when the lock is read and not written, so every reader of a test's `result` goes on reading one."""
    results = [line['result'] for line in targets.values() if 'result' in line]
    return 'fail' if 'fail' in results else 'pass' if results and all(r == 'pass' for r in results) else 'none'


def digest(targets):
    """The `code` of a clause that has its code per target: a hash of the targets' hashes, in the order of their names."""
    return h('\n'.join(f'{t}:{targets[t]["code"]}' for t in sorted(targets)))


def fold(data):
    """The lock as the tool works with it: each per-target line `K@t` of the file (kind `code`) goes into the entry of its clause as
    `targets[t]` = {code, built}, and the clause's `code` becomes the digest of its targets'. A line whose clause is not in the
    file has nothing to belong to and is dropped."""
    out, lines = {}, []
    for k, e in data.items():
        if isinstance(e, dict) and e.get('kind') == LINE_KIND:
            lines.append(e)
        else:
            out[k] = e
    for e in lines:
        parent = out.get(e.get('of'))
        if isinstance(parent, dict) and isinstance(e.get('target'), str):
            parent.setdefault('targets', {})[e['target']] = {x: v for x, v in e.items() if x not in ('kind', 'of', 'target')}
    for e in out.values():
        if isinstance(e, dict) and e.get('targets'):
            e['code'] = digest(e['targets'])
            if e.get('kind') == 'test' and any('result' in line for line in e['targets'].values()):
                e['result'] = derived_result(e['targets'])
    return out


def unfold(entries):
    """The entries as the file holds them: a clause that has code per target loses its `code` and `targets`, and each target gets
    a line `K@t` of its own. Refuses an id that is already a key."""
    out = {}
    for k, e in entries.items():
        targets = e.get('targets') if isinstance(e, dict) else None
        if not targets:
            out[k] = e
            continue
        out[k] = {x: v for x, v in e.items() if x not in ('targets', 'code')}
        if any('result' in line for line in targets.values()):
            out[k].pop('result', None)   # derived from its lines when the lock is read
        for t, line in targets.items():
            if f'{k}@{t}' in entries:
                raise LockWriteError(f'{k}@{t} is a clause of its own and also the lock line for the code of {k} in {t}: rename one of them')
            out[f'{k}@{t}'] = dict({'kind': LINE_KIND, 'of': k, 'target': t}, **line)
    return out


class LockWriteError(Exception):
    """The lock file cannot be written."""


def existing_path(project):
    """The lock file there is: sor-lock.json, else an older clauses-lock.json, else None."""
    for p in (project.lock_path, project.legacy_lock_path):
        if os.path.isfile(p):
            return p
    return None


def check_writable(project):
    """Refuse, naming no version control, when the lock file exists but is read-only. Some environments
    keep files read-only until they are opened for edit; replacing the file would bypass that."""
    p = existing_path(project) or project.lock_path
    if os.path.exists(p) and not os.access(p, os.W_OK):
        raise LockWriteError(f'{os.path.relpath(p, project.root).replace(os.sep, "/")} is read-only: make it writable (your version control may '
                             'need it opened for edit), then try again')


def render(entries, fmt=None):
    """The text of a lock file: a format above 1 opens with its marker, then one entry per line, sorted. The format follows the
    entries: 3 when a line of a language holds more than `code` and `built` (it was confirmed to fit), 2 when a clause has code per
    target, else 1. A caller cannot name a lower one than the entries need."""
    needed = 1
    for e in entries.values():
        if isinstance(e, dict) and e.get('targets'):
            needed = max(needed, 3 if any(set(line) - set(LINE_FIELDS) for line in e['targets'].values()) else 2)
    fmt = needed if fmt is None else fmt
    if fmt > FORMAT:
        raise ValueError(f'lock format {fmt} is newer than this tool ({FORMAT})')
    if fmt < needed:
        raise ValueError(f'these entries need lock format {needed}, not {fmt}')
    entries = unfold(entries)
    lines = [json.dumps(k, ensure_ascii=False) + ': ' +
             json.dumps(entries[k], sort_keys=True, separators=(', ', ': '), ensure_ascii=False)
             for k in sorted(entries)]
    if fmt > 1:
        lines.insert(0, json.dumps(FORMAT_KEY) + ': ' + str(fmt))
    return '{\n' + ',\n'.join(lines) + '\n}\n'


def write(project, entries, fmt=None):
    """Writes the lock, in the format its entries need (`render`). Refuses to replace a lock that a newer sor wrote since it was read."""
    text = render(entries, fmt)
    # Through a temp file and os.replace: a reader (the edit hook, an editor, another agent's
    # `sor status`) sees the old lock or the new one, never half of one.
    check_writable(project)
    try:
        load(project)
    except (OSError, ValueError):
        pass   # a lock that cannot be read is replaced, as it always was; only a newer format stops the write
    for old in glob.glob(project.lock_path + '.*.tmp'):   # left behind by a write that crashed
        try:
            if time.time() - os.path.getmtime(old) > 300:
                os.remove(old)
        except OSError:
            pass
    tmp = f'{project.lock_path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf8', newline='\n') as fh:
        fh.write(text)
    had = existing_path(project)
    if had:
        shutil.copymode(had, tmp)   # keep the permissions the file had
    os.replace(tmp, project.lock_path)
    if had and had != project.lock_path:   # an older clauses-lock.json is replaced by sor-lock.json
        try:
            os.remove(had)
        except OSError:
            pass


def own_test(key):
    """The lock key of the test named after an item: camera/limits → camera/test:limits."""
    part, _, name = key.rpartition('/')
    return f'{part}/test:{name}' if part else f'test:{name}'


def language_keys(project, clause):
    """The lock keys that a claim or a lock of one language of a clause covers (SPEC §16): the clause, its rows (a row can have code of its own
    in a language) and its own test, last, since what it proves is settled by the code before it. What each of them holds in that language is
    its line `key@language`."""
    item = project.items.get(clause)
    return [clause] + ([r.id for r in item.rows.values()] if isinstance(item, Item) else []) + [own_test(clause)]


class Finding:
    """One line of `sor status`."""

    def __init__(self, status, key, detail='', where=''):
        self.status, self.key, self.detail, self.where = status, key, detail, where

    def as_dict(self):
        return {k: v for k, v in vars(self).items() if v}


GROUPS = [
    ('recompile', ('new', 'changed', 'removed', 'behind'), 'clauses changed since the last lock: build their code; behind: the code of a target is for an older text of the clause'),
    ('review', ('stale', 'shared'), 'something they refer to, or code they share, changed: check they still hold'),
    ('drift', ('drift',), 'code changed but its clause did not: if a person changed it, update the clause to say what the code now does; if you did, revert it and change the clause first'),
    ('built', ('built', 'fixing'), 'locked without code and built now, or fixed against a failing test'),
    ('info', ('code-changed', 'glue'), 'code changed for a reason above, or where that is allowed'),
]


def status(project, scan, lock):
    """Findings, comparing the files now with the lock."""
    lock = upgrade(lock, scan)
    now = conform(snapshot(project, scan), lock, scan)
    lock_basis = bases(project, lock)
    hand = {p.key: p for p in project.parts.values() if p.source_code}
    owner_part = {}
    for p in project.parts.values():
        owner_part[p.key] = p
        for it in p.items.values():
            owner_part[it.id] = p
            for r in it.rows.values():
                owner_part[r.id] = p

    def where(key):
        return ', '.join(r.where for r in scan.regions_for(key))

    def where_in(key, targets):
        """Where the code of a clause is in these targets (all of it when the project has no targets)."""
        if not targets:
            return where(key)
        return ', '.join(r.where for r in scan.regions_for(key) if (project.target_of(r.file) or '*') in targets)

    def code_note(key, a, b):
        if 'code' not in b and 'code' not in a:
            return ''
        if a.get('targets') and b.get('targets'):
            moved = moved_targets(a, b)
            unmoved = sorted(t for t in a['targets'] if t not in moved)
            if moved and unmoved:
                return f'code updated in {", ".join(moved)} · not yet in {", ".join(unmoved)}'
            return 'code updated' if moved else f'code not updated yet in {", ".join(unmoved)}'
        return 'code updated' if a.get('code') != b.get('code') else 'code not updated yet'

    def changed_values(key):
        out = []
        for k in sorted(set(now) | set(lock)):
            if k.startswith(key + '.') and '/' not in k[len(key) + 1:]:
                if now.get(k, {}).get('text') != lock.get(k, {}).get('text'):
                    out.append(k[len(key) + 1:])
        return out

    findings = []
    for key in sorted(set(now) | set(lock)):
        a, b = now.get(key), lock.get(key)
        kind = (a or b).get('kind')
        if kind == 'value':
            continue  # reported with the item or row that holds it
        if b is None:
            findings.append(Finding('new', key, '', where(key)))
            continue
        if a is None:
            findings.append(Finding('removed', key, 'delete its code' if b.get('code') else ''))
            continue
        if a.get('text') != b.get('text'):
            vals = changed_values(key)
            detail = ' · '.join(x for x in [('values: ' + ', '.join(vals)) if vals else '',
                                             code_note(key, a, b)] if x)
            findings.append(Finding('changed', key, detail, where(key)))
        elif a.get('refs', {}) != b.get('refs', {}):
            ra, rb = a.get('refs', {}), b.get('refs', {})
            moved = [t for t in sorted(set(ra) | set(rb)) if ra.get(t) != rb.get(t)]
            detail = 'refers to ' + ', '.join(moved) + ' (changed)'
            note = code_note(key, a, b)
            findings.append(Finding('stale', key, detail + (' · ' + note if note else ''), where(key)))
        elif a.get('code') != b.get('code'):
            moved = moved_targets(a, b) if a.get('targets') and b.get('targets') else []
            late = lagging_targets(project, key, b, owner_part, lock_basis) if moved else []
            first = [t for t in unbuilt_targets(project, key, b, owner_part) if t in moved]   # a language the clause was locked without
            if 'code' not in b:
                findings.append(Finding('built', key, 'first code for a locked clause', where(key)))
            elif moved and set(moved) <= set(late) | set(first):   # the code of the targets that are behind is being rebuilt: not drift
                findings.append(Finding('behind', key, ', '.join(moved) + (' (first code)' if not late else ' (being rebuilt)'), where_in(key, moved)))
            elif kind == 'glue':
                findings.append(Finding('glue', key, '', where(key)))
            elif owner_part.get(key) and owner_part[key].key in hand:
                anchored = [r.target for r in scan.regions_for(key) if r.kind == 'anchor']
                detail = (f'its code changed ({", ".join(anchored)}): check the clause still holds'
                          if anchored else 'hand-written code')
                findings.append(Finding('code-changed', key, detail, where(key)))
            elif any(lock.get(t, {}).get('result') in ('fail', 'none') for t in project.tests_of(key, regressions_only=True)):
                # its own test, or a bug test that proves it, did not pass at the last lock: the code is being fixed
                # against it. A test of another item that merely refers to it does not keep its code free for good.
                findings.append(Finding('fixing', key, 'its test did not pass at the last lock', where(key)))
            else:
                findings.append(Finding('drift', key, ', '.join(moved), where_in(key, moved) or where(key) or 'code removed'))
    # a locked clause whose text has not changed, but whose code in a target was accepted for an older text
    seen = {f.key for f in findings}
    for key, b in sorted(lock.items()):
        a = now.get(key)
        if a is None or key in seen or not b.get('targets') or a.get('text') != b.get('text'):
            continue
        late = [t for t in lagging_targets(project, key, b, owner_part, lock_basis) if t in (a.get('targets') or {})]
        if late:
            findings.append(Finding('behind', key, ', '.join(late), where_in(key, late)))
    # A table's code is usually marked with the item, not each row: a changed, added or removed
    # row is a change to that code. The row's own line points at it.
    rows_changed = {}
    for f in findings:
        if f.status in ('new', 'changed', 'removed', 'built') and (now.get(f.key) or lock.get(f.key, {})).get('kind') == 'row':
            item = f.key.rsplit('/', 1)[0]
            rows_changed.setdefault(item, []).append(f.key.rsplit('/', 1)[1])
            if not f.where and where(item):
                a, b = now.get(item, {}), lock.get(item, {})
                note = 'code updated' if a.get('code') != b.get('code') else 'code not updated yet'
                f.detail = ' · '.join(x for x in [f.detail, f'{note} (in {item})'] if x)
                f.where = where(item)
    for f in findings:
        if f.status == 'drift' and f.key in rows_changed:
            f.status, f.detail = 'changed', 'rows changed: ' + ', '.join(rows_changed[f.key]) + ' · code updated'
    # A test that changed first allows its item's code to change: the bug-fix path. Any test that proves the
    # item counts (SPEC §8): the one named after it, or one whose `expect:` refers to it, a value or a row of it.
    tests_changed = {f.key for f in findings if f.status in ('new', 'changed')}
    for f in findings:
        if f.status == 'drift' and tests_changed & set(project.tests_of(f.key)):
            f.status, f.detail = 'fixing', 'its test changed first'
    # A region marked with several ids may change for any of them. The other ids are not drift,
    # but they are not free either: each must be reviewed, and its own test must pass again.
    explained = {f.key for f in findings if f.status in ('new', 'changed', 'stale', 'built', 'fixing', 'behind')}
    for f in findings:
        if f.status == 'drift':
            shared = {k for r in scan.regions_for(f.key) for k in r.keys} & explained
            if shared:
                test = own_test(f.key)
                need = f'its test {test} must pass again' if test in now else 'review it: it has no test'
                f.status, f.detail = 'shared', f'code changed with {", ".join(sorted(shared))}; {need}'
    not_passed = sorted(k for k, e in now.items() if e.get('kind') == 'test'
                        and k in lock and lock[k].get('result') not in SETTLED)
    return findings, not_passed


def checked_manual(project, scan, old):
    """Manual tests a person confirmed at the last lock that still stand: the test reads the
    same and the code of the item it checks did not change since."""
    old = upgrade(old, scan)
    now, out = conform(snapshot(project, scan), old, scan), set()
    for key, e in old.items():
        n = now.get(key)
        if e.get('result') != 'checked' or n is None:
            continue
        if n.get('text') != e.get('text') or n.get('refs', {}) != e.get('refs', {}):
            continue
        item = key.replace('test:', '', 1)
        if now.get(item, {}).get('code') != old.get(item, {}).get('code'):
            continue
        out.add(key)
    return out


def built_for(project, entries, old):
    """Fills in `built` for the keys of `entries` that have code per target: a target whose code is new or changed since `old` was
    accepted for the clause as it is now (`bases`), one whose code is the same is still built for what it was."""
    now_basis, old_basis = bases(project, entries), bases(project, old or {})
    for key, e in entries.items():
        if not e.get('targets'):
            continue
        prior = ((old or {}).get(key) or {}).get('targets') or {}
        for t, line in e['targets'].items():
            if t in prior and prior[t].get('code') == line['code']:
                line.update({x: v for x, v in prior[t].items() if x not in ('code', 'result')})
                line['built'] = prior[t].get('built', old_basis.get(key))
                if line['built'] != now_basis[key]:
                    line.pop('fits', None)   # confirmed for an older text of the clause: it says nothing about this one
            else:
                line['built'] = now_basis[key]


def confirm_fits(project, entries, keys, owners, languages):
    """Marks the languages of the clauses among `keys` that are behind and are named in `languages` as built for the clause as it is now,
    and as confirmed rather than rebuilt (`fits`). Returns [(key, [targets])] of what it marked."""
    marked, basis = [], bases(project, entries)
    for key in sorted(keys):
        e = entries.get(key) or {}
        late = [t for t in lagging_targets(project, key, e, owners, basis) if t in languages]
        for t in late:
            e['targets'][t]['built'] = basis[key]
            e['targets'][t]['fits'] = True
        if late:
            marked.append((key, late))
    return marked


def confirmed_fits(project, lock):
    """[(key, [targets])] of the clauses whose code in a language was confirmed to fit the clause as it is (`fits`, and built for its
    current text) and not rebuilt: what `sor status` keeps naming."""
    basis, out = bases(project, lock), []
    for key in sorted(lock):
        e = lock[key]
        langs = sorted(t for t, line in (e.get('targets') or {}).items() if line.get('fits') and line.get('built') == basis.get(key))
        if langs:
            out.append((key, langs))
    return out


def behind_after(project, entries, keys, owners, allowed):
    """[(key, [targets])] of the clauses among `keys` that would stay behind in `entries` and are not allowed to."""
    out, basis = [], bases(project, entries)
    for key in sorted(keys):
        e = entries.get(key) or {}
        late = [t for t in lagging_targets(project, key, e, owners, basis) if t not in allowed]
        if late:
            out.append((key, late))
    return out


CODE_BUILT = ('new', 'changed', 'built')   # the findings of a clause that is new, changed, or built now after being locked without code


def no_code_after(project, scan, findings, keys, allowed):
    """[(key, [targets])] of the clauses among `keys` that are being locked with a change of their own (CODE_BUILT) and have code in
    some target but none in a target that applies to them (`Targets:`), and that are not allowed to. Only a project that says its
    targets is asked, and only a clause with a change of its own: a project that adds a second target does not find every clause it
    has locked refused, a bug fix in old code is not told to add the other language, and what stays unbuilt shows in the note
    of `sor status` (`lint.no_code_for_target`), which counts the same way."""
    if not project.targeted():
        return []
    have = scan.targets_with_code()
    out = []
    for key in sorted({f.key for f in findings if f.status in CODE_BUILT} & set(have) & set(keys)):
        late = sorted(t for t in project.targets_applying_to(key) if t not in have[key] and t not in allowed)
        if late:
            out.append((key, late))
    return out


def owner_parts(project):
    """{key: the part that holds it} for every part, item and row."""
    owners = {}
    for p in project.parts.values():
        owners[p.key] = p
        for it in p.items.values():
            owners[it.id] = p
            for r in it.rows.values():
                owners[r.id] = p
    return owners


def result_language(key, languages, bare=None):
    """(language, reason) for a result given as `test` or `test@language` when the test has test code in `languages` (sorted names; none when it has
    no test code per language). The language is '' for a test with none, whose one result is the test's. The reason is None, or why the key names no
    result: the lock and the evidence a CI job writes read their results by this rule. `bare`: the language a plain `test` stands for when the
    results come from the run of that language (`sor test --targets`)."""
    base, _, target = key.partition('@')
    if not languages:
        return '', (f'results: {key}: {base} has no test code per language, so it has one result: {base}' if target else None)
    if bare and not target:
        return (bare, None) if bare in languages else \
            ('', f'results: {key}: the test code of {base} is in {", ".join(languages)}, not in {bare}')
    if target:
        return (target, None) if target in languages else \
            ('', f'results: {key}: the test code of {base} is in {", ".join(languages)}, not in {target}')
    if len(languages) > 1:
        return '', (f'results: {base} has test code in {", ".join(languages)}: give a result for each, '
                    + ', '.join(f'{base}@{t}' for t in languages))
    return languages[0], None


def accept(project, scan, results, allow_incomplete, findings=(), old=None, confirm=(), scope=None, allow_behind=(), already_fits=()):
    """The entries `sor lock` would write, or the reasons it refuses. `confirm` names manual
    tests a person has just checked; earlier confirmations carry over while they still stand.
    `scope`: lock keys to accept; every other key keeps its entry from `old` (SPEC §11).
    `allow_behind`: targets that may stay behind the clause, or lack code for it (`sor lock --allow-behind`).
    `already_fits`: targets whose code was checked against the changed clause and needs no change (`sor lock --already-fits`): they are
    marked built for it and confirmed, and nothing is behind for them."""
    old = upgrade(old, scan) if old else old
    entries = snapshot(project, scan)
    built_for(project, entries, old)
    if scope is not None:
        full = entries
        entries = {k: dict(v) for k, v in (old or {}).items()}
        for k in scope:
            if k in full:
                entries[k] = full[k]
                refs = dict(full[k].get('refs', {}))
                for target in refs:
                    # A clause outside the scope may have a change nobody locked yet. Reviewing this
                    # clause against it now would absorb that change: keep the old hash, so this
                    # clause is flagged for review once the other one is locked.
                    if target not in scope and target in (old or {}):
                        refs[target] = old[target].get('text', refs[target])
                if refs:
                    entries[k] = dict(full[k], refs=refs)
            else:
                entries.pop(k, None)
    reasons = []
    owners = owner_parts(project)
    keys = entries if scope is None else scope
    if already_fits:
        clash = sorted(set(already_fits) & set(allow_behind))
        if clash:
            reasons.append(f'{", ".join(clash)} is named by --allow-behind and by --already-fits: say either "not rebuilt yet" or "needs no change"')
        elif not confirm_fits(project, entries, keys, owners, set(already_fits)):
            reasons.append(f'--already-fits {",".join(already_fits)}: nothing to confirm, no clause being locked has code in '
                           f'{", ".join(already_fits)} that is behind')
    for key, late in behind_after(project, entries, keys, owners, set(allow_behind)):
        reasons.append(f'behind  {key}  its code in {", ".join(late)} was accepted for an older text of the clause: rebuild it '
                       f'(change that code). Only when the user has said that {", ".join(late)} is rebuilt later, lock again with '
                       '--allow-behind <language>; it then stays listed as behind')
    for key, late in no_code_after(project, scan, findings, entries if scope is None else scope, set(allow_behind)):
        reasons.append(f'no code  {key}  it applies to {", ".join(late)} (`Targets:`) and has no code there: add the code, or limit its part '
                       f'with `Targets:`. Only when the user has said that {", ".join(late)} comes later, lock again with '
                       '--allow-behind <language>; the note of `sor status` keeps listing it')
    still = checked_manual(project, scan, old or {})
    for key in confirm:
        if scope is not None and key not in scope:
            reasons.append(f'--confirm: {key} is outside the clauses being locked')
        elif entries.get(key, {}).get('result') != 'manual':
            reasons.append(f'--confirm: {key} is not a manual test')
    for key, e in entries.items():
        if e.get('result') == 'manual' and (key in confirm or key in still):
            e['result'] = 'checked'
    for key, res in results.items():
        base, _, target = key.partition('@')   # `greet/test:hello@py`: the result of the test code in one language
        if scope is not None and base not in scope:
            continue   # a run of all tests also reports the tests of clauses that are not being locked
        entry = entries.get(base)
        if entry is None or entry.get('kind') != 'test':
            reasons.append(f'results: {key} is not a test')
            continue
        lines = {t: line for t, line in (entry.get('targets') or {}).items() if 'result' in line}
        if not lines and entry.get('result') in ('manual', 'checked', 'deferred'):
            continue   # a person or a CI job settles it: a result given for it, bare or for a language, is not read (the lock says so for `runs on:`)
        language, why = result_language(key, sorted(lines))
        if why:
            reasons.append(why)
        elif lines:
            lines[language]['result'] = res if res in ('pass', 'fail') else 'none'
        elif entry['result'] not in ('manual', 'checked', 'deferred'):   # a result never settles what CI proves
            entry['result'] = res if res in ('pass', 'fail') else 'none'
    for entry in entries.values():
        if entry.get('kind') == 'test' and any('result' in line for line in (entry.get('targets') or {}).values()):
            entry['result'] = derived_result(entry['targets'])
    for f in findings:
        test = own_test(f.key)
        if f.status == 'shared' and test in entries and entries[test]['result'] not in SETTLED:
            reasons.append(f'shared  {f.key}  its code changed with another clause, so {test} must pass '
                           '(--allow-incomplete does not cover this)')
    basis = bases(project, entries) if allow_behind else {}   # only a language left behind can wait for a result

    def waiting(k):
        """The languages whose result a test may leave for later: `--allow-behind` leaves the test, or the clause it is named after, behind in
        them. The code of that language is not rebuilt yet, so a result now would be for the old code; the lock of the language asks for it."""
        if not allow_behind:
            return set()
        part, _, name = k.rpartition('/')
        clause = f'{part}/{name[5:]}' if part else name[5:]
        late = set(lagging_targets(project, k, entries[k], owners, basis)) | set(lagging_targets(project, clause, entries.get(clause) or {}, owners, basis))
        return late & set(allow_behind)

    def open_lines(k):
        """[(name, result)] of a test that stops the lock: a test with a result for each language is named by its lines."""
        e = entries[k]
        lines = {t: line for t, line in (e.get('targets') or {}).items() if 'result' in line}
        if not lines:
            return [(k, e['result'])] if e.get('result') in ('none', 'fail') else []
        later = waiting(k)
        return [(f'{k}@{t}', lines[t]['result']) for t in sorted(lines)
                if lines[t]['result'] == 'fail' or (lines[t]['result'] == 'none' and t not in later)]

    pending = sorted(k for k in entries if (scope is None or k in scope) and open_lines(k))
    if pending and not allow_incomplete:
        opened = [x for k in pending for x in open_lines(k)]
        failed_names = [n for n, r in opened if r == 'fail']
        left_names = [n for n, r in opened if r != 'fail']
        fails = [k for k in pending if any(r == 'fail' for _, r in open_lines(k))]
        reasons.append(f'{len(pending)} test(s) did not pass ({len(fails)} failed, {len(pending) - len(fails)} not run): '
                       + listed([f'{n} (failed)' for n in failed_names] + left_names))
        reasons.append(how_to_pass(project, failed_names + left_names, bool(fails)))
    return entries, reasons


def language_view(entry, target):
    """What a lock of one language depends on in an entry: everything but the code lines of the other languages (and what is worked out from
    them: `code`, and the `result` of a test that keeps one per language). Two views that are equal mean nobody changed what that lock read."""
    if not entry:
        return None
    lines = entry.get('targets') or {}
    own = {x: v for x, v in entry.items() if x not in ('targets', 'code') and not (x == 'result' and any('result' in l for l in lines.values()))}
    return own, lines.get(target)


def accept_language(project, scan, results, allow_incomplete, findings, old, wanted, already_fits=()):
    """What `sor lock K@t` writes (SPEC §16): the line of one language of a clause, the lines of its own test and of its rows in that language, and
    the glue of that language's files. The clause's text and every other language's line stay as the lock has them, so this lock and a lock of
    another language of the clause cannot step on each other. `wanted`: [(clause, language)]. Returns
    ({(key, language): line}, {glue key: entry}, [reasons])."""
    old = upgrade(old, scan) if old else {}
    entries = snapshot(project, scan)
    built_for(project, entries, old)
    reasons, lines, glue, confirmed = [], {}, {}, []   # `confirmed`: what --already-fits cleared, to refuse a flag that cleared nothing
    drifting = {f.key: f for f in findings if f.status == 'drift'}
    owners, old_basis = owner_parts(project), bases(project, old)

    def legit(key, prev):   # the languages whose code may change without a change to the clause: behind, or without a line yet
        return set(lagging_targets(project, key, prev, owners, old_basis)) | set(unbuilt_targets(project, key, prev, owners))

    units, seen = [], set()
    for clause, t in wanted:
        for key in language_keys(project, clause):   # the clause, its own test and its rows, each with the line it has in that language
            if (key, t) not in seen and key in entries:
                seen.add((key, t))
                units.append((key, t, clause, key == clause))
    needing, bare, coded = [], [], set()   # `coded`: the clause or one of its rows has code in a language, `bare`: the clause itself has none
    for key, t, clause, asked in units:
        name, new, prev = f'{key}@{t}', entries[key], old.get(key)
        line = (new.get('targets') or {}).get(t)
        if line is None:
            if asked:
                bare.append((key, t))
            continue
        if key != own_test(clause):
            coded.add((clause, t))
        if prev is None or (prev.get('code') and not prev.get('targets')) or basis_of(project, entries, key) != basis_of(project, old, key):
            reasons.append(f'changed  {name}  {key} is not locked as it reads now: lock it first, with `sor lock {clause}` '
                           '(only the code of one language can be locked on its own)')
            continue
        if key in drifting and t in moved_targets(new, prev) and t not in legit(key, prev):   # a language being rebuilt or built is no drift
            reasons.append(f'drift  {name}  @ {drifting[key].where}')
            continue
        was = (prev.get('targets') or {}).get(t)
        if line.get('built') != basis_of(project, entries, key):   # the lock has this code as accepted for an older text and it did not change
            if t not in already_fits:
                reasons.append(f'behind  {name}  its code was accepted for an older text of the clause and is the same code: rebuild it '
                               f'(change that code). Only if you checked that it fits the clause as it is, lock again with --already-fits {t}; '
                               'it is then recorded as confirmed, not rebuilt')
                continue
            line['built'] = basis_of(project, entries, key)
            line['fits'] = True
            confirmed.append(name)
        same = was is not None and {x: v for x, v in was.items() if x != 'result'} == {x: v for x, v in line.items() if x != 'result'}
        if 'result' in line:
            # a test that stands as it was, and passed, needs no new result, unless the code it proves is locked now (the clause's or a row's):
            # a language is locked together with the proof that its test passes against it
            if same and was.get('result') == 'pass' and not any((k, t) in lines for k in language_keys(project, clause) if k != key):
                continue
            needing.append((key, t, line))
        elif same:
            continue
        lines[(key, t)] = line
    for key, t in bare:
        if (key, t) not in coded:   # a clause whose code is all in its rows is locked in that language through them
            reasons.append(f'no code  {key}@{t}  {key} has no code in {t}: write it (a region marked `@clause {key}` in a file of {t}), then lock again')
    for key, t, line in needing:
        langs = sorted(x for x, l in entries[key]['targets'].items() if 'result' in l)
        got = results.get(f'{key}@{t}')
        if got is None and key in results:
            language, why = result_language(key, langs)   # the line of t is among langs, so a plain result is t's when it is nobody else's
            if why:
                reasons.append(why)
            else:
                got = results[key]
        line['result'] = got if got in ('pass', 'fail') else 'none'
        lines[(key, t)] = line
    bad = sorted((f'{k}@{t}', line['result']) for (k, t), line in lines.items() if 'result' in line and line['result'] != 'pass')
    if bad and not allow_incomplete:
        failed = [n for n, r in bad if r == 'fail']
        reasons.append(f'{len(bad)} test(s) did not pass ({len(failed)} failed, {len(bad) - len(failed)} not run): '
                       + listed([f'{n} (failed)' if n in failed else n for n, _ in bad]))
        reasons.append(how_to_pass(project, [n for n, _ in bad], bool(failed)))
    # the code of this language that is also the code of another clause: that clause must be locked in the same breath, or it has not changed
    mine = {k for k, _, _, _ in units}
    for key, t, clause, asked in units:
        for r in scan.regions:
            if project.target_of(r.file) != t or key not in r.keys:
                continue
            for other in r.keys:
                if other.startswith('glue:') or other in mine:
                    continue
                now_line = ((entries.get(other) or {}).get('targets') or {}).get(t) or {}
                was_line = (((old.get(other) or {}).get('targets') or {}).get(t)) or {}
                if now_line.get('code') != was_line.get('code'):
                    reasons.append(f'shares code  {key}@{t}  its code in {t} is also the code of {other}, which has a change of its own there: '
                                   f'lock them together (sor lock {clause}@{t} {other}@{t})')
    if already_fits and not confirmed and not reasons:
        reasons.append(f'--already-fits {",".join(already_fits)}: nothing to confirm, none of the languages being locked has code that is behind')
    wanted_languages = {t for _, t in wanted}
    owned = {r.file for r in scan.regions if any(not k.startswith('glue:') for k in r.keys)}
    for r in scan.regions:
        if project.target_of(r.file) not in wanted_languages:
            continue
        if r.file not in owned or any(k in mine for k in r.keys):
            g = f'glue:{r.file}'
            if g in entries and entries[g] != old.get(g):
                glue[g] = entries[g]
    return lines, glue, reasons


def is_manual(test):
    """Whether a test item carries a `manual:` line: nobody runs it, a person checks it."""
    return any((test_keyword(t) or ('',))[0] == 'manual' for _, t in test.lines)


def pending_tests(project, findings, not_passed):
    """Keys of the tests a lock would refuse for want of a passing result (`accept`): the tests that are new or changed,
    the tests of a clause that is (of every clause, for a part: locking a part takes all of its items), and the tests
    that had not passed at the last lock. A manual test needs no result, and a deferred one is left to CI."""
    wanted = set(not_passed)
    parts = {p.key: p for p in project.parts.values()}
    for f in findings:
        if f.status in ('new', 'changed', 'stale', 'built', 'shared', 'fixing'):
            o = project.items.get(f.key)
            if isinstance(o, Row):
                o = project.items.get(f.key.rsplit('/', 1)[0])
            if isinstance(o, Item):
                wanted |= {o.id} if o.is_test else set(project.tests_of(o.id))
            elif f.key in parts:
                wanted |= {i.id for i in parts[f.key].items.values() if i.is_test}
    return sorted(k for k in wanted if k in project.items and isinstance(project.items[k], Item)
                  and project.items[k].is_test and not is_manual(project.items[k]) and not project.items[k].runs_on())


def deferred_tests(project):
    """Keys of the tests left to CI: the ones that say `runs on:` (a manual test with one is a problem and stays manual)."""
    return sorted(i.id for i in project.all_items() if i.is_test and i.runs_on() and not is_manual(i))


def deferred_lines(project, keys):
    """The lines `sor status` prints for the tests CI proves: which, and where they run. No lines when there are none."""
    if not keys:
        return []
    return [f'tests deferred ({len(keys)}) — left to the CI jobs that provide their environment; `sor verify` checks their evidence: '
            + listed(keys), '']


def pending_lines(project, pending, languages=None):
    """The lines `sor status` prints for tests without a passing result: which, and what to do. No lines when there are none. `languages`: for a
    test that keeps a result for each language, those languages; it is named by its lines then (`part/test:name@py`), which is what a result is given for."""
    if not pending:
        return []
    names = []
    for k in pending:
        langs = (languages or {}).get(k)
        names += [f'{k}@{t}' for t in langs] if langs else [k]
    return [f'tests ({len(pending)}) — no passing result yet, so locking them is refused: {listed(names)}',
            '  ' + how_to_pass(project, names), '']


def how_to_pass(project, keys, failed=False):
    """What to do about tests that have no passing result, in words. Which way out there is depends on whether `sor test`
    has a page to run them in; a test in the project's own framework takes its result from a file either way."""
    file = f'`--results F`, a JSON file like {{"{keys[0]}": "pass"}}'
    own = f"a test written in the project's own framework takes its result from {file}"
    allow = '`--allow-incomplete` locks them as not passed instead'
    first = 'Fix the failed ones first. ' if failed else ''
    if project.has_web_target():
        marked = f"a test written in the project's own framework, with its code marked `@clause test <id>`, takes its result from {file}"
        return f'{first}`sor lock --run-tests` runs the tests and locks with what they say; {marked}; {allow}'
    return (f'{first}This project has no web target, so `sor test` cannot run them. A test nobody can run yet needs a '
            f'`manual:` line saying what a person checks by hand; {own}; {allow}')
