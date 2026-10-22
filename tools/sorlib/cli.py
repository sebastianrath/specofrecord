"""sor: check, status, lock, markers and show for a Spec of Record project.

    sor check [--strict] [PART ...]  every problem in the spec files and the code markers, and notes (too long, open:, loose text);
                                  with parts: only those parts and the parts inside them
    sor parts [--json] [--tree] [PART ...]  an index of every part: why it exists, its size, its open questions;
                                  with parts: only those parts and the parts inside them
    sor needs [PART] [--json]     what a part needs from other parts, found from its references
    sor changes [--json]          the changes pending since the last lock, in words
    sor new PART | --root         write a skeleton part (or the root file) with <fill in: ...> placeholders
    sor status [--json]           what to recompile, review, or revert since the last lock
    sor test [ID ...] [--out F]   run the tests in headless Chrome against the web target's probes
    sor test --strength [ID ...]  rerun each passing test with every value it refers to changed
    sor test --list [ID ...] [--provides NAMES] [--all]  the tests a run would run and the ones it leaves to CI; runs nothing
    sor evidence --job NAME --provides NAMES --results F [--commit SHA] [--run ID]  write what a CI job proved about the tests that say `runs on:`
    sor verify [FILE|FOLDER ...]  the gate: every test that says `runs on:` has a current pass in every environment it names
    sor lock [IDS|--all] [--run-tests] [--allow-behind T]  accept clauses, code and test results: IDS, else what you claimed (--all: the whole project)
    sor claim IDS --as NAME       say you are working on these clauses; refused (exit 3) when someone else is
    sor release [IDS|--all]       give them up again
    sor markers [ID | FILE:LINE] [--json]  where a clause's code is, or which clauses a line serves
    sor show PART|ITEM            the clauses with their code underneath: one view to read
    sor hook pre-edit|post-read|session-start   Claude Code hooks (JSON on stdin; the session-start note lists the parts), see sorlib/hook.py

Run from a project folder (the one holding sor/), or pass -C <folder>.
Exit codes: 0 clean · 1 work pending (status), or an environment not proven (verify) · 2 problems or drift, or lock refused · 3 claim refused.
"""
import argparse
import difflib
import json
import os
import sys

from . import blame
from . import claims
from . import evidence
from . import hook
from . import index
from . import lint
from . import lock as lockfile
from . import testrun
from . import views
from .markers import Scan
from .model import Project, part_id, split_lines


def load(args):
    project = Project(args.root)
    return project, Scan(project)


def problems(project, scan):
    return project.check() + scan.problems + lockfile.line_collisions(project, scan)


def home(project, ident):
    """The id of the part an id lives in: a part's own, the part of an item or a row; an id that names nothing stands for itself."""
    found = project.find(ident)
    if found is None:
        return ident
    kind, o = found
    if kind == 'part':
        return o.id
    item = o if kind == 'item' else project.items.get(o.id.rsplit('/', 1)[0])
    return item.part.id if item else ident


def inside(ids, pid):
    """Whether the part pid is one of the parts `ids` or lies inside one: `audio` holds `audio/mixer`, not `audio-fx`."""
    return any(pid == i or pid.startswith(i + '/') for i in ids)


def parts_of(project, scan, where):
    """The ids of the parts a problem or note belongs to, from where it is. In a spec file (`audio.md:12`, relative to
    sor/) it belongs to that part; a `.tests.md` file adds tests to the part it is named after. In a code file it belongs
    to the parts of the region it is in (`out/app.js:40`), and code outside every region to every part with code in that file."""
    file, _, line = where.partition(':')
    path = os.path.join(project.spec_dir, file)
    if file.endswith('.md') and os.path.isfile(path):
        return {part_id(project.spec_dir, path[:-9] + '.md' if file.endswith('.tests.md') else path)}
    first = line.split('-')[0]
    here = scan.at(file, int(first)) if first.isdigit() else []
    return {home(project, i) for r in here or [r for r in scan.regions if r.file == file] for i in r.ids}


def wanted_parts(project, names, cmd='check'):
    """The ids of the parts named on the command line, or None after saying which names are no part."""
    ids, unknown = [], []
    for name in names:
        found = project.find(name.rstrip('/'))
        if found is None or found[0] != 'part':
            unknown.append(name)
        else:
            ids.append(found[1].id)
    keys = sorted(p.key for p in project.parts.values())
    for name in unknown:
        near = [k for k in keys if k.startswith(name) or name.startswith(k + '/')]
        near += difflib.get_close_matches(name, keys, n=5, cutoff=0.6)
        print(f'sor {cmd}: no such part: {name}. '
              + ('Closest part ids: ' + ', '.join(list(dict.fromkeys(near))[:5]) if near else '`sor parts` lists them'), file=sys.stderr)
    return None if unknown else ids


def cmd_parts(args):
    ids = wanted_parts(Project(args.root), args.parts, 'parts') if args.parts else []
    if ids is None:
        return 2
    return views.cmd_parts(args, (lambda pid: inside(ids, pid)) if ids else None)


def cmd_check(args):
    project, scan = load(args)
    found = problems(project, scan)
    parts, regions, mine = list(project.parts.values()), scan.regions, lambda x: True
    if args.parts:   # only these parts and the ones inside them
        ids = wanted_parts(project, args.parts)
        if ids is None:
            return 2
        mine = lambda x: any(inside(ids, h) for h in parts_of(project, scan, x.where))
        found = list(filter(mine, found))
        parts = [p for p in parts if inside(ids, p.id)]
        regions = [r for r in regions if any(inside(ids, home(project, i)) for i in r.ids)]
    for p in found:
        print(p)
    refs = sum(len(i.refs) for p in parts for i in p.items.values())
    print(f'{len(parts)} parts, {refs} references, {len(regions)} code regions; '
          f'{len(found)} problem(s)')
    notes = list(filter(mine, lint.notes(project, scan)))
    if notes:
        print(f'\nnotes ({len(notes)}): advice and open questions, not problems (SPEC §13); '
              'they never block a lock, `--strict` makes them fail the check')
        for n in notes:
            print('  ' + str(n))
    return 2 if found or (args.strict and notes) else 0


def cmd_status(args):
    project, scan = load(args)
    found = problems(project, scan)
    old = lockfile.read(project)
    findings, not_passed = lockfile.status(project, scan, old)
    blame.annotate(project, findings)
    pending = lockfile.pending_tests(project, findings, not_passed)
    deferred = lockfile.deferred_tests(project)
    if args.json:
        print(json.dumps({'locked': bool(old), 'problems': [vars(p) for p in found],
                          'findings': [f.as_dict() for f in findings],
                          'tests_not_passed': not_passed,
                          'tests_pending': pending,
                          'tests_deferred': deferred,
                          'claims': [{k: c[k] for k in ('agent', 'asked', 'since', 'until')}
                                     for c in claims.active(project)]}, indent=2, ensure_ascii=False))
    else:
        if not old:
            print(f'no {project.lock_file} yet: everything is new. `sor lock` accepts the current state.\n')
        if found:
            print(f'problems ({len(found)}) — fix these first, `sor check` lists the same')
            for p in found:
                print('  ' + str(p))
            print()
        for group, statuses, meaning in lockfile.GROUPS:
            rows = [f for f in findings if f.status in statuses]
            if not rows or (not old and group == 'recompile' and not args.all):
                continue
            print(f'{group} ({len(rows)}) — {meaning}')
            width = min(36, max(len(f.key) for f in rows))
            for f in rows:
                tail = '  '.join(x for x in [f.detail, f.where and f'@ {f.where}',
                                             getattr(f, 'by', '') and f'({f.by})'] if x)
                print(f'  {f.status:<12} {f.key:<{width}}  {tail}'.rstrip())
            print()
        held = claims.active(project)
        if held:
            print(f'claims ({len(held)}) — who is working on what (advisory; they expire)')
            for c in held:
                print('  ' + claims.describe(c))
            print()
        for line in lockfile.pending_lines(project, pending):
            print(line)
        for line in lockfile.deferred_lines(project, deferred):
            print(line)
        stale = lockfile.old_rule_keys(old, scan)
        if stale:
            print(f'note: {len(stale)} locked code hash(es) were made with the rule every file followed before it followed the file '
                  'type (Python indentation, `#` comments, or the lines of a multi-line string, for example). `sor lock --rehash` rewrites them and accepts no change; until '
                  'then a change only the old rule ignores is not seen.')
            print()
        if not old and not args.all:
            print(f'{len(findings)} new entries (--all lists them)')
        if not_passed:
            print(f'{len(not_passed)} test(s) had not passed at the last lock')
        if not findings and not found:
            print('clauses, code and lock agree' + (' (but not every test passed)' if not_passed else ''))
        if len(project.target_names()) >= 2:
            for note in lint.no_code_for_target(project, scan):
                print(f'note: {note.text} (not a pending change; `sor check` lists them)')
    if found or any(f.status == 'drift' for f in findings):
        return 2
    return 1 if findings else 0


PENDING = ('new', 'changed', 'removed', 'stale', 'built', 'behind')


def scope_plan(project, scan, old, findings, ids):
    """For `sor lock IDS`: (lock keys to accept, reasons to refuse). The keys are the clauses'
    own and the ones that share a code region with them, since their code is one and the same.
    A clause that shares code but has a change of its own is not pulled in silently: whoever is
    working on it must finish it first, or lock it together."""
    now = lockfile.conform(lockfile.snapshot(project, scan), old, scan)
    universe = set(now) | set(old)
    keys, unknown = claims.footprint(project, universe, ids)
    reasons = [claims.unknown_text(project, universe, unknown)] if unknown else []
    # An item moved or deleted since the last lock leaves its old entries behind: they belong to the nearest part
    # that still exists above them, so locking that part retires them (an item moved to another part is new there).
    owners = {project.find(i)[1].id for i in ids if project.find(i) and project.find(i)[0] == 'part'}
    for k in set(old) - set(now):
        if k.startswith('glue:'):
            continue
        pid = k.rpartition('/')[0]
        while pid and pid not in project.parts:
            pid = pid.rpartition('/')[0]
        if pid in owners:
            keys.add(k)
    wide, shared = claims.with_shared(project, scan, universe, keys)
    pending = {f.key: f for f in findings if f.status in PENDING}
    # A clause that shares code but whose entry would not change needs no lock: leave it alone, so a
    # hub like `colors` does not get dragged into every lock.
    unchanged = {k for k in wide - keys if lockfile.without_built(now.get(k)) == lockfile.without_built(old.get(k))}
    wide -= unchanged
    shared = [k for k in shared if k not in unchanged]
    for k in sorted(wide - keys):
        if k in pending:
            reasons.append(f'{k} shares code with {", ".join(ids)} and has its own pending change '
                           f'({pending[k].status}): lock it together with them, or let its owner finish first')
    # A test that proves a clause without being named after it (its `expect:` refers to the clause, SPEC §8) is part
    # of the same fix: when it is new or changed, it goes with the lock, or `sor status` would keep it pending.
    for k in sorted(wide):
        o = project.items.get(k)
        if o is not None and not getattr(o, 'is_test', True):   # an item, not a row or a test
            wide |= {t for t in project.tests_of(k) if t in pending}
    # Glue is the wiring around the clauses' code (`@clause glue`). It belongs to no clause, so a scoped lock
    # would never accept it and `sor status` would stay pending for good: accept the glue of the files the
    # locked clauses live in.
    glue = {f'glue:{r.file}' for k in wide for r in scan.regions_for(k)}
    # a file that is nothing but glue (an `__init__.py`) belongs to no clause at all: it goes with every lock
    owned = {r.file for r in scan.regions if any(not k.startswith('glue:') for k in r.keys)}
    glue |= {f'glue:{r.file}' for r in scan.regions if r.file not in owned}
    wide |= {g for g in glue if g in now or g in old}
    return wide, reasons, shared


def scope_files(project, scan, keys):
    """The spec files and code files the keys live in: only problems there block a scoped lock."""
    files = {r.file for k in keys for r in scan.regions_for(k)}
    for p in project.parts.values():
        if p.key in keys or any(k == it.id or k.startswith(it.id + '.') or k.startswith(it.id + '/')
                                for it in p.items.values() for k in keys):
            files.add(p.rel)
            files.update(it.file for it in p.items.values())
    return files


ITEM_LOCAL = ('broken', 'needs', 'proves', 'expect', 'runs on')   # problems of one item's own text, fixed by whoever works on that item
# 'unnamed test' and 'placeholder' are not among them: a person's draft test and a half-filled skeleton keep a lock waiting
# until they are tidied or filled in, wherever in the file they sit (DECISIONS: Loose tests).


def item_at(project, where):
    """The item whose lines hold `where` (file:line), or None: a line of code, or text outside any item."""
    file, _, line = where.rpartition(':')
    if not line.isdigit():
        return None
    return next((it for it in project.all_items() if it.file == file and any(n == int(line) for n, _ in it.lines)), None)


def covered(item, scope):
    """Whether the lock keys `scope` include the item, its rows or its values."""
    return any(k == item.id or k.startswith(item.id + '.') or k.startswith(item.id + '/') for k in scope)


def with_holder(project, me, problem):
    """The problem as a line of a refusal, and, when it lies in an item another agent has claimed, who that is."""
    item = item_at(project, problem.where)
    theirs = claims.others(project, me, {item.id}, ()) if item else []
    return str(problem) + (f'  (in {item.id}, claimed by {" and ".join(sorted({c["agent"] for c in theirs}))})' if theirs else '')


def cmd_rehash(args, project, scan):
    """`sor lock --rehash`: the one-time rewrite SPEC §11 describes when the rule for hashing code changes. Only the code hash of an
    entry whose code is unchanged under the old rule is replaced; text, refs and results stay as they are, and nothing is accepted."""
    if args.ids or args.all or args.run_tests or args.results or args.confirm or args.allow_incomplete:
        print('lock refused:\n  --rehash takes nothing else: it rewrites hashes and accepts no change')
        return 2
    try:
        with claims.lock_mutex(project):
            current = lockfile.read(project)
            stale = lockfile.old_rule_keys(current, scan)
            if stale:
                lockfile.write(project, lockfile.upgrade(current, scan))
    except (claims.ClaimError, lockfile.LockWriteError) as e:
        print(f'lock: {e}', file=sys.stderr)
        return 2
    if not stale:
        print('nothing to rewrite: ' + ('every code hash in the lock follows the rule of its file type' if current
                                        else f'there is no {project.lock_file} yet'))
        return 0
    print(f'rewrote {len(stale)} code hash(es) in {os.path.relpath(project.lock_path, project.root)}; text, refs and results are as they were')
    return 0


def cmd_lock(args):
    project, scan = load(args)
    old = lockfile.read(project)
    try:
        lockfile.check_writable(project)
    except lockfile.LockWriteError as e:
        print(f'lock refused:\n  {e}')
        return 2
    if args.rehash:
        return cmd_rehash(args, project, scan)
    old = lockfile.upgrade(old, scan)   # a hash only the old rule could tell apart is no change, here or in the scope below
    findings, _ = lockfile.status(project, scan, old)
    me = claims.agent_name(args.agent)
    scope = None
    ids = list(args.ids)
    if not ids and not args.all:
        # Scoped is the default: a plain `sor lock` locks what you claimed, never the whole project.
        mine = [c for c in claims.active(project) if claims.same_agent(c, me, claims.current_session())] if me else []
        ids = sorted({a for c in mine for a in c['asked']})
        lost = claims.lost(project, me, ids) if me else []   # claims that expired: they are no longer held
        if not ids:
            sid = claims.current_session()
            names = sorted({c['agent'] for c in claims.active(project) if sid and c.get('session') == sid})
            if lost:
                print(f'lock refused:\n  your {claims.lapse_text(lost)}; {claims.claim_again()} '
                      '(or say which clauses: sor lock <ids>).\n'
                      '  `sor lock --all` locks the whole project, including other agents\' unfinished work.')
            else:
                print('lock refused:\n  say which clauses: sor lock <ids> (or claim them first: sor claim <ids>).\n'
                      '  `sor lock --all` locks the whole project, including other agents\' unfinished work.')
            if names:
                print('  you claimed in this session as ' + ' and '.join(names) + ': pass --as <name> to lock what that name claimed.')
            return 2
        print('locking what you claimed: ' + ', '.join(ids))
        if lost:
            print(f'warning: your {claims.lapse_text(lost)}, so they are not part of this lock; {claims.claim_again()}')
        # a claimed part is locked with the parts under it, those made after the claim included
        kids = claims.child_parts(project, ids, [f.key for f in findings if f.status in PENDING])
        if kids:
            kids, busy = claims.unheld(project, scan, set(lockfile.snapshot(project, scan)) | set(old), kids, me)
            for pid, theirs in busy.items():
                print(f'not locking {pid}, which is claimed: ' + '; '.join(claims.describe(c) for c in theirs))
            if kids:
                print('locking the parts under them too: ' + ', '.join(kids))
                ids += kids
    if ids:
        scope, reasons, shared = scope_plan(project, scan, old, findings, ids)
        if shared and not reasons:
            print('locking with them (they share code): ' + ', '.join(shared))
        files = scope_files(project, scan, scope)
        found = problems(project, scan)
        here = [p for p in found if p.where.split(':')[0] in files]
        apart = [p for p in here if p.kind in ITEM_LOCAL and item_at(project, p.where) and not covered(item_at(project, p.where), scope)]
        reasons += [with_holder(project, me, p) for p in here if p not in apart]
        outside = [p for p in found if p.where.split(':')[0] not in files]
        if outside:
            print(f'note: {len(outside)} problem(s) in other files do not block this lock (`sor check` lists them)')
        if apart:
            print(f'note: {len(apart)} problem(s) in other items of these files do not block this lock (`sor check` lists them)')
        findings = [f for f in findings if f.key in scope]
        held = claims.others(project, me, scope, claims.regions_of(scan, scope))
    else:
        reasons = [str(p) for p in problems(project, scan)]
        held = claims.others(project, me)
    reasons += [f'drift  {f.key}  @ {f.where}' for f in findings if f.status == 'drift']
    if held:
        reasons += [f'claimed  {claims.describe(c)}' for c in held]
        reasons.append('lock only your own clauses: sor lock <ids>'
                       if not ids else 'wait for them, or ask them to release')
        if not me:
            reasons.append('say who you are with --as NAME (or SOR_AGENT): your own claims do not block you')
        sid = claims.current_session()
        names = sorted({c['agent'] for c in held if sid and c.get('session') == sid})
        if names:
            reasons.append('you made these claims in this session under another name: pass --as '
                           + ' or --as '.join(names) + ' (every claim, lock and release must use the same name)')
    if ids and (held or any(r.startswith('no such') or 'shares code' in r for r in reasons)):
        print('lock refused:')
        for r in reasons:
            print('  ' + r)
        return 2
    allow_behind = [t.strip() for t in (args.allow_behind or '').split(',') if t.strip()]
    unknown = sorted(set(allow_behind) - set(project.target_names()))
    if unknown:
        print(f'lock refused:\n  --allow-behind names {", ".join(unknown)}, which is no target (targets: {", ".join(project.target_names()) or "none"})')
        return 2
    confirm = [c if '/test:' in c or c.startswith('test:') else lockfile.own_test(c) for c in args.confirm]
    results, external = {}, set()
    if args.run_tests:
        ran, summary = testrun.run(project, confirmed=confirm)
        print_results(ran)
        print_coverage(summary, False)
        results = {k: r['status'] for k, r in ran.items() if r['status'] in ('pass', 'fail')}
        external = {k for k, r in ran.items() if r['status'] == 'external'}
        if args.results:   # the project's own results, for the tests `sor test` shows as EXTERNAL and for those only
            with open(args.results, encoding='utf8') as fh:
                given = json.load(fh)
            results.update({k: v for k, v in given.items() if k in external and v in ('pass', 'fail')})
            ignored = sorted(set(given) - external)
            if ignored:
                print(f'--results: ignored {", ".join(ignored)} (only tests shown as EXTERNAL take a result from the file)')
    elif args.results:
        with open(args.results, encoding='utf8') as fh:
            results = json.load(fh)
    entries, more = lockfile.accept(project, scan, results, args.allow_incomplete, findings, old, confirm, scope, allow_behind)
    gave = sorted(k for k, v in results.items() if entries.get(k, {}).get('result') == 'deferred' and (scope is None or k in scope))
    if gave:
        print(f'note: a result for {", ".join(gave)} is not recorded in the lock: it says `runs on:`, so a CI job proves it '
              '(`sor evidence` writes that result for a job)')
    waiting = sorted(k for k in external if k not in results and (scope is None or k in scope)
                     and entries.get(k, {}).get('result') != 'deferred')
    if waiting and more and not args.allow_incomplete:
        more.append(f'EXTERNAL {", ".join(waiting)}: no result yet. Run your own tests and pass --results F with '
                    f'{{"{waiting[0]}": "pass"}} (a file of the framework\'s results)')
    reasons += more
    if reasons:
        print('lock refused:')
        for r in reasons:
            print('  ' + r)
        return 2
    try:
        with claims.lock_mutex(project):
            if scope is not None:
                # another agent may have locked their clauses since we read the lock: keep theirs
                merged = lockfile.read(project)
                for k in scope:
                    if k in entries:
                        merged[k] = entries[k]
                    else:
                        merged.pop(k, None)
                entries = merged
            lockfile.write(project, entries)
    except (claims.ClaimError, lockfile.LockWriteError) as e:
        print(f'lock: {e}', file=sys.stderr)
        return 2
    newly = sorted(k for k, e in entries.items() if e.get('kind') == 'test' and e.get('result') == 'deferred'
                   and old.get(k, {}).get('result') != 'deferred' and (scope is None or k in scope))
    if newly:   # a line in the spec is all it takes to leave a test to CI: say which tests that is
        print(f'now left to CI, because they say `runs on:`: {", ".join(newly)}')
    tests = [e for e in entries.values() if e.get('kind') == 'test']
    n = {r: sum(e['result'] == r for e in tests) for r in ('pass', 'checked', 'manual', 'deferred')}
    what = f'{len(scope)} of {len(entries)} entries' if scope is not None else f'{len(entries)} entries'
    print(f'locked {what} in {os.path.relpath(project.lock_path, project.root)}; '
          f'tests: {n["pass"]} passed, {n["checked"]} manual checks confirmed, {n["manual"]} manual '
          f'unconfirmed, ' + (f'{n["deferred"]} deferred to CI, ' if n['deferred'] else '')
          + f'{len(tests) - sum(n.values())} not passed')
    if scope is not None:
        left, _ = lockfile.status(project, scan, entries)
        left = [f for f in left if f.status in PENDING and f.key not in scope]
        if left:
            print(f'still pending outside what you locked: {len(left)} (claim and lock those, or leave them to whoever works '
                  'on them; `sor status` lists them). Not a reason for --all while others hold claims.')
    return 0


def cmd_claim(args):
    project, scan = load(args)
    agent = claims.agent_name(args.agent)
    try:
        ttl = claims.parse_ttl(args.ttl)
        ok, res = claims.claim(project, scan, set(lockfile.snapshot(project, scan)), args.ids, agent, ttl)
    except claims.ClaimError as e:
        print(f'claim: {e}', file=sys.stderr)
        return 2
    if not ok:
        blocked = res.get('blocked') or list(args.ids)
        print(f'REFUSED {", ".join(blocked)}: held by')
        for c in res['holders']:
            print('  ' + claims.describe(c))
        free = [i for i in args.ids if i not in blocked]
        if free:   # a claim takes all its ids or none: say so, or the free ones look like they are held
            print(f'  nothing was claimed: {", ".join(free)} {"is" if len(free) == 1 else "are"} free, but a claim takes all its '
                  'ids or none. Claim them on their own, or ask for them again once the others are released')
        return 3
    print(f'claimed {", ".join(args.ids)} until {claims.when(res["until"])} ({claims.lifetime(ttl)})')
    if res['shared']:
        print('  its code regions are shared with ' + ', '.join(res['shared'])
              + ': nobody else can claim those regions meanwhile')
    return 0


def cmd_release(args):
    project = Project(args.root)
    agent = claims.agent_name(args.agent)
    if not args.ids and not args.all:
        print('release: name the clauses, or --all', file=sys.stderr)
        return 2
    try:
        gone, refused = claims.release(project, args.ids, agent, args.all, args.force)
    except claims.ClaimError as e:
        print(f'release: {e}', file=sys.stderr)
        return 2
    ran_out = [c for c in gone if claims.has_expired(c)]   # expired before: dropped from the file, but say so
    for c in gone:
        if c not in ran_out:
            print('released ' + ', '.join(c['asked']))
    for c in refused:
        print('NOT released (held by someone else; --force overrides): ' + claims.describe(c))
    if ran_out:
        print(('note: ' if len(ran_out) < len(gone) else 'nothing to release: ') + f'your {claims.lapse_text(ran_out)} '
              f'(claims last {claims.lifetime(claims.DEFAULT_TTL)} by default, `--ttl 2h` for longer)')
    elif not gone and not refused:
        print('nothing to release')
    return 3 if refused else 0


def print_results(results):
    marks = {'pass': 'PASS', 'fail': 'FAIL', 'skipped': 'SKIP', 'manual': 'MANUAL', 'external': 'EXTERNAL', 'deferred': 'DEFER'}
    width = max((len(k) for k in results), default=0)
    mark = max([6] + [len(marks[r['status']]) for r in results.values()])
    for tid, r in results.items():
        msg = r.get('message', '')
        print(f'  {marks[r["status"]]:<{mark}} {tid:<{width}}  {msg}'.rstrip())
    n = {s: sum(r['status'] == s for r in results.values()) for s in marks}
    print(f'{n["pass"]} passed, {n["fail"]} failed, {n["skipped"]} skipped, {n["manual"]} manual'
          + (f', {n["external"]} external' if n['external'] else '')
          + (f', {n["deferred"]} deferred to CI' if n['deferred'] else ''))
    return n


def print_coverage(summary, detail):
    fc, lc = summary['clause_coverage'], summary['line_coverage']
    if fc is not None:
        print(f'clause coverage {fc:.1f}% ({len(summary["unproven"])} rules and gives without a passing test)')
    if lc is not None:
        print(f'line coverage {lc:.1f}% ({summary["lines"][0]} of {summary["lines"][1]} marked code lines ran)')
    if detail:
        print()
        print('not proven by a passing test:')
        for i in summary['unproven']:
            print('  ' + i)
        print()
        print('line coverage per clause (lowest first):')
        rows = sorted(summary['by_clause'].items(), key=lambda kv: kv[1][0] / kv[1][1])
        for key, (ran, total) in rows:
            print(f'  {100 * ran / total:5.0f}%  {ran:>3}/{total:<3}  {key}')


def cmd_test_list(args, project, scan, provides):
    """`sor test --list`: the tests a run would run and the ones it would leave to CI, without running anything (so it needs no
    web target). Each test with its environments, whether a framework of your own runs it and its fingerprint."""
    fps = evidence.fingerprints(project, scan)
    rows = []
    for item in project.all_items():
        if not item.is_test or (args.ids and not testrun.selects(project, item, args.ids)):
            continue
        manual = lockfile.is_manual(item)
        why = None if manual else testrun.deferral(item, args.ids, provides, args.all)
        rows.append({'id': item.id, 'runs_on': [list(e) for e in item.runs_on()], 'manual': manual,
                     'external': not manual and testrun.external(item, scan),   # as `sor test` decides
                     'selected': not manual and why is None, 'fingerprint': fps[item.id]})
    if args.json:
        print(json.dumps({'tests': rows}, indent=2))
        return 0
    width = max((len(r['id']) for r in rows), default=0)
    for r in rows:
        mark = 'MANUAL' if r['manual'] else 'RUN' if r['selected'] else 'DEFER'
        where = ('runs on ' + ', '.join('+'.join(e) for e in r['runs_on'])) if r['runs_on'] else ''
        print(f'  {mark:<6} {r["id"]:<{width}}  {where}'.rstrip())
    print(f'{sum(r["selected"] for r in rows)} to run, {sum(r["runs_on"] != [] and not r["selected"] and not r["manual"] for r in rows)} '
          f'left to CI, {sum(r["manual"] for r in rows)} manual')
    return 0


def cmd_test(args):
    project, scan = load(args) if args.list else (Project(args.root), None)
    prov, err = evidence.names(args.provides or '', '--provides')
    if err:
        print(f'sor test: {err}', file=sys.stderr)
        return 2
    prov = frozenset(prov)
    unmatched = [o for o in args.ids if not any(testrun.selects(project, item, [o]) for item in project.all_items())]
    if unmatched:   # a typo must not look like "0 failed"
        print(f'sor test: no test matches {", ".join(unmatched)} (name a test, the item it proves, or a part)', file=sys.stderr)
        return 2
    if args.list:
        return cmd_test_list(args, project, scan, prov)
    if args.strength:
        return cmd_strength(project, args.ids or None, prov, args.all)
    results, summary = testrun.run(project, args.ids or None, provides=prov, everything=args.all)
    n = print_results(results)
    print_coverage(summary, args.coverage)
    if args.out:
        with open(args.out, 'w', encoding='utf8') as fh:
            json.dump({k: r['status'] for k, r in results.items() if r['status'] in ('pass', 'fail')},
                      fh, indent=2, sort_keys=True)
    return 1 if n['fail'] else 0


def cmd_strength(project, ids, provides=None, everything=False):
    results, weak, reruns, idle = testrun.strength(project, ids, provides=provides, everything=everything)
    passing = [t for t, r in results.items() if r['status'] == 'pass']
    print(f'{reruns} reruns of {len(passing) - len(idle)} of {len(passing)} passing tests, each with one value changed')
    if weak:
        print(f'{len(weak)} weak test(s), still passing with a value changed:')
        width = max(len(t) for t in weak)
        for tid, values in weak.items():
            for ref, literal, alts in values:
                print(f'  WEAK   {tid:<{width}}  {{{ref}}} = {literal}, still passes with {" and ".join(alts)}')
                tid = ''
    elif reruns:
        print('no weak tests: every value that was changed made its test fail')
    else:
        print('no weak tests found, but nothing was changed: strength says nothing about these tests')
    if idle:
        print(f'nothing to vary in {len(idle)} passing test(s); strength cannot tell whether they check anything:')
        width = max(len(t) for t in idle)
        for tid, why in idle.items():
            print(f'  IDLE   {tid:<{width}}  {why}')
    return 1 if weak else 0


def describe(project, key):
    found = project.find(key)
    if found is None:
        return key
    kind, o = found
    if kind == 'part':
        return f'{o.key}  ({o.rel}) — {o.header.get("Why", "")}'
    if kind == 'row':
        return f'{o.id}  {o.text}'
    return '\n    '.join(t for _, t in o.lines)


def dump(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_markers(args):
    project, scan = load(args)
    target = args.target
    if args.json and not target:
        dump(index.full_index(project, scan))
        return 0
    if target and ':' in target and target.rsplit(':', 1)[1].isdigit():
        file, line = target.rsplit(':', 1)
        if args.json:
            dump(index.at_line(project, scan, file, int(line), describe))
            return 0
        hits = scan.at(file, int(line))
        if not hits:
            print(f'{target} is in no @clause region')
            return 2
        for r in hits:
            print(f'{r.where}  {r.kind}')
            for k in r.keys:
                print('  ' + describe(project, k))
        return 0
    if target:
        found = project.find(target)
        key = target if found is None else (found[1].key if found[0] == 'part' else found[1].id)
        test_key = (key.rpartition('/')[0] + '/test:' + key.rpartition('/')[2]).lstrip('/')
        rows = scan.regions_for(key) + scan.regions_for(test_key)
        if args.json:
            dump(index.for_id(project, scan, key, rows, found))
            return 0 if found or rows else 2
        if found is None and not rows:
            print(f'{target}: no such item')
            return 2
        for r in rows:
            print(f'{r.where}  {r.kind}  {" ".join(r.keys)}')
        if not rows:
            print(f'{key} has no code')
        return 0
    by_file = {}
    for r in scan.regions:
        by_file.setdefault(r.file, []).append(r)
    for file, regions in sorted(by_file.items()):
        print(file)
        for r in regions:
            print(f'  {r.start:>5}-{r.end:<5} {r.kind:<5} {" ".join(r.keys) or " ".join(r.ids)}')
    for p in scan.problems:
        print(p)
    promises = [i for i in project.all_items() if i.section == 'Rules' or i.kind == 'gives']
    with_code = [i for i in promises if scan.regions_for(i.id) or any(scan.regions_for(r.id) for r in i.rows.values())]
    print(f'{len(scan.regions)} regions in {len(by_file)} files; {len(with_code)} of {len(promises)} '
          f'rules and gives have code; {len(scan.problems)} problem(s)')
    return 2 if scan.problems else 0


def cmd_show(args):
    project, scan = load(args)
    found = project.find(args.target) or (project.find(project.root_key) if args.target in ('', '.') else None)
    if found is None:
        print(f'{args.target}: no such part or item')
        return 2
    kind, o = found
    shown = set()

    def code(keys, indent='    '):
        out = []
        for key in keys:
            for r in scan.regions_for(key):
                if id(r) in shown:
                    out.append(f'{indent}> {r.where}  (shown above)')
                    continue
                shown.add(id(r))
                others = [k for k in r.keys if k != key]
                out.append(f'{indent}> {r.where}' + (f'  (also {", ".join(others)})' if others else ''))
                out += [f'{indent}| {l}' for l in r.lines]
        return out

    def item_keys(it):
        return [it.id] + [r.id for r in it.rows.values()]

    if kind == 'part':
        with open(o.path, encoding='utf8') as fh:
            lines = split_lines(fh.read())
        ends = {}
        for it in o.items.values():
            if it.lines:
                ends.setdefault(it.lines[-1][0], []).append(it)
        for n, line in enumerate(lines, 1):
            print(line)
            for it in ends.get(n, []):
                for l in code(item_keys(it)):
                    print(l)
        rest = code([o.key])
        if rest:
            print('\n## Code for the whole part')
            for l in rest:
                print(l)
    else:
        it = project.items[o.id.rsplit('/', 1)[0]] if kind == 'row' else o   # a row shows the item it belongs to
        print(f'# {it.part.title}  ({it.part.rel})')
        for _, t in it.lines:
            print(t)
        tests = [project.items[i] for i in project.tests_of(it.id) if i in project.items]   # every test that proves it
        for l in code(item_keys(it) if kind == 'item' else [o.id]):
            print(l)
        for test in tests if not it.is_test else []:
            print()
            for _, t in test.lines:
                print(t)
            for l in code([test.id]):
                print(l)
    return 0


def cmd_evidence(args):
    """Writes what this job proved: its results for the tests that say `runs on:` and name an environment it provides."""
    project, scan = load(args)
    prov, err = evidence.names(args.provides, '--provides')
    bad_job = evidence.job_problem(args.job)
    src, bad_src = evidence.source(args.commit, args.run)
    err = (f'--job {bad_job}' if bad_job else None) or err or (None if prov else '--provides names at least one environment') or bad_src
    results = None
    if not err:
        try:
            with open(args.results, encoding='utf8') as fh:
                results = json.load(fh)
        except OSError as e:
            err = f'cannot read {args.results} ({e.strerror or e})'
        except ValueError as e:
            err = f'{args.results} is not JSON ({e})'
        else:
            if not isinstance(results, dict):
                err = f'{args.results} holds {{"part/test:name": "pass"}}, as `sor test --out` writes it'
    if err:
        print(f'evidence refused:\n  {err}')
        return 2
    data, notes, errors = evidence.build(project, scan, args.job, prov, results, src)
    if errors:
        print('evidence refused:')
        for e in errors:
            print('  ' + e)
        return 2
    out = args.out or os.path.join(project.root, 'evidence', args.job + '.json')
    evidence.write(out, data)
    n = {s: sum(r['status'] == s for r in data['results'].values()) for s in evidence.STATUSES}
    print(f'wrote {os.path.relpath(out, project.root)}: job {args.job} provides {", ".join(prov)}; '
          f'{n["pass"]} passed, {n["fail"]} failed')
    for note in notes:
        print('note: ' + note)
    return 0


VERIFY_MARKS = {'pass': 'ok', 'fail': 'FAILED', 'stale': 'STALE', 'missing': 'MISSING'}


def cmd_verify(args):
    """The gate over the evidence: exit 0 when every test that says `runs on:` has a current pass in every environment it
    names, 1 when one has not, 2 for a problem in the spec or in an evidence file."""
    project, scan = load(args)
    found = [p for p in problems(project, scan) if p.kind == 'runs on']
    if found:
        print('verify refused: fix these `runs on:` lines first')
        for p in found:
            print('  ' + str(p))
        return 2
    folder = os.path.join(project.root, 'evidence')
    paths = args.files or ([folder] if os.path.isdir(folder) else [])
    files, errors = evidence.collect(paths)
    if errors:
        print('verify refused: evidence that cannot be read')
        for e in errors:
            print('  ' + e)
        return 2
    rows = evidence.verify(project, scan, files)
    stray = evidence.unknown(project, files)
    if rows and not files and not args.json:
        print('note: no evidence files (*.json) found in ' + (', '.join(paths) if paths else 'the evidence folder, which does not exist'))
    bad = [r for r in rows if any(e['status'] != 'pass' for e in r['environments'])]
    sources = {d['job']: d['from'] for _, d in files if 'from' in d}   # jobs that said which commit and run they saw (evidence format 2)

    def job_label(job):
        src = sources.get(job)
        return job + (' (' + ', '.join(f'{k} {v[:12] if k == "commit" else v}' for k, v in sorted(src.items())) + ')' if src else '')
    if args.json:
        print(json.dumps({'ok': not bad, 'tests': rows, 'unknown': [{'job': j, 'test': k} for j, k in stray],
                          'sources': sources}, indent=2))
    else:
        if not rows:
            print('no test says `runs on:`: nothing to verify')
        for r in rows:
            print(r['id'])
            width = max(len('+'.join(e['needs'])) for e in r['environments'])
            for e in r['environments']:
                print(f'  {"+".join(e["needs"]):<{width}}  {VERIFY_MARKS[e["status"]]:<7} {", ".join(job_label(j) for j in e["jobs"])}'.rstrip())
        if rows:
            left = sum(1 for r in bad)
            print(f'{len(rows)} deferred test(s): {len(rows) - left} proven, {left} not' + (' proven' if left else ''))
        if stray:
            print(f'note: results for tests that no longer say `runs on:` are ignored: {", ".join(k for _, k in stray[:10])}')
    return 1 if bad else 0


def build_parser():
    ap = argparse.ArgumentParser(prog='sor', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('-C', dest='root', default='.', help='project folder (default: here)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('check', help='problems in the spec files and markers, and notes')
    s.add_argument('parts', nargs='*', metavar='PART',
                   help='only these parts and the parts inside them, and the exit code follows only them (default: all)')
    s.add_argument('--strict', action='store_true',
                   help='notes (too long, open questions, loose text) also make the exit code 2')
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser('parts', help='an index of every part')
    s.add_argument('parts', nargs='*', metavar='PART', help='only these parts and the parts inside them (default: all)')
    s.add_argument('--json', action='store_true')
    s.add_argument('--tree', action='store_true', help='show the hierarchy: each part under its parent, with the number of parts under it')
    s.set_defaults(fn=cmd_parts)
    s = sub.add_parser('needs', help='what a part needs from other parts, derived from its references')
    s.add_argument('part', nargs='?', help='a part id (ROOT for the root); none: every part')
    s.add_argument('--json', action='store_true')
    s.set_defaults(fn=views.cmd_needs)
    s = sub.add_parser('changes', help='the changes pending since the last lock, in words')
    s.add_argument('--json', action='store_true')
    s.set_defaults(fn=views.cmd_changes)
    s = sub.add_parser('new', help='write a skeleton part, or the root file, with <fill in: ...> placeholders')
    s.add_argument('part', nargs='?', help='a part id: lowercase words joined by -, / for a part inside a part')
    s.add_argument('--root', dest='make_root', action='store_true', help='write sor/SPECOFRECORD.md for a new project')
    s.add_argument('--why', help='the Why: line (otherwise a placeholder)')
    s.set_defaults(fn=views.cmd_new)
    s = sub.add_parser('status')
    s.add_argument('--json', action='store_true')
    s.add_argument('--all', action='store_true', help='list every entry even before the first lock')
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser('lock')
    s.add_argument('ids', nargs='*', help='lock only these clauses or parts (and what shares their code); '
                   'none: what you claimed')
    s.add_argument('--all', action='store_true', help='lock the whole project (refused while others hold claims)')
    s.add_argument('--as', dest='agent', help='who you are (or set SOR_AGENT): your own claims do not block your lock')
    s.add_argument('--results', help='JSON file: {"camera/test:limits": "pass", ...}; with --run-tests only the tests shown as EXTERNAL take their result from it')
    s.add_argument('--run-tests', action='store_true', help='run `sor test` and lock with its results')
    s.add_argument('--confirm', nargs='+', default=[], metavar='TEST',
                   help='manual tests you checked yourself, e.g. scene/test:bodies')
    s.add_argument('--allow-incomplete', action='store_true',
                   help='lock although some tests did not pass; they are recorded as such')
    s.add_argument('--allow-behind', metavar='TARGETS',
                   help='lock a clause although its code in these targets (comma-separated) was accepted for an older text of the '
                        'clause; they stay listed as behind until their code changes')
    s.add_argument('--rehash', action='store_true',
                   help='rewrite the code hashes made with an older rule (no change is accepted, nothing else is rewritten)')
    s.set_defaults(fn=cmd_lock)
    s = sub.add_parser('claim', help='say you are working on these clauses or parts (advisory, expires)')
    s.add_argument('ids', nargs='+', help='clauses, rows or parts; to add a clause, claim its part')
    s.add_argument('--as', dest='agent', help='who you are (or set SOR_AGENT)')
    s.add_argument('--ttl', default='30m', help='how long it holds: 90s, 30m, 2h (default 30m)')
    s.set_defaults(fn=cmd_claim)
    s = sub.add_parser('release', help='give up claims')
    s.add_argument('ids', nargs='*')
    s.add_argument('--all', action='store_true', help='all of your claims')
    s.add_argument('--as', dest='agent', help='who you are (or set SOR_AGENT)')
    s.add_argument('--force', action='store_true', help='release a claim held by someone else')
    s.set_defaults(fn=cmd_release)
    s = sub.add_parser('test')
    s.add_argument('ids', nargs='*', help='tests, items or parts to run (default: all)')
    s.add_argument('--out', help='write {test id: pass|fail} for `sor lock --results`')
    s.add_argument('--coverage', action='store_true', help='list unproven clauses and line coverage per clause')
    s.add_argument('--strength', action='store_true',
                   help='list weak tests: ones that still pass with a value they refer to changed')
    s.add_argument('--provides', help='the environments this run provides, comma-separated: it also runs the tests that say `runs on:` one of them')
    s.add_argument('--all', action='store_true', help='also run every test that says `runs on:`, whatever it names')
    s.add_argument('--list', action='store_true', help='list the tests this run would run and the ones it leaves to CI; runs nothing')
    s.add_argument('--json', action='store_true', help='with --list: machine-readable')
    s.set_defaults(fn=cmd_test)
    s = sub.add_parser('evidence', help='write what a CI job proved about the tests that say `runs on:`')
    s.add_argument('--job', required=True, help='the job name; it is also the file name')
    s.add_argument('--provides', required=True, help='the environments this job provides, comma-separated: linux,db')
    s.add_argument('--results', required=True, help='JSON file {test id: pass|fail}, as `sor test --out` writes it')
    s.add_argument('--out', help='where to write it (default: evidence/<job>.json)')
    s.add_argument('--commit', help='the commit the job ran on (hexadecimal); with --run, writes evidence format 2')
    s.add_argument('--run', help='the CI run id; with --commit, writes evidence format 2')
    s.set_defaults(fn=cmd_evidence)
    s = sub.add_parser('verify', help='check that every test that says `runs on:` has a current pass in every environment it names')
    s.add_argument('files', nargs='*', help='evidence files or folders (default: the evidence folder)')
    s.add_argument('--json', action='store_true')
    s.set_defaults(fn=cmd_verify)
    s = sub.add_parser('markers')
    s.add_argument('target', nargs='?', help='an id, or FILE:LINE')
    s.add_argument('--json', action='store_true',
                   help='machine-readable; without a target: every item, reference and region')
    s.set_defaults(fn=cmd_markers)
    s = sub.add_parser('hook', help='Claude Code hooks; reads the hook JSON on stdin')
    s.add_argument('which', choices=['pre-edit', 'post-read', 'session-start'])
    s.set_defaults(fn=lambda a: hook.run(a.which))
    s = sub.add_parser('show')
    s.add_argument('target', help='a part id (camera, render/culling, ROOT for the root) or an item id')
    s.set_defaults(fn=cmd_show)
    return ap


def as_hint(ap, cmd, extra):
    """What to add to argparse's "unrecognized arguments" when --as was given to a command that does not take it. The
    commands that do are found in the parser, so one that gains `--as` is named at once."""
    if not any(x == '--as' or x.startswith('--as=') for x in extra):
        return ''
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    takers = sorted(name for name, p in sub.choices.items() if '--as' in p._option_string_actions)
    if not takers:
        return ''
    names = ', '.join(takers[:-1]) + ' and ' + takers[-1] if len(takers) > 1 else takers[0]
    return f' (`--as NAME` is for {names} only; `{cmd}` does not take it)'


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
    ap = build_parser()
    args, extra = ap.parse_known_args(argv)
    if extra:   # what parse_args says, and for --as, which commands take it
        ap.error('unrecognized arguments: ' + ' '.join(extra) + as_hint(ap, args.cmd, extra))
    try:
        return args.fn(args)
    except BrokenPipeError:
        raise
    except lockfile.LockFormatError as e:   # a lock in a format this copy does not read: say to update, change nothing
        print(f'sor: {e}', file=sys.stderr)
        return 2
    except OSError as e:   # a file that cannot be read or written: say which, not a traceback
        print(f'sor: {e.strerror or e}' + (f': {e.filename}' if e.filename else ''), file=sys.stderr)
        return 2
