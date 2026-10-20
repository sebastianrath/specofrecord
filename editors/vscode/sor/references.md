# References
Why: ctrl+click on a {reference} in a spec file jumps to the thing it names, and typing one offers the names.

## Rules
- **jump** — Go to Definition on a reference in a file under `sor/` jumps to the item, row or
  value it names, wherever it lives: `{item}`, `{part/item}`, `{item.value}`, `{name: = other}`.
- **cursor** — anywhere from the first to the last character of a reference counts as on it.
- **code-jump** — Go to Definition on a `code: path#name` line under a clause jumps to that code,
  where the project index places the anchor; an anchor the tool cannot find has no jump.
- **tool-resolves** — it never resolves a name itself; it jumps where the project index says.
- **unresolved** — a reference that names nothing, or more than one thing, has no jump; hovering
  it says it "names no item or value".
- **scope** — outside `sor/`, and in files of no project, Go to Definition is not ours.
- **complete** — typing `{` in a spec file under `sor/` (not inside backticks, not after a `name:` that makes it a
  value) offers every part, item and table row of the project, never the root part (under any of its names) and never a test; each shows its id
  with the clause's own words (a part: its Why) and picking one writes the id and closes the brace, which
  `sor check` accepts. The id is written in full, from the root, so it is found from any part. Values
  (`item.value`) are not offered.

## Approach
- **ambiguity** — known limit: the index gives the same empty answer for no target and for two,
  so the hover cannot tell them apart.

- **complete-words** — the words next to each choice are the lines the index names for the item, and the Why the tool's
  `parts --json` gives; they are only shown, nothing is worked out from them. For an item of the file being edited the
  lines are read from the open text, found by comparing paths without letter case (like everywhere, `paths-case`).

## Contract
- needs {project/index} — the index with every reference and where it goes.
- needs {project/run} — the Why of each part, from `sor parts --json`.

## Tests
- **jump** — a reference in SPECOFRECORD.md, and an `{item.value}` reference, each give the one place the
  index names (test/suite.js).
- **cursor** — the cursor anywhere on a reference counts as on it (test/suite.js).
- **code-jump** — Go to Definition on `code: out/index.html#positions` in the example's
  bodies.md lands on the `positions` function in `index.html` (test/suite.js).
- **unresolved** — a reference to nothing or to two things gives no jump, and its hover says so.
  manual: by eye
- **scope** — Go to Definition in a code file gives nothing from this part.
  manual: by eye
- **complete** — in the example, typing `{` in bodies.md offers its parts, items and rows with their words,
  not the root part nor a test, and the chosen one is a reference that resolves (test/suite.js).
- **tool-resolves** — in a saved spec file, a reference gives a place when the index has it, and one
  inside backticks, which the tool does not index, gives none (test/suite.js).
