# Proposal: a note for a new or changed clause that has no code (2026-11-02)

Status: draft, written in the working tree of branch `skill-improvements`, not committed. Which branch it belongs on is the owner's call.

## What happened
In the Plateau project a unit added nine rule clauses (`render/gpu/hdr/*`, `render/sdl3/hdr/*`, `games/model-viewer/hdr`).
Eight had no `@clause` region in any code file. One clause's prose said "Its code is marked by item in `viewer.h` and
`viewer.cpp`", which was untrue. `sor check` reported 0 problems and no note. A human reviewer found it by running
`sor markers`. The unit had not been locked yet; `sor lock` would have refused it (SPEC §9: a new or changed clause has
code in each target that applies to it).

## What sor shows today (measured on the committed head of that branch, copied to a scratch folder)
- `sor check`: no note. SPEC line 349 counts "have code in py but none in ts"; a clause with no code anywhere is not counted.
  A one-target project can therefore never get this note.
- `sor status`: lists the clauses as `new` without an `@ file:lines` location. Nothing says "no code".
- `sor markers` (the whole project): no line for them. Only `sor markers <id>` prints `<id> has no code`.
- `sor lock`: refuses, but only when someone tries to lock.

The gap is visibility before the lock, not detection.

## Proposed change (structural, language-neutral)
A `sor check` note, `no code`, for a clause that is new or changed since the last lock and has no non-test, non-glue
code region in any target, using the same predicate `sor lock` already applies. It changes no exit code; `--strict`
makes it exit 2. `sor status` prints the same note as a line after its groups. Clauses `sor lock` does not require code
for (check the §9 predicate: Why, approach items without code) are not noted.

## Prose that says where the code is (corrected after a challenge)
I first called the prose check noise and dropped it. That was wrong: a clause whose text names a file where it has no
marker is a real prose-versus-marker mismatch or a missing marker. Measured on Plateau main (everything locked):
- Broad check (any backticked source file named in an item): 23 of 1740 items name a file in which the clause has no
  marker. 13 of them have no code anywhere (looks like legitimately code-less constraint clauses; not all checked).
  Of the other 10, reading each sentence: 5 are real (a stale "Its code is in X" sentence: `tools/editor/program/files/answers`;
  a sentence that disagrees with the markers: `tools/material-load/id`; a file the clause describes but never marks:
  `render/lit/template/common` -> `lit_lobes.hlsli`, `tools/editor/program/files/paths` -> `document.h`,
  `platform/dialogs/no-library-types` -> `dialogs_sdl3.h`) and 5 are legitimate references to a file another clause owns
  (a version history naming `lit_constants.h`, "plain C over `plateau_abi.h`", `math.h` of the projection clause, the macros of
  `plateau_binding.hlsli`, an included `lit_common.hlsli`).
- Narrow check (only sentences of the form "Its code is ...", "The code is ...", "code is marked ..."): 89 items, 4 name a
  file without a marker for the clause, and all 4 are real (`games/model-viewer/hdr`, `tools/material-load/id`,
  `tools/editor/program/files/answers`, `tools/editor/program/files/modal-keys`).

So the narrow check has full precision on this project. The broad check has about 50% precision.

How it is possible: the location is written twice, once in prose and once in the `@clause` markers, and nothing compares
them. Code moves, a unit adds its code to an older clause's region, or a sentence is copied from a neighbour, and the
prose keeps saying the old thing.

Two ways to fix the cause, in order of preference:
1. Stop writing the location in prose. `sor show <id>` already prints the code locations from the markers. A convention
   (and a `sor check` note on the stock phrases "Its code is ..." / "marked by item in ...") removes the second copy, so it
   cannot disagree.
2. Keep the sentences and check them: a `sor check` note when an item has a sentence of that stock form, names a backticked
   file, and the clause has no marker in it. This is language-specific to English phrasing, which is why 1 is better.

## Companion problem: a pure marker move needs a clause text change twice (tested 2026-11-02)
Splitting the marker region of one piece of code between two clauses cannot be done without changing a clause's text:
- The edit guard refuses the Edit ("Clauses come first ... serves <id>: change <id> first").
- Even if a person makes the edit (the guard sees only agent edits), `sor lock` refuses. Test in a scratch project: two
  clauses `pair/a`, `pair/b` share one region `// @clause pair/a pair/b` around two lines; lock; then split it into two
  regions around the same two lines and nothing else. `sor status` then reports `drift pair/a` and `drift pair/b`; `sor lock
  pair/a pair/b` is refused with `drift`; `sor lock --rehash` answers "nothing to rewrite" and `--allow-incomplete` does not
  help.
So the fix has to cover both layers or it only moves the problem: the guard accepts a marker-only Edit AND `sor lock`
treats a region whose code, with the `@clause` marker lines and trailing `// @clause` comments removed, is byte-identical
to the locked code as unchanged for the clauses that keep their lines (a clause that gained or lost lines in its region
because the split moved them still needs its code accepted, so the lock should record the new region without asking for a
text change, as `--rehash` does for a hashing-rule change). Plateau's reference definition and proof script:
`docs/sor-requests/stripdiff.py` in that repository.

Until then the least bad practice is: put the text change to good use. Delete the stale "Its code is in ..." sentence of the
clause (the duplicate this proposal removes anyway) instead of inventing a dummy edit.

## Alternative that needs no sor change
A rule in the project's own gate: fail a branch whose changed clauses have no code, from `sor status --json` (kind
`new` or `changed` and no location). Plateau can add this to `tools/gate/merge_and_lock.py` or the preflight today.

## Also seen in the same incident (not caused by this gap)
New code went inside the regions of older clauses (the SDL3 targets region, the UI shader region). That shows up as drift
or a refused lock. It is the wide-region problem, tracked separately.
