# Spec of Record

A development philosophy and toolchain for AI-built software. The specs are the source code, and an AI agent acts like a
compiler. A project's specification is a folder of Markdown files (`sor/`) made of **clauses**: a rule, a number or a
table row, each with a name that code and tests point at. Every line of code sits in a `// @clause <id>` region that
names the clause it was built from, so spec and code trace to each other in both directions, for people and for tools.

This is a draft proposal (version 0.1) by [Sebastian Rath](https://sebastianrath.io). The page that explains it is
[index.html](index.html).

## What is in this repository

| Folder or file | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | The format: files and hierarchy, the four sections of a part (Rules, Approach, Contract, Tests), items and ids, values and references, targets, code markers, the lock file, what a tool enforces and how agents work in parallel. It starts with a cheat sheet. |
| [`tools/`](tools) | The `sor` command: `tools/sor.py` and the library behind it (`tools/sorlib/`). Python 3, standard library only, with its own tests (`tools/test_sor*.py`) and a coverage script (`tools/coverage.sh`). |
| [`plugins/specofrecord/`](plugins/specofrecord) | The Claude Code plugin: the workflow skill, the edit-guard hooks and a copy of `tools/`. See its [README](plugins/specofrecord/README.md). |
| [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) | Lets the repository itself be added as a plugin marketplace. |
| [`examples/solar-system/`](examples/solar-system) | A complete project built with it: planets orbit, you click one for a fun fact. Specs in `sor/`, the built page in `out/`, design tokens in `design/`. |
| [`editors/vscode/`](editors/vscode) | A VS Code extension that shows, inside the editor, which code comes from which clause and whether they still agree. See its [README](editors/vscode/README.md). |
| [`comparisons/`](comparisons) | The same solar-system project written for other spec-driven tools (BMad Method, CodeSpeak, Kiro, nima, OpenSpec, Spec Kit, SpecLock, Tessl), each with notes on the differences. |
| [`DECISIONS.md`](DECISIONS.md) | The design decisions behind the format, and the alternatives that were dropped. |
| [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md) | How a coding agent works in a project with a `sor/` folder. `CLAUDE.md` imports the plugin's skill, so the workflow is written once. |
| [`index.html`](index.html), [`social/`](social) | The project page and its banner image. |

## The `sor` command

```bash
python3 tools/sor.py -C examples/solar-system parts
```

Run it from a project folder (the one holding `sor/`), or pass `-C <folder>`. With the plugin enabled in Claude Code it is
on the PATH as plain `sor`.

| Command | What it does |
|---|---|
| `sor parts` | An index of every part: why it exists, its size, its open questions. |
| `sor show <part or id>` | A part's clauses with their code underneath. |
| `sor markers <id or file:line>` | Where a clause's code is, or which clauses a line of code serves. |
| `sor needs [part]` | What a part uses from other parts. |
| `sor status` | What changed since the last lock: code to rebuild, clauses to review, drift, claims. |
| `sor changes` | The pending changes in words. |
| `sor check` | Every problem in the spec files and the code markers. |
| `sor test` | Runs the clauses' tests (headless Chrome for web projects). |
| `sor new <part>` | Writes a skeleton part to fill in. |
| `sor claim` / `sor release` | Say which clauses you are working on, so several agents can work at once. |
| `sor lock` | Saves the agreed state: clauses, their code and their test results, in `sor/sor-lock.json`. |

`sor --help` lists the rest and the exit codes.

## Use it with Claude Code

```text
/plugin marketplace add sebastianrath/specofrecord
/plugin install specofrecord@specofrecord
```

Then, in an empty folder, tell Claude Code what to build and to follow Spec of Record. It writes the first specs, and from
then on a change starts at the clause: the edit guard refuses code edits whose clause did not change. Requirements and
other ways to load the plugin are in the [plugin README](plugins/specofrecord/README.md).

## Working on this repository

- The tests: `python3 -m unittest discover -s tools -p 'test_*.py'`. They need no browser and touch only temporary
  folders.
- `sh tools/coverage.sh` runs them under coverage.
- The plugin carries its own copy of `tools/` and of the cheat sheet. After changing `tools/` or the cheat sheet in
  `SPEC.md`, run `sh plugins/sync-tools.sh` (`--check` fails when the copy is out of date).
- Do not run `sor lock` or `sor claim` against `examples/` or `editors/vscode` to try the tool out: use a temporary
  folder.

## License

This draft (the specification and the documents) is licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The tools are published under the
[MIT License](https://opensource.org/license/mit).
