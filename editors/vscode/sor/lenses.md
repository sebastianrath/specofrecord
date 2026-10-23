# Lenses
Why: clickable lines above clauses and above their code, to jump from one to the other.

## Rules
- **clause-lens** — every item and table row with code gets a lens naming its code region
  (`out/index.html:26-28`), or how many regions it has and, when they are in more than one target,
  which (`2 code regions (py, ts)`); a part heading gets one even with no code.
- **flags** — an item that needs attention ends with `● drift`, `● to review` or `● to recompile`.
- **jump** — clicking a clause lens jumps to its code; with several regions it asks which first,
  naming the target of each when they are in more than one.
- **marker-lens** — every `@clause <id>` line gets one lens per id, `<id> · <state>`; clicking it
  jumps to that clause. `@clause end` lines get none.
- **glue-lens** — a `@clause glue` line gets one lens, `glue`, while the cursor is in its region.
  It jumps nowhere, because glue serves no clause.
- **show-all** — a line with several ids also gets a "Show all code" lens.
- **line-marker** — a marker at the end of a code line puts its lens on that same line.
- **folded** — when a marker line is folded away, its lens sits on the first line below it.
- **cursor-only** — lenses show only for the block the cursor is in: the item or table row in
  a spec file, the code region in a code file. All other lenses are hidden.

## Approach
- **from-index** — clause lenses come from the index's items and regions, marker lenses from the
  index's regions for the open file; the state comes from the status.
- **word-mismatch** — known limit: marker lenses show the raw status word (`stale`, `changed`),
  clause lenses show "to review", "to recompile".

## Contract
- needs {project/index}, {marker-lines/folds} — the data, and where folded markers are.

## Tests
- **clause-lens** — the sun item's lens names `out/index.html:` and a range and opens it; the Mars
  row's lens names a single line (test/suite.js).
- **marker-lens** — the `@clause bodies/sun` line has one lens, `bodies/sun · …`, that opens the
  sun item; `@clause end` has none (test/suite.js).
- **glue-lens** — with the cursor in a `@clause glue` region, its marker line has a `glue` lens and
  the lens has no click action (test/suite.js).
- **line-marker** — the line marker for `bodies/planets/Mars` has a lens with that id
  (test/suite.js).
- **show-all** — a region with several ids has a "Show all code" lens (test/suite.js).
- **folded** — with the marker folded, the lens is on the visible line below (test/suite.js).
- **cursor-only** — with the cursor on the sun item only its lens shows; moving to the moon item
  shows the moon's lens instead (test/suite.js).
- **flags** — a clause whose code is out of date shows `● to review`.
  manual: by eye
- **targets** — an item whose code is in two targets says which in its lens (`2 code regions (py, ts)`),
  and the list of regions it asks about names the target of each; code in one target shows neither
  (test/regions.js).
  proves: {clause-lens}
- **jump** — an item with several regions asks which one to open.
  manual: by eye
