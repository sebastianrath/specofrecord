# Highlight
Why: show the counterpart of what the cursor is in, when both are on screen, so nobody needs the lens to see it.

## Rules
<!-- What must be true: goals, rules, numbers, budgets, words. If a user or a test could notice a change, it is a rule. At most 7 items. -->
- **counterpart** — with the cursor in a clause, its code is highlighted in every visible editor that
  shows that code; with the cursor in code, the clauses it comes from are highlighted in every visible
  spec editor. The block is the one the lens uses: a clause, a table row, or a code region.
  The editor whose cursor moved last leads, and the other visible editors show its counterpart.
- **all-ids** — a code region marked for several clauses highlights all of them.
- **only-visible** — only editors that already show the counterpart file are touched; nothing is
  opened, scrolled or moved.
- **marker-lines** — the `@clause` lines around a code region are not painted, only what is between them.
- **clears** — the highlight goes when the cursor leaves the block, when either file has unsaved
  changes (the lines would be off), and when the counterpart editor closes.
- **theme** — the colour is a standard highlight colour of the theme, none fixed, and the scrollbar
  gets a mark in it, so a counterpart that is out of view can be found.

## Approach
<!-- How it is built, and why that way. Put the reason on a "because:" line under the item. -->
- **from-lens** — it asks the same question as the lenses (which block is under the cursor, which
  regions and clauses belong to it) and takes the lines from the index; it reads no files.
  because: the highlight and the lens then never disagree.
- **test-view** — the lit lines of each file are kept in `state.counterpart` (file → first and last
  line pairs), because VS Code gives no way to read a decoration back.

## Contract
<!-- gives: what others may call. owns: data only this part changes. If another part would break when it changes, it belongs here. needs is optional: sor needs derives it. -->

## Tests
<!-- Name each test after the rule it proves. Lines: do:, expect:, bug: for a fixed bug, proves: for a second test of the same rule, manual: for a check by hand. -->
- **counterpart** — spec beside code: the cursor on the sun item highlights its region in the code
  editor; the cursor in that region highlights the sun item in the spec editor (test/suite.js).
- **all-ids** — a region marked for several clauses highlights each of them (test/suite.js).
- **only-visible** — with only one of the two files open nothing is highlighted, and no editor is
  opened or scrolled (test/suite.js).
- **marker-lines** — the highlighted code starts below the opening marker line and ends above
  `@clause end` (test/suite.js).
- **clears** — the cursor moved out of the block, an unsaved change, or the counterpart closed: the
  highlight is gone (test/suite.js).
- **theme** — the colour and the scrollbar mark look right and stay slight in a light and a dark theme.
  manual: by eye
