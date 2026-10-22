"""Evidence: what one CI job proved about the tests that say `runs on:` (SPEC §8), and the gate over it, `sor verify`.

The lock never holds a result for such a test: it says `deferred`, from the spec alone, so identical input gives identical
bytes on every machine. A job that provides the environments writes its own file instead, one per job, so two jobs never
write the same file:

    {"job": "linux-ci", "provides": ["db", "linux"],
     "results": {"greet/test:hello": {"fingerprint": "0123456789ab", "status": "pass"}}}

A result counts only for the fingerprint it was made for: a hash of the test, of what it refers to and of the text and code
of every clause it proves. Change any of them and the result no longer matches, so there is no timestamp and nothing to
expire. In a project that says its targets, a test with test code in a language takes one result for each of those languages
(`greet/test:hello@py`), and the fingerprint of a language covers the code in that language only, so an edit in another language
leaves it current. A test with no test code per language keeps one result, for the code of every language. The file is as trustworthy as the job that wrote it: `sor verify` checks that a result is current and which
environments the job said it provides, not that the job really ran the test.

The file has a format number, as the lock has. Format 1 is the three keys above and has no marker. Format 2 adds `"format": 2` and
`"from": {"commit": ..., "run": ...}`, which says which commit and which CI run the job saw; the job gives both with flags, and a job
that gives neither writes format 1 with the same bytes as before. The reader is strict: a number it does not know is refused with a
message to update, and so is a key it does not know, which is how a tool from before the number refuses a format 2 file.
"""
import json
import os
import re

from . import lock as lockfile
from .model import ENV_NAME, listed

STATUSES = ('pass', 'fail')
FORMAT = 2                # the newest evidence format this tool reads and writes
FORMAT_KEY = 'format'
SOURCE_KEYS = {'commit': re.compile(r'^[0-9a-f]{7,64}$'), 'run': re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')}
FINGERPRINT_LENGTH = 12   # the length of every hash in the lock (lock.h)


def owner_of(key, ids):
    """The item a row or a value belongs to: `a/b/row.size` -> `a/b`. A key that is an item is its own owner."""
    while key and key not in ids:
        head, sep, tail = key.rpartition('/')
        name, dot, _ = tail.partition('.')
        key = head + sep + name if dot else head
    return key


def code_in(entry, target):
    """The hash of an entry's code in one language, '' when it has none there. An entry that keeps its code in one hash (no `targets`) has that."""
    if 'targets' in entry:
        return entry['targets'].get(target, {}).get('code', '')
    return entry.get('code', '')


def result_names(project, now, key):
    """The keys a result for the test `key` may have: `key`, or `key@language` for each language it has test code in (a test that needs a
    result from the project's own framework or from CI, per language, like the lock's lines of a test)."""
    languages = sorted((now.get(key) or {}).get('targets') or {})
    return [f'{key}@{t}' for t in languages] or [key]


def fingerprints(project, scan, keys=None, snap=None):
    """{key: fingerprint} for the tests asked for (all of them by default), and for a test with test code in some languages also for each
    of them (`test@py`). The hash covers the test's own text, what it refers to, its own rows and values, the code marked with it (a test in
    your own framework), and for every clause it proves the clause's text, its code, and the text and code of its rows and values, so a
    result is stale as soon as any of them changes. The one of a language covers the code in that language only. `snap`: the snapshot of the
    project, when the caller has one (it hashes all the code)."""
    now = snap or lockfile.snapshot(project, scan)
    ids = {i.id for i in project.all_items()}
    parts = {}   # item id -> [(key, text hash, code hash)] of its rows and values
    entries = {}   # item id -> [(key, text hash, entry)] of the same
    for k, e in now.items():
        if e.get('kind') in ('row', 'value'):
            owner = owner_of(k, ids)
            parts.setdefault(owner, []).append((k, e.get('text', ''), e.get('code', '')))
            entries.setdefault(owner, []).append((k, e.get('text', ''), e))
    out = {}
    for item in project.all_items():
        if not item.is_test or (keys is not None and item.id not in keys):
            continue
        own = now[item.id]
        proved = []
        for pid in sorted(project.proves(item)):
            e = now.get(pid, {})
            proved.append([pid, e.get('text', ''), e.get('code', ''), sorted(parts.get(pid, []))])
        payload = [own.get('text', ''), sorted(own.get('refs', {}).items()), own.get('code', ''), sorted(parts.get(item.id, [])),
                   proved]
        out[item.id] = lockfile.h(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        for t in sorted(own.get('targets') or {}):
            proved_in = [[pid, now.get(pid, {}).get('text', ''), code_in(now.get(pid, {}), t),
                          sorted((k, text, code_in(e, t)) for k, text, e in entries.get(pid, []))] for pid in sorted(project.proves(item))]
            payload = [own.get('text', ''), sorted(own.get('refs', {}).items()), code_in(own, t),
                       sorted((k, text, code_in(e, t)) for k, text, e in entries.get(item.id, [])), proved_in]
            out[f'{item.id}@{t}'] = lockfile.h(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return out


def names(text, what):
    """([names], error): a comma-separated list of environment names, as `--provides` takes it."""
    out = [n.strip().lower() for n in text.split(',')] if text.strip() else []
    bad = [n for n in out if not ENV_NAME.match(n)]   # an empty entry is bad too, as in `runs on:`
    if bad:
        return [], f'{what}: {"an empty name" if not bad[0] else chr(34) + bad[0] + chr(34)} is not a name ' \
                   '(lowercase letters, digits, dots, dashes and underscores, separated by commas)'
    return sorted(set(out)), None


RESERVED = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}


def job_problem(job):
    """None, or why this is no job name. A job name becomes a file name, so it holds nothing that could leave the folder
    and is not a device name Windows will not make a file of (`con`, `nul`, ...), whatever the extension."""
    if isinstance(job, str) and ENV_NAME.match(job) and job.split('.')[0] not in RESERVED:
        return None
    return (f'"{job}" is not a job name: use lowercase letters, digits, dots, dashes and underscores, '
            'and not a Windows device name such as con or nul')


def source(commit, run):
    """(source dict or None, error) for the `--commit` and `--run` a job gives. Both are optional; a value is a token, not free text."""
    given = {k: v for k, v in (('commit', commit), ('run', run)) if v is not None}
    for k, v in given.items():
        if not SOURCE_KEYS[k].match(v.lower() if k == 'commit' else v):
            return None, (f'--{k} {v!r} is not ' + ('a commit (7 to 64 hexadecimal digits)' if k == 'commit' else
                          'a run id (letters, digits, dots, dashes and underscores, up to 64)'))
    if 'commit' in given:
        given['commit'] = given['commit'].lower()
    return given or None, None


def format_problem(path, data):
    """None, or why a parsed evidence file is in a format this tool does not read."""
    if FORMAT_KEY not in data:
        return None
    number = data[FORMAT_KEY]
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        return f'{path}: "{FORMAT_KEY}" is not an evidence format number (a whole number from 1 up)'
    if number > FORMAT:
        return (f'{path}: evidence in format {number}, and this sor reads format {FORMAT} at most. Update sor, every copy of it '
                '(the project\'s tools, the plugin and the editor extension), and try again')
    return None


def read(path):
    """(data, error): an evidence file, read strictly. Unknown keys, unknown statuses and malformed hashes are errors, so a
    typo is never taken for a missing result."""
    try:
        with open(path, encoding='utf8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        return None, f'{path}: cannot read it as evidence ({e})'
    where = f'{path}:'
    if not isinstance(data, dict):
        return None, f'{where} an evidence file has exactly the keys job, provides and results'
    problem = format_problem(path, data)
    if problem:
        return None, problem
    number = data.get(FORMAT_KEY, 1)
    if number == 1:
        if set(data) - {FORMAT_KEY} != {'job', 'provides', 'results'}:
            return None, f'{where} an evidence file has exactly the keys job, provides and results'
    else:
        if set(data) != {FORMAT_KEY, 'from', 'job', 'provides', 'results'}:
            return None, f'{where} an evidence file of format {number} has exactly the keys format, from, job, provides and results'
        src = data['from']
        if not isinstance(src, dict) or not src or set(src) - set(SOURCE_KEYS) or not all(
                isinstance(v, str) and SOURCE_KEYS[k].match(v) for k, v in src.items()):
            return None, f'{where} from holds a commit (hexadecimal), a run id or both'
    if job_problem(data['job']):
        return None, f'{where} job {job_problem(data["job"])}'
    prov = data['provides']
    if not isinstance(prov, list) or not all(isinstance(n, str) and ENV_NAME.match(n) for n in prov):
        return None, f'{where} provides is a list of environment names'
    if not isinstance(data['results'], dict):
        return None, f'{where} results is an object: {{test key: {{fingerprint, status}}}}'
    for key, r in data['results'].items():
        ok = isinstance(r, dict) and set(r) == {'fingerprint', 'status'} and r['status'] in STATUSES
        ok = ok and isinstance(r['fingerprint'], str) and len(r['fingerprint']) == FINGERPRINT_LENGTH \
            and all(c in '0123456789abcdef' for c in r['fingerprint'])
        if not ok:
            return None, f'{where} the result for {key} is {{"fingerprint": 12 hex digits, "status": "pass" or "fail"}}'
    return data, None


def write(path, data):
    """Writes an evidence file through a temp file and os.replace, as the lock is written: a reader (`sor verify` in another
    job) sees the old file or the new one, never half of one. Sorted, no timestamps."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf8', newline='\n') as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + '\n')
        os.replace(tmp, path)
    except BaseException:   # a cancelled or full-disk job must not leave its temp file in the evidence folder
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def build(project, scan, job, provides, results, src=None):
    """(data, notes, errors): the evidence a job writes from the results it has ({test key: 'pass' | 'fail'}, the format of
    `sor test --out` and `sor lock --results`). Only a test that says `runs on:` and names an environment the job provides is
    evidence; every other result is left out and said, never refused, because a job's own results hold all its tests. A test with test
    code in some languages takes a result for each (`greet/test:hello@py`), by the lock's rule for the results of such a test."""
    notes, errors = [], []
    deferred = {k: project.items[k] for k in lockfile.deferred_tests(project)}
    prov = frozenset(provides)
    now = lockfile.snapshot(project, scan)
    fps = fingerprints(project, scan, {k.partition('@')[0] for k in results} & set(deferred), now)
    out, quiet, nowhere = {}, [], []
    for key, status in sorted(results.items()):
        base = key.partition('@')[0]
        item = project.items.get(base)
        if not (item is not None and getattr(item, 'is_test', False)):
            errors.append(f'{key} is not a test')
        elif base not in deferred:
            quiet.append(key)
        else:
            language, why = lockfile.result_language(key, sorted((now.get(base) or {}).get('targets') or {}))
            name = f'{base}@{language}' if language else base
            if why:
                errors.append(why.replace('results: ', '', 1))
            elif not any(set(env) <= prov for env in deferred[base].runs_on()):
                nowhere.append(key)
            elif status not in STATUSES:   # only a result that is kept has to be pass or fail: a job's file holds skipped tests too
                errors.append(f'{key}: "{status}" is not a result (pass or fail)')
            else:
                out[name] = {'fingerprint': fps[name], 'status': status}
    if quiet:
        notes.append(f'left out, they do not say `runs on:` (the lock proves them): {listed(quiet)}')
    if nowhere:
        notes.append(f'left out, this job provides none of their environments: {listed(nowhere)}')
    data = {'job': job, 'provides': sorted(prov), 'results': out}
    if src:
        data.update({FORMAT_KEY: 2, 'from': dict(src)})
    return data, notes, errors


def collect(paths):
    """Evidence files from files and folders (a folder holds *.json): ([(path, data)], errors). Two files for one job name
    are an error: the second would hide the first."""
    files, errors = [], []
    for p in paths:
        if os.path.isdir(p):   # all the way down: a download of several CI artifacts makes one folder for each
            for folder, dirs, found in os.walk(p):
                dirs.sort()
                files += [os.path.join(folder, f) for f in sorted(found) if f.endswith('.json')]
        else:
            files.append(p)
    out, seen = [], {}
    for f in files:
        data, err = read(f)
        if err:
            errors.append(err)
        elif data['job'] in seen:
            errors.append(f'{f}: the job {data["job"]} is also in {seen[data["job"]]}')
        else:
            seen[data['job']] = f
            out.append((f, data))
    return out, errors


def verify(project, scan, evidence, snap=None):
    """[row]: for each deferred test and each environment it must pass in, whether a current result proves it. A row is
    {id, environments: [{needs: [names], status, jobs}]} and the status is pass, fail (a current result says so), stale (only
    results for an older fingerprint) or missing. A current failure beats a current pass: it is not averaged away."""
    deferred = {k: project.items[k] for k in lockfile.deferred_tests(project)}
    snap = snap or lockfile.snapshot(project, scan)
    fps = fingerprints(project, scan, set(deferred), snap)
    rows = []
    for test in sorted(deferred):
        for key in result_names(project, snap, test):   # the test, or each language it has test code in
            envs = []
            for env in deferred[test].runs_on():
                seen = [(d['job'], d['results'][key]) for _, d in evidence
                        if key in d['results'] and set(env) <= set(d['provides'])]
                now = [(j, r) for j, r in seen if r['fingerprint'] == fps[key]]
                failed = sorted({j for j, r in now if r['status'] == 'fail'})
                passed = sorted({j for j, r in now if r['status'] == 'pass'})
                status = 'fail' if failed else 'pass' if passed else 'stale' if seen else 'missing'
                envs.append({'needs': list(env), 'status': status, 'jobs': failed or passed or sorted({j for j, _ in seen})})
            rows.append({'id': key, 'environments': envs})
    return rows


def expected(project, scan, snap=None):
    """{key: test} of every result a job may write: for a test that says `runs on:` its own key, or one for each language it has test code in."""
    snap = snap or lockfile.snapshot(project, scan)
    return {key: test for test in lockfile.deferred_tests(project) for key in result_names(project, snap, test)}


def unknown(project, scan, evidence, snap=None):
    """[(job, key)]: results for tests that no longer exist or no longer say `runs on:`. Information, never a failure."""
    keys = expected(project, scan, snap)
    deferred = set(keys.values())
    return sorted((d['job'], k) for _, d in evidence for k in d['results'] if k not in keys and k not in deferred)


def renamed(project, scan, evidence, snap=None):
    """[(job, test, [keys])]: results a job wrote for a test as one, when the test now takes a result for each language (it has test code in
    them). They are not taken for the test, and `sor verify` says so: the job has to write the keys it names."""
    keys = expected(project, scan, snap)
    by_test = {}
    for key, test in keys.items():
        by_test.setdefault(test, []).append(key)
    return sorted((d['job'], k, by_test[k]) for _, d in evidence for k in d['results'] if k in by_test and k not in keys)
