# Spec of Record (SoR)

A development philosophy and toolchain for AI-built software. Plain-language specs are the source code, and an AI agent
acts like a compiler. The spec is split into parts with responsibilities, so engineering, QA and UX can each focus on
their own area of expertise while the whole team works from one source. You can jump from any part of the spec to its
code, and back. The AI changes the spec first, then the code. If you change the code yourself, it updates the spec to
match.

Version 0.1, a draft proposal by [Sebastian Rath](https://sebastianrath.io). The goal, an example, how to install it, the
tools and the questions people ask are on the [project page](https://specofrecord.org). This README only says what is in
this repository.

## What is in this repository

| Folder or file | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | The format: files and hierarchy, the four sections of a part (Rules, Approach, Contract, Tests), items and ids, values and references, targets, code markers, the lock file (`sor-lock.json`), what a tool enforces and how agents work in parallel. It starts with a cheat sheet. |
| [`tools/`](tools) | The `sor` command: `tools/sor.py` and the library behind it (`tools/sorlib/`), with its own tests and a coverage script. `python3 tools/sor.py --help` lists what it does. |
| [`plugins/specofrecord/`](plugins/specofrecord) | The Claude Code plugin: the workflow skill, the edit guard and a copy of `tools/`. Its [README](plugins/specofrecord/README.md) has the requirements. |
| [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) | Lets the repository itself be added as a plugin marketplace. |
| [`examples/solar-system/`](examples/solar-system) | A complete project built with it: planets orbit, you click one for a fun fact. Specs in `sor/`, the built page in `out/`. A good place to read real clauses next to their code. |
| [`editors/vscode/`](editors/vscode) | The VS Code extension: shows, inside the editor, which code comes from which clause and whether they still agree. |
| [`comparisons/`](comparisons) | The same solar-system project written for other spec-driven tools (BMad Method, CodeSpeak, Kiro, nima, OpenSpec, Spec Kit, SpecLock, Tessl), each with notes on the differences. |
| [`DECISIONS.md`](DECISIONS.md) | The design decisions behind the format, and the alternatives that were dropped. |
| [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md) | How a coding agent works in a project with a `sor/` folder. `CLAUDE.md` imports the plugin's skill, so the workflow is written once. |
| [`index.html`](index.html), [`social/`](social) | The project page and its banner. |

## Working on this repository

- The tests: `python3 -m unittest discover -s tools -p 'test_*.py'`. They need no browser and touch only temporary
  folders.
- `sh tools/coverage.sh` runs them under coverage.
- The plugin carries its own copy of `tools/` and of the cheat sheet. After changing `tools/` or the cheat sheet in
  `SPEC.md`, run `sh plugins/sync-tools.sh` (`--check` fails when the copy is out of date).
- Do not run `sor lock` or `sor claim` against `examples/` or `editors/vscode` to try the tool out: use a temporary
  folder.

## License

The spec itself, this draft, is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). You may share and
adapt it, including commercially, if you credit the author, link the license and say what you changed.

The toolset (the `sor` command in [`tools/`](tools), the [plugin](plugins/specofrecord) and the
[VS Code extension](editors/vscode)) is published under the [MIT License](https://opensource.org/license/mit). Each of
the three folders carries its own `LICENSE` file.
