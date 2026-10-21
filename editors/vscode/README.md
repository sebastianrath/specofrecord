# Spec of Record for VS Code

Shows, inside the editor, which code comes from which clause, and whether they still agree.

- Lenses above clauses (`out/index.html:26-28`, with a flag when something needs attention) and above `@clause` lines in code.
- Hover on generated code shows the clauses behind the line and their state.
- Gutter marks: red drift, amber review, blue recompile. Status bar counts them.
- Ctrl+click on a `{reference}` in a spec file jumps to what it names.
- With a spec file and its code side by side, the block under the cursor lights up its counterpart in the other editor (a clause lights its code, code lights its clauses). Nothing scrolls or opens by itself.
- `@clause` comment lines are hidden (display only, the files never change). "Spec of Record: Toggle marker lines" flips it.
- Syntax colors for files under `sor/`.

Everything comes from the `sor` tool. The extension uses `tools/sor.py` from the project or a folder above it when there is one, and otherwise the copy it ships with, so it works with nothing else installed except Python 3.9 or newer (`python3`, or `py -3` on Windows). Settings: `sor.pythonPath`, `sor.toolPath`, `sor.hideMarkerLines`, `sor.livePreview`.
It starts only when the workspace holds a `sor/SPECOFRECORD.md` (or the older `sor/CLAUSES.md`). It never edits a spec or code file.

Test: `npm test` (grammar test, a check of the bundled tool, then a real VS Code on `examples/solar-system`). The bundled copy in `tools/` is made from the repository's `tools/` by `sh plugins/sync-tools.sh`; never edit it by hand.
