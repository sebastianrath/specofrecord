# Hover and marks
Why: point at a line of generated code and see which clauses it came from and whether they are
up to date.

## Rules
- **hover** — hovering a line inside a `@clause` region shows every clause behind it: its id as a
  link, its text, and its state; the hover asks the tool for that one line.
- **no-hover** — a line outside every region, or a file of no project, shows no hover.
- **blame** — when the tool names who last changed drifted code ("changed by NAME in SHA",
  or "not committed yet"), the hover shows it next to the state.
- **states** — four words, the same in hover, gutter and status bar: in sync, review (the clause or
  one it depends on changed), recompile (new, changed or removed since the lock), drift (the code
  was edited and no longer matches the lock).
- **gutter** — red for drift, amber for review, blue for recompile, on the lines of each code
  region and of each item; in sync shows no mark.
- **worst-wins** — when several states apply, the worst wins: drift, then review, then recompile.
- **status-bar** — the status bar counts "N drift · N review · N recompile" over all projects.

## Approach
- **words** — the tool's status names map to the words: stale and shared are review; new,
  changed, removed and behind are recompile (behind: the code of one language of a clause was
  built for an older text of the clause). Any other status counts as in sync.
- **hover-cut** — the text under each clause in the hover is cut to {lines: 6} lines.

## Contract
- needs {project/index}, {project/run} — the data, and the per-line question for the hover.

## Tests
- **hover** — hovering the Mars line in `index.html` names `bodies/planets/Mars` and its text
  (test/suite.js).
- **states** — a line whose clause changed shows "to recompile" (test/suite.js).
- **gutter** — after a refresh `index.html` has marks in each state the tool reports, and a clause
  item that needs review has an amber mark (test/suite.js).
- **words** — each status the tool reports has one word: behind is recompile, stale and shared are
  review, and a status the extension does not know counts as in sync (test/regions.js).
- **no-hover** — a line outside any region, and a file outside any project, show nothing.
  manual: by eye
- **blame** — a drifted line in a git repository shows who changed it in its hover.
  manual: by eye
- **worst-wins** — when one line has two states, the worse one is the colour.
  manual: by eye
- **status-bar** — with a clause changed on disk the status bar reads the numbers the tool's status
  gives, and `0 drift · 0 review · 0 recompile` again once it is restored (test/suite.js).
