# Working in this repository

This repository is Spec of Record itself: the tool (`tools/`), the format (`SPEC.md`), the Claude Code plugin
(`plugins/specofrecord/`) and two projects built with it (`examples/solar-system`, `editors/vscode`).

## The workflow is written once, in the plugin's skill
How to work in a project with a `sor/` folder (change the clause first, claim, test, lock, release) is in the
skill below. It is imported here so it is always in context; the reference files it links are read when a task needs them. Change the workflow there and nowhere else; `AGENTS.md`
only adds what agents other than Claude Code need.

@plugins/specofrecord/skills/specofrecord/SKILL.md

In this repository:
- `sor` means `python3 tools/py/sor.py -C <project>`, where a project is a folder holding `sor/`, for example
  `examples/solar-system`. Ignore the skill's `${CLAUDE_SKILL_DIR}` fallback. The edit guard is wired in
  `.claude/settings.json`, not through the plugin.
- The `reference/...` paths in the skill are under `plugins/specofrecord/skills/specofrecord/`.
- `SPEC.md` is the full format. The skill's `reference/format-cheatsheet.md` is its short form, generated from it.

## Developing the tool itself
- The tool is in two folders that mirror each other. `tools/py` is the Python tool that agents run (`sor.py`, `sorlib/`, its tests and the coverage
  script) and `tools/js` is the JavaScript copy of its reading half that the extension runs (`sor.js`, `sorlib/`, `test/`).
- `sh tools/py/coverage.sh` runs those tests under coverage and prints it per file with the lines no test reaches, the programs
  the tests start included. The first run creates `.venv-coverage` (git ignores it) and needs the network once for `pip`;
  the tool itself stays standard-library only. `.coveragerc` holds the settings; "Cover" counts lines and branches together.
- The tests are `python3 -m unittest discover -s tools/py -p 'test_*.py'`. They need no browser and touch only temporary
  folders; the two real projects are only read.
- `tools/py/test_sor_docs.py` checks the documents against the code: a command, flag, number or name that a document gets wrong
  fails there, and the message names the document. The limits of the format are written only in SPEC §13 and the cheat sheet;
  point to them, do not repeat the numbers.
- The plugin carries its own copy of `tools/py` and of the cheat sheet, without the `py` level (`sor.py` and `sorlib/` sit directly in its `tools/`). The VS Code extension carries the
  JavaScript tool, `tools/js` (`editors/vscode/tools`), and always runs that one, never Python. After you change `tools/py`, `tools/js` or the cheat sheet in `SPEC.md`, run
  `sh plugins/sync-tools.sh`; `sh plugins/sync-tools.sh --check` fails when a copy is out of date.
- `tools/js/` is the JavaScript copy of how the tool reads a project (`markers --json`, `status --json`, `parts --json`) and of the hashing, marker
  and lock text rules (`node tools/js/test/vectors.js` runs it against the vectors, and `tools/py/test_sor_js.py` in the normal test run compares it
  with the Python tool on a project in many states). A change in `tools/py/sorlib/` to how a project is read, or to what those commands print, goes
  into `tools/js/sorlib/` in the same change; a change to the hashing, marker or lock rules also goes into `vectors/hashing.json` through
  `python3 vectors/make_hashing.py`. After a change to how the Python tool reads a project, run the whole suite once with `SOR_COMPARE_JS=1`
  (about twelve minutes): it compares the two tools on every state the tests build.
- Do not run `lock` or `claim` against `examples/` or `editors/vscode` to try the tool out: use a temporary
  folder.
