# Marker lines
Why: hide the `// @clause …` comment lines in generated code, without ever changing the files.

## Rules
- **setting** — `sor.hideMarkerLines` is on by default; "Spec of Record: Toggle marker lines" flips it.
- **which** — only lines that are a marker on their own are hidden (`@clause <id>`, `@clause end`, a
  marker at the top of a file); a marker at the end of a code line is never hidden. The comment may
  start the way the tool accepts it in the file's language: one to four punctuation characters
  (`//`, `#`, `--`, `;`, `%`, `!`, `'`, `(*`, `/*`, `<!--`, `::`) or `rem`.
- **fold** — a hidden marker folds into the line above, so line numbers skip and the line above
  ends with "…"; a run of markers is one fold.
- **blank-rows** — a marker that cannot fold (after a line that closes another fold, or on line
  1) is still hidden, as a blank row.
- **cursor-opens** — a fold opens while the cursor or a selection touches the marker or the line
  above, and folds again when the cursor leaves.
- **cursor-kept** — folding never moves a cursor someone placed: only a cursor that folding itself
  pushed onto a fold's first line is put back where it was.
- **toggle-off** — turning hiding off unfolds only the extension's folds; folds a person made
  stay; turning it on folds the markers again.
- **own-regions** — a file with its own `#region` folds, or `editor.foldingStrategy`
  "indentation", gets no marker folds: the markers are blank rows.

## Approach
- **from-index** — the marker lines come from the index; folds are Region ranges applied with
  `editor.foldAllMarkerRegions`, and marker N is hidden by the fold from N-1 to N.
- **fallback-folds** — where no other folding provider exists, it adds indentation folds so
  normal folding keeps working; built-in language servers are asked a few times while starting.
- **plan-cache** — a fold plan is made once per document version and applied again shortly after,
  because VS Code can be late in taking up the ranges.

## Contract
- gives **folds** — which marker lines are folded, so a lens can move below a folded marker.

## Tests
- **setting** — hiding is on by default and hides exactly the marker lines; the toggle shows them
  all and hides them again (test/suite.js).
- **cursor-opens** — the marker under the cursor is shown, the others hidden; the cursor on the
  line above opens a fold and leaving closes it (test/suite.js).
- **fold** — folded markers leave the view, the line above stays, line numbers skip
  (test/suite.js).
- **blank-rows** — markers that cannot fold are still hidden as blank rows (test/suite.js).
- **toggle-off** — hiding off brings every marker back, on folds them again, and a fold the
  person made stays closed (test/suite.js).
- **cursor-kept** — a cursor placed right after opening a file, while folds are still being
  applied, stays where it was put (test/suite.js).
  bug: the cursor jumped back to where it was before
- **own-regions** — a `#region` file, or the "indentation" strategy, gets blank rows, not folds.
  manual: by eye
- **which** — the opening and closing marker lines of a region, and one at the top of a file, are
  hidden; the marker at the end of the Mars row's code line is not (test/suite.js).
- **starters** — a marker line written after `%`, `!`, `'`, `(*`, `::` or `rem` is a marker of its own
  like one after `//`; a line of code that only ends with a marker, or a comment about something
  else, is not (test/regions.js).
  proves: {which}
