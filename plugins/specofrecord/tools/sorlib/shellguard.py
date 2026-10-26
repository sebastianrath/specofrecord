"""A warning when a shell command changes files that the edit guard watches (SPEC §15).

The edit guard (`hook.pre_edit`) sees Edit, Write and MultiEdit. A `sed -i`, a script, a formatter or a redirect writes the same files and goes by
it. So before a Bash command `sor hook pre-bash` notes, for each project the session works in, the stamps (time and size) of the files the guard
watches and which clauses already drift; after the command `sor hook post-bash` (also when it failed: Claude Code calls PostToolUse after a command
that succeeded and PostToolUseFailure after one that failed) compares, and tells Claude what the guard would have refused. It only says it: the
command has run, nothing is undone, and the hook never blocks.

What it says: code that now drifts because of the command (a clause whose code changed while the clause did not), code of a clause that someone else
claimed (when claims are enforced), and a change to the lock file by anything but `sor lock`. Drift that was there before the command is not the command's:
the drift of a project is kept for the stamps it was worked out for, so that it costs a scan only when something changed since.

What it leaves alone: a line whose every command is `git` or `sor` (they rewrite spec, code and lock on purpose) or `cd`, `pushd`, `popd`, `export`, as long as
nothing is redirected to a file; a project of more than MAX_FILES files or whose files take longer than STAMP_SECONDS to look through; a command that
ends after the hook ran (a background job); a command that is cancelled (no hook runs after it). Projects are those above the folder the session is in
when the command runs (the `cwd` of the payload; it moves when the agent does `cd`) or, when there is none, up to MAX_PROJECTS below it (FIND_DEPTH levels,
FIND_DIRS folders, FIND_SECONDS), looked for again after FOUND_TTL.

What it does not look at: spec files. The edit guard refuses to rewrite one with Write and, when claims are enforced, to change a clause someone else claimed;
a script that does the same goes unnoticed, and so does code that a script adds outside every region (`sor check` finds that).

Anything that changes between the two hooks is told as having changed while the command ran: the hook cannot tell the command's writes from a person's, who may
save a file in an editor meanwhile, so the warning does not say to revert.
"""
import glob
import hashlib
import json
import os
import re
import shlex
import tempfile
import time

from . import claims
from .invoke import command_lines
from . import lock as lockfile
from .hook import clause_first_reasons, enforcing, find_root, program_index
from .invoke import CMD
from .markers import SKIP_DIRS, Scan, file_stamps
from .model import LEGACY_LOCK_FILE, LOCK_FILE, SPEC_DIR, Project, has_spec

MAX_FILES = 20000        # more files than this under the code roots: the project is left alone
STAMP_SECONDS = 1.0      # looking through the files takes at most this long, or the project is left alone
MAX_PROJECTS = 8
FIND_DEPTH = 4           # levels below the session's folder in which projects are looked for
FIND_DIRS = 3000         # folders looked through
FIND_SECONDS = 0.25
FOUND_TTL = 600          # seconds a list of projects (an empty one too) is kept
KEEP_SECONDS = 86400     # state files older than this are removed; a command that was cancelled leaves one
TOOLS = ('git', 'sor', 'sor.py')         # programs that change spec, code and lock on purpose
NEUTRAL = ('cd', 'pushd', 'popd', 'export')   # programs that write nothing
REDIRECT = re.compile(r'^[0-9]*[<>]+[&|]?$|^&>+$')
SEPARATOR = re.compile(r'^[();&|]+$')


# --- the command line ---------------------------------------------------------------------------------------------------------------

def parts_of(command):
    """([the words of each command of the line], readable): the commands joined by `&&`, `||`, `;`, `|`, `&`, parentheses or a new line, with the
    redirections among their words. `readable` is False when a line cannot be read (an open quote)."""
    parts, readable = [], True
    for line in command_lines(command):
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            readable = False
            continue
        current = []
        for w in words:
            if SEPARATOR.match(w):
                parts += [current] if current else []
                current = []
            else:
                current.append(w)
        parts += [current] if current else []
    return parts, readable


def redirects_to_a_file(words):
    """Whether a command writes with `>`, `>>`, `&>` or the like: a redirection that merges one stream into another (`2>&1`) and one to /dev/null do not."""
    for n, w in enumerate(words):
        if '>' in w and REDIRECT.match(w):
            target = words[n + 1] if n + 1 < len(words) else ''
            if (w.endswith('&') and target.isdigit()) or target == '/dev/null':
                continue
            return True
    return False


def kind_of(words):
    """'tool' for a `git` or `sor` command, 'neutral' for `cd` and the like or a line of assignments only, else None."""
    i = program_index(words)
    if i >= len(words):
        return 'neutral'
    base = os.path.basename(words[i])
    return 'tool' if base in TOOLS else 'neutral' if base in NEUTRAL else None


def analyse(command):
    """(exempt, has_tool): whether nothing in the line can change what the guard watches (every command is git, sor or neutral, nothing is redirected to a
    file, the line can be read), and whether some command of it is git or sor."""
    parts, readable = parts_of(command)
    exempt = readable and all(kind_of(p) and not redirects_to_a_file(p) for p in parts)
    return exempt, any(kind_of(p) == 'tool' for p in parts)


# --- state kept between the two hooks -------------------------------------------------------------------------------------------------

def tmp(name):
    return os.path.join(tempfile.gettempdir(), f'sor-shell-{name}.json')


def digest(*parts):
    return hashlib.sha1('\0'.join(parts).encode('utf8', 'replace')).hexdigest()[:16]


def read_json(path):
    try:
        with open(path, encoding='utf8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    scratch = f'{path}.{os.getpid()}.tmp'
    try:
        with open(scratch, 'w', encoding='utf8') as fh:
            json.dump(data, fh)
        os.replace(scratch, path)
    except OSError:
        try:
            os.remove(scratch)
        except OSError:
            pass


def sweep():
    """Removes the state files nobody will read: a command that was cancelled leaves one. At most every FOUND_TTL seconds."""
    marker = tmp('sweep')
    try:
        if time.time() - os.stat(marker).st_mtime < FOUND_TTL:
            return
    except OSError:
        pass
    write_json(marker, {})
    for path in glob.glob(tmp('*')):
        try:
            if path != marker and time.time() - os.stat(path).st_mtime > KEEP_SECONDS:
                os.remove(path)
        except OSError:
            pass


def call_id(payload):
    """What the two hooks of one command share: the session and the call (`tool_use_id`; the command itself when the payload has none)."""
    return digest('call', payload.get('session_id') or '', payload.get('tool_use_id') or (payload.get('tool_input') or {}).get('command') or '')


# --- the projects and what is known of each ---------------------------------------------------------------------------------------------

def look_below(top):
    found, seen, began = [], 0, time.monotonic()
    queue = [(os.path.abspath(top), 0)]
    while queue and seen < FIND_DIRS and len(found) < MAX_PROJECTS and time.monotonic() - began < FIND_SECONDS:
        folder, depth = queue.pop(0)
        seen += 1
        if has_spec(folder):
            found.append(folder)   # a project: not looked into
            continue
        if depth >= FIND_DEPTH:
            continue
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            if not name.startswith('.') and name not in SKIP_DIRS and os.path.isdir(path) and not os.path.islink(path):
                queue.append((path, depth + 1))
    return found


def projects_of(payload):
    """The project roots the session works in: the one above the folder it is in (the `cwd` of the payload), else those below it (kept for FOUND_TTL seconds)."""
    cwd = os.path.abspath(payload.get('cwd') or os.getcwd())
    above = find_root(os.path.join(cwd, 'x'))
    if above:
        return [above]
    path = tmp(digest('projects', payload.get('session_id') or '', cwd))
    kept = read_json(path)
    if kept and time.time() - kept.get('at', 0) < FOUND_TTL:
        return [r for r in kept.get('roots', []) if has_spec(r)]
    roots = look_below(cwd)
    write_json(path, {'at': time.time(), 'roots': roots})
    return roots


def stamps(project):
    """{path: [mtime_ns, size]} of what the guard watches in a project (the spec files, the files under the code roots, the lock), or None for a project
    too big to look through quickly."""
    found = file_stamps(project, until=time.monotonic() + STAMP_SECONDS, limit=MAX_FILES)
    if found is None:
        return None
    for name in (LOCK_FILE, LEGACY_LOCK_FILE):
        path = os.path.join(project.spec_dir, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        found[path] = (st.st_mtime_ns, st.st_size)
    return {p: list(v) for p, v in found.items()}


def drift_findings(project, scan=None):
    """The findings with status drift, or None when that cannot be told (a lock this copy cannot read, a project that does not load). No lock: no drift."""
    try:
        old = lockfile.read(project)
        if not old:
            return []
        findings, _ = lockfile.status(project, scan or Scan(project), old)
    except (Exception, SystemExit):
        return None
    return [f for f in findings if f.status == 'drift']


def identities(findings):
    return sorted([f.key, f.detail] for f in findings)


def known_drift(session, project, found):
    """[[key, detail]] of the clauses that drift in a project whose files have these stamps: kept from the last time it was worked out for the same
    stamps, so that a scan is paid for only when something changed. None when it cannot be told."""
    path = tmp(digest('drift', session, project.root))
    kept = read_json(path)
    if kept and kept.get('stamps') == found:
        return kept.get('drift')
    drift = drift_findings(project)
    write_json(path, {'stamps': found, 'drift': None if drift is None else identities(drift)})
    return None if drift is None else identities(drift)


# --- the two hooks --------------------------------------------------------------------------------------------------------------------

def before(payload):
    """Notes what a Bash command could change: for each project, the stamps of the files the guard watches and the clauses that drift."""
    exempt, _ = analyse((payload.get('tool_input') or {}).get('command') or '')
    if exempt:
        return None
    session, state = payload.get('session_id') or '', {}
    for root in projects_of(payload):
        try:
            project = Project(root)
            found = stamps(project)
            if found is not None:
                state[root] = {'stamps': found, 'drift': known_drift(session, project, found)}
        except (Exception, SystemExit):
            continue
    if state:
        write_json(tmp(call_id(payload)), {'at': time.time(), 'projects': state})
        sweep()
    return None


def check_project(root, was, payload, has_tool):
    """The lines to say about one project after a command, given what `before` noted."""
    project = Project(root)
    now = stamps(project)
    if now is None:
        return []
    changed = sorted(p for p in set(was['stamps']) | set(now) if was['stamps'].get(p) != now.get(p))
    if not changed:
        return []
    rel = lambda p: os.path.relpath(p, root).replace(os.sep, '/')   # noqa: E731
    locks = {os.path.join(project.spec_dir, LOCK_FILE), os.path.join(project.spec_dir, LEGACY_LOCK_FILE)}
    lines = []
    if not has_tool and locks & set(changed):
        lines.append(f'- {SPEC_DIR}/{LOCK_FILE} changed: it is written only by `{CMD} lock`, which checks clauses, code and test results first '
                     '(another session\'s lock can be the reason).')
    scan = Scan(project)
    code = [rel(p) for p in changed if p not in locks and not p.startswith(project.spec_dir + os.sep) and scan.covers(rel(p))]
    if not code:
        return lines
    drift = drift_findings(project, scan)
    write_json(tmp(digest('drift', payload.get('session_id') or '', project.root)),
               {'stamps': now, 'drift': None if drift is None else identities(drift)})
    if drift is not None and was.get('drift') is not None:
        known = {tuple(x) for x in was['drift']}
        new = [f for f in drift if (f.key, f.detail) not in known]
        if new:
            lines.append('Clauses come first: code changes only after the clause it serves has changed.')
            lines += clause_first_reasons(project, new, code[0])
    session = payload.get('session_id') or ''
    if enforcing() and session:
        keys = {k for r in scan.regions if r.file in code for k in r.keys if not k.startswith('glue:')}
        regions = {(f, ids) for f, ids in claims.regions_of(scan, keys) if f in code}
        held = claims.others_for_agent(project, session, payload.get('agent_id') or '', keys, regions, text=False)
        if held:
            lines.append('Someone else is working on this: the code of a clause in a file the command changed is claimed.')
            lines += [f'- {claims.describe(c)}' for c in held]
    return lines


def after(payload):
    """Tells Claude what a command that has run changed behind the edit guard's back. None when it changed nothing the guard watches."""
    path = tmp(call_id(payload))
    saved = read_json(path)
    if not saved:
        return None
    try:
        os.remove(path)
    except OSError:
        pass
    _, has_tool = analyse((payload.get('tool_input') or {}).get('command') or '')
    lines = []
    for root, was in saved.get('projects', {}).items():
        try:
            found = check_project(root, was, payload, has_tool)
        except (Exception, SystemExit):
            continue
        if found:
            lines += ([f'In {root}:'] if len(saved['projects']) > 1 else []) + found
    if not lines:
        return None
    text = ('Spec of Record: files that the edit guard watches changed while this command ran. The guard checks Edit, Write and MultiEdit only, so it did '
            'not see the change, and nothing was undone.\n' + '\n'.join(lines) + '\n'
            'If the behaviour should change, edit the clause and make the code change again. If the command made a change that should not stand, revert that '
            'one. A person may have saved a file in the editor while the command ran: keep a change of theirs, and follow the steps for code a person changed. '
            'Use Edit on files the guard watches: it checks this before it writes.')
    return {'hookSpecificOutput': {'hookEventName': payload.get('hook_event_name') or 'PostToolUse', 'additionalContext': text}}
