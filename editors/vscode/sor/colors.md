# Colors
Why: give spec files a few extra colors so their structure shows at a glance, in any theme.

## Rules
- **kinds** — headers, section headings, bold item names, gives/owns/needs, {references}, test
  and approach keywords, comparison signs and words, `remember` and probe calls each get a
  color of their own; in `{name: value unit}` name, value and unit are colored apart.
- **plain-words** — the plain format gets the same colors: headings read by meaning (Rules,
  Notes, How it works, Checks, …), the settings Run and Code, offers/uses/stores, the test words
  given, when, then, should, shows, by eye, by hand, sign-off and fixes, and `code:` lines.
- **theme** — only standard scopes, no fixed color, so every theme paints them its own way.
- **only-spec-files** — only Markdown files under a `sor/` folder get them.
- **text-unchanged** — coloring never changes the text of a file.

## Approach
- **grammar** — the colors come from `syntaxes/sor.tmLanguage.json`: Markdown plus a few
  patterns, slight on purpose.
- **limits** — keywords are colored only on an indented line, and a probe call needs a "("
  right after its name.

## Tests
- **kinds** — each kind gets its scope on a sample spec file, and a plain sentence gets none
  (test/grammar.js).
- **plain-words** — each plain-format word gets the scope of the word it stands for
  (test/grammar.js).
- **only-spec-files** — a file in `sor/` opens in the Spec of Record language (test/suite.js).
- **theme** — the colors look right and stay slight in a light and a dark theme.
  manual: by eye
- **text-unchanged** — a spec file opened with colors and the live preview on, and walked through
  with the cursor, is not edited, and its file on disk is the same bytes (test/suite.js).
