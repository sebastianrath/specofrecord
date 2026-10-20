# Project and tool
Why: find the Spec of Record projects and the `sor` tool, ask the tool, and hand the answers to the other
parts.

## Rules
- **wake** — it starts when the workspace holds a `sor/SPECOFRECORD.md` (or the older `sor/CLAUSES.md`) at any depth; without one it stays
  asleep.
- **projects** — a project is the folder above `sor/`; up to {max: 20} are found, and
  `node_modules` is skipped.
- **tool-path** — the tool is `tools/sor.py`, looked for in the project folder
  and every folder above it, in each also under `.claude/skills/specofrecord/` (or the earlier name
  `.claude/skills/spec-of-record/`); the setting `sor.toolPath` wins when set.
- **python** — Python is `sor.pythonPath` when set, otherwise `py -3` on Windows and `python3`
  elsewhere.
- **from-json** — everything comes from `sor markers --json` and `sor status --json`, run with
  `-C <project>`; exit codes 1 and 2 still count, the JSON is what matters.
- **refresh** — it refreshes on any file saved, created or deleted, when workspace folders
  change, and on "Spec of Record: Refresh"; changes within {burst: 0.4 s} become one refresh, and a new
  request waits for a running one.
- **failures** — a failing project (no tool, no Python, bad output) crashes nothing and stops no
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
- **tool-path** — `sor.toolPath` and `sor.pythonPath` win over the defaults.
  manual: by eye
- **failures** — a missing tool or Python gives a line in the Spec of Record output and no crash.
  manual: by eye
- **nesting** — two projects in one workspace keep their own data.
  manual: by eye
- **refresh** — creating a file gives a refresh; creating two in the same moment gives one, and
  deleting them gives one more (test/suite.js).
- **projects** — a `sor/` folder inside `node_modules` is not found; with 22 projects in the
  workspace, 20 are found (test/suite.js).
- **python** — a script set as `sor.pythonPath` is what the tool is run with: it is called with the
  tool's path (test/suite.js, not on Windows).
