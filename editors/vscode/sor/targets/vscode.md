# VS Code
Why: where the extension runs, and how its code is delivered and tested.

## Rules
- **code** — the extension's own code is one file, {path: src/extension.js}; the `sor` tool it ships is that
  tool's code, not the extension's.
- **runtime** — plain JavaScript on Node in VS Code 1.80 or newer; no build step, no network; the
  only program it starts is the `sor` tool, which is JavaScript too, so no Python is needed.
- **files-only** — it runs for files on disk (the `file:` scheme), also over Remote (WSL, SSH).
- **package** — it packages as one `.vsix` (`npm run package`) that installs on its own, with a copy of the `sor`
  tool inside (`tools/`, made from the repository's `tools/js` by `plugins/sync-tools.sh`, never edited by hand).
- **paths-case** — paths are compared without case, so Windows paths match.

## Approach
- **markers** — JavaScript `// @clause …`; `package.json`, the grammar and the tests are not marked.
- **notes** — the builder's notes, and the choices the clauses left open, go in the comment at the top
  of `extension.js`.
- **test-run** — `npm test` runs `test/grammar.js`, `test/bundle.js` and `test/regions.js` (the code of a
  few clauses, run alone without VS Code), then a real VS Code with `@vscode/test-electron` on
  `examples/solar-system`, running `test/suite.js`.

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
- **code** — the extension's own code is one file: `src/extension.js` is the only file under `src/` in the package,
  and the only other code in it is the `sor` tool in `tools/`.
  manual: by eye
- **runtime** — no build step, no network, the only program it starts is `sor`, and it runs on VS Code 1.80.
  manual: by eye
- **paths-case** — a project opened with its path in the other letter case (`c:\` for `C:\`) still shows lenses and marks.
  manual: by eye
