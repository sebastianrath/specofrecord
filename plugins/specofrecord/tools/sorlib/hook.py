"""Claude Code hooks that keep an agent clauses-first.

    sor hook pre-edit    PreToolUse on Edit|Write|MultiEdit: refuses an edit that changes the
                          code of a clause that has not changed since the last lock
    sor hook post-read   PostToolUse on Read: adds the clauses behind the regions just read
    sor hook session-start   SessionStart: a note saying this project has a spec, when it has, a short index of its parts, and what is pending
    sor hook pre-bash    PreToolUse on Bash: asks the user before a `sor lock` or `sor test` runs with an option that is theirs to decide (GUARDED), and notes which files the command could change
    sor hook post-bash   PostToolUse and PostToolUseFailure on Bash: says what the guard would have refused if the command changed code or the lock (shellguard.py)
    sor hook session-end   SessionEnd: records on the claims of the ending session that it ended
    sor hook stop            Stop: records whether the session works in the background (a long build), which keeps its claims from falling quiet
    sor hook subagent-start  SubagentStart: tells a subagent to name itself (--as) when it claims; clears "stopped" for a subagent that was resumed
    sor hook subagent-stop   SubagentStop: records on the claims of that subagent that it stopped

They read the hook's JSON on stdin. Files outside a project, or outside its code, pass.
"""
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import time
from collections import Counter

from . import approvals, claims
from . import lock as lockfile
from . import views
from .claims import CLAIMS_FILE
from .invoke import CMD, PLUGIN, command_lines, getenv
from .markers import Scan
from .model import LEGACY_LOCK_FILE, LOCK_FILE, PART_FILE_NAME, SPEC_DIR, Project, has_spec

PENDING = ('new', 'changed', 'stale', 'removed', 'behind')
GONE_LOOKED_AT = 5   # the claims of holders that are gone that the note a session starts with looks at (about half a second each in a project of hundreds of parts)
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


def marker_hint(text):
    """What to do about one marker problem an edit adds. A marker that names an id nobody wrote needs the clause first; one that breaks
    the shape of the regions needs closing; the others already say what is wrong."""
    if text.endswith(('has no test', 'is no item, row or part')):
        return f'markers may only name ids that exist in {SPEC_DIR}/: add the clause first'
    if text.startswith(('regions never nest', 'region is never closed', '@clause end without')):
        return 'close every region with `@clause end` before the next `@clause` line'
    return ''


def clause_first_reasons(project, drift, fallback):
    """One line for each place whose code drifts (a finding with status drift): where it is, the clauses it serves, and where to change them first.
    `fallback` is the place to name for a finding that has none. The edit guard refuses with these lines, and the check after a shell command says them."""
    by_where, reasons = {}, []
    for f in drift:
        by_where.setdefault(f.where or fallback, []).append(f.key)
    for where, keys in by_where.items():
        targets = [where_to_change(project, k) for k in keys]
        if len(keys) == 1:
            reasons.append(f'- {where} serves `{keys[0]}`: change {targets[0]} first.')
        else:
            reasons.append(f'- {where} serves {", ".join(f"`{k}`" for k in keys)}: change one of '
                           + ', '.join(targets) + ' first.')
    return reasons


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
                        ignore=shutil.ignore_patterns('.sor-claims.*', '.sor-bindings.*', '.sor-approved-targets.*', '.sor-lock.mutex', '.claims.*', '.lock.mutex'))
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


def claim_refusal(project, payload, keys, regions=(), text=True):
    """A refusal when another agent holds a claim on what the edit touches: who, since when, until
    when at the latest. The agent decides what to do next. None when free, or not enforcing."""
    if not enforcing() or not keys:
        return None
    sid = (payload.get('session_id') or '').strip()
    if not sid:
        return None   # cannot tell who is editing
    held = claims.others_for_agent(project, sid, payload.get('agent_id') or '', keys, regions, text=text)
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


def renew_quietly(project, session, agent_id=''):
    """A hook call is a sign of life of the claims of its session (`claims.touch`), and whatever goes wrong while recording it costs the hook
    nothing: the edit keeps its check and the read its note. Inside a subagent (`agent_id`) it is a sign of life of the claims under the name that subagent is
    bound to and of nobody else's: a subagent that has bound no name holds nothing, and the parent working on does not keep a finished subagent's claims alive."""
    try:
        if agent_id:
            name = claims.bound_name(project, session, agent_id)
            if name:
                claims.touch(project, session, name=name)
        else:
            claims.touch(project, session)
    except Exception:  # noqa: BLE001  a hook must not fail for this
        pass


def renew_claims(root, payload):
    """An edit by a session renews its claims. It reads the claims file and nothing else, so the project is not parsed for it."""
    session = payload.get('session_id') or ''
    if session and os.path.isfile(claims.path(claims.at(root))):
        renew_quietly(claims.at(root), session, payload.get('agent_id') or '')


def pre_edit(payload):
    tool, inp = payload.get('tool_name', ''), payload.get('tool_input') or {}
    refusal = approvals_refusal(payload)
    if refusal:
        return refusal
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
    except (lockfile.LockConflict, lockfile.LockDamaged) as e:   # a merge is being resolved: the edits that resolve it must go through
        return context('PreToolUse', f'Spec of Record: {e} Edits to code are not checked against the lock until it is restored.')
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
        regions = claims.regions_of(after, touched)
        if project.targeted():
            # a claim of one language holds the regions of its own files, and the same clause in another file is not what is being edited; a project
            # that keeps its code in one place has no such claims and is asked as it always was. Code is not the text of the clause, which they pin.
            regions = {(f, ids) for f, ids in regions if f == rel}
        refusal = claim_refusal(project, payload, touched, regions, text=False)
        if refusal:
            return refusal
    was, _ = lockfile.status(project, before, lock)
    now, _ = lockfile.status(project, after, lock)
    pending = {f.key for f in now if f.status in PENDING}
    was_drift = {(f.key, f.detail) for f in was if f.status == 'drift'}   # a clause drifting in another target is more drift
    drift = [f for f in now if f.status == 'drift' and (f.key, f.detail) not in was_drift]
    reasons = clause_first_reasons(project, drift, rel)

    def counts(scan):
        return Counter((p.kind, p.text) for p in scan.problems if p.where.startswith(rel + ':'))
    added = counts(after) - counts(before)
    for (kind, text), n in sorted(added.items()):
        hint = ('put it inside a `@clause <id>` … `@clause end` region named after its clause' if kind == 'unmarked'
                else marker_hint(text) if kind == 'marker' else '')
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
VALUE_FLAGS = {'lock': ('--as',), 'test': ('--out', '--provides')}   # options that take a value and are not guarded: the value is not an id
AUTO_MODES = ('bypassPermissions', 'auto', 'dontAsk')   # permission modes in which a hook's question may be answered without the user


def project_of(payload, root):
    """The project at a root, read once per hook call: the cache is in the payload, which lives as long as the call does."""
    cache = payload.setdefault('_projects', {})
    if root not in cache:
        cache[root] = Project(root)
    return cache[root]


def single_root(payload, folder=''):
    """The project a call of `sor` runs in, found as `sor` finds it: the one that the folder of `-C` is in (relative to the cwd of the payload), else the one above the
    cwd. Never a project below the cwd, which `project_roots` falls back to for other uses: `sor` itself does not run there."""
    cwd = os.path.abspath(payload.get('cwd') or os.getcwd())
    return find_root(os.path.join(os.path.abspath(os.path.join(cwd, os.path.expanduser(folder))), 'x'))


def commands_in_words(payload, names):
    """The test commands the spec of the project the call runs in gives for these targets, in words, so that the user sees what would run on their computer and
    not a target's name (`python3 run_tests.py` and `npm test`), and which of them is not the one they allowed before. The project is the one a `-C` names, else
    the one the session works in. Without the project, or when a target gives none, the target's command is described instead."""
    try:
        command = (payload.get('tool_input') or {}).get('command') or ''
        folder = next((f for f, n in plain_target_calls(command) if n == names), '')
        root = single_root(payload, folder)
        project = project_of(payload, root) if root else None
        given = project.target_commands() if project else {}
        changed = approvals.state(project, names)[1] if project else []
    except (Exception, SystemExit):
        given, changed = {}, []
    said = [(f'`{given[n]["run"]}`' if 'run' in given.get(n, {}) else f'the test command your spec gives for {n}') + (' (not the one you allowed before)' if n in changed else '')
            for n in names]
    return ' and '.join(said) if said else "the test commands your spec gives"


CHANGES_FOLDER = ('cd', 'pushd', 'popd', 'chdir')


def changes_folder(words):
    """Whether a command changes the folder the commands after it run in (`cd`, `pushd`, `env -C`), so that they run in another project than the hook's cwd."""
    i = program_index(words)
    if any(os.path.basename(w) in CHANGES_FOLDER for w in words[:i + 1]):
        return True
    return 'env' in [os.path.basename(w) for w in words[:3]] and any(w in ('-C', '--chdir') or w.startswith('--chdir=') for w in words)


def plain_target_calls(command):
    """[(folder, targets)] for each `sor lock` or `sor test --targets ...` that a command line runs as plainly as the shell guard reads it: the program is `sor` or
    `sor.py` itself, not a variable or a script that may run something else, and the `-C` folder it names is `folder` ('' for none). A call this does not give is
    one the hook cannot tell the project of, so it is never taken as allowed."""
    out = []
    if any(changes_folder(words) for words in command_segments(command)):   # `cd ../worktree && sor test --targets py` runs in a folder the hook did not look at
        return out
    for sub, args, folder in sor_calls(command):
        if sub in ('lock', 'test'):
            call = guarded_call(['sor', sub] + args)
            if call and call[2].get('targets'):
                out.append((folder, call[2]['targets']))
    return out


def targets_allowed(payload, command, calls):
    """Whether every call of a command line that names `--targets` runs only commands the user allowed before: it is read plainly (`plain_target_calls` finds as many
    of them as `calls` has), the project it runs in is one, and the spec gives for each target the text that `approvals` has written down."""
    try:
        named = sum(1 for _, _, found in calls if found.get('targets'))
        plain = plain_target_calls(command)
        if not named or len(plain) != named:
            return False
        for folder, names in plain:
            root = single_root(payload, folder)
            if not root or not approvals.state(project_of(payload, root), names)[0]:
                return False
    except (Exception, SystemExit):
        return False
    return True


def asked_note(payload):
    from . import shellguard   # not at the top: it uses this module
    return shellguard.tmp('asked-' + shellguard.call_id(payload))


def note_shown(payload, command, asked):
    """Keeps for the hook after the call what the question showed ([{'root', 'run': {target: text}}]), or, when the call is not asked about, removes what an earlier
    note of this call held (an agent could have written one). `record_allowed_targets` writes down what the note holds and nothing else, so a command that changed
    between the question and the run, or one the user was not shown, is never taken as allowed. No note is kept in a mode that answers the question itself."""
    from . import shellguard
    shown = []
    try:
        if asked and payload.get('permission_mode') not in AUTO_MODES:
            for folder, names in plain_target_calls(command):
                root = single_root(payload, folder)
                given = approvals.commands(project_of(payload, root), names) if root else None
                if given:
                    shown.append({'root': root, 'run': given})
    except (Exception, SystemExit):
        shown = []   # no note: the call is asked about all the same, and nothing is written down for it
    if shown:
        shellguard.write_json(asked_note(payload), {'at': time.time(), 'shown': shown})
    else:
        try:
            os.remove(asked_note(payload))
        except OSError:
            pass


def record_allowed_targets(payload):
    """After a call went through (a hook after a tool call does not run for one the user refused): writes down the test commands the question showed for it, which
    `note_shown` kept, so that the same text is not asked about again."""
    from . import shellguard
    note = shellguard.read_json(asked_note(payload))
    if not note:
        return
    try:
        os.remove(asked_note(payload))
    except OSError:
        pass
    for entry in note.get('shown') or []:
        approvals.record(project_of(payload, entry['root']), entry['run'])


READ_ONLY = ('grep', 'egrep', 'rg', 'ls', 'cat', 'head', 'tail', 'wc', 'less', 'more', 'stat', 'file', 'git', 'sor', 'sor.py', 'cd', 'echo', 'printf', 'diff')


def approvals_write_refusal(payload):
    """A refusal for a shell command that names the file of allowed test commands and could write it: a redirection to a file, a line that cannot be read, or a
    program that is not read-only. Reading it (`grep`, `cat`) passes. The edit guard sees edits only, and an agent that writes the file allows its own commands."""
    command = (payload.get('tool_input') or {}).get('command') or ''
    if approvals.FILE not in command and approvals.OWN_FILE not in command:
        return None
    from . import shellguard
    parts, readable = shellguard.parts_of(command)
    if readable and not any(shellguard.redirects_to_a_file(p) for p in parts) and \
            all(program_index(p) >= len(p) or os.path.basename(p[program_index(p)]) in READ_ONLY for p in parts):
        return None
    return deny(f'{approvals.FILE} holds the test commands the user has allowed, and is written only by the hook after a call that ran them went through. '
                'A shell command that may write it is refused: when a test command is new or changed, the user is asked, and their yes writes it down.')


def approvals_refusal(payload):
    """A refusal when an edit would write the file of allowed test commands: it is the user's answer, written by the hook only."""
    path = os.path.abspath(os.path.expanduser((payload.get('tool_input') or {}).get('file_path') or ''))
    if os.path.basename(path) not in (approvals.FILE, approvals.OWN_FILE):
        return None
    try:
        for root in project_roots(payload):
            if os.path.realpath(approvals.file(Project(root))) == os.path.realpath(path):
                return deny(f'{os.path.basename(path)} holds the test commands the user has allowed, and is written only by the hook after a call that ran them went through. '
                            'Do not edit it: when a test command is new or changed, the user is asked, and their yes writes it down.')
    except (Exception, SystemExit):
        pass
    return None


# The options that need the user's yes, and everything the hook knows about each, so that a new one is a new row and nothing else. The user reads the
# question in a permission dialog and may never have heard of the option, so it is put in plain words, with no option name or clause id in it (only a test,
# a language or a program that the call names): what Claude wants to do, and what saying yes means trusting. The dialog shows the command itself, and cuts a
# long text off at the end, so the first sentence says the whole point, with what would run in it, and the last one, which says what to trust, stays short.
#   option, least: the option and the shortest prefix of it that argparse takes     values: how many values follow it ('none', 'one', 'many')
#   commands: the commands that have it                                             fallback: what stands for its value when the command gives none
#   says: what Claude wants to do, finishing `Claude wants` ({value}; {then}: and what follows)     trust: what saying yes trusts, finishing `Allow only if`
#   value: how to put the values in words (default: they are listed); it gets the payload and the values
# The `--results` of `sor evidence` is a CI job's own file, so it is not here. The rows are in the order the user reads them.
GUARDED = {
    'allow-behind': dict(option='--allow-behind', least=len('--allow-b'), values='one', commands=('lock',), fallback='one language',
                         says='to save its work as finished, although the code for {value} is out of date with the new spec, or missing',
                         trust='you have already agreed that {value} can come later'),
    'already-fits': dict(option='--already-fits', least=len('--alr'), values='one', commands=('lock',), fallback='one language',
                         says='to save its work as finished, and to say that the code for {value} already matches the new spec without changing it',
                         trust='you have checked that the code still does what the new spec says'),
    'allow-incomplete': dict(option='--allow-incomplete', least=len('--allow-i'), values='none', commands=('lock',), fallback='',
                             says='to save its work as finished, although some tests have not passed',
                             trust='those tests were already failing before this change'),
    'confirm': dict(option='--confirm', least=len('--c'), values='many', commands=('lock',), fallback='a test',
                    says='to record that a person has tried {value} by hand and it works',
                    trust='you have tried that yourself'),
    'results': dict(option='--results', least=len('--res'), values='one', commands=('lock',), fallback='a file',
                    says='to save its work as finished using the test results in {value}, which nobody checks against a real test run',
                    trust="you saw the tests run, or are happy to take Claude's word that they passed"),
    'targets': dict(option='--targets', least=len('--t'), values='one', commands=('lock', 'test'), fallback='a target',
                    says='to run {value} on your computer{then}',
                    trust='you trust what it runs, which has your access and whose report counts as the test results',
                    value=commands_in_words),
}


def guarded_option(word, command):
    """The name of the option a word is, when it is one that `sor <command>` needs the user's yes for (see GUARDED), also as `--allow-behind=ts` and
    as the shortest prefix argparse takes for it; else None."""
    name = word.split('=', 1)[0]
    for short, row in GUARDED.items():
        if command in row['commands'] and len(name) >= row['least'] and row['option'].startswith(name):
            return short
    return None


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
            if base == 'env':   # `env -C folder sor ...`, `env -i -u NAME sor ...`: its options, and the values of the ones that take one
                while i < len(words) and words[i].startswith('-') and words[i] != '--':
                    i += 2 if words[i] in ('-C', '-u', '-S', '--chdir', '--unset', '--split-string') else 1
        else:
            break
    if i < len(words) and re.match(r'^(python[0-9.]*|py)(\.exe)?$', os.path.basename(words[i])):
        i += 1
        while i < len(words) and words[i].startswith('-'):
            i += 1
    return i


OPAQUE = re.compile(r'[$`]|/|\.(?:sh|bash|zsh)$')   # a program word that hides what runs: a variable (`$P`, `${P:-sor}`), a substitution, a script path


def guarded_call(words):
    """(command, ids, found) when these words are a `sor lock` or `sor test` that carries an option the user has to say yes to (see GUARDED), else
    None. `ids` are the clauses it names; `found` has each of those options with the values after it. A program word that hides what runs
    (OPAQUE) counts as sor when the words after it are those of a call, with launcher options and a `sor.py` skipped, because this hook is the only
    check the skill leaves and it says nothing when it misses; a plain program (grep, echo, git) never does."""
    i = program_index(words)
    if i >= len(words):
        return None
    if os.path.basename(words[i]) in ('sor', 'sor.py') or OPAQUE.search(words[i]):
        k = i + 1
        while k < len(words) and (words[k].startswith('-') or os.path.basename(words[k]) in ('sor', 'sor.py')):   # `$PY -I tools/py/sor.py -C folder lock`
            k += 2 if words[k] == '-C' else 1
    elif words[i] in ('lock', 'test'):   # what is left of `$(which sor) lock ...` once the parentheses have split the line
        k = i
    else:
        return None
    if k >= len(words) or words[k] not in ('lock', 'test'):
        return None
    command, args = words[k], words[k + 1:]
    ids, found, n = [], {}, 0
    while n < len(args):
        a = args[n]
        short = guarded_option(a, command)
        if short:
            values, n = [], n + 1
            if '=' in a:
                values = [v for v in a.split('=', 1)[1].split(',') if v]
            elif GUARDED[short]['values'] == 'one' and n < len(args) and not args[n].startswith('-'):
                values, n = [v for v in args[n].split(',') if v], n + 1
            elif GUARDED[short]['values'] == 'many':
                while n < len(args) and not args[n].startswith('-'):
                    values, n = values + [args[n]], n + 1
            found.setdefault(short, []).extend(values)
        elif a in VALUE_FLAGS[command]:
            n += 2
        else:
            if not a.startswith('-') and not a.isdigit():   # a number is what is left of `2>&1`
                ids.append(a)
            n += 1
    return (command, ids, found) if found else None


def guarded_calls(command, depth=0):
    """[(command, ids, found)] of every `sor lock` or `sor test` with a guarded option in a shell command line: the commands joined by `&&`, `||`, `;`,
    `|` or a new line, and what a quoted argument holds (`bash -c "..."`). The word `lock` or `test` and the option in a command that cannot be read
    (an open quote) count, for a guard that errs the other way would not guard."""
    found, body_ends = [], None   # body_ends: the word that ends a here-document whose lines are data, not commands
    for line in command_lines(command):
        if body_ends is not None:
            if line.strip() == body_ends:
                body_ends = None
            continue
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            named = {c for c in ('lock', 'test') if re.search(rf'\b{c}\b', line)}
            options = {guarded_option(word, c) for word in re.findall(r'--[A-Za-z][A-Za-z-]*', line) for c in named} - {None}   # `--cached` is not `--confirm`
            if options:
                found.append(('lock' if 'lock' in named else 'test', [], {short: [] for short in options}))
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
            call = guarded_call(segment)
            if call:
                found.append(call)
            elif depth < 3:
                i = program_index(segment)
                if i < len(segment) and os.path.basename(segment[i]) in SHELLS:   # `bash -c "sor lock ..."`: its argument is a command line
                    for w in segment[i + 1:]:
                        if ' ' in w:
                            found += guarded_calls(w, depth + 1)
    return found


def command_segments(command, depth=0):
    """The simple commands of a shell command line as lists of words, split the way `guarded_calls` splits them: at `&&`, `||`, `;`, `|` and new lines, past
    here-documents whose lines are data, and into what a quoted argument of a shell holds (`bash -c "..."`). A line that cannot be read gives none."""
    out, body_ends = [], None
    for line in command_lines(command):
        if body_ends is not None:
            if line.strip() == body_ends:
                body_ends = None
            continue
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            continue
        segments, current = [], []
        for n, w in enumerate(words):
            if w == '<<' and n + 1 < len(words) and body_ends is None:
                i = program_index(current)
                if not (i < len(current) and os.path.basename(current[i]) in SHELLS):
                    body_ends = words[n + 1].lstrip('-')
            if SHELL_OPERATOR.match(w):
                segments, current = segments + ([current] if current else []), []
            else:
                current.append(w)
        for segment in segments + ([current] if current else []):
            out.append(segment)
            if depth < 3:
                i = program_index(segment)
                if i < len(segment) and os.path.basename(segment[i]) in SHELLS:
                    for w in segment[i + 1:]:
                        if ' ' in w:
                            out += command_segments(w, depth + 1)
    return out


def sor_calls(command):
    """[(subcommand, words after it, the folder `-C` names or '')] for every `sor <subcommand> ...` a shell command line runs."""
    out = []
    for words in command_segments(command):
        i = program_index(words)
        if i >= len(words) or os.path.basename(words[i]) not in ('sor', 'sor.py'):
            continue
        k, folder = i + 1, ''
        while k < len(words) and words[k].startswith('-'):   # the options before the command: `-C folder`
            if words[k] == '-C' and k + 1 < len(words):
                folder = words[k + 1]
            elif words[k].startswith('-C') and len(words[k]) > 2:
                folder = words[k][2:]
            k += 2 if words[k] == '-C' else 1
        if k < len(words):
            out.append((words[k], words[k + 1:], folder))
    return out


def option_value(args, name):
    """The value of `--name value` or `--name=value` among the words of a command, '' when it is not there."""
    for n, a in enumerate(args):
        if a == name:
            return args[n + 1] if n + 1 < len(args) and not args[n + 1].startswith('-') else ''
        if a.startswith(name + '='):
            return a[len(name) + 1:]
    return ''


def forces(args):
    """Does a `sor release` ask to force? argparse takes `--force` as any unambiguous prefix of it (`--f`, `--fo`, `--forc`), as `guarded_option` knows for the others."""
    return any(len(a.split('=', 1)[0]) >= 3 and '--force'.startswith(a.split('=', 1)[0]) for a in args)


def project_roots(payload, folder=''):
    """The project roots a hook works on: the folder a `sor -C folder` names (relative to the cwd of the payload), else the project above the cwd, else the projects below
    it, found as the shell guard finds them (a repository root with its projects in subfolders)."""
    cwd = os.path.abspath(payload.get('cwd') or os.getcwd())
    if folder:
        root = find_root(os.path.join(os.path.abspath(os.path.join(cwd, os.path.expanduser(folder))), 'x'))
        return [root] if root else []
    root = find_root(os.path.join(cwd, 'x'))
    if root:
        return [root]
    from . import shellguard   # not at the top: it uses this module
    return shellguard.projects_of(payload)


def agent_rules(payload):
    """What an agent's shell command may not do, as a refusal, or None. A person at a terminal runs no hook, so nothing here takes anything from a person.
    `sor release --force` frees another holder's claim, with nobody asked: an agent that wants a claim another holds says so (`sor claim`, which frees what holds
    nothing back and takes over what a gone holder left unfinished) and does not force. A subagent names itself on every claim, lock and release (--as), and the
    name binds it: its edits are attributed to the name, so the guard can tell it from its siblings and its parent."""
    command = (payload.get('tool_input') or {}).get('command') or ''
    calls = sor_calls(command)
    if not calls:
        return None
    agent_id, session = payload.get('agent_id') or '', (payload.get('session_id') or '').strip()
    for sub, args, folder in calls:
        if sub == 'release' and forces(args):
            return deny('`sor release --force` frees a claim somebody else holds without asking them, so an agent does not run it. Claim the clause instead: `' + CMD +
                        ' claim <id>` frees a claim that holds nothing back, and says why when one still stands; `--take-over` continues the work of a gone '
                        'holder that left it unfinished. A person can force a release from a terminal.')
        if agent_id and session and sub in ('claim', 'lock', 'release'):
            name = option_value(args, '--as')
            if not name:
                return deny(f'You are a subagent, so a claim, lock or release needs a name of your own: pass `--as <name>` on every call (for example `--as {agent_id[:8]}`). '
                            'The name is how the claims you make are told from your parent\'s and your siblings\'.')
            for root in project_roots(payload, folder):
                ok, other = claims.bind(claims.at(root), session, agent_id, name)
                if not ok:
                    return deny(f'The name `{name}` is already used by another subagent of this session ({other[:8]}). Pass a name of your own with `--as`, '
                                f'for example `--as {agent_id[:8]}`.')
    return None


def session_end(payload):
    """Records that the session is ending on its claims (`claims.mark_ended`), and frees nothing: what the claims of an ended session mean is decided
    when somebody asks for the clause. It has 1.5 seconds, so it reads the claims file and nothing else, not the project. It records in the project above the folder
    the session ends in, or, from a repository root that holds projects in subfolders, in each project below it (`project_roots`)."""
    for root in project_roots(payload):
        claims.mark_ended(claims.at(root), payload.get('session_id') or '', payload.get('reason') or 'other')
    return None


def pre_bash(payload):
    """Asks the user before a `sor lock` or `sor test` runs with an option that is theirs to decide (GUARDED): `--allow-behind` lets a language stay
    behind a clause, or lack code for it, `--already-fits` clears a language with no code change, `--allow-incomplete` locks tests that did not
    pass, `--confirm` says a person checked a manual test, `--results` takes the pass or fail of tests from a file, and `--targets` runs the commands
    a spec declares. A command that merely mentions an option (a grep, a document) passes. This guards Claude Code only; a person's terminal is not
    touched."""
    if payload.get('tool_name') not in (None, 'Bash'):
        return None
    try:
        from . import shellguard   # not at the top: it uses this module
        shellguard.before(payload)
    except (Exception, SystemExit):
        pass   # a note about the command that follows is not worth stopping it
    try:
        refusal = approvals_write_refusal(payload)
    except (Exception, SystemExit):
        refusal = None
    refusal = refusal or agent_rules(payload)
    if refusal:
        return refusal
    command_line = (payload.get('tool_input') or {}).get('command') or ''
    calls = guarded_calls(command_line)
    if not calls:
        return None
    allowed = {'targets'} if targets_allowed(payload, command_line, calls) else set()   # commands the user allowed before, and that are the same now
    parts, advice = [], []
    for command, _, found in calls:
        then = ', then save its work as finished with their results' if command == 'lock' else ''
        for name, row in GUARDED.items():
            if name in found and name not in allowed:
                value = row['value'](payload, found[name]) if 'value' in row else ', '.join(found[name]) or row['fallback']
                parts.append(row['says'].format(value=value, then=then))
                advice.append(row['trust'].format(value=value))
    note_shown(payload, command_line, bool(parts))
    if not parts:
        return None
    wants = [('Claude wants ' if n == 0 else 'It also wants ') + part + '.' for n, part in enumerate(dict.fromkeys(parts))]
    reason = ' '.join(wants) + ' Allow only if ' + ', and '.join(dict.fromkeys(advice)) + '.'
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask', 'permissionDecisionReason': reason}}


def post_bash(payload):
    """After a shell command: writes down the test commands a call with `--targets` ran, which the user was asked about (`record_allowed_targets`), and says what the edit guard would
    have refused had the command been an edit (see shellguard.py), also for one that failed."""
    if payload.get('tool_name') not in (None, 'Bash'):
        return None
    try:
        if payload.get('hook_event_name') != 'PostToolUseFailure':   # a tool that failed may be one the user refused: only a call that went through says they allowed it
            record_allowed_targets(payload)
    except (Exception, SystemExit):
        pass   # a note about what was allowed is not worth failing the command's own report
    from . import shellguard
    return shellguard.after(payload)


def context(event, text):
    """Words for the agent, with no decision: what a hook says when it lets something through or cannot do its job."""
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': text}}


EVENT = {'pre-edit': 'PreToolUse', 'pre-bash': 'PreToolUse', 'post-read': 'PostToolUse', 'post-bash': 'PostToolUse', 'session-start': 'SessionStart', 'subagent-start': 'SubagentStart'}


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
    renew_quietly(project, payload.get('session_id') or '', payload.get('agent_id') or '')
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
    """One plain line about what is pending since the last lock: every finding `sor status` lists apart from the information group (clauses to
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


def claims_lines(project, session='', source=''):
    """Lines about claims for the note a session starts with: on resume or compaction the claims this session holds (an agent forgets them after a compaction, and
    a resumed session shows its signs of life, which clears the fact that it ended), each claim that stands because its holder is gone and left something (parked,
    or waiting for its merge) with how long that has been so, and with whom the claims are shared. Empty when there are no claims and the store is the
    project's own folder."""
    held = claims.active(project)
    st = claims.store(project)
    lines = []
    if session and source in ('resume', 'compact') and any(c.get('session') == session for c in held):
        claims.touch(claims.at(project.root), session)
        lines.append('Claims you hold in this session: ' + '; '.join(claims.describe(c) for c in claims.active(project) if c.get('session') == session) + '.')
    now = time.time()
    others = [c for c in held if not session or c.get('session') != session]
    window = claims.project_parked(project)
    gone = [c for c in others if claims.is_gone(c, now, window)]
    looked = gone[:GONE_LOOKED_AT]      # each one gone is read in its own folder, and a session start has 10 seconds
    for c, d in claims.states(project, looked):
        if d.kind in ('parked', 'waiting'):
            seconds = max(0, int(now - claims.gone_since(c, now)))
            first = claims.explain(c, d).replace('\n    ', ' — ', 1)
            lines.append(f"{d.kind.capitalize()} for {seconds // 3600} h: {first}" if seconds >= 3600 else f"{d.kind.capitalize()} for {seconds // 60} min: {first}")
    if len(gone) > len(looked):
        lines.append(f'{len(gone) - len(looked)} more claims of holders that are gone were not looked at: `{CMD} claims` lists them all.')
    if held or st.kind != 'folder':
        lines.append(f'Claims are shared by {st.shared}.')
    return lines


def pending_note(project, session='', source=''):
    """Lines of plain status a session finds when it starts: what is pending since the last lock (`pending_line`), and the claims in force, which exist
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
    try:
        lines += claims_lines(project, session, source)
    except (Exception, SystemExit):
        pass   # a note about the claims is not worth failing the start of a session
    return '\n'.join(lines)


def session_start(payload):
    """One short note when the session starts in a project that has a spec, so an agent knows the
    workflow exists before it edits anything. Stated as plain information, not orders (Claude Code's advice).
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
        pending = pending_note(Project(root), (payload.get('session_id') or '').strip(), payload.get('source') or '')
        if pending:
            ctx += '\n' + pending
    except (Exception, SystemExit):
        pass   # a lock this copy cannot read, a broken part: the note above is enough
    return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': ctx}}


FINISHED = ('completed', 'failed', 'killed', 'cancelled', 'canceled', 'stopped', 'done', 'error')   # the states of a background task that works no more


def working(tasks):
    """Does the `background_tasks` list of a Stop name work that is still going on? A task counts unless its status is one that has ended; a task with no status does."""
    return any(not (isinstance(t, dict) and str(t.get('status') or '').lower() in FINISHED) for t in tasks or ())


def stop(payload):
    """Records what the `Stop` of the session said about its background work (`claims.mark_busy`): with work in flight (a long build, a subagent), its claims are
    not quiet for a while; without, that is forgotten. It frees nothing and decides nothing: it is idle only in the sense of waiting for the user."""
    for root in project_roots(payload):
        claims.mark_busy(claims.at(root), (payload.get('session_id') or '').strip(), working(payload.get('background_tasks')))
    return None


def subagent_start(payload):
    """A subagent starts, or is resumed: its claims are no longer stopped, and it is told to name itself when it claims."""
    roots = project_roots(payload)
    for root in roots:
        claims.mark_stopped(claims.at(root), (payload.get('session_id') or '').strip(), payload.get('agent_id') or '', False)
    if not roots:
        return None
    return context('SubagentStart', f'This project keeps its specification as clauses in {SPEC_DIR}/ (Spec of Record). If you claim, lock or release clauses, pass `--as <a name '
                   'of your own>` on every `' + CMD + ' claim`, `lock` and `release`: your claims are held under it, apart from your parent\'s and your siblings\'.')


def subagent_stop(payload):
    """A subagent stopped: its claims say so, which makes the holder gone (a subagent can be resumed, and `subagent_start` clears it)."""
    for root in project_roots(payload):
        claims.mark_stopped(claims.at(root), (payload.get('session_id') or '').strip(), payload.get('agent_id') or '', True)
    return None


HOOKS = {'pre-edit': pre_edit, 'post-read': post_read, 'session-start': session_start, 'pre-bash': pre_bash, 'post-bash': post_bash, 'session-end': session_end,
         'stop': stop, 'subagent-start': subagent_start, 'subagent-stop': subagent_stop}


def run(which):
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8') or '{}')
        out = HOOKS[which](payload)
    except (Exception, SystemExit) as e:  # never block the agent because the tool itself failed (a refused project too)
        print(f'sor hook {which} failed: {type(e).__name__}: {e}', file=sys.stderr)
        # Claude Code treats exit 1 as a non-blocking error and prints noise; exit 0 with a note says the same to the agent and keeps the transcript clean
        if which in EVENT:
            sys.stdout.write(json.dumps(context(EVENT[which], f'Spec of Record: the {which} hook failed ({type(e).__name__}: {e}), so it did not check this.'),
                                        ensure_ascii=False))
        return 0
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0
