# Spec of Record (SoR)

Spec of Record is a development philosophy and toolchain for AI-built software, aimed at mid-sized to large projects. It turns the spec into a centralized design document that always stays in sync with the code, so a team of different specialties can understand, review and change the software together. You write what your software should do in plain language, an AI agent turns it into code, and each piece of code stays linked to the statements in the spec and to its test results.

The spec is split into parts, so engineering, QA and UX can each work in their own field of expertise while sharing a common design document. You can change either side, the spec or the code, and the other one is updated to match.

To learn how this works, start at [specofrecord.org](https://specofrecord.org). It covers the goal, an example, how to install it,
the tools and the questions people ask. This README only says what is in this repository.

## What is in this repository

| Folder or file | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | The format. It covers files and hierarchy, the four sections of a part (Rules, Approach, Contract, Tests), items and ids, values and references, targets, code markers, the lock file (`sor-lock.json`), what a tool enforces and how agents work in parallel. It starts with a cheat sheet. |
| [`tools/`](tools) | The `sor` command. That is `tools/sor.py` and the library behind it (`tools/sorlib/`), with its own tests and a coverage script. `python3 tools/sor.py --help` lists what it does. `tools/js/` is a JavaScript copy of the commands an editor needs (`markers`, `status` and `parts` as JSON), which the VS Code extension runs so that it needs no Python. |
| [`plugins/specofrecord/`](plugins/specofrecord) | The Claude Code plugin, with the workflow skill, the edit guard and a copy of `tools/`. Its [README](plugins/specofrecord/README.md) has the requirements. |
| [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) | Lets the repository itself be added as a plugin marketplace. |
| [`examples/solar-system/`](examples/solar-system) | A complete project built with it, where planets orbit and you click one for a fun fact. Specs in `sor/`, the built page in `out/`. A good place to read real clauses next to their code. |
| [`editors/vscode/`](editors/vscode) | The VS Code extension. It shows, inside the editor, which code comes from which clause and whether they still agree. It ships a copy of `tools/` to fall back on when a project has none. |
| [`.github/workflows/`](.github/workflows) | The builds. One makes the plugin zip, with `tools/` bundled, and the other makes the extension's `.vsix`. |
| [`comparisons/`](comparisons) | The same solar-system project written for other spec-driven tools (BMad Method, CodeSpeak, Kiro, nima, OpenSpec, Spec Kit, SpecLock, Tessl), each with notes on the differences. |
| [`DECISIONS.md`](DECISIONS.md) | The design decisions behind the format, and the alternatives that were dropped. |
| [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md) | How a coding agent works in a project with a `sor/` folder. `CLAUDE.md` imports the plugin's skill, so the workflow is written once. |
| [`index.html`](index.html), [`social/`](social) | The project page and its banner. |

## Working on this repository

- Run the tests with `python3 -m unittest discover -s tools -p 'test_*.py'`. They need no browser and touch only temporary
  folders.
- `sh tools/coverage.sh` runs them under coverage.
- With `node` installed (16 or later) the same run also checks the JavaScript copy in `tools/js/` against the Python tool. Without it that test is skipped and says so.
- The plugin carries its own copy of `tools/` and of the cheat sheet, and the VS Code extension carries the JavaScript tool, `tools/js`.
  After changing `tools/` or the cheat sheet in `SPEC.md`, run `sh plugins/sync-tools.sh` (`--check` fails when a copy is
  out of date).
- To release, push a tag. `plugin-v<version>` builds the plugin zip with `plugins/build-plugin.py` and `vscode-v<version>`
  builds the `.vsix`. Each build attaches its file to a GitHub release, and the tag must match the version in
  `plugins/specofrecord/.claude-plugin/plugin.json` or `editors/vscode/package.json`. Each file also gets a build
  attestation, so a download can be checked against this repository with `gh attestation verify <file> --repo sebastianrath/specofrecord`.
  The `vscode-v<version>` build then publishes the `.vsix` to the Visual Studio Marketplace, once a publisher exists and the
  secret `VSCE_PAT` is set in the repository's `marketplace` environment.
- Do not run `sor lock` or `sor claim` against `examples/` or `editors/vscode` to try the tool out. Use a temporary
  folder.

## License

The spec is CC BY 4.0 and the toolset is MIT. See [LICENSE.md](LICENSE.md).
