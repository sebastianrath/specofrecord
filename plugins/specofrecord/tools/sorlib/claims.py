"""Clause claims (SPEC §16): who is working on which clauses, so parallel agents and people do not
collide. Advisory: `sor claim` records it, `sor status` shows it, `sor lock` respects it.

    <store>/claims.json    {"claims": [{agent, asked, keys, since, until, grant, rev, ...}], "next_grant": n}, rewritten whole through a
                           temp file and os.replace, so a reader never sees half a file
    <store>/claims.lock    the mutex: an OS file lock, which ends with the process that holds it

The store is one place for every working folder of a project, found per environment: a folder named by SOR_CLAIMS_DIR, else the
common git directory of the checkout (every worktree of a repository has the same one), else `sor/` as before, where the two files
are `.sor-claims.json` and `.sor-claims.lock`. See `store`.

A claim names clauses; what it holds is (1) every lock key those clauses own (their rows, values,
own test; for a part: all its items) and (2) the code regions marked with them. Two claims by
different agents conflict when either overlaps: a part against its items, an item against its
rows, or two clauses that share a code region, because editing that region is editing both. A
clause that merely shares *some other* region is not held: `colors` shares regions with almost
everything, and claiming the moon must not lock out the light.
Work renews a claim: a hook call or a `sor` command that carries the holder's session id (`renew`). A claim records `idle`, the
window in seconds or null for none, and `last`, the time of the last activity; `until` is `last + idle` (a date far away for none).
When it has passed the holder is *quiet*, which is not the end of the claim: whether a quiet holder's claim stands is decided when
somebody asks for the clause (`decide`), by what the holder left behind. A claim ends when its holder releases it, when `sor claim`
finds that nothing is left to protect, or by a takeover. What it leaves is a tombstone for TOMBSTONE seconds, only so that its
holder can be told (`sor lock`, `sor release`); every reader that wants claims in force goes through `active`.
"""
import errno
import glob
import hashlib
import json
import os
import re
import socket
import time
from types import SimpleNamespace

try:   # the OS file lock: fcntl on Unix, msvcrt on Windows; both are in the standard library
    import fcntl
except ImportError:   # pragma: no cover
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

from . import lock as lockfile
from .invoke import CMD, getenv
from .model import PART_FILE_NAME, SPEC_DIR, has_spec


CLAIMS_FILE = '.sor-claims.json'     # the claims file of a project whose claims live in its own folder (no repository, no SOR_CLAIMS_DIR)
MUTEX_FILE = '.sor-claims.lock'
STORE_SUBDIR = 'sor-claims'           # under the common git directory
STORE_FILE = 'claims.json'
STORE_MUTEX = 'claims.lock'
LOCK_MUTEX_FILE = '.sor-lock.mutex'   # held while the lock file is merged and rewritten
STALE_LOCK = 10      # seconds after which a leftover mutex file is broken where an OS lock cannot be had (the exclusive-create fallback)
WAIT_LOCK = 5        # seconds to wait for the mutex
DEFAULT_TTL = 30 * 60   # the idle window of a claim, in seconds, when nothing else says (`--ttl`, `Claims:` in the root file)
NEVER = 4102444800      # 2100-01-01: the `until` of a claim with no idle window, a date every tool can read (not null, not year 9999)
RENEW_FLOOR = 300       # a claim records its last activity at most this often, so it can end this much before its idle window is over
TOMBSTONE = 2 * 3600   # seconds a freed claim stays in the file, to tell its holder; pruned when the file is written
BIND_REFRESH = 3600     # a binding is rewritten when the same subagent binds again after this long, so that the day it is kept for counts from its last use
DEFAULT_PARKED = 24 * 3600   # how long a claim that its gone holder left unfinished work behind is held, in seconds, when the root file says nothing


class ClaimError(Exception):
    """Bad input: unknown id, no agent name, a busy claims file."""


def agent_name(given=None):
    """Who is asking: --as, else SOR_AGENT, else the Claude Code session (its Bash tool exports
    CLAUDE_CODE_SESSION_ID, and hooks get the same id as `session_id`). '' when none is known."""
    name = (given or getenv('AGENT') or '').strip()
    return name or session_agent(os.environ.get('CLAUDE_CODE_SESSION_ID'))


def current_session():
    """The Claude Code session this process runs in ('' for a person at a terminal)."""
    return (os.environ.get('CLAUDE_CODE_SESSION_ID') or '').strip()


def same_agent(c, agent, session):
    """Is claim `c` held by this agent? An agent is a session plus a name: two chats that both call a
    subagent `sub-a` are two agents. An old claim without a `session` field is compared by name."""
    if 'session' not in c:
        return c['agent'] == agent
    return c['agent'] == agent and c['session'] == session


def session_agent(session_id):
    """The agent name for a Claude Code session id ('' without one). The CLI and the edit hook both
    use this, so a claim made from the Bash tool is recognised by the hook."""
    sid = (session_id or '').strip()
    return 'session-' + sid[:8] if sid else ''


def parse_ttl(text):
    """The idle window a text names, in seconds: 90s, 30m, 2h, or `never` (None)."""
    if (text or '').strip().lower() == 'never':
        return None
    m = re.fullmatch(r'(\d+)\s*([smh]?)', (text or '').strip())
    if not m:
        raise ClaimError(f'--ttl "{text}": write it like 90s, 30m, 2h or never')
    n, unit = int(m.group(1)), m.group(2) or 'm'
    return n * {'s': 1, 'm': 60, 'h': 3600}[unit]


SETTING = re.compile(r'^(idle|parked)\s+(\S+)$', re.I)


def claims_setting(text):
    """(ok, {'idle': seconds or None, 'parked': seconds or None}) for the value of a `Claims:` line: `idle 30m`, `idle 2h`, `idle never`, and
    `parked 24h` (how long a claim that a gone holder left unfinished work behind is held), alone or joined with a comma: `idle 30m, parked 12h`."""
    out = {'idle': DEFAULT_TTL, 'parked': DEFAULT_PARKED}
    items = [x.strip() for x in (text or '').split(',')]
    for item in items:
        m = SETTING.match(item)
        if not m:
            return False, out
        try:
            out[m.group(1).lower()] = parse_ttl(m.group(2))
        except ClaimError:
            return False, out
    return bool(text and text.strip()), out


def idle_setting(text):
    """(ok, seconds or None) for the idle window a `Claims:` line says; see `claims_setting`."""
    ok, values = claims_setting(text)
    return ok, values['idle']


def project_setting(project, name):
    root = project.root_part()
    text = root.header.get('Claims', '').strip() if root else ''
    ok, values = claims_setting(text) if text else (True, {'idle': DEFAULT_TTL, 'parked': DEFAULT_PARKED})
    return values[name] if ok else {'idle': DEFAULT_TTL, 'parked': DEFAULT_PARKED}[name]


def project_idle(project):
    """The idle window the root file sets with `Claims: idle 30m` (seconds, None for never); DEFAULT_TTL when it says nothing or says
    something `sor check` reports."""
    return project_setting(project, 'idle')


def project_parked(project):
    """How long a claim that a gone holder left unfinished work behind is held, from the root file's `Claims: parked 24h` (seconds, None for never);
    DEFAULT_PARKED when it says nothing or says something `sor check` reports."""
    return project_setting(project, 'parked')


# --- where the claims live

def root_of(project):
    return getattr(project, 'root', None) or os.path.dirname(project.spec_dir)


def git_dirs(root):
    """(top of the checkout, its common git directory) for a folder inside a git checkout, else None. Every worktree of a repository has the
    same common directory. It is read from the files git keeps: a `.git` folder (the main checkout), or a `.git` file (a linked worktree) that
    names the worktree's own git directory, which names the common one in `commondir`. Git itself is not started: this runs on every hook call."""
    d = os.path.realpath(root)
    while True:
        g = os.path.join(d, '.git')
        if os.path.isdir(g):
            return d, g
        if os.path.isfile(g):
            try:
                with open(g, encoding='utf8') as fh:
                    first = fh.readline().strip()
            except OSError:
                return None
            if not first.startswith('gitdir:'):
                return None
            gitdir = os.path.normpath(os.path.join(d, first[len('gitdir:'):].strip()))
            try:
                with open(os.path.join(gitdir, 'commondir'), encoding='utf8') as fh:
                    common = os.path.normpath(os.path.join(gitdir, fh.read().strip()))
            except OSError:
                common = gitdir   # a submodule's git directory, or one with no linked worktrees
            return d, common
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def root_title(spec_dir):
    """The title of the root file (`# Title`), '' when there is none: the name of a project that is in no repository."""
    for name in (PART_FILE_NAME + '.md', 'CLAUSES.md'):
        try:
            with open(os.path.join(spec_dir, name), encoding='utf8') as fh:
                for line in fh:
                    if line.startswith('# '):
                        return line[2:].strip()
        except OSError:
            continue
    return ''


def project_key(project, top, titled=False):
    """The name of a project's folder in a store several projects share (SOR_CLAIMS_DIR, a repository with more than one sor project): its path within
    the repository, or, with no repository, the title of its root file. A folder that SOR_CLAIMS_DIR names serves every project of the machine, so there the
    title is part of the key too (`titled`): two unrelated projects at the root of their repositories do not share one. In the common git directory it is
    not, since that store is the repository's own and a branch may rename the title. A readable start and a hash."""
    rel = ''
    if top:
        rel = os.path.relpath(os.path.realpath(root_of(project)), os.path.realpath(top)).replace(os.sep, '/')
        rel = '' if rel == '.' else rel
    title = root_title(project.spec_dir) if (titled or not top) else ''
    slug = re.sub(r'[^a-z0-9]+', '-', (rel or title).lower()).strip('-')[:24] or 'project'
    return f'{slug}-{hashlib.sha1((rel + chr(10) + title).encode("utf8")).hexdigest()[:8]}'


def store(project):
    """Where this project's claims are kept, found the same way from every working folder of it: SOR_CLAIMS_DIR (a folder the user names: for a shared
    drive, clones, Perforce workspaces, anything), else the common git directory of the checkout (every worktree of a repository shares it), else the
    project's own `sor/` folder as before. `kind` says which; `shared` says with whom, in words."""
    git = git_dirs(root_of(project))
    env = getenv('CLAIMS_DIR')
    if env and not os.path.isabs(os.path.expanduser(env)):
        raise ClaimError(f'SOR_CLAIMS_DIR={env} is a relative path, which every process would read against its own folder (a hook follows the agent\'s `cd`) and so find a store of its own: '
                         'write an absolute path')
    if env:
        folder = os.path.join(os.path.abspath(os.path.expanduser(env)), project_key(project, git[0] if git else None, titled=True))
        kind, shared = 'dir', f'every working folder that sets SOR_CLAIMS_DIR to {os.path.abspath(os.path.expanduser(env))}'
    elif git:
        folder = os.path.join(git[1], STORE_SUBDIR, project_key(project, git[0]))
        kind, shared = 'git', 'every working folder of this git repository (its worktrees); a clone of it has a store of its own unless SOR_CLAIMS_DIR names one'
    else:
        folder = project.spec_dir
        kind, shared = 'folder', 'this working folder only (no git repository, and SOR_CLAIMS_DIR is not set)'
    own = kind == 'folder'
    return SimpleNamespace(kind=kind, dir=folder, shared=shared, file=os.path.join(folder, CLAIMS_FILE if own else STORE_FILE),
                           mutex=os.path.join(folder, MUTEX_FILE if own else STORE_MUTEX))


def path(project):
    return store(project).file


def branch_label(root):
    """The branch a working folder is on, read from its HEAD file ('' when it is on none, or in no repository): a label for people, not part of any rule."""
    d = os.path.realpath(root)
    while True:
        g = os.path.join(d, '.git')
        try:
            if os.path.isfile(g):
                with open(g, encoding='utf8') as fh:
                    g = os.path.normpath(os.path.join(d, fh.readline().strip()[len('gitdir:'):].strip()))
            if os.path.isdir(g):
                with open(os.path.join(g, 'HEAD'), encoding='utf8') as fh:
                    head = fh.readline().strip()
                return head[len('ref: refs/heads/'):] if head.startswith('ref: refs/heads/') else ''
        except OSError:
            return ''
        parent = os.path.dirname(d)
        if parent == d:
            return ''
        d = parent


def where_here(project):
    """Where a claim is made: the working folder, the machine, and the branch as a label."""
    root = os.path.realpath(root_of(project))
    return {'path': root, 'host': socket.gethostname(), 'label': branch_label(root)}


def entry_sig(entry):
    """A short signature of a lock entry: what a claim remembers of the lock at the moment it was granted (`base`), and what it is compared with later."""
    return hashlib.sha1(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode('utf8')).hexdigest()[:12] if entry else ''


def lock_base(project, keys):
    """{key: signature of its lock entry now} for the keys of a claim, '' for a key the lock does not have yet. Empty when the lock cannot be read."""
    try:
        lock = lockfile.read(project)
    except (OSError, lockfile.LockFormatError):
        return {}
    return {k: entry_sig(lock.get(k)) for k in sorted(keys) if '@' not in k}


def start_state(project, scan, keys):
    """{key: signature of the entry the files make of it now} for the keys of a claim: what the claim starts from, so that `sor claim` can tell later what its holder
    changed since (`inspect`) from what was there before it, such as a project that has no lock yet, where every key is new. Empty when it cannot be worked out."""
    try:
        now = lockfile.snapshot(project, scan)
    except (Exception, SystemExit):
        return {}
    return {k: entry_sig(now[k]) for k in sorted(keys) if '@' not in k and k in now}


def old_file(project):
    """The claims file a tool from before the shared store left in the project's own folder."""
    return os.path.join(project.spec_dir, CLAIMS_FILE)


def adopt_old_file(project):
    """Moves the claims of the project's own folder (`sor/.sor-claims.json`, where claims lived before the shared store) into the store, once: a
    session that began before the move keeps its claims. Nothing happens when the store has a file already, or there is no old one."""
    st = store(project)
    old = old_file(project)
    if st.kind == 'folder' or not os.path.isfile(old) or os.path.isfile(st.file):
        return
    try:
        with open(old, encoding='utf8') as fh:
            held = json.load(fh).get('claims', [])
    except (OSError, ValueError):
        held = []
    if st.mutex in _HELD:
        _move_in(project, st, old, held)
    else:
        with _Mutex(project):
            if not os.path.isfile(st.file):
                _move_in(project, st, old, held)


def _move_in(project, st, old, held):
    held = [dict(c, where=c.get('where') or {'path': root_of(project), 'host': socket.gethostname()}) for c in held]
    _write(project, held)
    try:
        os.remove(old)
    except OSError:
        pass


def _read_raw(project):
    try:
        with open(path(project), encoding='utf8') as fh:
            held = json.load(fh).get('claims', [])
    except (OSError, ValueError):
        return []
    for c in held:   # a record from before grants (or written by hand) is given one that depends on what it says, and the next write keeps it
        if not c.get('grant'):
            c['grant'] = int(hashlib.sha1(json.dumps([c.get('agent'), c.get('asked'), c.get('since')]).encode()).hexdigest()[:12], 16)
    return held


def read(project):
    st = store(project)
    if st.kind != 'folder' and not os.path.isfile(st.file):
        adopt_old_file(project)
    return _read_raw(project)


def has_expired(c, now=None):
    """Has this claim been freed (it is a tombstone: it holds nothing, and stays in the file only so that its holder can be told)? A claim whose idle
    window has passed is not freed by that: it is quiet, and what happens to it is decided when somebody asks for the clause (`decide`)."""
    return bool(c.get('freed'))


def active(project, now=None):
    """The claims in force: every one that has not been freed. A quiet holder's claim is among them until it is decided that nothing is left to protect."""
    return [c for c in read(project) if not c.get('freed')]


def freed_at(c):
    return (c.get('freed') or {}).get('at', c.get('until', 0))


def lapsed(project, agent, session=None, now=None):
    """The agent's claims that were freed without it (quiet, the parked window over, or taken over) less than TOMBSTONE seconds ago, oldest first:
    what it has to be told when it comes back to lock or release."""
    now = time.time() if now is None else now
    session = current_session() if session is None else session
    out = [c for c in read(project) if c.get('freed') and now - TOMBSTONE < freed_at(c) <= now and same_agent(c, agent, session)
           and c['freed'].get('why') != 'released']
    return sorted(out, key=freed_at)


def _stamp(project, claims):
    """Gives every record its `grant` (a number no other record of the file has, and that rises with the clock, so one that comes back after the file was
    emptied is still a new one) and its `rev` (the number of writes that changed it: a reader that looked at a record can tell whether it is still the
    one it looked at)."""
    old = {c['grant']: c for c in _read_raw(project) if c.get('grant')}
    top = max([int(time.time() * 1000)] + [g + 1 for g in old] + [c['grant'] + 1 for c in claims if c.get('grant')])
    for c in claims:
        if not c.get('grant'):
            c['grant'], top = top, top + 1
        before = old.get(c['grant'])
        if before is None:
            c['rev'] = c.get('rev', 1)
        else:
            same = {k: v for k, v in c.items() if k != 'rev'} == {k: v for k, v in before.items() if k != 'rev'}
            c['rev'] = before.get('rev', 1) + (0 if same else 1)
    return claims


def _write(project, claims):
    st = store(project)
    p = st.file
    now = time.time()
    claims = [c for c in claims if not c.get('freed') or freed_at(c) > now - TOMBSTONE]   # tombstones older than that are forgotten here
    if not claims:   # nothing claimed: leave nothing behind in the project
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        return
    os.makedirs(st.dir, exist_ok=True)
    claims = _stamp(project, claims)
    for old in glob.glob(p + '.*.tmp'):   # left behind by a write that crashed
        try:
            if time.time() - os.path.getmtime(old) > 300:
                os.remove(old)
        except OSError:
            pass
    tmp = f'{p}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf8', newline='\n') as fh:
        json.dump({'claims': claims}, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    os.replace(tmp, p)


_HELD = set()   # the mutex files this process holds now (adopting the old claims file takes the mutex unless the caller already has it)


class _NoOsLock(Exception):
    """The file system gives no OS lock (some network shares): the mutex falls back to a file made exclusively and broken by age."""


class _Mutex:
    """The mutex of the claims store. An OS file lock (fcntl on Unix, msvcrt on Windows): it ends with the process that holds it, so a crashed holder
    leaves nothing to break, and the lock file itself is never removed (removing it would let two processes hold "the" lock on two files). Where the file
    system gives no OS lock, the old way: a file made with O_EXCL, broken when older than STALE_LOCK seconds, which two waiters can race for after a crash (SPEC §16)."""

    def __init__(self, project, name=None, path=None):
        self.path = path or (os.path.join(project.spec_dir, name) if name else store(project).mutex)
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        end = time.time() + WAIT_LOCK
        if fcntl or msvcrt:
            try:
                return self._os_lock(end)
            except _NoOsLock:
                pass
        return self._file_lock(end)

    def _os_lock(self, end):
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        while True:
            try:
                if fcntl:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                self.fd = fd
                _HELD.add(self.path)
                return self
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EACCES, errno.EDEADLK, errno.EWOULDBLOCK) or getattr(e, 'winerror', None) in (32, 33):
                    if time.time() > end:
                        os.close(fd)
                        raise ClaimError('the claims or lock file is busy; try again in a moment')
                    time.sleep(0.01)
                    continue
                os.close(fd)
                raise _NoOsLock() from None

    def _file_lock(self, end):
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                _HELD.add(self.path)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > STALE_LOCK:
                        # whoever left it died. If two waiters race here, one may remove the other's
                        # fresh mutex: after a crash only (SPEC §16)
                        os.remove(self.path)
                        continue
                except OSError:
                    continue
                if time.time() > end:
                    raise ClaimError('the claims or lock file is busy; try again in a moment')
                time.sleep(0.01)

    def __exit__(self, *exc):
        _HELD.discard(self.path)
        if self.fd is not None:
            try:
                if fcntl:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
                else:
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = None
            return
        try:
            os.remove(self.path)
        except OSError:
            pass


def line_id(project, ident):
    """(clause, language) for an id like `greet/hello@py`, the code of one language of a clause (SPEC §16); None for any other id. An id of that
    form that names no clause, or a language that does not apply to it, is not an id: `line_problem` says why."""
    base, sep, target = ident.rpartition('@')
    if not sep or not base or not project.targeted() or project.find(base) is None or project.find(base)[0] == 'part':
        return None
    return (base, target) if target in project.targets_applying_to(base) else None


def line_problem(project, ident):
    """Why an id with an `@` in it, which `line_id` does not take, is no language of a clause; '' for an id with no `@`."""
    base, sep, target = ident.rpartition('@')
    if not sep or not base:
        return ''
    if not project.targeted():
        return f'{ident}: this project keeps no code per language (`Targets:` in the root file), so there is only the clause'
    found = project.find(base)
    if found is None or found[0] == 'part':
        return f'{ident}: {base} is no clause'
    applies = project.targets_applying_to(base)
    return f'{ident}: {target} is not a language of {base} (it has {", ".join(applies) or "none"})'


def line_keys(project, base, target):
    """The keys a claim of one language of a clause holds: its line, and the lines of its own test and of its rows when they have any."""
    return {f'{k}@{target}' for k in lockfile.language_keys(project, base) if k == base or k in project.items}


def regions_in(project, scan, bases, target):
    """The code regions marked with any of these keys that lie in the files of one language: as `regions_of`, only a language's."""
    out = set()
    for r in scan.regions:
        if project.target_of(r.file) == target and any(k in bases for k in r.keys):
            out.add((r.file, tuple(sorted(k for k in r.keys if not k.startswith('glue:')))))
    return out


def footprint(project, universe, ids):
    """(keys, unknown): every lock key the ids own. `universe` is the set of lock keys that exist
    (now, and for `sor lock` also in the old lock, so a deleted clause can still be locked). A clause also owns its line in each language that
    applies to it (`greet/hello@py`, a key of the claim and not of the lock file), and the id of one language of a clause owns that line only."""
    keys, unknown = set(), []
    for ident in ids:
        lang = line_id(project, ident)
        if lang:
            keys |= line_keys(project, *lang)
            continue
        found = project.find(ident)
        mine = set()
        if found and found[0] == 'part':
            part = found[1]
            mine.add(part.key)
            for it in part.items.values():
                mine.add(it.id)
                mine.update(k for k in universe if k.startswith(it.id + '.') or k.startswith(it.id + '/'))
        else:
            for k in universe:
                if k == ident or k.startswith(ident + '.') or k.startswith(ident + '/'):
                    mine.add(k)
            part, _, name = ident.rpartition('/')
            test = f'{part}/test:{name}' if part else f'test:{name}'
            if ident in universe and found and found[0] == 'item':
                for k in universe:
                    if k == test or k.startswith(test + '.'):
                        mine.add(k)
        if not mine:
            unknown.append(ident)
        elif project.targeted():
            mine |= {f'{k}@{t}' for k in list(mine) if k in project.items for t in project.targets_applying_to(k)}
        keys.update(mine)
    return keys, unknown


def with_shared(project, scan, universe, keys):
    """keys plus everything that shares a code region with them: (all keys, the added ids)."""
    extra = set()
    for k in sorted(keys):
        for r in scan.regions_for(k):
            for other in r.keys:
                if other.startswith('glue:') or other in keys or other in extra:
                    continue
                extra.add(other)
    more = set()
    for other in extra:
        more |= footprint(project, universe, [other])[0]
    return keys | extra | more, sorted(extra)


def regions_of(scan, keys):
    """The code regions marked with any of the keys, as (file, ids on the region): line numbers
    move while agents edit, the ids on a region do not."""
    out = set()
    for r in scan.regions:
        if any(k in keys for k in r.keys):
            out.add((r.file, tuple(sorted(k for k in r.keys if not k.startswith('glue:')))))
    return out


def _regions(c):
    return {(f, tuple(ks)) for f, ks in c.get('regions', [])}


def conflicts(claim_list, keys, regions, text=True):
    """The claims that overlap these keys and regions. A claim of one language of a clause pins the clause (`pins` in the claim): it relies on its
    text, so it conflicts with whoever holds or edits that text (`text`: the keys include text, as for a spec edit or a lock of the clause, and not
    for an edit of code). A claim of the clause as a whole holds the clause's line in every language, so it overlaps a claim of one of them, and
    two claims of different languages of a clause do not overlap."""
    keys, regions = set(keys), set(regions)
    return [c for c in claim_list if set(c['keys']) & keys or _regions(c) & regions or (text and set(c.get('pins', ())) & keys)]


def when(ts):
    return time.strftime('%H:%M', time.localtime(ts))


def lifetime(seconds):
    """How long a claim holds, as people write it in --ttl: 30 min, 2 h, 90 s."""
    seconds = int(seconds)
    if seconds % 3600 == 0:
        return f'{seconds // 3600} h'
    return f'{seconds // 60} min' if seconds % 60 == 0 else f'{seconds} s'


def describe(c, now=None):
    """Who holds what, since when, when it last did something and when the claim ends if nothing more happens (a claim made by a tool from
    before `idle` has no record of activity and shows only when it ends). A holder that is gone says so: its session ended, a subagent stopped, or
    its window ran out and it is quiet."""
    now = time.time() if now is None else now
    mins = max(0, int((now - c['since']) // 60))
    if 'idle' not in c:
        return f"{c['agent']}: {', '.join(c['asked'])} (since {mins} min, until {when(c['until'])})"
    active = max(0, int((now - c.get('last', c['since'])) // 60))
    if c.get('ended'):
        ends = f"its session ended at {when(c['ended']['at'])}"
    elif c.get('stopped'):
        ends = f"it stopped at {when(c['stopped'])}"
    elif c['idle'] is None:
        ends = 'no idle limit'
    elif c['until'] <= now:
        ends = f"quiet since {when(c['until'])}"
    else:
        ends = f"ends at {when(c['until'])} if idle"
    return f"{c['agent']}: {', '.join(c['asked'])} (since {mins} min, last active {active} min ago, {ends})"


QUEUE_SILENT = 6 * 3600   # a queued signal older than this is "silent": the merge queue stopped saying it will merge the work


def queue(project, holder, by, now=None):
    """Records on the claims of `holder` that the party responsible for the merge (`by`: a merge queue, an orchestrator, a CI job, a person) has queued
    its work. It is a notice and nothing else: it frees nothing, ends no window, and is a name and not a proof. The number of claims marked."""
    now = time.time() if now is None else now
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if c.get('agent') == holder and not c.get('freed'):
                c['queued'] = {'by': by, 'at': now}
                count += 1
        if count:
            _write(project, held)
    return count


def queue_words(c, now=None):
    """What the notice says about whether finished work waiting for its merge is queued: by whom since when, nobody has said so, or the queue went silent."""
    now = time.time() if now is None else now
    q = c.get('queued')
    if not q:
        return 'nobody has said they will merge it'
    if now - q['at'] > QUEUE_SILENT:
        return f"queued by {q['by']}, but the queue has been silent since {when(q['at'])}"
    return f"queued by {q['by']} since {when(q['at'])}"


def states(project, held, scan=None, now=None, limit=None, first=False):
    """[(claim, Decision)] for every claim in `held`, the ones that hold nothing back too (kind free): what `sor claims` and `sor status` show. A holder at work is held
    without looking at anything else; the project is read only when a holder is gone, each holder's folder once per call. `limit`: at most that many holders that are gone
    are read, and the rest are taken to stand ("not looked at"). `first`: stop after the first that stands."""
    now = time.time() if now is None else now
    window = project_parked(project)
    out, lock, cache, looked = [], None, {}, 0
    for c in held:
        if not is_gone(c, now, window) and not _folder_gone(c):
            out.append((c, Decision('held', 'its holder is at work or has reserved it', folder=(c.get('where') or {}).get('path', ''),
                                    label=(c.get('where') or {}).get('label', ''))))
        elif limit is not None and looked >= limit:
            out.append((c, Decision('held', 'too many holders are gone to read them all here; `sor claim` decides', folder=(c.get('where') or {}).get('path', ''),
                                    label=(c.get('where') or {}).get('label', ''))))
        else:
            looked += 1
            if scan is None:
                from .markers import Scan
                scan = Scan(project)
            if lock is None:
                lock = _lock_of(project)
            out.append((c, decide(project, c, scan, lock, now, window, cache)))
        if first and out[-1][1].kind != 'free':
            break
    return out


def explain(c, d, now=None):
    """`describe`, and for a claim that stands because its holder left something behind, what and where, and what can be done about it."""
    line = describe(c, now)
    place = d.folder + (f' (branch {d.label})' if d.label else '')
    if d.kind == 'parked':
        n = d.changes
        return (line + f'\n    parked: its holder is gone and left unfinished work ({n} change{"s" if n != 1 else ""}) in {place}. `{CMD} claim --take-over <ids>` '
                       'continues the work there; the claim frees itself when the parked window is over')
    if d.kind == 'waiting':
        return (line + f'\n    waiting for the merge ({queue_words(c, now)}): its holder is gone, and its finished work in {place} has not reached this copy. The claim is '
                       'freed when that work arrives here (update this copy from where it is merged), or when its holder or a person releases it')
    if d.kind == 'free':
        return line + f'\n    holds nothing back: {d.why}; the next claim of it frees it'
    return line


def covers(ident, other):
    """Does the claimed id `ident` cover `other`: itself, or something under it (a part: its items and child
    parts)?"""
    return other == ident or other.startswith(ident + '/') or other.startswith(ident + '@')


def lapse_text(cs):
    """'claims on a, b expired at 00:31' for freed claims: one group per minute and kind. A claim that was taken over says by whom."""
    groups = {}
    for c in sorted(cs, key=freed_at):
        why = c.get('freed', {}).get('why')
        verb = f"taken over by {c['freed'].get('by')}" if why == 'taken over' else 'expired'
        ids = groups.setdefault((when(freed_at(c)), verb), [])
        ids += [a for a in c['asked'] if a not in ids]
    parts = [f"{', '.join(ids)} {verb} at {t}" if i == 0 else f"{', '.join(ids)} at {t}" if verb == 'expired' else f"{', '.join(ids)} {verb} at {t}"
             for i, ((t, verb), ids) in enumerate(groups.items())]
    return 'claims on ' + ', on '.join(parts)


def claim_again():
    """What to do about an expired claim, in the words the commands end their note with."""
    return f'claim again (a holder is quiet after {lifetime(DEFAULT_TTL)} idle by default; `--ttl 2h` for a longer window)'


def lost(project, agent, in_force=(), session=None, now=None):
    """The agent's expired claims (see `lapsed`), cut down to the ids that none of `in_force` covers: what
    it lost without knowing. A claim whose ids are all covered again is left out."""
    out = []
    for c in lapsed(project, agent, session, now):
        rest = [a for a in c['asked'] if not any(covers(i, a) for i in in_force)]
        if rest:
            out.append(dict(c, asked=rest))
    return out


def child_parts(project, ids, pending):
    """The parts under the claimed parts (`audio/mixer` under `audio`), those made after the claim included:
    a claim on a part is a claim on its subtree when it comes to locking, by the prefix rule `release` uses.
    Only those with a change of their own (`pending`: lock keys that are new, changed or removed): an untouched
    one has nothing to accept, and its drift or problems are not this lock's. The root is not expanded, its
    subtree would be the whole project."""
    under = set()
    for ident in ids:
        found = project.find(ident)
        if found and found[0] == 'part' and found[1].id:
            under.update(p for p in project.parts if covers(found[1].id, p))
    changed = {owner_part(project, k) for k in pending}
    return sorted((under & changed) - set(ids))


def owner_part(project, key):
    """The part a lock key belongs to: the part itself, or the nearest part above an item, row or value (also
    one that left the spec). '' for the root and for keys that belong to no part."""
    return project.owner_part_id(key)


def unheld(project, scan, universe, pids, agent, session=None):
    """(the parts of `pids` that no other agent's claim overlaps, {the others: the claims in the way}): a
    child part that someone else holds is theirs, and is left out of a lock rather than refusing it."""
    free, busy = [], {}
    for pid in pids:
        keys = footprint(project, universe, [pid])[0]
        theirs = others(project, agent, keys, regions_of(scan, keys), session=session)
        if theirs:
            busy[pid] = theirs
        else:
            free.append(pid)
    return free, busy


def _one(project, scan, universe, ident):
    """(keys, regions) of one asked id."""
    keys = footprint(project, universe, [ident])[0]
    lang = line_id(project, ident)
    if lang:
        return keys, regions_in(project, scan, lockfile.language_keys(project, lang[0]), lang[1])
    return keys, regions_of(scan, keys)


# --- whether a claim stands: what its holder left behind decides, not the clock alone

UNFINISHED = ('new', 'changed', 'removed', 'behind', 'drift')   # the findings of `sor status` that are work somebody has begun and not finished


def is_busy(c, now, window):
    """Is the holder's session working in the background? The last `Stop` of a session that has not ended listed work in flight (a long build runs in
    the background and renews nothing), which keeps it not quiet until the parked window has passed since then."""
    at = c.get('busy_at')
    return bool(at) and not c.get('ended') and (window is None or now - at < window)


def is_quiet(c, now, window=None):
    """Has the holder shown no sign of life for its idle window (`until` has passed), and is it not busy in the background?"""
    return c['until'] <= now and not is_busy(c, now, window)


def is_gone(c, now, window=None):
    """Has the holder ended its session, stopped (a subagent that `SubagentStop` reported), or fallen quiet?"""
    return bool(c.get('ended') or c.get('stopped')) or is_quiet(c, now, window)


def gone_since(c, now):
    """When the holder went: its session ended, it stopped, or its window ran out, whichever is the latest sign."""
    return max([(c.get('ended') or {}).get('at', 0), c.get('stopped') or 0] + ([c['until']] if c['until'] <= now else []))


class Decision(SimpleNamespace):
    """What `decide` says about one claim in the way: `kind` is free (nothing is left to protect), held (its holder is at work or reserved the clause),
    parked (the holder is gone and left unfinished work in another place), waiting (it is gone and its finished work has not reached this copy),
    and `why` the words for it; `folder`, `label` and `changes` say where the leftovers are."""

    def __init__(self, kind, why, **more):
        super().__init__(**dict({'folder': '', 'label': '', 'changes': 0}, kind=kind, why=why, **more))


def _lock_of(project):
    try:
        return lockfile.read(project)
    except (OSError, lockfile.LockFormatError):
        return None


def folder_state(project, c, scan, lock, same_folder, cache):
    """(project, scan, lock, findings, snapshot) of the working folder a holder is in, read the way `sor status` reads a project and without writing anything, or
    None when it cannot be read (another machine, no permission, not a project any more). `cache` ({path: result}) keeps what was read for the rest of the call:
    the claims of one folder share it."""
    from .markers import Scan
    from .model import Project
    if same_folder:
        proj, sc, lk = project, scan, lock
        where = os.path.realpath(root_of(project))
    else:
        if (c.get('where') or {}).get('host') not in (None, socket.gethostname()):
            return None   # a path on another machine says nothing about this one
        where = c['where']['path']
        if cache is not None and where in cache:
            return cache[where]
        try:
            proj = Project(where)
            sc, lk = Scan(proj), lockfile.read(proj)
        except (Exception, SystemExit):
            if cache is not None:
                cache[where] = None
            return None
    result = None
    if lk is not None and sc is not None:
        try:
            findings, _ = lockfile.status(proj, sc, lk)
            result = (proj, sc, lk, findings, lockfile.snapshot(proj, sc))
        except (Exception, SystemExit):
            result = None
    if cache is not None and not same_folder:
        cache[where] = result
    return result


def inspect(project, c, scan, lock, same_folder, cache=None):
    """What a holder has in its working folder: (unfinished keys, changed keys, worked, lock), or None when the folder cannot be read. `unfinished`: its keys that
    `sor status` lists as new, changed, removed, behind or drifting and that are not what they were when the claim was granted (`start`): what it did since, not what
    was there before it, so a project with no lock yet, or a person's edit made before the claim, does not park a claim that did nothing. A claim from before `start`
    counts every such finding. `changed`: the keys it locked since the grant, the ones whose entry differs from the `base` the claim recorded."""
    seen = folder_state(project, c, scan, lock, same_folder, cache)
    if seen is None:
        return None
    _, _, lk, findings, now = seen
    keys = {k for k in c.get('keys', []) if '@' not in k}
    start = c.get('start')
    unfinished = sorted({f.key.split('@')[0] for f in findings if f.status in UNFINISHED and f.key.split('@')[0] in keys
                         and (start is None or f.key.split('@')[0] not in start or entry_sig(now.get(f.key.split('@')[0])) != start[f.key.split('@')[0]])})
    base = c.get('base') or {}
    changed = sorted(k for k in keys if base and entry_sig(lk.get(k)) != base.get(k, ''))   # the keys it locked since the grant
    return SimpleNamespace(unfinished=unfinished, changed=changed, worked=bool(changed), lock=lk)


def decide(project, c, scan=None, lock=None, now=None, window=None, cache=None):
    """Whether a claim in the way stands, seen from this working folder (`project`, with its `scan` and `lock` when the caller has them): a Decision.
    The rules, first that fits: the holder's folder is gone (free, unless it locked work: that waits for its merge); the holder is not gone (held); its
    work has arrived in this copy (free); it is gone and its folder is this one (free: what it left is in files that are shared, and shows as changes
    to finish); it left unfinished work in another folder (parked, and free after the parked window); it left finished work that has not arrived
    (waiting for the merge, no limit); nothing was left (free). A folder that cannot be read leaves the idle window alone to decide."""
    now = time.time() if now is None else now
    window = project_parked(project) if window is None else window
    where = c.get('where') or {}
    path, here = where.get('path'), os.path.realpath(root_of(project))
    on_this_machine = where.get('host') in (None, socket.gethostname())
    if path and on_this_machine and not os.path.isdir(path):
        if not c.get('locked'):
            return Decision('free', 'its working folder is gone', folder=path, label=where.get('label', ''))
        lock = _lock_of(project) if lock is None else lock
        base = c.get('base') or {}
        if lock is not None and base and any(entry_sig(lock.get(k)) != base.get(k, '') for k in c.get('keys', []) if '@' not in k):   # the folder cannot say, this copy can
            return Decision('free', 'its working folder is gone, and its work has reached this copy', folder=path, label=where.get('label', ''))
        return Decision('waiting', 'its working folder is gone, and it locked work that waits for its merge', folder=path, label=where.get('label', ''))
    if not is_gone(c, now, window):
        return Decision('held', 'its holder is at work or has reserved it', folder=path or '', label=where.get('label', ''))
    same_folder = not path or os.path.realpath(path) == here
    ended = bool(c.get('ended') or c.get('stopped'))
    since = gone_since(c, now)
    if scan is None:
        from .markers import Scan
        scan = Scan(project)
    lock = _lock_of(project) if lock is None else lock
    seen = inspect(project, c, scan, lock, same_folder, cache)
    folder, label = path or here, where.get('label', '')
    if seen is None:   # a folder nobody here can read: only the idle window speaks
        return Decision('free' if is_quiet(c, now, window) else 'held', 'its folder cannot be read from here', folder=folder, label=label)
    base = c.get('base') or {}
    # arrived: it locked work, left nothing unfinished, and every entry it changed differs from the grant in this copy too (the merge brought it, or a later change)
    arrived = (seen.worked and not seen.unfinished and lock is not None and all(entry_sig(lock.get(k)) != base.get(k, '') for k in seen.changed))
    if arrived:
        return Decision('free', 'its work has reached this copy', folder=folder, label=label)
    if same_folder and ended:
        return Decision('free', 'its session ended, and what it left is in the files of this folder', folder=folder, label=label, changes=len(seen.unfinished))
    if seen.unfinished:
        if window is not None and now - since >= window:
            return Decision('free', 'it left unfinished work and the parked window passed', folder=folder, label=label, changes=len(seen.unfinished))
        return Decision('parked', 'its holder is gone and left unfinished work', folder=folder, label=label, changes=len(seen.unfinished))
    if seen.worked:
        return Decision('waiting', 'its holder is gone and its finished work has not reached this copy', folder=folder, label=label)
    return Decision('free', 'its holder is gone and left nothing', folder=folder, label=label)


GUARD_LOOKS = 8   # the holders that are gone which the edit guard reads per call: each is read in its own folder, and the hook has 30 seconds


def standing(project, held, scan=None, now=None):
    """[(claim, Decision)] of the claims in `held` that still stand, seen from this working folder: `states` without the ones that hold nothing back. It stops at the
    first that stands, which is all a refusal needs, and reads at most GUARD_LOOKS holders that are gone; a holder past that is taken to stand until `sor claim` decides."""
    return [(c, d) for c, d in states(project, held, scan, now, limit=GUARD_LOOKS, first=True) if d.kind != 'free']


def _folder_gone(c):
    where = c.get('where') or {}
    return bool(where.get('path')) and where.get('host') in (None, socket.gethostname()) and not os.path.isdir(where['path'])


def claim(project, scan, universe, ids, agent, ttl=DEFAULT_TTL, session=None, take_over=False):
    """(ok, result). `ttl`: the idle window in seconds, None for none. On success result has `keys`, `shared` (ids pulled in), `until`, `freed` (the claims it
    found nothing left to protect in, and freed) and `took_over` (the parked claims it took over, with `take_over`); on refusal `holders`, the claims in the
    way, `states` (what `decide` said about each), and `blocked`, the asked ids they are in the way of: a refused claim takes none of its ids, the free ones
    too. `blocked` is worked out after the mutex is let go: it does not need the claims file."""
    ok, res = _claim(project, scan, universe, ids, agent, ttl, session, take_over)
    if not ok:
        theirs = res.pop('theirs')
        res['blocked'] = [i for i in ids if conflicts(theirs, *_one(project, scan, universe, i))]
    return ok, res


def unknown_text(project, universe, unknown):
    """"no such clause or part: ...", and, for an id written with the root in front (`ROOT/year`, `SPECOFRECORD/year`),
    the id of the root item it was meant for: items of the root have no prefix."""
    text = 'no such clause or part: ' + ', '.join(unknown)
    fixes = []
    why = [line_problem(project, ident) for ident in unknown if line_problem(project, ident)]
    if why:
        return '; '.join(why)
    for ident in unknown:
        head, _, rest = ident.partition('/')
        if rest and head in ('ROOT', PART_FILE_NAME) and not footprint(project, universe, [rest])[1]:
            fixes.append(f'`{rest}`, not {ident}')
    return text + (f' (items of the root have no prefix: use {"; ".join(fixes)})' if fixes else '')


def _claim(project, scan, universe, ids, agent, ttl, session, take_over=False):
    """`claim` without `blocked`: a refusal carries the other agents' claims it was measured against, as `theirs`."""
    if not agent:
        raise ClaimError('say who you are: --as NAME, or set SOR_AGENT (a Claude Code session is recognised by itself)')
    session = current_session() if session is None else session
    keys, unknown, owned = set(), [], {}
    for ident in ids:
        owned[ident], bad = footprint(project, universe, [ident])
        keys |= owned[ident]
        unknown += bad
    if unknown:
        raise ClaimError(unknown_text(project, universe, unknown) + ' (to add a clause, claim the part that will hold it)')
    regions, pins, plain = set(), set(), {k for k in keys if '@' not in k}
    for ident in ids:   # a clause holds all its code, one language of it only that language's
        lang = line_id(project, ident)
        if lang:
            bases = set(lockfile.language_keys(project, lang[0]))
            regions |= regions_in(project, scan, bases, lang[1])
            pins |= bases   # the text of the clause, of its test and of its rows: what the code of that language is built for
            plain |= bases
        else:
            regions |= regions_of(scan, owned[ident])
    shared = sorted({k for _, ids_ in regions for k in ids_} - plain)
    base, here, start = lock_base(project, keys), where_here(project), start_state(project, scan, keys)
    lock, window = _lock_of(project), project_parked(project)
    looks, cache = 0, {}
    while True:
        looks += 1
        # Look first, without the mutex: deciding whether a gone holder left something to protect reads other folders, which takes time.
        now = time.time()
        mind = [c for c in read(project) if not c.get('freed') and not same_agent(c, agent, session) and conflicts([c], keys, regions)]
        decided = {c.get('grant'): (c.get('rev'), decide(project, c, scan, lock, now, window, cache)) for c in mind}
        with _Mutex(project):
            now = time.time()
            held = read(project)   # in force, or freed and kept for a while: see `lapsed`
            claims = [c for c in held if not c.get('freed')]
            theirs = [c for c in claims if not same_agent(c, agent, session)]
            holders = conflicts(theirs, keys, regions)
            if looks < 3 and any(c.get('grant') not in decided or decided[c['grant']][0] != c.get('rev') for c in holders):
                continue   # the record of a holder changed since it was looked at (it renewed, it resumed): look again
            # a holder whose record changed since it was looked at, or that appeared, counts as held on the last look too, never as what was decided of its old record
            states = {c['grant']: decided[c['grant']][1] if c.get('grant') in decided and decided[c['grant']][0] == c.get('rev')
                      else Decision('held', 'it changed while it was looked at') for c in holders}
            free = [c for c in holders if states[c['grant']].kind == 'free']
            stand = [c for c in holders if states[c['grant']].kind != 'free']
            took = []
            if stand and take_over and all(states[c['grant']].kind == 'parked' for c in stand):
                took, free, stand = stand, free + stand, []
            for c in free:   # nothing is left to protect, or the work goes on in the taker's hands: the claim is freed, and its holder told when it comes back
                c['freed'] = {'by': agent, 'at': now, 'why': 'taken over' if c in took else 'quiet', 'because': states[c['grant']].why}
                c['until'] = now
            if stand:
                if free:
                    _write(project, held)
                return False, {'holders': stand, 'theirs': theirs, 'states': {c['grant']: states[c['grant']] for c in stand}}
            mine = [c for c in claims if same_agent(c, agent, session) and set(c['asked']) == set(ids)]
            # `session` is who made the claim as far as the edit hook can tell: it sees a session id, never a
            # name given with --as. Several agents of one session (its subagents) share it.
            record = {'agent': agent, 'asked': sorted(ids), 'keys': sorted(keys), 'since': now,
                      'until': NEVER if ttl is None else now + ttl, 'idle': ttl, 'last': now,
                      'regions': [[f, list(ks)] for f, ks in sorted(regions)], 'session': session, 'where': here, 'base': base, 'start': start}
            if pins:
                record['pins'] = sorted(pins)   # the keys whose text this claim relies on (a claim of one language of a clause)
            if took:
                record['took_over'] = [{'agent': c['agent'], 'where': c.get('where') or {}, 'changes': states[c['grant']].changes,
                                        'keys': [k for k in c['keys'] if '@' not in k]} for c in took]
                # the work goes on in the old holder's folder, so that is where this claim is, and what it is measured against
                record['where'] = dict(took[0].get('where') or here)
                record['base'] = dict({k: v for c in took for k, v in (c.get('base') or {}).items()}, **{k: v for k, v in base.items() if k not in
                                                                                                           {k2 for c in took for k2 in (c.get('base') or {})}})
                if all('start' in c for c in took):   # and what its unfinished work is measured from: what it left is still its work, whoever continues it
                    record['start'] = dict(start, **{k: v for c in took for k, v in c['start'].items()})
            if mine:   # the agent claims what it already holds: the same claim goes on, with what it knows of its work (a new look at the files must not forget it)
                before = mine[0]
                record['grant'], record['since'] = before['grant'], before['since']
                for fact in ('locked', 'queued', 'took_over'):
                    if before.get(fact) and fact not in record:
                        record[fact] = before[fact]
                if before.get('took_over'):   # the unfinished work is still where the old holder left it
                    record['where'] = dict(before.get('where') or record['where'])
                for fact in ('base', 'start'):   # what it began from stays; only keys that are new since are measured from now
                    if fact in before:
                        record[fact] = dict(record.get(fact) or {}, **before[fact])
            # what this claim covers is no news any more: the agent's own freed claims on it go, other agents' stay
            spent = [c for c in held if c.get('freed') and same_agent(c, agent, session)
                     and all(any(covers(i, a) for i in ids) for a in c['asked'])]
            _write(project, [c for c in held if c not in mine and c not in spent] + [record])
            return True, {'keys': sorted(keys), 'shared': shared, 'until': record['until'], 'freed': [(c, states[c['grant']]) for c in free if c not in took],
                          'took_over': [(c, states[c['grant']]) for c in took]}


def at(root):
    """Just enough of a project to read and write its claims file (the folder of it), without parsing a spec: `root` is a project folder or
    the spec folder itself, as for `Project`."""
    root = os.path.abspath(root)
    return SimpleNamespace(spec_dir=os.path.join(root, SPEC_DIR) if has_spec(root) else root, root=root)


def touch(project, session='', agent='', name=None):
    """`renew`, as a side effect that is allowed to fail: a busy claims file or a folder that cannot be written costs the command that renewed
    nothing, and `sor status` must not fail because a claim could not be renewed. 0 when it failed."""
    try:
        return renew(project, session, agent, name=name)
    except (ClaimError, OSError):
        return 0


def renew(project, session='', agent='', now=None, name=None):
    """Records that the holder is at work: the claims of this Claude Code session (`session`), or, for a person at a terminal who names
    themselves, of this `agent` with no session, get `last` = now and `until` = now + their idle window, and lose the facts that said the holder was gone
    (its session had ended, a background build was running). A claim that was freed is not renewed: it may be someone else's now, and its holder is
    told through the lapse notice; one that is only quiet is, since nobody has decided anything about it. A claim with no `idle` (made by a tool from
    before) keeps its fixed end. Cheap, as the hooks call it on every read and edit: nothing happens without a claims file, the file is read
    without the mutex, and it is rewritten (under the mutex, re-read) only for a claim whose last activity is older than RENEW_FLOOR seconds
    or half its window, whichever is less. So a claim ends at most that long before its window is over. Returns the number of claims renewed.
    `name`: only the claims of that name: what a subagent's hook call or command renews. Without it, those of the session except the ones a subagent
    of it is bound to (`bind`), so that the parent working on does not keep a finished subagent's claims alive."""
    if not (session or agent):
        return 0
    now = time.time() if now is None else now
    skip = bound_names(project, session) if session and name is None else set()   # the subagents of this session renew their own claims, not the parent's

    def due(c):
        if 'idle' not in c or c.get('freed'):
            return False
        if name is not None and c.get('agent') != name:
            return False
        mine = (c.get('session') == session and c.get('agent') not in skip) if session else (not c.get('session') and c['agent'] == agent)
        step = RENEW_FLOOR if c['idle'] is None else min(c['idle'] / 2, RENEW_FLOOR)
        return mine and (now - c.get('last', c['since']) >= step or c['until'] <= now or c.get('ended') or c.get('busy_at') or c.get('stopped'))

    if not any(due(c) for c in read(project)):
        return 0
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if due(c):
                c['last'] = now
                c['until'] = NEVER if c['idle'] is None else now + c['idle']
                for fact in ('ended', 'busy_at', 'stopped'):
                    c.pop(fact, None)
                count += 1
        if count:
            _write(project, held)
    return count


def bindings_file(project):
    st = store(project)
    return os.path.join(st.dir, '.sor-bindings.json' if st.kind == 'folder' else 'bindings.json')


def read_bindings(project):
    """{session: {agent_id: {'name', 'at'}}}: which name each subagent of a session acts under, as the hooks learned it from its first `sor` command."""
    try:
        with open(bindings_file(project), encoding='utf8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def bound_name(project, session, agent_id):
    """The name a subagent acts under, or '' when it has not said (it has run no claim, lock or release yet)."""
    return ((read_bindings(project).get(session) or {}).get(agent_id) or {}).get('name', '')


def bound_names(project, session):
    return {b['name'] for b in (read_bindings(project).get(session) or {}).values()}


def bind(project, session, agent_id, name, now=None):
    """Binds a subagent (`agent_id`, which Claude Code gives a hook inside it) to the name it passes with --as. (True, '') when it is bound now or was; (False, other)
    when a sibling of the same session already acts under that name. Written under the mutex: parallel tool calls fire their hooks at the same time."""
    now = time.time() if now is None else now
    with _Mutex(project):
        data = read_bindings(project)
        mine = data.setdefault(session, {})
        for other, b in mine.items():
            if b.get('name') == name and other != agent_id:
                return False, other
        if (mine.get(agent_id) or {}).get('name') != name or now - (mine.get(agent_id) or {}).get('at', 0) > BIND_REFRESH:   # a live subagent keeps its binding past a day
            mine[agent_id] = {'name': name, 'at': now}
            for sid in list(data):   # a binding is forgotten after a day: sessions come and go
                data[sid] = {a: b for a, b in data[sid].items() if now - b.get('at', now) < 24 * 3600}
                if not data[sid]:
                    del data[sid]
            os.makedirs(os.path.dirname(bindings_file(project)), exist_ok=True)
            tmp = f'{bindings_file(project)}.{os.getpid()}.tmp'
            with open(tmp, 'w', encoding='utf8', newline='\n') as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, bindings_file(project))
    return True, ''


def mark_stopped(project, session, agent_id, stopped, now=None):
    """Records that a subagent stopped (`SubagentStop`), on the claims of the name it is bound to, or clears it (`SubagentStart`, which also fires when a subagent is
    resumed). A subagent that stopped is gone. The number of claims changed."""
    name = bound_name(project, session, agent_id)
    if not name or not any(c.get('session') == session and c.get('agent') == name and not c.get('freed') for c in read(project)):
        return 0
    now = time.time() if now is None else now
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if c.get('session') == session and c.get('agent') == name and not c.get('freed') and bool(c.get('stopped')) != bool(stopped):
                if stopped:
                    c['stopped'] = now
                else:
                    c.pop('stopped', None)
                count += 1
        if count:
            _write(project, held)
    return count


def mark_ended(project, session, reason='other', now=None):
    """Records that a Claude Code session ended (`sor hook session-end`), on each of its claims. It frees nothing: what an ended holder's claim
    means is decided when somebody asks for the clause. The budget of the hook is 1.5 seconds, so this reads the claims file and nothing else. The number marked."""
    if not session or not any(c.get('session') == session and not c.get('freed') for c in read(project)):
        return 0
    now = time.time() if now is None else now
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if c.get('session') == session and not c.get('freed'):
                c['ended'] = {'reason': reason, 'at': now}
                count += 1
        if count:
            _write(project, held)
    return count


def mark_busy(project, session, working, now=None):
    """Records what the `Stop` of a session said about its background work: with work in flight, its claims are not quiet for a while (a long build
    renews nothing); without, that is forgotten. The number of claims changed."""
    if not session or not any(c.get('session') == session and not c.get('freed') for c in read(project)):
        return 0
    now = time.time() if now is None else now
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if c.get('session') == session and not c.get('freed') and bool(c.get('busy_at')) != bool(working):
                if working:
                    c['busy_at'] = now
                else:
                    c.pop('busy_at', None)
                count += 1
        if count:
            _write(project, held)
    return count


def note_locked(project, agent, session, keys):
    """Records on the claims of an agent that cover `keys` that it locked work (`sor lock`): a working folder that is swept away afterwards does not
    take the claim with it, because that work waits for its merge."""
    keys = set(keys)

    def covered(c):
        return same_agent(c, agent, session) and not c.get('freed') and keys & set(c.get('keys', ())) and not c.get('locked')

    if not any(covered(c) for c in read(project)):
        return 0
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if covered(c):
                c['locked'] = True
                count += 1
        if count:
            _write(project, held)
    return count


def release(project, ids, agent, everything=False, force=False, session=None):
    """(released claims, refused claims). A claim is released by the agent that holds it, or by --force. A
    caller that gives no name (a parent cleaning up after its subagents, which share its session) also
    releases every claim of its session; one that names itself releases only its own, so `release --all
    --as a5` leaves a5's siblings alone. Expired claims still in the file go the same way and come back
    with the released ones (their `until` is in the past); they are never refused."""
    session = current_session() if session is None else session
    if not agent and not force and not session:
        raise ClaimError('say who you are: --as NAME, or set SOR_AGENT')
    cleaning_up = bool(session) and (not agent or agent == session_agent(session))   # no name given
    with _Mutex(project):
        now = time.time()
        gone, refused, keep = [], [], []
        for c in read(project):
            asked = everything or any(i == a or a.startswith(i + '/') or i.startswith(a + '/') or a.startswith(i + '@')
                                      for i in ids for a in c['asked'])
            if not asked:
                keep.append(c)
            elif same_agent(c, agent, session) or force or (cleaning_up and c.get('session') == session):
                gone.append(c)
            elif not everything and not c.get('freed'):
                refused.append(c)
                keep.append(c)
            else:
                keep.append(c)
        _write(project, keep)
    return gone, refused


def others(project, agent, keys=None, regions=None, now=None, session=None, text=True, scan=None):
    """Claims of other agents (another session, or another name) that still stand, seen from this working folder (`standing`); with `keys` and
    `regions`, only those that overlap them (`text`: the keys include the text of the clauses, see `conflicts`)."""
    session = current_session() if session is None else session
    held = [c for c in active(project, now) if not same_agent(c, agent, session)]
    if keys is not None:
        held = conflicts(held, keys, regions or (), text=text)
    return [c for c, _ in standing(project, held, scan, now)]


def is_own(c, session_id):
    """Is this claim the editor's own, as the hook sees it (by session id)? A claim made by a person
    at a terminal (session '') is never an agent's own. An old claim without a `session` field is
    compared by name, as before."""
    if 'session' not in c:
        return c['agent'] == session_agent(session_id)
    return bool(c['session']) and c['session'] == (session_id or '').strip()


def others_for_session(project, session_id, keys, regions=(), now=None, text=True, scan=None):
    """Claims that overlap keys or regions, are not this session's and still stand (`standing`): what the edit hook
    refuses on. The names given with --as do not matter here, only the session. `text`: the edit is of the text of the
    clauses (a spec file), which a claim of one language of them pins; an edit of code is not."""
    held = [c for c in active(project, now) if not is_own(c, session_id)]
    return [c for c, _ in standing(project, conflicts(held, keys, regions, text=text), scan, now)]


def others_for_agent(project, session_id, agent_id, keys, regions=(), now=None, text=True, scan=None):
    """`others_for_session`, for an edit made inside a subagent (`agent_id`, which Claude Code gives a hook inside one): its own claims are the ones under the name
    it is bound to, so a claim of a sibling, or of its parent, is not its own. A subagent that has bound no name holds nothing: it may edit what nobody
    holds, and is refused what somebody does."""
    if not agent_id:
        return others_for_session(project, session_id, keys, regions, now, text, scan)
    name = bound_name(project, (session_id or '').strip(), agent_id)
    held = [c for c in active(project, now) if not (name and same_agent(c, name, (session_id or '').strip()))]
    return [c for c, _ in standing(project, conflicts(held, keys, regions, text=text), scan, now)]


def own_git_dir(root):
    """The git directory of this working folder itself (for a linked worktree its own folder under the common one), None in no repository."""
    d = os.path.realpath(root)
    while True:
        g = os.path.join(d, '.git')
        try:
            if os.path.isfile(g):
                with open(g, encoding='utf8') as fh:
                    first = fh.readline().strip()
                return os.path.normpath(os.path.join(d, first[len('gitdir:'):].strip())) if first.startswith('gitdir:') else None
        except OSError:
            return None
        if os.path.isdir(g):
            return g
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def lock_mutex(project):
    """Held while the lock file is re-read, merged and rewritten, so two scoped locks by different agents both keep their entries. The lock file is a file of
    the working folder, so its mutex is one of the working folder: in a git repository in that folder's own git directory (git has nothing to ignore then),
    else `sor/.sor-lock.mutex`."""
    git = own_git_dir(root_of(project))
    if git:
        return _Mutex(project, path=os.path.join(git, f'sor-lock-{project_key(project, git_dirs(root_of(project))[0])}.mutex'))
    return _Mutex(project, LOCK_MUTEX_FILE)
