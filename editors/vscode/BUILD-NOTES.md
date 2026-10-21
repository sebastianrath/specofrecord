# Build notes: where the facts were unclear

Built from editors/vscode/fact-human/*.md, test/, the `fact` tool JSON and the svg assets only.
Both checks pass: `node test/grammar.js` (34 scope checks) and `node test/run.js <clean copy>/examples/solar-system <Code.exe>`
(all 9 suite checks; 10 of 10 runs in a row after the fixes below, 3 of 10 failed before).
`npx vsce package` works offline (13 KB, 10 files). The test runner got VS Code by path argument
(the installed Code.exe), because editors/vscode/.vscode-test holds no cached VS Code.

1. **What the index calls a marker line.** marker-lines says the lines "come from the index", but the index
   has regions, not marker lines. Found by reading the JSON: for kind `code`/`glue` the region `start` and `end`
   are the opener and `@clause end` lines themselves. I take both lines of each non-`line` region and keep them only
   if the text is an own-line comment (`//`, `#`, `--`, `;`, `/*`, `<!--` followed by `@clause`, or the old `@fact`). The comment list is my guess;
   the test only needs `//` and `<!--`. This means the extension looks at line text, a small step beyond "reads no markers itself".
2. **Which lines the hiding spares.** The rules say a fold opens when the cursor touches "the marker or the line above".
   The test (hidden lines must equal all marker lines outside the selection) fails when the cursor sits on the line above
   and I also spare the marker. So the hiding spares only a marker the selection is on. Folds still open for the line above;
   then the opened marker is a blank row, not text. (Visibility checks pass because the row is in view.)
3. **"Only about half can fold" vs. how to decide.** The fact names the reason ("line before closes another fold") but not the
   rule. I ask `vscode.executeFoldingRangeProvider` for the other providers' ranges (my provider answers `[]` meanwhile),
   and skip a marker run when line N-1 is the start or the end of another range, or when ranges overlap partially. Result on
   the example: 30 folds, 30 skipped, as the fact says.
0. **The integration test needs an unlocked screen and a window that can take focus.** On a locked macOS session (`ioreg -n Root -d1` says
   `IOConsoleLocked = Yes`) no window gets focus, `vscode.window.state.focused` is false, and VS Code's own `editor.foldAll` leaves
   `visibleRanges` unchanged, so the folding check fails with the plan intact (31 folds, 31 not foldable). On 2026-10-19 it failed in every run
   after the screen was locked at 17:57 and had passed before; with the older tool, the older layout and the older extension it failed the same
   way. `test/run.js` now stops with a message when the screen is locked, and the folding assertion says when the window had no focus.
   This is also the likelier reading of the "flaky" runs recorded in item 4 than the HTML server.
4. **Indentation fallback.** "Where no other folding provider exists, add indentation folds": I decide "none exists" by the
   other providers returning no ranges. The built-in HTML server sometimes answers empty while it starts, which gave
   different fold plans and flaky tests, so for server languages (html, js, ts, css, json, xml, markdown) I ask up to 6 times,
   400 ms apart. With hiding off I return no ranges at all (no fallback then). Not stated in the facts.
5. **Applying folds ("applied again shortly after").** No timing given. I run `editor.foldAllMarkerRegions` at 150, 600,
   1100, 1700, 2500 ms after a plan or a change, but only if some fold in view is still open (visibleRanges). I remember the
   selection before folding, unfold folds the cursor touches, and put the selection back, because VS Code moves a cursor
   out of folded lines. Turning hiding off runs `editor.unfoldAllMarkerRegions` now and once more after 500 ms.
6. **Fold plan cache.** "Once per document version": I also key it by the marker line list, so a refresh does not recompute it
   (recomputing on each refresh made the plan, and the tests, wobble).
7. **Contradiction between "line numbers skip" and the test's skipped list.** `plan.skipped` holds 0-based marker lines;
   the test accepts `l===0` as undecorated. I decorate all markers (including line 1 and folded ones), because the first
   assertion wants exactly all marker lines. No conflict in the end, but the shape of `state.folds` (`fold` as `{start,end}`
   0-based, `skipped` 0-based, `state.markerLines` 1-based `lines`) is only in suite.js, not in the facts.
8. **State shape for tests.** vscode.md names `state` (projects, marks, markerLines, folds) and `refresh()`, nothing more.
   I use: `projects[i] = {root, factDir, index, status, worst, ...}`, `marks: Map(lowercased fsPath -> {drift, review, recompile}` of
   1-based line arrays`)`, all from reading suite.js. A file with regions but no findings gets empty arrays.
9. **Hiding as "blank row".** How to hide is not said. I use a decoration with `opacity: 0` on the line.
10. **Lens wording.** "ends with a flag": I join with one space (`out/index.html:26-28 ● to review`). Part headings with no
    code get the title `no code` and a click does nothing. Flag for a fact lens uses the item's own id only ("strongest state
    among a row's ids" is unclear for a single row; I took the one id). Marker lenses show the raw status word, as the known limit says.
11. **Severity order and words.** Gutter "worst wins: drift, review, recompile" is clear; the lens flag words (`to review`)
    and the hover words (`to review`, `to recompile`, `in sync`) are one set in my build. Status words not in the lists
    (anything but drift/stale/shared/new/changed/removed) count as in sync.
12. **Status bar counts.** "counts findings": I count each finding of `status --json` once by class, over all projects,
    including findings that have no code or item. Always shown when a project exists, even at 0.
13. **Hover details.** Fact id link opens the fact via the command `fact.openFact` (a name I chose). A region of kind `glue`
    gives no hover. Text is cut to 6 lines and shown in a markdown code block. Reference hover (`names no item or value`)
    is added for fact files too, since the references fact asks for it.
14. **Reference hit area.** "From the first to the last character of a reference": the index has `col` at the first
    character after `{` and `end` exclusive. I accept `col-1 .. end` (the braces included).
15. **Fact-file detection.** "Under `fact/`": I use the project's `factDir` from the index and `.md`. `fact-human/` is not
    covered, as the known gaps say. Language `fact-markdown` is given by `filenamePatterns: **/fact/**/*.md`; that was enough,
    no `files.associations` default needed.
16. **Grammar structure.** "Markdown plus a few patterns": I use an injection (`L:text.html.markdown.fact`) so my rules also
    work inside Markdown's own list/paragraph rules. The item head rule consumes the list marker with the bold name, so Markdown's
    list scope is lost on those lines. `is`, operators, `remember` and probe calls are only colored on indented test lines
    (known limit says so for keywords; for these words I chose the same to avoid coloring every "is" in prose). A probe call
    is any `name(`. `{name: = other}` is one rule: the `=` is a comparison sign, `other` a reference. `Source` as a header, and
    the standard-only scopes: `markup.inline.raw.fact` for backticks (the test wants prefix `markup.inline.raw`).
17. **Project discovery.** `findFiles('**/fact/FACT.md', '**/node_modules/**', 20)`; project = folder above `fact/`. A
    project is dropped when FACT.md goes away. The file watcher ignores `__pycache__` (the tool's first run writes there and
    would trigger a second refresh); the fact says it watches everything.
18. **No timeout, no popups**: as the known limits say. `activate()` waits for the first refresh, so the test finds data at once.
19. **"Run another fact command"** (project contract): the internal `runFact` is used by the hover only; not exported on the api.
20. **vsce**: needs `--allow-missing-repository --skip-license` flags offline-quiet; I put a placeholder repository URL in
    package.json (`example.invalid`) — change it. No icon, no LICENSE file.
21. **Not run**: the "by eye" tests (two projects, toolPath/pythonPath, missing tool, Remote, `#region` file, indentation strategy).
    Gutter marks with real findings were checked on the live tree (recompile marks on lines 96-104 and 111-119 of index.html);
    the suite's optional `FACT_EXPECT_REVIEW` check (review mark on scene.md) does not apply to the live tree's current status
    (there the review findings are on bodies/needs, calm, journey, parts, controls/needs), so it was not satisfied.
22. **Highlight (0.9.6), where the spec was silent.**
    - *Colour:* `editor.rangeHighlightBackground` was almost invisible in Default Dark Modern (about 4% white), so the code uses
      `editor.selectionHighlightBackground` (and its overview-ruler colour). It is the colour VS Code gives other occurrences of
      selected text; both are theme colours, none fixed. Looked at in Default Dark Modern and Default Light Modern.
    - *Which regions lose their first and last line:* kinds `code` and `test`, whose index `start` and `end` are the marker lines
      themselves (item 1). `line` (a marker at the end of a code line) and `anchor` (a `code:` function) are lit whole.
    - *Which editor leads:* the editor whose cursor moved last (an editor made active counts as a cursor that moved), not
      `activeTextEditor`. In normal use they are the same. In the test window `window.state.focused` was false, and then
      `activeTextEditor` stayed on the code editor after `showTextDocument` and even after `focusFirstEditorGroup` on the
      spec's group, while the tab groups already said the spec was active; the Mars-row check failed 3 runs out of 3 for this
      reason. Following the cursor event fixed it, and is also how a person experiences it. (A guess, not checked: the person's
      own VS Code was open during these runs, and `keepInFront` in `test/run.js` targets the process name "Code".)
    - *Unsaved changes* on either side clear the highlight (the index lines would be off); a save is followed by the refresh,
      which lights it again. A file shown in two panes lights only the pane that does not hold the cursor.
    - *What tests read:* `state.counterpart` is rebuilt from what was drawn into each visible editor, not from what was meant to be
      drawn, so a decoration that stayed on screen shows up in the test.
    - *Tests set a cursor through the editor `showTextDocument` returns*, and the highlight follows that cursor event, so no
      step of the suite needs the window to take focus for the highlight (the rest of the suite still does, see item 0).
    - *Not built:* scrolling the counterpart into view; the scrollbar mark is the only hint for a counterpart out of view.
23. **Seven more automatic checks, three by-eye rules.** Added to `test/suite.js` for `project/refresh`, `project/projects`,
    `project/python`, `state/status-bar`, `marker-lines/which`, `references/tool-resolves` and `colors/text-unchanged`; each
    was broken on purpose to see its check fail. Two were too weak at first and were made stronger: the status-bar check never
    produced a "review" count (it now changes a value that tests refer to), and the marker-lines mutant was guarded twice in the
    code (`MARKER_RE` and the `line` skip), so it only fails when both are removed.
    - *Test hook:* `state.statusBarText` (a status bar item cannot be read back); the region `state` now carries `state/status-bar`.
    - *Cap mismatch:* `discover()` calls `findFiles(…, 20)` once for each root-file name, so with both `SPECOFRECORD.md` and the older
      `CLAUSES.md` present up to 40 projects are found, and `project/projects` says "up to 20". The check covers the current name
      only (22 projects, 20 found).
    - *A deviation fixed:* the completion words compared `doc.uri.fsPath === it.path` without `norm`, against `paths-case`. It was
      fixed clause first (the Approach item `references/complete-words` now says so). No automatic check can reach it on macOS,
      because VS Code gives a document the real letter case of its path (tried: the check passed without the fix), so
      `paths-case` is a by-eye test on Windows.
    - *Refresh check:* it waits until no refresh has fired for 2.5 s before counting, because a refresh already running turns one
      burst into two.
    - **By-eye steps** (from the repository root; I ran each one and saw the result written here):
      - `targets/vscode/test:code`: `ls editors/vscode/src` shows only `extension.js`; `unzip -l editors/vscode/sor-vscode-0.9.7.vsix
        | grep extension/src/` shows exactly one line.
      - `targets/vscode/test:runtime`: `grep -n '"engines"' -A1 editors/vscode/package.json` shows `"vscode": "^1.80.0"` and
        `"main"` is `./src/extension.js`; the `scripts` in `package.json` are only `test` and `package` (no build);
        `grep -nE "require\('(https?|net|tls|dgram|dns)'\)|fetch\(|XMLHttpRequest|WebSocket|https?://" editors/vscode/src/extension.js`
        prints nothing; `grep -nE "child_process|\bcp\.|spawn|execSync|execFile" editors/vscode/src/extension.js` prints two lines, the
        `require('child_process')` and the `cp.execFile` that runs `sor`. The version claim itself needs a VS Code 1.80 to install the
        `.vsix` in; without one these checks are what can be done.
      - `targets/vscode/test:paths-case`: `grep -n "toLowerCase" editors/vscode/src/extension.js` shows one line, the `norm` helper;
        `grep -nE "(fsPath|\.path|\.root)\s*(===|!==)" editors/vscode/src/extension.js` prints nothing. The real check needs Windows:
        open the project from a path whose drive letter has the other case (`c:\…` for `C:\…`), open `sor/bodies.md`, and the lenses
        and gutter marks still show.
24. **Code regions of `lenses`, `marker-lines` and `preview` split by what each block serves.** Only `@clause` lines and blank lines
    changed in `src/extension.js` (checked: the diff without them is empty); every edit went through the edit guard.
    - `lenses`: the helpers and the cursor block (`lenses/cursor-only`, with `marker-lens` for `wordOf`/`locOf` and `show-all` for
      `regionsFor`), the provider (`clause-lens`, `flags`, `marker-lens`, `show-all`, `line-marker`, `folded`), and `openAt`/`showCode`
      (`jump`).
    - `marker-lines`: finding and hiding the lines (`which`, `setting`); the fold plan (`fold`, `blank-rows`, `own-regions`,
      `fallback-folds`); the cursor and the toggle (`cursor-opens`, `cursor-kept`, `toggle-off`, `setting`).
    - `preview`: the styles (`pv`, `previewOn`) against the ranges (`previewRanges`, `applyPreview`). Most preview rules appear in both
      halves, so the gain there is small. `preview/display-only` has no code: it promises what the code never does, like
      `show-only` and `out-of-scope`.
    - 18 of the 48 rules that had no code region now have one; 30 remain, in `project`, `state`, `references`, `colors` and
      `targets`, and three promises that cannot have code.
25. **The `sor` tool ships inside the extension.** `project/tool-path` now ends in a fallback: when the folder walk finds no
    `tools/sor.py` (and `sor.toolPath` is empty), `findTool` returns `tools/sor.py` next to `src/`, found through `__dirname`. An
    install of the `.vsix` alone then works with nothing but Python 3.9 or newer.
    - *Order:* the setting and any tool found in or above the project still win, because a project's own tool matches the version of
      its own spec. The bundled copy is the last resort.
    - *The copy:* `tools/` holds `sor.py` and `sorlib/*.py` only, copied from the repository's `tools/` by `sh plugins/sync-tools.sh`
      (the script that also feeds the plugin; `--check` covers both). It is committed, so packaging stays `vsce package` with no
      build step and `package.json` keeps only the scripts `test` and `package`. Never edit it by hand.
    - *Tests:* `test/bundle.js` (added to `npm test`) checks that the copy equals `tools/` and, run on a copy of the example with no
      tool above it, answers `status --json` and `markers --json`. `project/test:tool-fallback` is by eye.
    - *Spec wording that had to move:* `targets/vscode/code` said `src/extension.js` is "the only code file in the package"; it now
      says the extension's own code is one file and the only other code in the package is the bundled tool. The `project` part's Why
      names the bundled copy, because its code region serves the part.
    - *Region:* `findTool` has its own region, `project/tool-path`; the rest of the part keeps `project project/wake`.
    - *Packaging:* the CI workflow runs `vsce package --no-dependencies` (the extension has no runtime dependencies; vsce's dependency
      scan broke on npm 11 and gave an empty file list) and checks the package for `tools/sor.py` and for no `test/`, `sor/` or
      `node_modules/`.
    - *Python:* not bundled. `python3` (`py -3` on Windows) or `sor.pythonPath`, 3.9 or newer, as before.
