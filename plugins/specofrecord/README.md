# Spec of Record: Claude Code plugin

Keeps a project's specification as clauses in Markdown (a `sor/` folder) and builds the code from
them. The plugin gives Claude Code three things:

| Part | What it does |
|---|---|
| **Skill** `specofrecord:specofrecord` | The working order: change the clause first, claim it, rebuild only its code, run the tests, lock your own clauses. Claude loads it when a project has a `sor/` folder. |
| **Hooks** | Refuse code edits whose clause did not change (and full-file rewrites of spec files), add the clauses behind the lines Claude reads, and say once at session start that the project has a spec, with a short index of its parts. They do nothing in projects without `sor/`. |
| **`sor` command** | `sor status`, `show`, `markers`, `parts`, `needs`, `changes`, `new`, `check`, `test`, `claim`, `release`, `lock`. On the PATH while the plugin is enabled. |

The format itself is in `skills/specofrecord/reference/format-cheatsheet.md` (full version: SPEC.md in the
project this came from).

## Requirements
- **Python 3.9 or newer** as `python3` on the PATH. The tools are plain Python (standard library only). Without
  it the hooks do nothing and `sor` prints a message; with an older Python `sor` says which version it found.
- **Chrome or Edge** only for `sor test` on web projects (set `SOR_CHROME` if it is not found).
- macOS or Linux. **Windows is untested**: the hooks and `bin/sor` are POSIX shell.

## Try it
**Status:** validated, tested with simulated hook input, and loaded live once: from a project's
`.claude/skills/` folder (second way below) the session start note arrived, the skill was listed, bare `sor` worked and
the edit guard refused an edit. With `--plugin-dir`, in three headless sessions (2026-10-19 and 2026-10-20), the session-start hook ran and the edit
guard refused and allowed edits; bare `sor` resolved on the PATH in the last one and in smoke tests (after the launcher was
made executable), and in a smoke test the skill's path variable came out filled in. Not tried: the marketplace install, the hook that adds clauses to what is read,
and claim enforcement between two sessions.

From a terminal (loads the plugin for that session only, nothing is installed):

```bash
claude --plugin-dir /path/to/plugins/specofrecord
```

Or put this folder at `<your project>/.claude/skills/specofrecord/` (it has its own
`.claude-plugin/plugin.json`) and start Claude Code in that project. Per the Claude Code docs this loads only
when the session starts at the project's root folder (not a subfolder) and after you accept the workspace
trust dialog for it.

Or add the repository as a marketplace and install from it:

```text
/plugin marketplace add /path/to/the/repository
/plugin install specofrecord@specofrecord
```

Then, in a project that has a `sor/` folder, ask Claude to run `sor status` (a smoke test; in everyday use you never ask for `sor` commands, Claude runs them). There is no
`sor init`: `sor new --root` writes `sor/SPECOFRECORD.md` and `sor new <part>` a part file, each with `<fill in: ...>`
placeholders that `sor check` reports until they are filled in. Or create the files yourself, following the cheat sheet.

## Things to know
- **Hooks run in every project** where the plugin is enabled. In a folder without `sor/` they exit
  silently (about 0.1 s). Do not enable the plugin in a project that already has the same hooks in its own
  `.claude/settings.json`: they would run twice.
- **`--allow-behind` asks you first.** A Bash hook reads each command Claude is about to run and asks you before a `sor lock` that carries
  `--allow-behind` (the flag that lets a language stay behind a clause, or lack code for it). A command that only mentions the flag, a grep or a
  document, is not asked; a command line that runs `sor lock` the hook cannot read counts as one. Every other Bash call pays about 15 ms for a text
  check. It guards Claude Code only: your own terminal, other agents and a script that Claude writes and runs are not covered, and how Claude
  Code's bypass-permissions mode treats an `ask` is not verified. The same flag is the way out of `sor lock` refusing a language
  that is behind or has no code, so the answer to the question is yours.
- **A claim ends with its session or when it is idle.** It is renewed by every `sor` command and every edit or read that carries the session id, and a
  `SessionEnd` hook frees the claims of the chat that ends. A chat that crashed skips the hook, and its claims end after 30 minutes without activity.
  `--ttl 2h` sets that window for one claim, `--ttl never` removes it, and `Claims: idle 2h` (or `idle never`) in `SPECOFRECORD.md` sets it for the
  project (a change to that line shows as a change of the root file). The editor extension has no session id, so its refreshes keep nothing alive.
- **Claims.** `sor claim` records who works on which clauses and `sor lock` respects it. The edit hook also
  refuses edits to a clause someone else holds (it says who and until when, and the agent decides what to do).
  An agent that never claims is not stopped. This relies on the session id a hook receives being the one
  `sor claim` finds in `CLAUDE_CODE_SESSION_ID`: checked equal live. Subagents share their parent's session id,
  so a parent running subagents in parallel gives each its own name (`--as`); two subagents then conflict at
  `sor claim`. Who may release what is in "Claims" of `skills/specofrecord/SKILL.md`. The edit hook does not enforce
  between sibling subagents.
- **One language of a clause.** In a project that says its targets, `sor claim greet/hello@py` holds the Python side of a clause and another agent may
  hold the TypeScript side. `sor lock greet/hello@py` writes that language's lock lines and never the clause's own, so the two locks cannot undo each
  other. The clause has to be locked first, and the hook that asks before `--allow-behind` asks before `--already-fits` as well. The order is in
  `skills/specofrecord/reference/parallel-agents.md`.
- **Tests of other targets.** A target whose rules say `{run: …}` and `{results: …}` has its tests run by `sor test --targets py`, and
  `sor lock --run-tests --targets py` locks with their results. A command runs only when the call names its target.
- **Open questions and notes.** An `open: <question>` line under any item but a test flags a question nobody has
  answered: `sor check` lists it as a note, it is not part of the item's lock text, and the agent builds only what is
  not in question instead of choosing an answer. `sor check` also notes a part that outgrows the limits of the format
  (listed in `skills/specofrecord/reference/format-cheatsheet.md`). Notes never change the
  exit code; `sor check --strict` makes them exit 2.
- The VS Code extension (clause lenses, gutter marks) is separate, in `editors/vscode/`.

## Start a new project
Today the plugin is this folder; nothing is published, so you put it in the project (second way above). That is all
the setup:
1. Make an empty folder for the new project and copy this folder to `<project>/.claude/skills/specofrecord/`.
2. Start Claude Code in the project folder (its root) and accept the workspace trust dialog.
3. Say what you want, mentioning Spec of Record once. For example:

```text
I want to build a game engine. Write the first specs following Spec of Record. Keep them simple and easy to understand.
```

or, for the smallest possible try: `I want a web page that says "Hello, world". Use Spec of Record.`

You never run or ask for `sor` commands, checks or locks: the agent writes the specs, checks and locks them, and tells
you in plain words what it wrote. For a big project it stops there so you can read the specs, and offers to build
the first part. Then just say what you want next, for example `Build the rendering part.` or, later, `Make the frame
budget 8 ms.`

- **Permission prompts:** the skill pre-approves `sor` for the turn that uses it. A plugin cannot set permissions
  itself, so if Claude still asks the first time, choose "always allow", or add `Bash(sor *)` to your allowed tools once.
- **Why the first message matters:** the start-of-session note only appears once a project has a `sor/` folder, so in
  an empty folder the words "Spec of Record" are what bring the skill in.
- **Tests:** `sor test` only runs web projects. For anything else the agent writes the tests as clauses and tells you
  once that they cannot run yet.
- **Status:** tried live with `--plugin-dir`: a fresh Claude Code session wrote and locked a first game engine specification
  (63 parts) from a short request, and two later sessions grew it to 237 parts from long briefs (2026-10-19 and 2026-10-20).
  The marketplace install was not tried.

## Version control and other environments
The tools do not depend on how your project is run or built, and they never commit, merge, fetch or open files
for edit. The one exception is an optional lookup of who last changed drifted lines (git today; without git it is
simply left out). What your project handles itself:
- Keep `sor/.sor-claims.json`, `sor/.sor-claims.lock`, `sor/.sor-lock.mutex`, `sor/*.tmp` and the page copies `.sor-test-*`
  that a crashed `sor test` can leave next to the web page out of version control, with whatever ignore mechanism you use.
  The claims file is removed when no claim, and no claim that merely expired, is left. An expired claim stays in it for 2
  hours (so its holder can be told) and is dropped by the first claim or release after that; reading does not touch the file.
- If your environment keeps files read-only until they are opened for edit, open `sor/sor-lock.json` and the
  files an agent will change first. `sor lock` refuses, and changes nothing, when the lock file is read-only.
- Line endings do not matter: an LF and a CRLF checkout of the same files give the same lock.
- Claims live in one workspace. Agents in separate workspaces (git worktrees, Perforce clients, Lore instances) or
  on separate machines do not see each other's claims; a shared place for them is not built.

## For maintainers
`tools/` in the repository is the one place to edit. After a change, run `sh plugins/sync-tools.sh` to copy
it into this plugin, and `sh plugins/sync-tools.sh --check` to see whether the copy is current. Check the
plugin with `claude plugin validate plugins/specofrecord --strict`.

Spec text: Sebastian Rath, CC BY 4.0. A license for the code has not been chosen yet.
