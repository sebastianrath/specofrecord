# Project and tool
Why: find the Spec of Record projects, ask the `sor` tool that ships in the extension, and hand the answers to the other parts.

## Rules
- **wake** — it starts when the workspace holds a `sor/SPECOFRECORD.md` (or the older `sor/CLAUSES.md`) at any depth; without one it stays
  asleep.
- **projects** — a project is the folder above `sor/`; up to {max: 20} are found, and
  `node_modules` is skipped.
- **tool-path** — the tool is always `tools/sor.js`, the JavaScript tool that ships inside the extension (next to `src/`).
  A tool in the project or in a folder above it is not used, and there is no setting to point it elsewhere.
- **node** — the tool runs on the editor's own Node (the program of the extension host, started as plain Node), so nothing
  else has to be installed: no Python, and the extension never starts it.
- **from-json** — everything comes from `sor markers --json`, `sor status --json` and `sor parts --json`, run with
  `-C <project>`; exit codes 1 and 2 still count, the JSON is what matters.
- **refresh** — it refreshes on any file saved, created or deleted, when workspace folders
  change, and on "Spec of Record: Refresh"; changes within {burst: 0.4 s} become one refresh, and a new
  request waits for a running one.
- **failures** — a failing project (no tool, bad output, a lock in a format the tool does not read) crashes nothing and stops no
  other project; the last lines go to the "Spec of Record" output and it keeps the data it had.
- **nesting** — a file belongs to the deepest project that contains it; each project has its own
  index and status.

## Approach
- **setting-names** — the settings and commands use the prefix `sor.`, and the language id is `sor-markdown`.
- **version-unchecked** — the answers carry a `version` field the extension does not look at.
- **no-timeout** — the command has no timeout and no popup when it fails, only the log.

## Contract
- gives **index** — every project with its root, index, status and the worst finding per id.
- gives **belongs-to** — which project a file belongs to.
- gives **run** — run another `sor` command in a project and read its JSON.

## Tests
- **wake** — opening the example finds its project (test/suite.js).
- **from-json** — index and status come back from the tool and every lens, hover and gutter
  check works on them (test/suite.js).
- **tool-path** — the command that runs the tool names `tools/sor.js` next to `src/` and nothing from the project, and
  it asks for no Python (test/regions.js).
- **bundled-tool** — the copy that ships in the extension is the repository's `tools/js` (`sor.js` and `sorlib/*.js`) and, run
  away from the repository, answers `sor status --json`, `sor markers --json` and `sor parts --json` (test/bundle.js).
  proves: {tool-path}
- **failures** — a missing tool or bad output gives a line in the Spec of Record output and no crash.
  manual: by eye
- **nesting** — two projects in one workspace keep their own data.
  manual: by eye
- **refresh** — creating a file gives a refresh; creating two in the same moment gives one, and
  deleting them gives one more (test/suite.js).
- **projects** — a `sor/` folder inside `node_modules` is not found; with 22 projects in the
  workspace, 20 are found (test/suite.js).
- **node** — a refresh starts programs, and every one of them is the editor's own Node running `tools/sor.js`: none is
  Python, and every project still loads (test/suite.js).
