# Working in a Spec of Record project (for any coding agent)

The clauses in a `sor/` folder are the source of truth; code is built from them. `SPEC.md` is the full format.

The workflow (the commands, how to make a change, claims, open questions, the rules) is written once, in
`plugins/specofrecord/skills/specofrecord/SKILL.md`. Read that file first and follow it. It links reference files in
the same folder (`reference/new-project.md` for starting a project, `reference/parallel-agents.md` for working beside
other agents, which you need most): read them when the task calls for them. `CLAUDE.md` imports the same file for
Claude Code, so there is one text to keep up to date. This file only says what differs when you are not
Claude Code.

The tool is `python3 tools/sor.py -C <project> <command>` (a project is a folder holding `sor/`, e.g.
`examples/solar-system`). In the skill, `sor` stands for that whole command.

## If you are not Claude Code
- The edit guard (hooks) exists only in Claude Code. You get no hook: nothing refuses an edit to code whose clause did
  not change, nothing shows the clauses behind code you read, nothing says at session start that a spec exists. So run
  `sor parts` first, `sor show` or `sor markers` before you edit code, and `sor status` after: drift that appears
  after your own edit means you broke the order. Drift that was already there is a person's change: see "Code a person
  changed" in the skill. `sor status` still reports drift and `sor lock` still refuses it.
- You have no Claude session id, so the tool cannot tell who you are. Choose one name and pass `--as NAME` on every
  `sor claim`, `sor lock` and `sor release` (or set `SOR_AGENT=NAME`); no other command takes `--as`. Use the same name
  every time: another name is another agent. Without a name, a claim and a release fail and a plain `sor lock` is
  refused. Because you name yourself, your `sor release --all` frees only the claims made under your name, never another
  agent's, so the skill's line that only the parent runs `release --all` without a name does not apply to you: always pass yours.
- The skill also speaks of the plugin, `${CLAUDE_SKILL_DIR}`, Claude Code sessions and refusals by the edit hook. None
  of that applies to you: use the command above, `--as NAME`, and `sor status`.
- Where a Claude Code agent works in the same project, its edit guard may refuse edits to what you claimed. Release
  when you are done.
