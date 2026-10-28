"""The test commands a person has allowed to run (`sor lock --targets`, `sor test --targets`), so that the hook asks about one only when it is new or changed.

A target's `run:` command is text in a spec file, which an agent can edit, so the hook asks before a call that runs it. Asking again for the
text the user has already allowed tells them nothing: the hook writes a command down here after a call that ran it went through, and does not ask
about it while the spec still gives the same text. What is allowed is the text of the command: the programs it starts may change without a new question. One text per target; a new text for it is asked about, and is written down when its call goes through.

The file is one of the store (`claims.store`), next to the claims and the bindings, so every working folder of the project reads it. It is a personal
decision and is not in the lock, which people share. It is written by the hook only: the edit guard refuses an edit of it (`hook.approvals_refusal`).
"""
import json
import os
import time

from . import claims
from .invoke import replace_file

FILE = 'approved-targets.json'                # in a store of its own folder
OWN_FILE = '.sor-approved-targets.json'       # in the project's own `sor/` folder (no git repository, no SOR_CLAIMS_DIR)


def file(project):
    st = claims.store(project)
    return os.path.join(st.dir, OWN_FILE if st.kind == 'folder' else FILE)


def read(project):
    """{target: {'run': the command text that was allowed, 'at': when}}; empty when there is no file or it cannot be read."""
    try:
        with open(file(project), encoding='utf8') as fh:
            data = json.load(fh)
        return {n: v for n, v in data.items() if isinstance(v, dict) and isinstance(v.get('run'), str)} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def commands(project, names):
    """{target: its `run:` command in the spec now} for these targets, or None when one of them gives none (a call naming it cannot run)."""
    given = project.target_commands()
    if not names or any('run' not in given.get(n, {}) for n in names):
        return None
    return {n: given[n]['run'] for n in names}


def state(project, names):
    """(allowed, changed): whether the spec gives, for every one of these targets, the command text that was allowed, and the targets whose text is not
    the one that was allowed (a target never allowed is not in `changed`, it is new). A target that gives no command is not allowed."""
    now = commands(project, names)
    if now is None:
        return False, []
    known = read(project)
    return all(known.get(n, {}).get('run') == c for n, c in now.items()), [n for n, c in now.items() if n in known and known[n]['run'] != c]


def record(project, shown, now=None):
    """Writes down the commands the user was shown ({target: its `run:` text in the question}), each one only if the spec still gives that text: a spec that
    changed between the question and the run (an agent, a merge) is not what the user allowed. Written under the mutex of the claims, since the hooks of
    parallel tool calls fire at the same time."""
    now = time.time() if now is None else now
    given = commands(project, list(shown))
    if not given:
        return
    given = {n: c for n, c in given.items() if shown[n] == c}
    if not given:
        return
    with claims._Mutex(project):
        data = read(project)
        if all(data.get(n, {}).get('run') == c for n, c in given.items()):
            return
        for n, c in given.items():
            data[n] = {'run': c, 'at': now}
        os.makedirs(os.path.dirname(file(project)), exist_ok=True)
        tmp = f'{file(project)}.{os.getpid()}.tmp'
        with open(tmp, 'w', encoding='utf8', newline='\n') as fh:
            json.dump(data, fh, indent=1)
        replace_file(tmp, file(project))
