"""Claude Code hooks that keep an agent clauses-first.

    sor hook pre-edit    PreToolUse on Edit|Write|MultiEdit: refuses an edit that changes the
                          code of a clause that has not changed since the last lock
    sor hook post-read   PostToolUse on Read: adds the clauses behind the regions just read
    sor hook session-start   SessionStart: a note saying this project has a spec, when it has, a short index of its parts, and what is pending
    sor hook pre-bash    PreToolUse on Bash: asks the user before a `sor lock` that carries --allow-behind runs
    sor hook session-end   SessionEnd: frees the claims the ending session made

They read the hook's JSON on stdin. Files outside a project, or outside its code, pass.
"""
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from collections import Counter

from . import claims
from . import lock as lockfile
from . import views
from .claims import CLAIMS_FILE
from .invoke import CMD, PLUGIN, getenv
from .markers import Scan
from .model import LEGACY_LOCK_FILE, LOCK_FILE, PART_FILE_NAME, SPEC_DIR, Project, has_spec

PENDING = ('new', 'changed', 'stale', 'removed', 'behind')
MAX_CONTEXT = 6000
INDEX_MAX = 1200   # characters of the parts index at session start (SPEC §15)
PENDING_MAX = 900  # characters of the line about pending changes at session start, its end included


def find_root(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if has_spec(d):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def apply_edit(tool, inp, text):
    """The file's text after the tool call, or None when it cannot be worked out."""
    if tool == 'Write':
        return inp.get('content')
    edits = inp.get('edits') if tool == 'MultiEdit' else [inp]
    for e in edits or []:
        old, new = e.get('old_string', ''), e.get('new_string', '')
        if text is None or old not in text:
            return None
        text = text.replace(old, new) if e.get('replace_all') else text.replace(old, new, 1)
    return text


def where_to_change(project, key):
    found = project.find(key)
    if found is None:
        return key
    kind, o = found
    file = lambda part: os.path.relpath(part.path, project.root).replace(os.sep, '/')
    if kind == 'part':
        return file(o)
    if kind == 'row':
        item = project.items[o.id.rsplit('/', 1)[0]]
        return f'the row **{o.name}** of **{item.name}** in {file(item.part)}'
    return f'**{o.name}** in {file(o.part)}'


class _NoCode:
    """Stands in for a Scan when only the clauses' own text matters."""
    def code_hashes(self, legacy=False):
        return {}

    def target_code_hashes(self):
        return {}


def enforcing():
    """Claims are enforced only when SOR_ENFORCE_CLAIMS=1 is set for the hook (SPEC §16): switched
    on once the hook's session id is known to match the one the CLI finds."""
    return getenv('ENFORCE_CLAIMS').lower() in ('1', 'true', 'yes')


def spec_keys_touched(project, path, new_text):
    """Lock keys whose text the edit would change, found by parsing a copy with the edit applied.
    None when that cannot be worked out (then the edit is not blocked)."""
    tmp = tempfile.mkdtemp(prefix='sor-guard-')
    try:
        shutil.copytree(project.spec_dir, os.path.join(tmp, project.spec_name),
                        ignore=shutil.ignore_patterns('.sor-claims.*', '.sor-lock.mutex', '.claims.*', '.lock.mutex'))
        target = os.path.join(tmp, project.spec_name, os.path.relpath(path, project.spec_dir))
        with open(target, 'w', encoding='utf8', newline='') as fh:
            fh.write(new_text)
        a = lockfile.snapshot(Project(tmp), _NoCode())
        b = lockfile.snapshot(project, _NoCode())
        return {k for k in set(a) | set(b) if a.get(k, {}).get('text') != b.get(k, {}).get('text')}
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def claim_refusal(project, payload, keys, regions=()):
    """A refusal when another agent holds a claim on what the edit touches: who, since when, until
    when at the latest. The agent decides what to do next. None when free, or not enforcing."""
    if not enforcing() or not keys:
        return None
    sid = (payload.get('session_id') or '').strip()
    if not sid:
        return None   # cannot tell who is editing
    held = claims.others_for_session(project, sid, keys, regions)
    if not held:
        return None
    lines = [f'- {claims.describe(c)}' for c in held]
    return deny('Someone else is working on this: the clause or its code is claimed.\n' + '\n'.join(lines) + '\n'
                'A claim ends at the time shown at the latest, sooner if its holder releases it. Work on another '
                f'clause, or wait a little and try again (`{CMD} claim <id>` tells you when it is '
                'free). Do not edit this clause or its code meanwhile.')


def is_skeleton(root, rel, path):
    """Whether the file is byte for byte what `sor new` writes for its part: nobody has touched it, so nobody's changes can
    be lost by writing it whole. The sentence given to --why is read from the file's Why: line and the skeleton is made
    again with it, so only a change to that line goes unnoticed (it is the one line whose text `sor new` does not choose)."""
    name = rel[len(SPEC_DIR) + 1:-3]
    if name != PART_FILE_NAME and not views.PART_ID.match(name):   # the folder form (<id>/SPECOFRECORD.md), CLAUSES.md, .tests.md: sor new writes none
        return False
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
    except OSError:
        return False
    why = next((line[5:] for line in data.decode('utf8', 'replace').split('\n') if line.startswith('Why: ')), None)
    if why is None:
        return False
    return data == views.skeleton('' if name == PART_FILE_NAME else name, root, None if why == views.WHY else why).encode('utf8')


def renew_quietly(project, session):
    """A hook call is a sign of life of the claims of its session (`claims.touch`), and whatever goes wrong while recording it costs the hook
    nothing: the edit keeps its check and the read its note."""
    try:
        claims.touch(project, session)
    except Exception:  # noqa: BLE001  a hook must not fail for this
        pass


def renew_claims(root, payload):
    """An edit by a session renews its claims. It reads the claims file and nothing else, so the project is not parsed for it."""
    session = payload.get('session_id') or ''
    if session and os.path.isfile(os.path.join(root, SPEC_DIR, CLAIMS_FILE)):
        renew_quietly(claims.at(root), session)


def pre_edit(payload):
    tool, inp = payload.get('tool_name', ''), payload.get('tool_input') or {}
    path = inp.get('file_path') or ''
    root = path and find_root(path)
    if not root:
        return None
    rel = os.path.relpath(os.path.abspath(path), root).replace(os.sep, '/')
    renew_claims(root, payload)
    if rel in (f'{SPEC_DIR}/{LOCK_FILE}', f'{SPEC_DIR}/{LEGACY_LOCK_FILE}'):
        return deny(f'{LOCK_FILE} is written only by `sor lock`, which checks clauses, code and '
                    f'test results first. Run `{CMD} lock` instead of editing it.')
    if rel in (f'{SPEC_DIR}/{CLAIMS_FILE}', f'{SPEC_DIR}/.claims.json'):
        return deny(f'{CLAIMS_FILE} is written only by `sor claim` and `sor release`. '
                    f'Run `{CMD} claim <id>` instead of editing it.')
    if rel.startswith(SPEC_DIR + '/'):
        if tool == 'Write' and rel.endswith('.md') and os.path.isfile(path) and not is_skeleton(root, rel, path):
            # Write replaces the whole file from what the agent read earlier, and erases whatever
            # other agents changed since. Edit replaces one string in the current text. A skeleton
            # `sor new` just wrote has nothing to erase: the claims below still apply to it.
            return deny(f'Do not rewrite {rel} with Write: it erases changes others made since you read it. '
                        'Change the clause with Edit (one clause at a time), or MultiEdit.')
        if enforcing() and rel.endswith('.md') and os.path.isfile(path):
            with open(path, encoding='utf8', errors='replace', newline='') as fh:
                new_text = apply_edit(tool, inp, fh.read())
            if new_text is not None:
                project = Project(root)
                refusal = claim_refusal(project, payload, spec_keys_touched(project, path, new_text))
                if refusal:
                    return refusal
        return None  # clauses are free to change: that is the first step
    project = Project(root)
    before = Scan(project)
    if not before.covers(rel):
        return None
    try:
        lock = lockfile.read(project)
    except lockfile.LockFormatError as e:   # the guard cannot tell what drifted from a lock it cannot read
        return deny(f'{e} Until then this copy cannot tell which edits the clauses allow, so edits to code are refused.')
    if not lock:
        return None  # nothing accepted yet, so nothing to drift from
    old_text = None
    if os.path.isfile(path):
        with open(path, encoding='utf8', errors='replace') as fh:
            old_text = fh.read()
    new_text = apply_edit(tool, inp, old_text)
    if new_text is None:
        return None  # the edit will fail on its own
    after = Scan(project, {path: new_text})
    if enforcing():
        a, b = after.code_hashes(), before.code_hashes()
        touched = {k for k in set(a) | set(b) if a.get(k) != b.get(k) and not k.startswith('glue:')}
        refusal = claim_refusal(project, payload, touched, claims.regions_of(after, touched))
        if refusal:
            return refusal
    was, _ = lockfile.status(project, before, lock)
    now, _ = lockfile.status(project, after, lock)
    pending = {f.key for f in now if f.status in PENDING}
    was_drift = {(f.key, f.detail) for f in was if f.status == 'drift'}   # a clause drifting in another target is more drift
    drift = [f for f in now if f.status == 'drift' and (f.key, f.detail) not in was_drift]
    reasons, by_where = [], {}
    for f in drift:
        by_where.setdefault(f.where or rel, []).append(f.key)
    for where, keys in by_where.items():
        targets = [where_to_change(project, k) for k in keys]
        if len(keys) == 1:
            reasons.append(f'- {where} serves `{keys[0]}`: change {targets[0]} first.')
        else:
            reasons.append(f'- {where} serves {", ".join(f"`{k}`" for k in keys)}: change one of '
                           + ', '.join(targets) + ' first.')

    def counts(scan):
        return Counter((p.kind, p.text) for p in scan.problems if p.where.startswith(rel + ':'))
    added = counts(after) - counts(before)
    for (kind, text), n in sorted(added.items()):
        hint = {'unmarked': 'put it inside a `@clause <id>` … `@clause end` region named after its clause',
                'marker': f'markers may only name ids that exist in {SPEC_DIR}/: add the clause first'}.get(kind, '')
        reasons.append(f'- {kind}: {text}' + (f' — {hint}' if hint else ''))
    glue = [f for f in now if f.status == 'glue' and f.key == f'glue:{rel}']
    if glue and not pending and not any(f.status == 'glue' and f.key == f'glue:{rel}' for f in was):
        reasons.append('- glue changed while no clause is being built: wiring changes come with a clause change.')
    if not reasons:
        return None
    return deny(
        'Clauses come first: code changes only after the clause it serves has changed.\n'
        + '\n'.join(reasons) + '\n'
        'If the behaviour should change, edit the clause, then repeat this edit. If the code is wrong '
        'and the clause is right (a bug), first give the clause\'s own test another `do:` / `expect:` pair and a '
        '`bug:` line, or add a second test with `proves: {clause}` and a `bug:` line. '
        f'`{CMD} show <id>` shows a clause with its code; `{CMD} status` lists what may change now.')


SHELL_OPERATOR = re.compile(r'^[();&|<>]+$')   # what shlex makes of `&&`, `||`, `;`, `|`, parentheses and redirections
LOCK_FLAGS_WITH_A_VALUE = ('--as', '--results', '--confirm')


def is_allow_behind(word):
    """Whether a word is the option --allow-behind, also as `--allow-behind=ts` and as the shortest prefix argparse takes for it."""
    name = word.split('=', 1)[0]
    return len(name) >= len('--allow-b') and '--allow-behind'.startswith(name)


PREFIXES = ('env', 'time', 'nohup', 'command', 'exec', 'sudo', 'nice', 'timeout')   # words that run the next word as a program
SHELLS = ('bash', 'sh', 'zsh', 'dash', 'ksh', 'eval')                               # programs whose argument is a command line


def program_index(words):
    """Where the program of a command is: past `VAR=x` assignments, the words in PREFIXES and a Python launcher with its options. A word
    that merely appears among the arguments of another program (`echo sor lock ...`) is not one."""
    i = 0
    while i < len(words):
        base = os.path.basename(words[i])
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', words[i]):
            i += 1
        elif base in PREFIXES:
            i += 2 if base == 'timeout' else 1
        else:
            break
    if i < len(words) and re.match(r'^(python[0-9.]*|py)(\.exe)?$', os.path.basename(words[i])):
        i += 1
        while i < len(words) and words[i].startswith('-'):
            i += 1
    return i


def lock_allowance(words):
    """(ids, languages) when these words are a `sor ... lock` that carries --allow-behind, else None."""
    i = program_index(words)
    if i >= len(words) or os.path.basename(words[i]) not in ('sor', 'sor.py') or 'lock' not in words[i + 1:]:
        return None
    args = words[words.index('lock', i + 1) + 1:]
    ids, languages, allowed, k = [], [], False, 0
    while k < len(args):
        a = args[k]
        if is_allow_behind(a):
            allowed = True
            value = a.split('=', 1)[1] if '=' in a else (args[k + 1] if k + 1 < len(args) else '')
            languages += [t for t in value.split(',') if t]
            k += 1 if '=' in a else 2
        elif a in LOCK_FLAGS_WITH_A_VALUE:
            k += 2
        else:
            if not a.startswith('-') and not a.isdigit():   # a number is what is left of `2>&1`
                ids.append(a)
            k += 1
    return (ids, languages) if allowed else None


def lock_allowances(command, depth=0):
    """[(ids, languages)] of every `sor lock --allow-behind` in a shell command line: the commands joined by `&&`, `||`, `;`, `|` or a new
    line, and what a quoted argument holds (`bash -c "..."`). A word `lock` and the option in a command that cannot be read (an open quote) count,
    for a guard that errs the other way would not guard."""
    found, body_ends = [], None   # body_ends: the word that ends a here-document whose lines are data, not commands
    for line in command.split('\n'):
        if body_ends is not None:
            if line.strip() == body_ends:
                body_ends = None
            continue
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            if re.search(r'\block\b', line) and re.search(r'--allow-b', line):
                found.append(([], []))
            continue
        segments, current = [], []
        for n, w in enumerate(words):
            if w == '<<' and n + 1 < len(words) and body_ends is None:   # a here-document: `cat > f <<'EOF'` writes the lines that follow, `bash <<EOF` runs them
                i = program_index(current)
                if not (i < len(current) and os.path.basename(current[i]) in SHELLS):
                    body_ends = words[n + 1].lstrip('-')
            if SHELL_OPERATOR.match(w):
                segments, current = segments + ([current] if current else []), []
            else:
                current.append(w)
        for segment in segments + ([current] if current else []):
            call = lock_allowance(segment)
            if call:
                found.append(call)
            elif depth < 3:
                i = program_index(segment)
                if i < len(segment) and os.path.basename(segment[i]) in SHELLS:   # `bash -c "sor lock ..."`: its argument is a command line
                    for w in segment[i + 1:]:
                        if ' ' in w:
                            found += lock_allowances(w, depth + 1)
    return found


def session_end(payload):
    """Frees the claims made in the session that is ending, so a closed chat does not hold clauses until its idle window runs out. A crash skips
    this hook, and the idle window covers that. It looks for the project from the folder the session ends in, so a session started above its
    project (a monorepo root with the project in a subfolder) keeps its claims until the idle window runs out."""
    root = find_root(os.path.join(payload.get('cwd') or os.getcwd(), 'x'))
    if root:
        claims.release_session(Project(root), payload.get('session_id') or '')
    return None


def pre_bash(payload):
    """Asks the user before a `sor lock --allow-behind` runs: the flag lets a language stay behind a clause, or lack code for it, and that is the
    user's call. A command that merely mentions the flag (a grep, a document) passes. This guards Claude Code only; a person's terminal is not
    touched."""
    if payload.get('tool_name') not in (None, 'Bash'):
        return None
    calls = lock_allowances((payload.get('tool_input') or {}).get('command') or '')
    if not calls:
        return None
    parts = []
    for ids, languages in calls:
        what = ', '.join(ids) if ids else 'what it claimed'
        who = ', '.join(languages) if languages else 'a language'
        parts.append(f'`{CMD} lock` of {what} with --allow-behind: {who} would stay behind the clause or have no code for it')
    reason = '; '.join(parts) + '. Allow it only if you have said that this language comes later.'
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask', 'permissionDecisionReason': reason}}


def deny(reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': reason}}


def post_read(payload):
    inp = payload.get('tool_input') or {}
    path = inp.get('file_path') or ''
    root = path and find_root(path)
    if not root:
        return None
    project = Project(root)
    renew_quietly(project, payload.get('session_id') or '')
    scan = Scan(project)
    SPEC_DIR = project.spec_name
    rel = scan.rel(path)
    if rel.startswith(SPEC_DIR + '/') or not scan.covers(rel):
        return None
    first = int(inp.get('offset') or 1)
    last = first + int(inp['limit']) - 1 if inp.get('limit') else 10 ** 9
    regions = [r for r in scan.regions if r.file == rel and r.start <= last and (r.end or r.start) >= first]
    if not regions:
        return None
    hand = scan.by_hand(rel)
    lines = [f'Spec of Record: {rel} is {"hand-written code guarded by" if hand else "built from"} the clauses '
             f'in {SPEC_DIR}/. Change a clause before its code: edits to code whose clause did not change are refused.']
    try:
        lock = lockfile.read(project)
    except lockfile.LockFormatError:
        lock = {}   # the note below is about pending changes, which this copy cannot tell; the refusal comes with an edit
    if lock:
        findings, _ = lockfile.status(project, scan, lock)
        here = {k for r in regions for k in r.keys}
        open_ = [f'{f.key} ({f.status})' for f in findings if f.status in PENDING and f.key in here]
        if open_:
            lines.append('Clauses changed since the last lock, so their code may change now: ' + ', '.join(open_))
    shown = set()
    for r in regions:
        keys = [k for k in r.keys if not k.startswith('glue:')]
        if not keys:
            continue
        lines.append(f'\nlines {r.start}-{r.end} serve {", ".join(keys)}:')
        for k in keys:
            if k in shown:
                continue
            shown.add(k)
            found = project.find(k) if not k.split('/')[-1].startswith('test:') else ('item', project.items[k])
            if found is None:
                continue
            kind, o = found
            text = (f'{o.title}: {o.header.get("Why", "")}' if kind == 'part'
                    else o.text if kind == 'row' else '\n'.join(t for _, t in o.lines))
            lines.append(f'  [{k}] ' + text.strip().replace('\n', '\n    '))
    ctx = '\n'.join(lines)
    if len(ctx) > MAX_CONTEXT:
        ctx = ctx[:MAX_CONTEXT] + f'\n… (more: {CMD} markers ' + rel + ')'
    return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': ctx}}


def pending_line(project):
    """One line of facts about what is pending since the last lock: every finding `sor status` lists apart from the information group (clauses to
    build, a language behind, code built and not locked, something to review, drift), each with its detail, as many as fit in PENDING_MAX and then
    "and N more". Empty when nothing is pending and when there is no lock yet (every clause would be new)."""
    old = lockfile.read(project)
    if not old:
        return ''
    findings, _ = lockfile.status(project, Scan(project), old)
    listed = {s for group, statuses, _ in lockfile.GROUPS if group != 'info' for s in statuses}
    items = []
    for f in findings:
        if f.status in listed:
            detail = ' '.join((f.detail or '').split())
            items.append(f'{f.key} {f.status}' + (f' ({detail if len(detail) <= 60 else detail[:59].rstrip() + "…"})' if detail else ''))
    if not items:
        return ''

    def line(shown):   # the first `shown` items, and a count of the rest
        text = 'Pending since the last lock: ' + '; '.join(items[:shown])
        if shown < len(items):
            text += ('; ' if shown else '') + f'... and {len(items) - shown} more'
        return text + f' (`{CMD} status` has the detail).'

    shown = len(items)
    while shown and len(line(shown)) > PENDING_MAX:
        shown -= 1
    return line(shown)


def pending_note(project):
    """Lines of facts a session finds when it starts: what is pending since the last lock (`pending_line`), and the claims in force, which exist
    with or without a lock. Nobody can say which session left a change, so it says "since the last lock". A pending line that cannot be worked
    out (a lock this copy cannot read, a broken part) is left out, never an error."""
    lines = []
    try:
        pending = pending_line(project)
        if pending:
            lines.append(pending)
    except (Exception, SystemExit):
        pass
    held = claims.active(project)
    if held:
        shown = [claims.describe(c) for c in held[:3]]
        lines.append('Claims in force: ' + '; '.join(shown) + (f'; ... and {len(held) - 3} more' if len(held) > 3 else '') + '.')
    return '\n'.join(lines)


def session_start(payload):
    """One short note when the session starts in a project that has a spec, so an agent knows the
    workflow exists before it edits anything. Stated as facts, not orders (Claude Code's advice).
    It ends with a compact index of the parts (`id - Why`, at most INDEX_MAX characters); when the index
    cannot be built, the note stands alone."""
    cwd = payload.get('cwd') or os.getcwd()
    root = find_root(os.path.join(cwd, 'x'))
    if not root:
        return None
    how = ('The specofrecord:specofrecord skill describes the working order: change a clause first, claim it before '
           'editing, lock only what you claimed. ' if PLUGIN else 'CLAUDE.md describes the working order. ')
    ctx = (f'This project keeps its specification as clauses in {SPEC_DIR}/ (Spec of Record): the clauses are the '
           f'source of truth and the code is built from them. {how}`{CMD} status` lists what changed and who holds '
           'which clauses.')
    try:
        # a compact index of the parts, so an agent knows what exists: `id - Why`, the root left out
        project = Project(root)
        parts = []
        for pid in sorted(p for p in project.parts if p):
            part = project.parts[pid]
            why = ' '.join((part.header.get('Why') or part.title or '').split())
            why = why if len(why) <= 60 else why[:59].rstrip() + '…'
            parts.append(f'{pid} - {why}' if why else pid)
        for shown in range(len(parts), -1, -1):   # as many as fit in INDEX_MAX characters, with the tail saying how many are left
            index = 'Parts: ' + '; '.join(parts[:shown])
            if shown < len(parts):
                index += ('; ' if shown else '') + f'... and {len(parts) - shown} more: run `{CMD} parts`'
            if len(index) <= INDEX_MAX:
                break
        if parts:
            ctx += '\n' + index
    except (Exception, SystemExit):
        pass   # the note above is enough
    try:
        pending = pending_note(Project(root))
        if pending:
            ctx += '\n' + pending
    except (Exception, SystemExit):
        pass   # a lock this copy cannot read, a broken part: the note above is enough
    return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': ctx}}


HOOKS = {'pre-edit': pre_edit, 'post-read': post_read, 'session-start': session_start, 'pre-bash': pre_bash, 'session-end': session_end}


def run(which):
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8') or '{}')
        out = HOOKS[which](payload)
    except (Exception, SystemExit) as e:  # never block the agent because the tool itself failed (a refused project too)
        print(f'sor hook {which} failed: {type(e).__name__}: {e}', file=sys.stderr)
        return 1
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0
