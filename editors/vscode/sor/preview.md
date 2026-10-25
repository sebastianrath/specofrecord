# Live preview
Why: spec files read like a formatted note, the way Slack or Obsidian show text while you type,
instead of a wall of `**`, braces and backticks.

## Rules
- **marks-hidden** — in a spec file the formatting marks disappear and their text is shown styled:
  `**name**` bold, `` `code` `` as inline code, `## Heading` as a heading, `{reference}` as a link.
- **code-box** — like Slack, inline code sits in one small box: a thin border, rounded corners, a
  light background and code-coloured text. It stays one box when VS Code colours part of it differently
  (`hello(test)` is not four boxes). A fenced code block (lines between ```) is one shaded block, its ``` lines faint.
- **values** — in `{name: value}` the braces disappear and the name goes faint, so the value
  stands out; hovering it still says what it is.
- **code-lines** — in a `code: path#name` line the word `code:` goes faint and the path looks
  like a link.
- **tables** — table pipes and the `|---|` line go faint.
- **reveal** — like Slack, bold marks stay hidden even while you type on that line. The marks of
  a value, a reference or a heading come back only while the cursor or a selection touches that one
  element; the rest of the line stays formatted.
- **code-closes** — the ticks of inline code are hidden as soon as the pair is there, like the bold marks, wherever the
  cursor is: typing `hello` and the closing tick shows the code box at once, without ticks.
- **code-open** — a pair of ticks with nothing between them and the cursor between them is already a box, with the
  ticks hidden and a few pixels of width for the cursor. That is what VS Code leaves after typing one tick, because it
  adds the closing one itself; Slack and Claude Desktop draw the box at once as well. Once the cursor leaves, an empty
  pair stays as the two ticks typed.
- **display-only** — nothing changes in the file; it is only how the editor draws it.
- **toggle** — `sor.livePreview` is on by default; "Spec of Record: Toggle live preview" flips it.

## Approach
- **element-reveal** — the way Obsidian's live preview and codemirror-rich-markdoc do it:
  each element's marks are hidden unless a selection overlaps that element, not the whole line.
- **text-only** — like the colors, it looks only at the text of the line, not at what the clauses
  mean, so it needs no answer from the tool.
- **decorations** — marks are hidden with editor decorations; nothing is rendered outside the
  editor.
- **zero-size** — a hidden mark is shrunk to nothing, never taken out of the line, so the editor still measures every
  character: a cursor or a selection beside or inside hidden marks is drawn where the text is. Taken out of the line,
  selecting a word that follows hidden marks (a double click on `colors` in `**ui-colors**`) draws neither the selection
  nor the cursor.
- **cursor-place** — a line with hidden marks gets an invisible zero-width piece of text after its end, so the editor
  measures where the cursor goes on the screen instead of counting characters; otherwise it counts the hidden marks
  too and draws the cursor too far right.

## Tests
- **marks-hidden** — in bodies.md the `**` around `sun` are hidden and `sun` is bold, and the
  backticks of inline code are hidden (test/suite.js).
- **reveal** — with the cursor on the sun line the `**` around `sun` stay hidden; with the cursor
  inside `{size: 28}` its braces show while the rest of the line stays formatted (test/suite.js).
- **toggle** — turning live preview off removes every hidden mark, on brings them back
  (test/suite.js).
- **values** — a `{name: value}` shows the value, the name faint, the braces gone (test/suite.js).
- **code-box** — inline code shows as a framed box, and a fenced block as one shaded block. For `hello(test)` the
  whole word has the top and bottom lines, the left line is on `h` only and the right line on the last `)` only
  (test/suite.js); drawn, it is one box with no frame inside it.
  manual: by eye
- **display-only** — the file on disk is the same with live preview on and off.
  manual: by eye
- **tables** — the planets table reads cleanly, pipes faint.
  manual: by eye
- **code-lines** — `code: out/index.html#positions` shows faint `code:` and a link-coloured path.
  manual: by eye
- **code-closes** — in `abc `test` ok` both ticks are hidden with the cursor right after the closing tick, and also with
  the cursor between the ticks (test/suite.js).
- **code-open** — typing one tick (VS Code adds the second) shows a small framed box with the cursor inside it and no ticks;
  moving away leaves the two ticks as typed (test/suite.js).
- **zero-size** — double-clicking `colors` in `- **ui-colors** — x` draws the selection over `colors`, and the cursor shows.
  manual: by eye
- **cursor-place** — with the cursor after the last `k` of `abc `test` ok`, it is drawn right after the `k`.
  manual: by eye
