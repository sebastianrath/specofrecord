# Spec of Record for VS Code
Why: show, inside the editor, which code comes from which clause, and whether they still agree.
Owner: sebastian

## Rules
- **show-only** — it only shows things; it never changes a spec file or a code file on disk.
- **from-tool** — everything it shows comes from the `sor` tool; it never works out clauses or markers
  on its own. It may show a clause's own words, read from the lines the tool names.
- **click-through** — you can go from a clause to its code and from a line of code back to its
  clause, by clicking.
- **marks** — a line of code that drifted, or a clause that needs a look, is marked where you
  already look: in the gutter and on hover.
- **hiding-is-display** — hiding the `@clause` comment lines is only how the editor looks; the
  lines stay in the files.
- **out-of-the-way** — no popups; a folder without a Spec of Record project is left alone.
- **out-of-scope** — editing clauses or code from the extension, running tests, other editors.

## Approach
- **parts** — {project} finds the tool and asks it · {lenses} the buttons · {state} hover and
  gutter marks · {references} ctrl+click · {marker-lines} hiding and folding · {colors} syntax
  colors in spec files · {preview} live preview of spec files · {highlight} the counterpart of the
  cursor's block, lit in the other visible editor.
- **one-asker** — only {project} talks to the `sor` tool and hands the answers to the others;
  the rest only show.
- **known-gaps** — the JSON version is never checked, and a failed refresh keeps the old marks
  without saying so.

## Contract
- gives **extension** — one `.vsix`, delivered as {targets/vscode} describes.

## Tests
- **click-through** — in the solar-system example, lenses show on clauses and on `@clause` lines;
  clicking a clause's lens lands on its code, a marker's lens on its clause; ctrl+click on a
  `{reference}` lands on what it names (test/suite.js).
- **marks** — hovering generated code shows the clauses behind it; a clause changed without its
  code shows as drift until the code is built again (test/suite.js).
- **hiding-is-display** — turning marker hiding off and on leaves the files on disk the same.
  manual: compare the file bytes by hand
- **out-of-the-way** — a folder with no `sor/SPECOFRECORD.md` (or older `sor/CLAUSES.md`) shows nothing.
  manual: by eye
