# Proposal: a note for a clause with no code, and a safe way to move markers (2026-11-02, revised after review)

Implemented (this repository, dummy projects only, see `tools/py/test_sor_nocode.py`): change 1 as a `no code` note in `sor
check` and `sor status`, and the weaker form of change 2 as a `code location` note. NOT implemented: the marker-only rule
(guard and lock): it changes what the lock accepts, see the open questions at its end.

Status: draft. Committed on the local `main` of this repository (not pushed). `proposals/` is listed in `.gitignore` as
"kept locally, never committed"; the file was force-added on the owner's instruction, as the two older files in this folder were.

## What happened
In the Plateau project a unit added nine rule clauses (`render/gpu/hdr/*`, `render/sdl3/hdr/*`, `games/model-viewer/hdr`).
Eight had no `@clause` region in any code file. One clause's prose said "Its code is marked by item in `viewer.h` and
`viewer.cpp`", which was untrue. `sor check` reported 0 problems and no note. A human reviewer found it by running
`sor markers`, before anything was locked.

## What sor does today (read from the sources and tested in a scratch project, 2026-11-02)
- `sor check`: no note. `lint.no_code_for_target` (lint.py:149) deliberately says nothing for a clause with no code anywhere
  ("a rule such as `out-of-scope` has none anywhere") and counts only a target that lacks code another target has.
- `sor status`: lists the clauses as `new` without an `@ file:lines` location. Nothing says "no code".
- `sor markers` (whole project): no line for them. Only `sor markers <id>` prints `<id> has no code`.
- **`sor lock` does NOT refuse a new clause that has no code anywhere.** Tested: a new rule `pair/c` with no marker in any file
  was locked ("locked 2 of 11 entries") and `sor markers pair/c` still says "has no code". lock.py:803 and :962 refuse
  "no code" only per target, when the clause has code in another target or a per-language lock asks for it. An earlier
  version of this proposal said the lock would have refused the incident; that was wrong, it was never tested.

So the gap is detection, not only visibility: a clause with no code anywhere can be locked and nothing ever mentions it.

## Proposed change 1: a `no code` note, scoped to new or changed clauses
A `sor check` note, `no code`, for a clause that is new or changed since the last lock and has no non-test, non-glue code
region in any target. It changes no exit code; `--strict` makes it exit 2. `sor status` prints the same note as a line
after its groups. There is no existing predicate to reuse (see above), so the note must be a new check.
Scoping matters: on Plateau main, with every clause locked, 114 to 123 Rules items have no code anywhere (constraints,
contracts, gate rules). Unscoped, the note would show all of them every time. Scoped to new or changed clauses it is silent on
a locked tree and fires on the eight clauses of the incident. A clause that is meant to have no code is acknowledged by locking
it: the note shows once, at creation.

## Proposed change 2: stop writing where the code is in the clause prose
The location is written twice, in prose and in the `@clause` markers, and nothing compares them. Measured on Plateau main
(everything locked; a throwaway script, not committed, so the numbers are indicative):
- Any backticked source file named in an item: 23 of 1740 items name a file in which the clause has no marker. 13 of those
  have no code anywhere (they look like constraint clauses; not all checked). Of the other 10, reading each sentence, 5 are real
  (`tools/editor/program/files/answers`: a stale "Its code is in X"; `tools/material-load/id`: the sentence and the markers
  disagree; `render/lit/template/common` -> `lit_lobes.hlsli`, `tools/editor/program/files/paths` -> `document.h`,
  `platform/dialogs/no-library-types` -> `dialogs_sdl3.h`: a file the clause describes but never marks) and 5 are legitimate
  references to a file another clause owns.
- Only sentences like "Its code is ...", "The code is ...", "code is marked ...": 89 items, 4 name a file without a marker for
  the clause, and all 4 are real. That is a small sample (4 of 89); the script's sentence split stops at the first ". " and its
  file matching is by basename or path suffix.

Preferred fix: do not write the location in prose. `sor show <id>` prints the locations from the markers, so there is one copy
and it cannot disagree. A convention plus a `sor check` note on the stock phrases ("Its code is ...", "marked by item in ...")
enforces it. Weaker alternative: a note when such a sentence names a file in which the clause has no marker; it depends on
English phrasing, which is why the first is better.

## Companion problem: a marker-only change needs a clause text change twice
Splitting the marker region of one piece of code between two clauses cannot be done without changing a clause's text:
- The edit guard refuses the Edit ("Clauses come first ... serves <id>: change <id> first").
- Even if a person makes the edit (the guard sees only agent edits), `sor lock` refuses. Test in a scratch project: two
  clauses `pair/a`, `pair/b` share one region `// @clause pair/a pair/b` around two lines; lock; then split it into two
  regions around the same two lines and nothing else. `sor status` reports `drift pair/a` and `drift pair/b`; `sor lock
  pair/a pair/b` is refused with `drift`; `sor lock --rehash` answers "nothing to rewrite" and `--allow-incomplete` does not help.

### The refusal protects something: do not remove it wholesale
A marker decides which clause answers for which code. Tested (scratch project, both clauses locked with passing tests):
- wrapping a line that was `glue` in `// @clause pair/b` (the code bytes are unchanged): `drift pair/b`;
- moving `pair/b`'s only line into `// @clause glue`: `drift pair/b`.
So today an ownership change is reviewed even when no byte of code changes. A rule that accepts any change whose code is
byte-identical after the marker lines are stripped would accept both, and an agent could attach unreviewed code to a clause or
move code out of every clause (into `glue`) with no text change and no re-acceptance.

### Proposed rule (guard and lock, both)
Accept a change with no clause text change when, line by line, the set of clauses that answer for each code line only
shrinks: after the change each line is owned by a non-empty subset of the clauses that owned it before (never a new clause on
a line, never a line that had a non-glue owner and now has only `glue`, never a glue or unowned line that gains an owner), and
the code with markers removed is byte-identical. A clause whose region narrows is re-recorded by the lock without a text
change (as `--rehash` does for a hashing-rule change). Any other marker change keeps today's behaviour: the receiving clause
(or the clause losing its only owner) must change or be accepted first. Splitting a shared region into per-clause regions
passes; the two cases above are still refused.

Adding markers around code that has none (the Plateau "missing marker" fixes, e.g. around `lit_lobes.hlsli`), tested in a
scratch project with both clauses locked and passing:
- In a project that declares no code roots (the default, `code_roots() == ['.']`), a source file with no `@clause` marker at
  all is invisible to sor: `sor check` reports 0 problems, the lock is clean, no note (markers.py `_add` returns early on
  purpose, so documents and data are not flagged). In a project that declares code roots (a target with a `path`) every
  line under them must be in a region, so an unmarked file is a problem. Not tested with declared roots; read from the code.
- Wrapping every line of such a file in `// @clause pair/b` gives `drift pair/b` (the clause now owns code it did not
  before): refused today without a text change, and refused by the proposed rule (a new owner on a line).
- In a file that already has markers, a line left outside every region is a problem (`unmarked out/extra.js:4 code
  outside any @clause region`), and giving `pair/b` only the first line gives `drift pair/b` too.
So the proposed rule must treat "unmarked file gains markers" like "glue gains an owner": acceptance required. The blind
spot of the first bullet has a remedy that exists already: declare the code roots. No new note is proposed for it.

### What "markers removed" means
The strip must use sor's own marker parser (SPEC §10; markers.py reads many comment starters: `//`, `#`, `--`, `;;`, block
comments, runs such as `///`), not a regex for `//`. The reference script in Plateau (`docs/sor-requests/stripdiff.py`)
strips only `// @clause` and hard-codes the base branch as `main:`; it is a proof for that C++ project, not a definition.

Until the rule exists the least bad practice is: put the text change to good use. Delete the stale "Its code is in ..."
sentence of the clause (the duplicate change 2 removes anyway) instead of inventing a dummy edit.

## Alternative that needs no sor change
A rule in the project's own gate: fail a branch whose changed clauses have no code, from `sor status --json` (kind `new` or
`changed` and no location). Plateau is adding it to `tools/gate/merge_and_lock.py`.

## Related documents
Plateau's request to the sor owner, `docs/sor-requests/marker-only-edits.md`, asks for the guard half only and says the
strip is a `//` regex. It should link here for the rule above, and this file is the one source for the definition.

## Also seen in the same incident (not caused by this gap)
New code went inside the regions of older clauses (the SDL3 targets region, the UI shader region). That shows up as drift
or a refused lock. It is the wide-region problem, tracked separately.

## Open questions for the marker-only rule (not implemented)
The guard half is straightforward: `Scan(project, overrides={file: new text})` already parses a change before it is written, so
the hook can compare the owner sets of every line before and after and apply the shrink rule above. The lock half has no
baseline: the lock stores one code hash per clause, not which lines a clause owned, so `sor lock` cannot tell a shrink from
a gain. Three ways, all with a cost:
1. Record the owners: add a per-clause line-owner digest to the lock (a format change, 4 to 5) so the lock can check the rule.
2. Use git as the baseline: accept the drift only for files whose last committed version, scanned, reproduces the locked hashes
   and satisfies the rule against the working copy. No lock format change; needs git and a clean committed baseline.
3. A ticket: the guard, when it allows a marker-only edit, writes a record next to the claims, in the store where the
   approved test commands are kept, that `sor lock` consumes. A change made by a person has no ticket and keeps the
   text-change requirement.
Each decides what `sor lock` is willing to accept without a text change, which is the central guarantee of the tool, so it is
the sor owner's decision.
