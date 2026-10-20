# VS Code
Why: where the extension runs, and how its code is delivered and tested.

## Rules
- **code** — the extension's code is one file, {path: src/extension.js}.
- **runtime** — plain JavaScript on Node in VS Code 1.80 or newer; no build step, no network; the
  only program it starts is the `sor` tool.
- **files-only** — it runs for files on disk (the `file:` scheme), also over Remote (WSL, SSH).
- **package** — it packages as one `.vsix` (`npm run package`) that installs on its own.
- **paths-case** — paths are compared without case, so Windows paths match.

## Approach
- **markers** — JavaScript `// @clause …`; `package.json`, the grammar and the tests are not marked.
- **notes** — the builder's notes go in the comment at the top of `extension.js` and in
  `BUILD-NOTES.md`.
- **test-run** — `npm test` runs `test/grammar.js`, then a real VS Code with
  `@vscode/test-electron` on `examples/solar-system`, running `test/suite.js`.

## Contract
- gives **api** — `activate()` returns `state` (projects, marks, marker lines and fold plans per
  file) and `refresh()`, so tests can read what is shown.

## Tests
- **test-run** — the integration run starts, finds the example project and passes every check of
  the other parts (test/suite.js).
- **package** — the vsix installs in a clean VS Code and starts.
  manual: by eye
- **files-only** — it works over Remote (WSL, SSH).
  manual: by eye
- **code** — the extension's code is one file: `src/extension.js` is the only code file in the package.
  manual: by eye
- **runtime** — no build step, no network, the only program it starts is `sor`, and it runs on VS Code 1.80.
  manual: by eye
- **paths-case** — a project opened with its path in the other letter case (`c:\` for `C:\`) still shows lenses and marks.
  manual: by eye
