"""Who last changed drifted code, and when, if the environment can tell. Today that is `git blame` on
the drifted lines; without git, or outside a repository, nothing is added. Nothing else in the tools asks
any version control system anything."""
import datetime
import os
import re
import subprocess

WHERE = re.compile(r'^(.*):(\d+)(?:-(\d+))?$')
UNCOMMITTED = '0' * 40


def _blame(root, file, a, b):
    try:
        out = subprocess.run(['git', 'blame', '--porcelain', '-L', f'{a},{b}', '--', file],
                             cwd=root, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    commits, cur = {}, None
    for line in out.stdout.decode('utf-8', errors='replace').splitlines():
        head = re.match(r'^([0-9a-f]{40}) \d+ \d+', line)
        if head:
            cur = commits.setdefault(head.group(1), {})
        elif cur is not None and ' ' in line:
            k, _, v = line.partition(' ')
            if k in ('author', 'author-time', 'summary'):
                cur[k] = v
    return [dict(sha=sha, **info) for sha, info in commits.items()]


def describe(root, where):
    """'changed by NAME in 1a2b3c4 (2026-10-17)', 'not committed yet', or '' for a `where`
    like 'out/index.html:12-30, out/index.html:40-41'."""
    found = []
    for part in [w.strip() for w in where.split(',') if w.strip()]:
        m = WHERE.match(part)
        if m:
            found += _blame(root, m.group(1), m.group(2), m.group(3) or m.group(2))
    if not found:
        return ''
    if any(c['sha'] == UNCOMMITTED for c in found):
        return 'not committed yet'
    last = max(found, key=lambda c: int(c.get('author-time', 0)))
    day = datetime.datetime.fromtimestamp(int(last.get('author-time', 0))).strftime('%Y-%m-%d')
    return f'changed by {last.get("author", "?")} in {last["sha"][:7]} ({day})'


def annotate(project, findings, statuses=('drift', 'code-changed'), most=20):
    """Adds `by` to drift findings: the last change to their lines."""
    done = 0
    for f in findings:
        if f.status in statuses and f.where and done < most:
            by = describe(project.root, f.where)
            if by:
                f.by = by
            done += 1
