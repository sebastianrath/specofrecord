"""Evidence: what one CI job proved about the tests that say `runs on:` (SPEC §8), and the gate over it, `sor verify`.

The lock never holds a result for such a test: it says `deferred`, from the spec alone, so identical input gives identical
bytes on every machine. A job that provides the environments writes its own file instead, one per job, so two jobs never
write the same file:

    {"job": "linux-ci", "provides": ["db", "linux"],
     "results": {"greet/test:hello": {"fingerprint": "0123456789ab", "status": "pass"}}}

A result counts only for the fingerprint it was made for: a hash of the test, of what it refers to and of the text and code
of every clause it proves. Change any of them and the result no longer matches, so there is no timestamp and nothing to
expire. The file is as trustworthy as the job that wrote it: `sor verify` checks that a result is current and which
environments the job said it provides, not that the job really ran the test.
"""
import json
import os

from . import lock as lockfile
from .model import ENV_NAME, listed

STATUSES = ('pass', 'fail')
FINGERPRINT_LENGTH = 12   # the length of every hash in the lock (lock.h)


def owner_of(key, ids):
    """The item a row or a value belongs to: `a/b/row.size` -> `a/b`. A key that is an item is its own owner."""
    while key and key not in ids:
        head, sep, tail = key.rpartition('/')
        name, dot, _ = tail.partition('.')
        key = head + sep + name if dot else head
    return key


def fingerprints(project, scan, keys=None):
    """{test key: fingerprint} for the tests asked for (all of them by default). The hash covers the test's own text, what
    it refers to, its own rows and values, the code marked with it (a test in your own framework), and for every clause it
    proves the clause's text, its code, and the text and code of its rows and values, so a result is stale as soon as any of
    them changes."""
    now = lockfile.snapshot(project, scan)
    ids = {i.id for i in project.all_items()}
    parts = {}   # item id -> [(key, text hash, code hash)] of its rows and values
    for k, e in now.items():
        if e.get('kind') in ('row', 'value'):
            parts.setdefault(owner_of(k, ids), []).append((k, e.get('text', ''), e.get('code', '')))
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


def read(path):
    """(data, error): an evidence file, read strictly. Unknown keys, unknown statuses and malformed hashes are errors, so a
    typo is never taken for a missing result."""
    try:
        with open(path, encoding='utf8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        return None, f'{path}: cannot read it as evidence ({e})'
    where = f'{path}:'
    if not isinstance(data, dict) or set(data) != {'job', 'provides', 'results'}:
        return None, f'{where} an evidence file has exactly the keys job, provides and results'
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


def build(project, scan, job, provides, results):
    """(data, notes, errors): the evidence a job writes from the results it has ({test key: 'pass' | 'fail'}, the format of
    `sor test --out` and `sor lock --results`). Only a test that says `runs on:` and names an environment the job provides is
    evidence; every other result is left out and said, never refused, because a job's own results hold all its tests."""
    notes, errors = [], []
    deferred = {k: project.items[k] for k in lockfile.deferred_tests(project)}
    prov = frozenset(provides)
    fps = fingerprints(project, scan, set(results) & set(deferred))
    out, quiet, nowhere = {}, [], []
    for key, status in sorted(results.items()):
        item = project.items.get(key)
        if not (item is not None and getattr(item, 'is_test', False)):
            errors.append(f'{key} is not a test')
        elif key not in deferred:
            quiet.append(key)
        elif not any(set(env) <= prov for env in deferred[key].runs_on()):
            nowhere.append(key)
        elif status not in STATUSES:   # only a result that is kept has to be pass or fail: a job's file holds skipped tests too
            errors.append(f'{key}: "{status}" is not a result (pass or fail)')
        else:
            out[key] = {'fingerprint': fps[key], 'status': status}
    if quiet:
        notes.append(f'left out, they do not say `runs on:` (the lock proves them): {listed(quiet)}')
    if nowhere:
        notes.append(f'left out, this job provides none of their environments: {listed(nowhere)}')
    return {'job': job, 'provides': sorted(prov), 'results': out}, notes, errors


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


def verify(project, scan, evidence):
    """[row]: for each deferred test and each environment it must pass in, whether a current result proves it. A row is
    {id, environments: [{needs: [names], status, jobs}]} and the status is pass, fail (a current result says so), stale (only
    results for an older fingerprint) or missing. A current failure beats a current pass: it is not averaged away."""
    deferred = {k: project.items[k] for k in lockfile.deferred_tests(project)}
    fps = fingerprints(project, scan, set(deferred))
    rows = []
    for key in sorted(deferred):
        envs = []
        for env in deferred[key].runs_on():
            seen = [(d['job'], d['results'][key]) for _, d in evidence
                    if key in d['results'] and set(env) <= set(d['provides'])]
            now = [(j, r) for j, r in seen if r['fingerprint'] == fps[key]]
            failed = sorted({j for j, r in now if r['status'] == 'fail'})
            passed = sorted({j for j, r in now if r['status'] == 'pass'})
            status = 'fail' if failed else 'pass' if passed else 'stale' if seen else 'missing'
            envs.append({'needs': list(env), 'status': status, 'jobs': failed or passed or sorted({j for j, _ in seen})})
        rows.append({'id': key, 'environments': envs})
    return rows


def unknown(project, evidence):
    """[(job, key)]: results for tests that no longer exist or no longer say `runs on:`. Information, never a failure."""
    deferred = set(lockfile.deferred_tests(project))
    return sorted((d['job'], k) for _, d in evidence for k in d['results'] if k not in deferred)
