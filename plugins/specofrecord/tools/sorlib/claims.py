"""Clause claims (SPEC §16): who is working on which clauses, so parallel agents and people do not
collide. Advisory: `sor claim` records it, `sor status` shows it, `sor lock` respects it.

    sor/.sor-claims.json   {"claims": [{agent, asked, keys, since, until}]}, rewritten whole through a
                           temp file and os.replace, so a reader never sees half a file
    sor/.sor-claims.lock   a short mutex (O_EXCL), broken when older than STALE_LOCK seconds

A claim names clauses; what it holds is (1) every lock key those clauses own (their rows, values,
own test; for a part: all its items) and (2) the code regions marked with them. Two claims by
different agents conflict when either overlaps: a part against its items, an item against its
rows, or two clauses that share a code region, because editing that region is editing both. A
clause that merely shares *some other* region is not held: `colors` shares regions with almost
everything, and claiming the moon must not lock out the light.
A claim ends when its holder has done nothing for a while (an idle window, default 30 minutes), so a crashed agent does
not block the project for good, and when its Claude Code session ends (`sor hook session-end`). Work renews it: a hook
call or a `sor` command that carries the holder's session id (`renew`). A claim records `idle`, the window in seconds
or null for none, and `last`, the time of the last activity; `until` is `last + idle` (a date far away for none), and
is the only field a reader has to compare with the clock, so a tool from before `idle` reads the same file. An expired
claim stays in the file for TOMBSTONE seconds, only so that its holder can be told that it ran out
(`sor lock`, `sor release`); every reader that wants claims in force goes through `active`, and a tool that
does not know tombstones treats them as expired anyway, since their `until` is in the past.
Plain Python, no fcntl: the tool also runs on Windows.
"""
import glob
import json
import os
import re
import time

from .invoke import getenv
from .model import PART_FILE_NAME


CLAIMS_FILE = '.sor-claims.json'
MUTEX_FILE = '.sor-claims.lock'
LOCK_MUTEX_FILE = '.sor-lock.mutex'   # held while the lock file is merged and rewritten
STALE_LOCK = 10      # seconds after which a leftover mutex is broken
WAIT_LOCK = 5        # seconds to wait for the mutex
DEFAULT_TTL = 30 * 60   # the idle window of a claim, in seconds, when nothing else says (`--ttl`, `Claims:` in the root file)
NEVER = 4102444800      # 2100-01-01: the `until` of a claim with no idle window, a date every tool can read (not null, not year 9999)
RENEW_FLOOR = 300       # a claim with no idle window records its last activity at most this often
TOMBSTONE = 2 * 3600   # seconds an expired claim stays in the file, to tell its holder; pruned when the file is written


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


IDLE_LINE = re.compile(r'^idle\s+(\S+)$', re.I)


def idle_setting(text):
    """(ok, seconds or None) for the value of a `Claims:` line: `idle 30m`, `idle 2h`, `idle never`."""
    m = IDLE_LINE.match((text or '').strip())
    if m:
        try:
            return True, parse_ttl(m.group(1))
        except ClaimError:
            pass
    return False, DEFAULT_TTL


def project_idle(project):
    """The idle window the root file sets with `Claims: idle 30m` (seconds, None for never); DEFAULT_TTL when it says nothing or says
    something `sor check` reports."""
    root = project.root_part()
    text = root.header.get('Claims', '').strip() if root else ''
    return idle_setting(text)[1] if text else DEFAULT_TTL


def path(project):
    return os.path.join(project.spec_dir, CLAIMS_FILE)


def read(project):
    try:
        with open(path(project), encoding='utf8') as fh:
            return json.load(fh).get('claims', [])
    except (OSError, ValueError):
        return []


def has_expired(c, now=None):
    return c['until'] <= (time.time() if now is None else now)


def active(project, now=None):
    """The claims in force. Expired ones (tombstones) that the file still holds are not among them."""
    now = time.time() if now is None else now
    return [c for c in read(project) if c['until'] > now]


def lapsed(project, agent, session=None, now=None):
    """The agent's claims that ran out less than TOMBSTONE seconds ago, oldest first: what it has to be told
    when it comes back to lock or release."""
    now = time.time() if now is None else now
    session = current_session() if session is None else session
    out = [c for c in read(project) if now - TOMBSTONE < c['until'] <= now and same_agent(c, agent, session)]
    return sorted(out, key=lambda c: c['until'])


def _write(project, claims):
    p = path(project)
    now = time.time()
    claims = [c for c in claims if c['until'] > now - TOMBSTONE]   # tombstones older than that are forgotten here
    if not claims:   # nothing claimed: leave nothing behind in the project
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        return
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


class _Mutex:
    def __init__(self, project, name=MUTEX_FILE):
        self.path = os.path.join(project.spec_dir, name)

    def __enter__(self):
        end = time.time() + WAIT_LOCK
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
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
        try:
            os.remove(self.path)
        except OSError:
            pass


def footprint(project, universe, ids):
    """(keys, unknown): every lock key the ids own. `universe` is the set of lock keys that exist
    (now, and for `sor lock` also in the old lock, so a deleted clause can still be locked)."""
    keys, unknown = set(), []
    for ident in ids:
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


def conflicts(claim_list, keys, regions):
    return [c for c in claim_list if set(c['keys']) & set(keys) or _regions(c) & set(regions)]


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
    before `idle` has no record of activity and shows only when it ends)."""
    now = time.time() if now is None else now
    mins = max(0, int((now - c['since']) // 60))
    if 'idle' not in c:
        return f"{c['agent']}: {', '.join(c['asked'])} (since {mins} min, until {when(c['until'])})"
    active = max(0, int((now - c.get('last', c['since'])) // 60))
    ends = 'no idle limit' if c['idle'] is None else f"ends at {when(c['until'])} if idle"
    return f"{c['agent']}: {', '.join(c['asked'])} (since {mins} min, last active {active} min ago, {ends})"


def covers(ident, other):
    """Does the claimed id `ident` cover `other`: itself, or something under it (a part: its items and child
    parts)?"""
    return other == ident or other.startswith(ident + '/')


def lapse_text(cs):
    """'claims on a, b expired at 00:31' for expired claims: one group per minute they ran out."""
    groups = {}
    for c in sorted(cs, key=lambda c: c['until']):
        ids = groups.setdefault(when(c['until']), [])
        ids += [a for a in c['asked'] if a not in ids]
    parts = [f"{', '.join(ids)} expired at {t}" if i == 0 else f"{', '.join(ids)} at {t}"
             for i, (t, ids) in enumerate(groups.items())]
    return 'claims on ' + ', on '.join(parts)


def claim_again():
    """What to do about an expired claim, in the words the commands end their note with."""
    return f'claims end after {lifetime(DEFAULT_TTL)} idle by default: claim again, `--ttl 2h` for a longer window'


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
    return keys, regions_of(scan, keys)


def claim(project, scan, universe, ids, agent, ttl=DEFAULT_TTL, session=None):
    """(ok, result). `ttl`: the idle window in seconds, None for none. On success result has `keys`, `shared` (ids pulled in) and `until`; on refusal `holders`, the
    claims in the way, and `blocked`, the asked ids they are in the way of: a refused claim takes none of its ids,
    the free ones too. `blocked` is worked out after the mutex is let go: it does not need the claims file."""
    ok, res = _claim(project, scan, universe, ids, agent, ttl, session)
    if not ok:
        theirs = res.pop('theirs')
        res['blocked'] = [i for i in ids if conflicts(theirs, *_one(project, scan, universe, i))]
    return ok, res


def unknown_text(project, universe, unknown):
    """"no such clause or part: ...", and, for an id written with the root in front (`ROOT/year`, `SPECOFRECORD/year`),
    the id of the root item it was meant for: items of the root have no prefix."""
    text = 'no such clause or part: ' + ', '.join(unknown)
    fixes = []
    for ident in unknown:
        head, _, rest = ident.partition('/')
        if rest and head in ('ROOT', PART_FILE_NAME) and not footprint(project, universe, [rest])[1]:
            fixes.append(f'`{rest}`, not {ident}')
    return text + (f' (items of the root have no prefix: use {"; ".join(fixes)})' if fixes else '')


def _claim(project, scan, universe, ids, agent, ttl, session):
    """`claim` without `blocked`: a refusal carries the other agents' claims it was measured against, as `theirs`."""
    if not agent:
        raise ClaimError('say who you are: --as NAME, or set SOR_AGENT (a Claude Code session is recognised by itself)')
    session = current_session() if session is None else session
    keys, unknown = footprint(project, universe, ids)
    if unknown:
        raise ClaimError(unknown_text(project, universe, unknown) + ' (to add a clause, claim the part that will hold it)')
    regions = regions_of(scan, keys)
    shared = sorted({k for _, ids_ in regions for k in ids_} - keys)
    with _Mutex(project):
        now = time.time()
        held = read(project)   # in force or expired: the expired ones are kept, see `lapsed`
        claims = [c for c in held if c['until'] > now]
        theirs = [c for c in claims if not same_agent(c, agent, session)]
        holders = conflicts(theirs, keys, regions)
        if holders:
            return False, {'holders': holders, 'theirs': theirs}
        mine = [c for c in claims if same_agent(c, agent, session) and set(c['asked']) == set(ids)]
        # `session` is who made the claim as far as the edit hook can tell: it sees a session id, never a
        # name given with --as. Several agents of one session (its subagents) share it.
        record = {'agent': agent, 'asked': sorted(ids), 'keys': sorted(keys), 'since': now,
                  'until': NEVER if ttl is None else now + ttl, 'idle': ttl, 'last': now,
                  'regions': [[f, list(ks)] for f, ks in sorted(regions)], 'session': session}
        if mine:
            record['since'] = mine[0]['since']
        # what this claim covers is no news any more: the agent's own expired claims on it go, other agents' stay
        spent = [c for c in held if c['until'] <= now and same_agent(c, agent, session)
                 and all(any(covers(i, a) for i in ids) for a in c['asked'])]
        _write(project, [c for c in held if c not in mine and c not in spent] + [record])
    return True, {'keys': sorted(keys), 'shared': shared, 'until': record['until']}


def renew(project, session='', agent='', now=None):
    """Records that the holder is at work: the claims of this Claude Code session (`session`), or, for a person at a terminal who names
    themselves, of this `agent` with no session, get `last` = now and `until` = now + their idle window. Only a claim in force is renewed:
    one that ran out may be someone else's now, and its holder is told through the lapse notice. A claim with no `idle` (made by a tool from
    before) keeps its fixed end. Cheap, as the hooks call it on every read and edit: nothing happens without a claims file, the file is read
    without the mutex, and it is rewritten (under the mutex, re-read) only for a claim whose last activity is older than half its window, or
    RENEW_FLOOR seconds for a claim with no window. Returns the number of claims renewed."""
    if not (session or agent):
        return 0
    now = time.time() if now is None else now

    def due(c):
        if 'idle' not in c or c['until'] <= now:
            return False
        mine = c.get('session') == session if session else (not c.get('session') and c['agent'] == agent)
        step = RENEW_FLOOR if c['idle'] is None else c['idle'] / 2
        return mine and now - c.get('last', c['since']) >= step

    if not any(due(c) for c in read(project)):
        return 0
    with _Mutex(project):
        held = read(project)
        count = 0
        for c in held:
            if due(c):
                c['last'] = now
                c['until'] = NEVER if c['idle'] is None else now + c['idle']
                count += 1
        if count:
            _write(project, held)
    return count


def release_session(project, session):
    """Frees every claim made in a Claude Code session, as the session ends (`sor hook session-end`). The number released."""
    if not session or not any(c.get('session') == session for c in read(project)):
        return 0
    gone, _ = release(project, [], '', everything=True, session=session)
    return len(gone)


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
            asked = everything or any(i == a or a.startswith(i + '/') or i.startswith(a + '/')
                                      for i in ids for a in c['asked'])
            if not asked:
                keep.append(c)
            elif same_agent(c, agent, session) or force or (cleaning_up and c.get('session') == session):
                gone.append(c)
            elif not everything and c['until'] > now:
                refused.append(c)
                keep.append(c)
            else:
                keep.append(c)
        _write(project, keep)
    return gone, refused


def others(project, agent, keys=None, regions=None, now=None, session=None):
    """Unexpired claims of other agents (another session, or another name); with `keys` and
    `regions`, only those that overlap them."""
    session = current_session() if session is None else session
    held = [c for c in active(project, now) if not same_agent(c, agent, session)]
    if keys is None:
        return held
    return conflicts(held, keys, regions or ())


def is_own(c, session_id):
    """Is this claim the editor's own, as the hook sees it (by session id)? A claim made by a person
    at a terminal (session '') is never an agent's own. An old claim without a `session` field is
    compared by name, as before."""
    if 'session' not in c:
        return c['agent'] == session_agent(session_id)
    return bool(c['session']) and c['session'] == (session_id or '').strip()


def others_for_session(project, session_id, keys, regions=(), now=None):
    """Unexpired claims that overlap keys or regions and are not this session's: what the edit hook
    refuses on. The names given with --as do not matter here, only the session."""
    held = [c for c in active(project, now) if not is_own(c, session_id)]
    return conflicts(held, keys, regions)


def lock_mutex(project):
    """Held while the lock file is re-read, merged and rewritten, so two scoped locks by different
    agents both keep their entries."""
    return _Mutex(project, LOCK_MUTEX_FILE)
