# Decisions — everything revisited

## Goals
Stated: easy to digest and maintain · scales from a small CLI to an engine or browser ·
high- and low-level objectives in one format · code traceable back to facts (AI as compiler) ·
few sections that are easy to remember · works in a plain text editor · version-controlled
lock · many agents at once · unit, property, regression, benchmark tests and coverage under
one roof.

Added because they were missing:
1. **Existing code** — a project must be adoptable without rewriting it (`Source: code at`).
2. **Stored data** — changing the shape of owned data must flag a migration (`owns`).
3. **Inventing** — new techniques are found by trying, so experiments are part of the format.
4. **Weak tests** — a test that cannot fail must be detected (test strength).
5. **Cost** — AI runs need hard limits (`limit:` on experiments, budgets in the build tool).
6. **Learnable in 10 minutes** — the cheat sheet is the whole day-to-day format.

## Decisions

| # | Earlier decision | Now | Why |
|---|---|---|---|
| 1 | Plain Markdown | keep | any editor, GitHub, diffs |
| 2 | Map / part card / facts as three altitudes | change | one file shape at every level; hierarchy = folders |
| 3 | ~14 section names (Gives, Needs, Must stay true, How it works, Design, Facts, Must have, Checks, Words, Not in scope, Journey, Parts, Boundaries, Draw order) | change | four: Facts · Approach · Contract · Tests. Words, out-of-scope, budgets → Facts; journey, parts, design → Approach; gives, needs, boundaries, owned state → Contract |
| 4 | `Precision: sketch / exact` | drop | a fact with a test is binding, one without is guidance; no switch to remember |
| 5 | Markdown links for references | **reversed** | braces only, looked up outward from where you are (SPEC §4, checked by `sor check`; the earlier standalone `tools/check-refs.py` was deleted 2026-10-19). Shorter, one mechanism; an id still maps to one file and one bold name by hand. Cost: GitHub does not make them clickable |
| 6 | `.human` / `.js.human` files | change | `.md` under `fact/` |
| 7 | `MAP.md` | change | `FACT.md`: the root and every folder use the same shape |
| 8 | `@fdd` markers, every line in a region | keep, renamed `@fact` | plus coarse markers and `Source: code` for scale and existing code |
| 9 | `fact-lock.json`, one entry per line, merge driver | keep | add tests' accepted results; optional split per folder at scale; adding a table row changes its item |
| 10 | `do:` / `expect:` checks compiled to tests | keep | `at:` and `repeat:` folded into `each:`; added `measure:`, `bug:`, generators, hand-written test markers |
| 11 | `fdd.json` config | change | its content moves into the target file (where code goes, how tests run) |
| 12 | Tier 1/2/3 review gates | change | one rule: BLOCKING problems stop the build of any part whose facts have tests |
| 13 | One screen per file | change | one screen above `## Tests`; long tests fold or move to `<part>.tests.md` |
| 14 | Max 7 items per list | keep | per section; more means child parts |
| 15 | Name "Fact-Driven Development" | **decided** | "Spec of Record"; the unit is a clause, see below |
| 16 | `@fact` markers, `## Facts` section, `fact-coverage` | **renamed** | `@clause`, `## Rules`, `clause-coverage`; the old names still read, see "Clause" |

## Name
- "Fact-driven development" is already used by [av/facts](https://github.com/av/facts): a CLI for
  `.facts` files, flat lists of truth statements checked by shell commands. It has no code
  tracing, lock, contracts, hierarchy or compiler, but the name would be confused with it.
- FACT works as the mnemonic for the four sections: **F**acts · **A**pproach · **C**ontract ·
  **T**ests. What is true · how it is built · what it promises · how we prove it.
- Options for the public name:
  1. **FACT** (the acronym, "FACT files", CLI `fact`): shortest; close to av/facts.
  2. **FACT-compiled development** / CLI `factc`: says what is new (AI compiles facts to code).
  3. A new name, keeping FACT only for the sections.
- Recommendation: option 2. Not checked yet for other uses or trademarks.

## Clause
The smallest unit of the spec (one rule, number or table row) is a **clause**, not a fact: "fact"
confused newcomers and clashes with av/facts. What changed, and what did not:
- Code markers are `@clause <id>` … `@clause end`. `@fact` is a deprecated alias, read for one more
  version; `fact check` prints a note with the count and the first line that still uses it.
- The section "What must be true?" is `## Rules` (the plain format already read "Rules" as it).
  `## Facts` stays an accepted heading for good, like "Must" or "Requirements".
- The built-in metric is `clause-coverage`; `fact-coverage` is read as it for one version.
- Kept: the folder `fact/`, the root file `FACT.md` (lock key `FACT`), `fact-lock.json`, the CLI
  `tools/fact.py` / `fact <command>`, `FACT_CHROME`. Renaming them touches every project's layout,
  every lock key of a root item, the edit hook and the editor's activation, and `clause/` would
  name one unit while the folder holds the whole spec (the website calls it "a folder like src/",
  so `spec/` is the likelier name). That choice is the owner's; the folder and lock names now sit
  in one place (`SPEC_DIR`, `LOCK_FILE` in tools/factlib/model.py), so a rename is small.
- Kept: JSON field names the editor reads (`factDir`, `facts` in `fact markers --json`), VS Code
  command and setting ids (`fact.*`) and the language id `fact-markdown`, so existing settings and
  the extension keep working. Only what people read changed.
- Update (2026-10-18): the folder, files and command kept above were renamed afterwards: see "Naming" below.

## Naming
Decided with the user (2026-10-18): the philosophy is **Spec of Record**, the unit is the **clause**, the tool is
`sor`, and each project keeps its clauses in a `clauses/` folder. "Fact" survives only where old projects, old
input and the history need it. The repository folder itself was renamed `fact` -> `sor` by the user afterwards (nothing in the project hard-codes the old path).

What a **fact** was: the old name of a clause (one rule, one number or one table row). The project began as
"Fact-Driven Development" and FACT stood for the four sections Facts · Approach · Contract · Tests. It was
renamed because it confused newcomers and clashed with av/facts (see "Clause" above), and because Facts became Rules.

| Old name | New name | Status |
|---|---|---|
| folder `fact/` | `clauses/` | **removed** (2026-10-19), with `sor migrate` |
| root file `fact/FACT.md`, and `FACT.md` of a folder part | `clauses/CLAUSES.md` | removed |
| lock file `fact-lock.json` | `clauses-lock.json` | removed |
| root lock key `FACT` (and the id `FACT` in `claim`, `lock`, `show`) | `CLAUSES` | removed |
| command `fact` | `sor` | removed, with `tools/fact.py` and the plugin's `bin/fact` |
| `tools/fact.py`, `tools/factlib/` | `tools/sor.py`, `tools/sorlib/` | removed |
| `FACT_CHROME`, `FACT_AGENT`, `FACT_ENFORCE_CLAIMS` | `SOR_CHROME`, `SOR_AGENT`, `SOR_ENFORCE_CLAIMS` | removed |
| hook commands in `.claude/settings.json` and the plugin's `hooks.json` | call `tools/sor.py` | |
| messages, docs, the skill, the plugin README | say `sor`, `clauses/` | |
| extension `fact-vscode` / publisher `fact` | `sor-vscode` / `sor` (0.8.0) | a new identity: uninstall the old one |
| `@fact`, `## Facts`, `fact-coverage` | `@clause`, `## Rules`, `clause-coverage` | removed |
| extension settings and commands `fact.*`, language `fact-markdown`, JSON fields `factDir` and `facts` | `sor.*`, `sor-markdown`, `specDir` and `clauses` | removed (2026-10-19); the extension was changed with the tool |
| `.fact-test-*` page copies, `fact-test` query, `fact-chrome-`/`fact-guard-` temp names | `sor-...` | the ignore entries are gone too |
| folder `clauses/` | `sor/` | renamed 2026-10-19, before anything was published; `CLAUSES.md` and `clauses-lock.json` kept their names then |
| root file `sor/CLAUSES.md`, root id and lock key `CLAUSES`; a split part's own file `sor/screen/CLAUSES.md` | root file `sor/SPECOFRECORD.md`, id and key `ROOT`; a split part is `sor/screen.md` with its children in `sor/screen/` | 2026-10-19; `CLAUSES` still accepted for the id and as the file name (read, never written) |
| lock file `clauses-lock.json` | `sor-lock.json` | 2026-10-19; an older file is read and replaced when the lock is next written |
| `.claims.json`, `.claims.lock`, `.lock.mutex` | `.sor-claims.json`, `.sor-claims.lock`, `.sor-lock.mutex` | 2026-10-19; short-lived working files, an old `.claims.json` is simply no longer read |
| plugin `spec-of-record`, marketplace `spec-of-record-plugins`, folder `plugins/spec-of-record/` | `specofrecord` for all three (repository `sebastianrath/specofrecord`) | renamed before anything was published (a local copy under `.claude/skills/spec-of-record/` may still exist, and the VS Code extension still finds it). Notes dated earlier in this file still say `spec-of-record` |
| skill `workflow` (`specofrecord:workflow`, folder `plugins/specofrecord/skills/workflow/`) | skill `specofrecord` (`specofrecord:specofrecord`, folder `plugins/specofrecord/skills/specofrecord/`) | 2026-10-21; the skill is named like the plugin; the paths in `CLAUDE.md`, `AGENTS.md`, `sync-tools.sh`, `build-plugin.py` and the tests follow, and a copy in a project's `.claude/skills/` has to be replaced |

Sections dated before 2026-10-19 (Many agents at once, Environment agnostic, Hooks never block by accident, the lessons) were written with
the old names and kept as written: read `clauses/` as `sor/`, `.claims.json` as `.sor-claims.json`, `clauses-lock.json` as `sor-lock.json`.

**The spec folder is `sor/` (2026-10-19), no longer `clauses/`.** It sits next to `src/`: three letters each, neighbours in a listing, and
the command is `sor` too. Product-named folders are normal (the comparison notes show `openspec/`, `.kiro/`, `.tessl/`), and it avoids the
`specs/` and `spec/` collisions (Spec Kit's `specs/`, Kiro's `.kiro/specs/`, test folders). Costs, accepted: the acronym has to be explained
once (SPEC §1 does), "SoR" also means "system of record" in data work, the editor gives its Spec of Record language to Markdown in any folder
called `sor`, and a child part named `sor` inside the spec folder is ambiguous for `-C`. A project folder that is itself called `sor` works:
the tool looks for `sor/SPECOFRECORD.md` inside it first.

**The root file is `sor/SPECOFRECORD.md`, its id is `ROOT` (2026-10-19).** Decided with the user after the other choice was weighed: keeping `CLAUSES.md`
was the recommendation, because `CLAUSES` then did three jobs (root file, every folder's own file, the root's id and lock key) and renaming
only the file would make the root the one id that does not name its file, with two names for the same role. The user chose a recognisable
entry-point name, `SPECOFRECORD.md` once per project (the "repeats in every subfolder" argument I first gave was weak: folder files exist
only where a part is split, and a count of 14 characters was wrong, it is 12 letters). What was done about the costs:
- Later the same day the lock became `sor-lock.json` and the working files `.sor-claims.json`, `.sor-claims.lock` and `.sor-lock.mutex`, so
  everything the tool writes has a `sor` name. `clauses-lock.json` is still read and replaced when the lock is next written.
- The id is `ROOT` everywhere (commands, output, the lock key). `CLAUSES` and `SPECOFRECORD` are accepted for it in commands, and an older
  lock that says `CLAUSES` is read as `ROOT` with the same hashes, so nothing counts as changed and the next lock rewrites the key.
- A root file called `CLAUSES.md` is still read, and so is `clauses-lock.json`, so projects made before the change keep working.
- The exception to "an id names a file" (SPEC §1, §4) is written down: it is `ROOT`.

**The final structure: one special file, the root (2026-10-19).** Folder files were tried twice that day (`player/CLAUSES.md`, then
`player/SPECOFRECORD.md`) and dropped: the same name repeated in every split folder, two names for one role, and splitting a part meant moving its
file. Now only the root is `sor/SPECOFRECORD.md`. Every other part is `<id>.md`, and its children go in a folder beside it (`web.md` and `web/page.md`;
`sor/targets/` and `sor/api/` are plain folders with no file). So every id except `ROOT` names its file, and splitting a part moves nothing, so its id,
its lock entries and its history stay. The older folder-file styles are still read. Checked in temporary projects before the change:
- **Sibling layout** works, including a child referring to an item of its parent beside it, and a folder with no file of its own.
- **Two files claiming one part silently replaced each other** (the second parsed one won, the other's items vanished and `sor status` called them
  removed). That was a bug whatever the layout: now the plain `<id>.md` counts first and the other is a problem naming both files.
- **A project inside a project** (a monorepo with `apps/web/sor/…`) was scanned by the outer one, which reported the inner markers as unknown ids,
  the same kind of bug as the `.claude/` one. The scan now stops at a folder that has a project of its own. The hook already used the nearest project.
- Costs, accepted: a part's file and its folder are two places on disk, and `sor new` no longer refuses to add a child under a plain file.

**Everything named after `fact` was removed (2026-10-19).** Nothing was published and nothing used it: the `fact/` folder layout and
`sor migrate`, the `@fact` marker, the `FACT_*` variables, `tools/fact.py`, the `fact-coverage` metric, the `## Facts` heading, and in the
editor extension the `fact.*` settings and commands, the language `fact-markdown` and the JSON fields `factDir` and `facts`. A `fact/`
folder is now an ordinary folder. The history above stays as it was written.

The plugin is one word like the domain specofrecord.org, and the install line has no hyphens: `/plugin marketplace add
sebastianrath/specofrecord`, `/plugin install specofrecord@specofrecord` (the skill is `specofrecord:specofrecord`). The command,
the library and the variables stay `sor`, `sorlib` and `SOR_*`: the plugin name is what a person types once, the command
is what an agent types all day. Cost: `specofrecord` is harder to read than `spec-of-record`, and a marketplace search for
the words "spec of record" does not split it. A plugin and a marketplace with one name is untried (see "Packaging").

Why `clauses/` and `sor`: `spec/` is the conventional test folder of RSpec and Jasmine, and the scan skips the
folder that holds the spec, so a Ruby project's tests would drop out; a plural container named after its contents
works like `tests/` or `docs/`. The command is the product's short name, which is on no PATH here, so it is
unlikely to be shadowed (a plugin's `bin/` comes after the user's own PATH).

## Many agents at once
The goal "many agents at once" had no mechanism. Parallel edits were tried on a copy of the
solar-system example (2026-10-18); SPEC §16 is the result.

| Failure | Before | After |
|---|---|---|
| Write from a stale read erases another agent's clause | lost update, every time | Claude hook refuses Write on an existing spec file; other agents: a rule in CLAUDE.md only |
| Edit with a 5 ms read-to-write gap | lost update, 200 of 200 rounds | **not fixed**, a rule only (re-read right before editing) |
| One agent's `sor lock` accepts another's unbuilt change | accepted, status went clean, code still old | a plain `sor lock` locks only what you claimed, and is refused if you claimed nothing; `--all` is refused while another agent holds a claim; a scoped lock leaves the other's change visible |
| Two scoped locks at once | (did not exist) | both entries kept (control without the merge step: 12 of 12 lost) |
| Reader sees a half-written lock | 793 of 22,644 reads unreadable | 0 of 22,597 |
| Same clause, same code region | no signal | second claim refused, exit 3 (8 processes racing, 25 rounds: one winner each) |
| Contradicting edits in different clauses | `sor check`: 0 problems | **unchanged**: the compiler's review and the tests must find it |

Defaults chosen, to overturn if wrong:
- **Scoped lock is the default** (decided with the user). A plain `sor lock` locks what you
  claimed; with ids, those clauses; `--all` locks the whole project. The cost is that someone working
  alone has to claim or name ids, which the agent does, not a person. The other choice was to keep
  the old whole-project lock as the default: its failure is silent (another agent's unbuilt change
  is accepted and status says everything agrees), the scoped default's is a loud refusal.
- **Claim what you edit plus the regions it is marked on, not every clause that shares code.** A
  first version also held every clause sharing a region: `colors` shares regions with almost
  everything, so one claim locked the whole spec file. In the example `ring` and `light` are marked
  on one region, so two agents cannot work on them at once; that is deliberate.
- **Identity is automatic** (decided with the user): `--as`, else `SOR_AGENT`, else the Claude Code
  session id from the Bash tool's environment (`CLAUDE_CODE_SESSION_ID`). A parent and its subagents
  count as one agent. Verified live (2026-10-18): the hook's `session_id` equals that variable, and subagents share their
  parent's id (the hook does see a distinct `agent_id`, the Bash tool does not). Each claim records its `session`, and the
  hook compares sessions, not names: with names it refused an agent whose claim was made under `--as`, a bug that was
  live while enforcement was on and is fixed.
- **Sibling subagents: the parent names them** (decided with the user, who asked whether the agent can choose, which it can).
  The Bash environment of a subagent is identical to its parent's (checked), so the CLI cannot tell siblings apart by itself.
  The parent gives each parallel subagent a name and a rule (`--as <name>` on every claim, lock and release, do not claim what
  you delegate); an agent is a session plus a name, so two subagents conflict at `sor claim` and the refusal names the holder,
  as for any collision. Two chats using the same name stay separate agents. Rejected: a `SubagentStart` hook that injects a name
  (relies on the subagent obeying, delivery of its text to the subagent is not confirmed, adds guard rules), rewriting Bash
  commands with `updatedInput` (intrusive, comes with auto-approval), a hook that auto-claims and adopts claims (too many
  rules). What stays open: the hook does not enforce between siblings, so a subagent that skips claiming is not stopped.
- **Claims live in one workspace** (`clauses/.claims.json`, kept out of version control by the project), decided with
  the user: today all agents edit one folder. Separate workspaces (git worktrees, Perforce clients, Lore instances)
  or machines would need a shared place, which differs per environment; none is built (see Environment agnostic).
  **Claims are advisory:** an agent that never claims is not stopped. The hook refuses edits to what another
  session holds where `SOR_ENFORCE_CLAIMS=1` is set (this repository's settings and the plugin), after the hook's
  `session_id` was confirmed live to equal `CLAUDE_CODE_SESSION_ID`. Refusing with who and until when, and
  letting the agent choose (another clause, wait and retry, ask), was chosen over making the hook wait:
  a waiting hook freezes the agent unseen, can deadlock, and outlasts the 30 s hook timeout.
- **Write is refused on existing spec files** in the Claude hook, because it was the one failure
  an agent cannot see coming. Other tools get the same rule as text. One exception since 2026-10-20: a file that is
  still exactly the skeleton `sor new` wrote (see "Claims that name themselves" below).
- **Not built:** automatic claiming by the hook, a VS Code lens for claims (the extension's own
  clauses are being edited elsewhere), clause-level merging across branches, a serialized-edit
  command for the Edit gap, detection of contradictions.

## Claims that name themselves, claims that ran out, and a few checks (2026-10-20)
Changes to the tool. SPEC §15, §16 and the skill say what it now does; this says why. Defaults chosen, to overturn if
wrong:
- **A name releases only its own claims.** Subagents share their parent's session, and `sor release --all` freed every
  claim made in the session under any name, so a subagent that finished could free its siblings' claims while they still
  worked. A caller that names itself (`--as`, `SOR_AGENT`) now frees only that agent's claims; another agent's claim
  named by id prints "NOT released (held by someone else; --force overrides)" and exits 3. A caller that gives no name
  (the parent, or the only agent) still frees the whole session, because the parent has to clear what a crashed subagent
  left behind. Cost: a subagent that forgets `--as` cannot be told from the parent, as before (same session, same
  environment), so the rule stays text in the skill: each subagent passes its own `--as`, and the parent's last release
  has none (`SOR_AGENT` counts as a name: a parent that has it set frees only its own).
- **Expired claims are kept for 2 hours.** An expired claim used to vanish: the agent's next `sor lock` said it had
  claimed nothing and its `sor release` said "nothing to release", with no hint that the claim had run out and that
  another agent may have taken the clause since. They stay in the file as tombstones (`claims.TOMBSTONE`) and are pruned
  whenever the file is written, so that `sor lock` and `sor release` can tell the holder and say how to go on (claim
  again, `--ttl 2h` for longer). The 2 hours are a guess: a default claim lasts 30 minutes and `--ttl 2h` is the longer
  one the messages suggest, so a lapse is reported at least as long as the longest claim they suggest. An older tool
  reads a tombstone as an expired claim, which it is, so nothing breaks. Costs: after a crash the claims file lingers, up
  to the first claim or release after those 2 hours (reading never writes it), and an agent that neither locks nor releases is still not told.
- **A plain lock covers the child parts of a claimed part.** A plain lock took only the claimed ids, so `audio/mixer`
  (new, or made after the claim on `audio`) stayed pending, and the way out on offer was `--all`, which is refused while
  others hold claims or takes their work: the trap of the glue file again (see Lessons below). A plain lock now takes
  each claimed part together with the child parts under it that have a change of their own (new, changed or removed) and
  says so. A child part that another agent's claim overlaps is left out and named, not refused: it is theirs. `ROOT` is
  not expanded, since its child parts are the whole project. A claim on a part still does not hold its child parts
  against other agents (a test pins it): holding the subtree would block every agent working under `audio/`, and a claim
  on the root would block the project. Cost: unfinished work in an unclaimed child part is locked with its parent;
  `sor lock <ids>` locks exactly what is named.
- **A words limit per item, as a note (the number is in SPEC §13).** Measured on the two real projects (162 items in Rules,
  Approach and Contract): 3 items exceed it and 6 would exceed a limit of 60, so it names a few items and not the habit. It is a note like the other limits:
  it never blocks a lock, `--strict` makes it fail. Words, because the line limit counts a part and not an item; tests
  are exempt (their limit is lines), and a table, an `open:` line and a `code:` line do not count.
- **Parts and items share one namespace; only the message changed.** A part `scene/modes` and a rule `modes` in
  `scene.md` were already a `collision` in `sor check`, and `sor new` already refused the id. The messages now say where
  the item is (`the rule **mixer** in audio.md`), name both files, and give the two ways out (another part name, or
  rename the item first). Both could not coexist: `{scene/modes}` would be found twice, which SPEC §4 makes an error.
  The cheat sheet and `reference/new-project.md` say it, so child part names are chosen not to repeat an item of the
  parent.
- **One Write over an untouched skeleton.** The hook refused Write over every existing spec file, so after `sor new` an
  agent could not fill the skeleton in whole, only Edit by Edit, placeholder by placeholder. A file that is byte for
  byte what `sor new` would write now has nothing in it to erase, so one Write is allowed; the first change makes it an
  existing file again, and the claims check still applies. A skeleton made with `--why` was first left out (the hook
  cannot know the sentence); see "What the engine runs left (2026-10-20)". Not covered: `.tests.md` files and the older folder form. A Write
  that creates a file was never refused.
- **A review of the documents (2026-10-20) changed behaviour in two places.** A reference in a table cell (`{x}`; an alias
  `{v: = x}` written in a cell counts too) is now a reference like any other, decided with the user: one that names nothing, or two things, is a problem that
  blocks the lock of its part, and the item that holds the table is flagged for review when the target changes. Before, a cell
  was neither checked nor followed, so a cell could go stale while `sor status` said everything agreed. Cost, measured on a copy of
  the engine specification (31 items with cell references): the first status with the new tool listed those 31 as `stale`
  (review, not recompile) in 12 parts, and one scoped lock of those parts cleared it; the two real projects have no reference in a
  table cell. What is not done: the format defines no alias form for a cell, so a bare `= x` cell is not read as one (a cell that only
  starts with `=` would be reported as broken), and an item that refers to a cell's own value is not flagged through a
  `{v: = x}` written in the cell; only the item that holds the table is. A reference in an `open:` question stays unchecked and no dependency, on purpose (a test pins it): a
  question may name what is not decided yet, and a question stays out of the lock. A refused batch claim
  names only the ids in the way and says the others were free but not claimed, because a claim takes all its ids or none; the
  skill told agents to avoid whatever REFUSED names, and they avoided free clauses.
- **Smaller, in SPEC §15:** `sor check PART` reports and fails only for those parts and the parts inside them, so an
  agent is not stopped by another agent's unfinished part; `sor status` lists the tests a lock would refuse
  (`tests (N)`, and `tests_pending` in the JSON) and the lock refusal names the first ten and the way out; reference
  errors suggest the nearest ids; `--as` is refused on commands that do not take it, with the three that do; a closed
  output pipe ends with exit 141 and no traceback.

## Depth, not width (2026-10-20)
The format always allowed any depth (SPEC §1: the same four sections at every level), but nothing asked for it: the 7-item cap counts
items in a section, not child parts, and `reference/new-project.md` showed one level only. The first engine specification (249
parts) came out flat: 26 parts under the root, 25 under `rendering`, 21 under `editor`, 17 under `roadmap`, 13 under `core`, and only
19 parts three levels deep. Decided with the user: a soft limit, a tree view and guidance. Defaults chosen, to overturn if wrong:
- **A soft limit on child parts per part, as a note (`too wide`; the number is in SPEC §13).** Calibrated on what exists: the two real
  projects never go above 8 under any part, the engine specification has five parts above the limit and several just under it that
  read fine (`physics` 12, `networking` 11, `glossary` 11). A note like the other limits: it never blocks a lock, `--strict` makes it fail. The root counts its top-level parts too, because the skill's advice of a few parts to start with
  was the first thing the engine specification outgrew. A folder that only groups parts is no part and is not counted.
- **`sor parts --tree`:** each part indented under its parent, only its last name, and the number of parts under it. The flat index
  and `--json` are unchanged (with `--tree` the JSON is the same entries in tree order). Without it, the flat list sorts `a-b`
  between `a` and `a/c`, which splits a part from its children.
- **Guidance, not a rule, for how to group:** `reference/new-project.md` says to group the children that change together or
  share an owner under a part of their own, to choose the groups before writing many parts, and why (ids are paths, there is no
  rename command, a reference outside the siblings writes the whole path).
- **Not done:** regrouping the engine specification (it renames ids and touches about 2,200 references, and another session is
  editing it); a rename command; a rule that a group must have its own file.

## Packaging as a Claude Code plugin
Decided with the user (2026-10-18): the way to hand the tools to a project is a Claude Code plugin, not
files to copy by hand and not a skill alone. A skill cannot keep the edit guard always on (a skill's hooks
start only once it is invoked); a plugin's hooks are active in every session where it is enabled.
- **Where:** `plugins/specofrecord/` (manifest, skill `specofrecord`, `hooks/hooks.json`, `bin/sor`, a copy of
  the tools). A folder of its own, because the repository root also holds the VS Code test archive and
  `node_modules`, which would be copied into every plugin cache. `.claude-plugin/marketplace.json` at the
  root lists it for `/plugin marketplace add`.
- **One source of truth:** `tools/` stays canonical; `sh plugins/sync-tools.sh` copies it (and regenerates
  the skill's cheat sheet from SPEC.md), `--check` fails when they differ.
- **Messages name the command `sor`** when running from the plugin, and `python3 tools/sor.py` from a
  checkout (`factlib/invoke.py`); a path that only exists in a checkout would mislead agents.
- **Hooks fire in every project** with the plugin on, so they exit silently without a `clauses/` folder, and
  without `python3`. Hook calls skip the CLI import: 0.18 s to 0.09 s.
- **Live test (2026-10-18):** loaded from a project's `.claude/skills/spec-of-record/`: the session start note,
  the skill, bare `sor` and the edit guard all worked, and the hook's `session_id` equalled the Bash tool's
  `CLAUDE_CODE_SESSION_ID`, so claim enforcement is on in the plugin's hooks. **Not done then:** `--plugin-dir` (done since, 2026-10-19 and 2026-10-20: three headless sessions, see the plugin README) and the
  marketplace install, two live sessions refusing each other, edit-time enforcement between sibling subagents, Windows (POSIX shell), a code
  license (the manifest names none), `sor init`. Do not enable the plugin in
  this repository: its hooks would run twice next to `.claude/settings.json`.

## Environment agnostic
Decided with the user (2026-10-18): Spec of Record is a philosophy and a toolchain that works the same
whatever the project uses for version control, workspaces and builds, and it must not dictate them.
- **Audit:** the only version-control code is the optional lookup of who last changed drifted lines
  (`blame.py`, git today, silent without it). The tools never commit, merge, fetch or open files for edit.
  The marker scan walks only the paths a project's target declares, so it needs no list of any system's
  metadata folders. Perforce and Lore were looked at from their documentation only; nothing was run on them.
- **Fixed:** my atomic lock write replaced a read-only `clauses-lock.json` (a file that Perforce keeps read-only
  until opened for edit) and left it writable: `sor lock` now refuses and changes nothing, naming no system;
  a writable lock keeps its permissions; stale temp files from a crashed write are removed; the claims file
  is deleted when the last claim is released, so nothing lingers for a reconcile or staging pass. (Since
  2026-10-20 a claim that merely expired stays in the file for 2 hours, as a tombstone, until the file is next
  written; the file is deleted when no claim and no tombstone is left.)
- **Checked:** hashes do not depend on line endings (an LF and a CRLF checkout give the same `sor status`,
  and the hook behaves the same on CRLF files). Recorded in SPEC §11.
- **What a project must handle itself:** keep `sor/.sor-claims.json`, `sor/.sor-claims.lock`, `sor/.sor-lock.mutex`,
  `sor/*.tmp` and the page copies `.sor-test-*` out of its version control, with whatever ignore mechanism it uses; and, in an environment that
  keeps files read-only until opened for edit, open files for edit before agents edit them and before `sor lock`.
- **Not built:** a shared place for claims across workspaces or machines (a small load/store/compare-and-set
  interface with a local default would fit), and non-git history lookups. A network share is unverified:
  `O_EXCL`, rename and clock skew behave differently there, and the 10 s stale-mutex rule assumes a local disk.

## Hooks never block by accident
Found 2026-10-18: another session could not write `website2.htm`. The page was never governed (the guard allows files
outside a project's spec folder and declared code paths); the write was blocked because the hook command failed
closed. That session's `CLAUDE_PROJECT_DIR` pointed at an old folder, the script path did not exist, and `python3`
exits with code 2 for a missing script, which Claude Code treats as a refusal. My own change from `python` to `python3`
exposed it: a missing `python` exited 127, which does not block.
- **Rule:** only a JSON deny may refuse an edit. Any other failure exits 1 with a one-line notice, so a broken guard
  announces itself instead of blocking everything or going silent. The repository's settings find the tool through
  `CLAUDE_PROJECT_DIR`, then upward from the session's directory (best effort: that hooks run in the session's
  directory is not verified); the plugin's hooks end in `|| exit 1`. Tested through `sh`: right directory, stale
  directory with the session in the repo, both wrong, a path with spaces, a tool that itself exits 2.
- **Already in place, so no new mechanism:** files outside the spec folder and the declared code paths are free, so the
  AI does not have to judge whether it may edit them. The skill and `CLAUDE.md` now say so in two sentences.
- **Alternatives, not built:** give the website a part with `Source: code at website2.htm` if it should be governed
  someday (hand-written code, no markers, status asks for review when it changes); an ignore list is not needed
  (declaring code paths precisely already exempts everything else; only a target that declares `path: .` governs the
  whole project); a `sor covers <path>` command that answers "is this governed, and by what?" would help agents but
  is not needed yet.
- **A session started before the fix keeps the old command** until it restarts; hooks load at session start.

## Code a person changed (2026-10-19)
Decided with the user: two cases, one rule each. When the AI makes a change, the clause comes first and then the code:
the edit guard keeps refusing an agent's code edit whose clause did not change. When a person changes the code
themselves, because they know better, the AI keeps their code and updates the clause to match.
- **Already in place, so no new mechanism:** the hooks see only an agent's own edits, so a person's edit already goes
  through and shows as drift, and `sor lock` refuses it until the clause agrees. Changing the clause after the code gives
  the same state as the other order: status says *changed* with *code updated*, and it locks. A flow test holds this.
- **Added:** `reference/code-a-person-changed.md` in the skill with the steps, a line in the skill's routine to start
  with `sor status`, and a drift line in `sor status` that says which of the two cases it is.
- **Cost:** the lock cannot tell which side came first, so the record does not show whether a clause led or followed.
  Version control does (the code commit, then the clause commit). A clause an AI writes after a person's change can say
  what the code does and miss why, which is why the AI tells the person in plain words what it wrote.
- **Alternatives, not built:** letting the guard allow an agent's code-first edits (the order the AI must keep is the
  point of the guard); keeping the old code in the lock so the AI can see the change without git (a heavier lock for
  what git already holds); a command that writes the clause from the diff (the tool cannot write plain language).

## The user states intent, the agent does the routine
Decided with the user (2026-10-18): a user adds the plugin once and then says what they want, for example "I want to
build a game engine. Write the first specs following Spec of Record." They never run or ask for `sor`, checks or locks.
My first quickstart prompt told the agent to run `sor check` and lock: that was a test script, not a way to use it.
- **Where it lives:** an explicit rule in the skill and `CLAUDE.md` (the agent runs check, test, lock and release itself and
  reports in plain words), a greenfield procedure in the skill, and `reference/new-project.md` with the structure, the
  style rules and a complete four-part example (verified: check, claim, lock, status).
- **Large projects stop after the specs:** write them, check, lock, summarise in plain words, offer to build the first
  part. Code is written straight away only when asked or when the project is tiny.
- **Triggering:** the skill description leads with "Spec of Record" and the phrasings people use; no bare "spec", which
  would fire in unrelated projects. The only thing the user must say, once, is "Spec of Record".
- **Permissions:** a plugin can only set two settings keys (`agent`, `subagentStatusLine`), so it cannot pre-approve
  `sor`; the skill's `allowed-tools` covers the turn that uses it, and the README says to allow `Bash(sor *)` once if
  Claude still asks.
- **Gap that stays:** `sor test` runs web targets only (SPEC §15). For other projects the agent writes tests as clauses,
  marks the ones that cannot run yet with `manual:`, and tells the user once.

## Lessons from reading ten spec formats (October 2026)
Ten formats were read side by side (Spec Kit, OpenSpec, Kiro, Tessl, AGENTS.md, Agent Skills, the MCP spec, OpenAPI, EARS
and Gherkin); the earlier notes on eight tools are in `comparisons/`, one NOTES.md each. What was adopted, each because
a format showed a gap here:
- **Readability notes:** `sor check` reports the limits SPEC §13 already named (rows 13 and 14 above), which nobody could
  see being broken: too many bullets in a Rules, Approach or Contract section, too many lines above `## Tests`, and a test
  that is too long (new; the numbers are in SPEC §13). Tests are exempt from the item cap. They are notes, not problems, because
  problems block `sor lock` and a long part is a smell, not a contradiction. `--strict` makes notes exit 2 for a project
  that wants them to fail.
- **`open:`:** an indented line under any item but a test, for a question nobody has answered. Until now the compiler
  could only write down a choice after it had made one (§14). The compiler now lists the question in its report and
  builds only what is not in question. The line stays out of the item's lock text: a question is not a promise, so
  adding or answering one must not mark the clause changed or unlock its code.
- **Derived needs:** `sor needs` finds a part's needs from the `{references}` in its items (the words of its parent files,
  its own child parts and design tokens do not count: a part is made of its children, it does not depend on them, so the
  root needs nothing) and marks each `gives` or not. A `needs` bullet only repeated what the references
  already said, and could go stale; it stays allowed, for saying why.
- **`sor parts` and the session-start index:** one printed index of every part (why, owner, source, size, gives, open
  questions), so an agent sees the project before it opens a file. It is never written into `clauses/`: every `.md`
  file there is a part, so an index file would be read as one.
- **`sor new` with placeholders that fail the check:** a skeleton with the four sections and `<fill in: ...>` text that
  `sor check` reports as a problem, so a half-filled part cannot be locked. It never overwrites.
- **`sor changes`:** what is pending since the last lock, in words: Added, Changed, Removed, Fixes (new or changed tests
  with `bug:`) and retired items. A reviewer reads that instead of hashes.
- **`AGENTS.md`:** what differs for agents that are not Claude Code. The edit guard is a Claude Code hook
  and exists nowhere else; drift in `sor status` and the refusal in `sor lock` hold for every agent. Such an agent has no
  session id, so it names itself with `--as`.
- **The workflow is written once:** in the plugin's skill (`skills/specofrecord/SKILL.md`). `CLAUDE.md` imports it and adds
  only what is true of this repository (how `sor` is called here, how to run the tests, `sync-tools.sh`); `AGENTS.md`
  points to it and adds what other agents need. Three copies had drifted within a day (`CLAUDE.md` lacked the newest
  commands), and a test now fails when the files stop pointing at the one text or the text stops naming a command.
- **Documents are checked against the code** (`tools/test_sor_docs.py`): every command, flag and `SOR_` variable a document names must exist
  (asked of the tool's own parser), every number it gives must equal the constant in the code, the readability limits are
  stated only in SPEC §13 and the cheat sheet generated from it, the plugin has one name everywhere, and every path and §N a document
  cites must exist. The order of authority when two disagree: the code, SPEC.md, the skill, everything else. Meaning (does a
  sentence still describe what the tool does?) cannot be tested: that takes a reviewer with a fixed rubric, run once after a large change. The first one (2026-10-19) found 15 contradictions between the documents and the code, all fixed; the ones a test can hold are tests now.
- **Normative wording:** MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY mean what RFC 2119 and RFC 8174 say, in
  capitals only, and only where an existing sentence already stated a requirement; no sentence was reworded. "Never"
  has no such form and stays lower case. An optional sentence pattern for rules (EARS: `When <trigger>, <thing> does
  <what>.`) is offered as a style, and nothing checks it.
- **A table of what is checked:** SPEC §15 says for each main statement whether `sor check`, `sor status`, `sor lock`,
  `sor test`, the hook or only convention makes sure of it.

Deliberately not adopted:
- **Priorities, plans and task lists.** The spec says how the thing works now. A list of what to do next is stale the
  day it is written, and `sor status` and `sor changes` already say what is pending.
- **Delta folders** (OpenSpec's `changes/`, merged into the specs when archived). The lock is the delta: it compares the
  clauses with the last accepted state, and version control keeps the history. A second place where a change lives
  would have to be kept in step with the first.
- **Linking a spec to whole code files** (Tessl). The legacy Framework (last in CLI 0.28.0) generated one file from each spec:
  Böckeler's hands-on review says so and adds that it may change. The current tile lists the files a spec covers in its
  `targets:` frontmatter, as paths or globs, so one spec can cover many files (whether several specs may share a file is not
  documented). Both link a spec to files. For the tile this was checked (2026-10-19): its format page has no requirement ids
  and no way to point at a function, a line or a single test; `[@test]` links name files. For the Framework it follows from
  its one file per spec but is not stated by Tessl. Here a clause is marked
  on any lines of any file, a region may serve several clauses, and a table row may have a line of its own. The
  one-HTML-file solar system needed a split into 8 generated files plus a hand-written bundle step under the Framework's one
  file per spec (`comparisons/tessl/NOTES.md`); the tile's `targets:` globs would probably not need it (not tried).
  Corrected 2026-10-19: this item first gave one spec per file as Tessl's mapping in general.

## The solar-system example, restructured to the format (2026-10-19)
The example was still written in the plain style of the first drafts: no `Why:`, no section names, 12, 9 and 18 rules in one
section, and `sor check` listed 12 notes against it. Now: every part has `Why:` and the sections `## Rules`, `## Approach`,
`## Tests`; `screen` became a folder (`screen/view`, `scene`, `select`, `hud`), the clock rules (`start`, `slider`,
`speed`, `pause`, `real-time`) moved to `clock`, and how the bodies are drawn (`colors`, `light`, `ring`, `fun-facts`)
to `looks`. Every sentence was moved, none reworded: only references changed (`{screen/sky}` is `{screen/scene/sky}`),
and the 23 `@clause` marker lines in `out/index.html` follow the new ids. Notes went from 12 to 7; the 7 left are tests
that prove one rule with many lines (`ui-colors` checks 7 colors, `click` 3 sizes and a reach), and a test must be named
after the item it proves (SPEC §8), so splitting them would need a rule per half. Two phases that another test already
proves word for word were dropped from `speed` and `zoom`. Same result as before: 35 pass, 4 by hand, clause coverage 90.5%.
Venus is 12 in the code now: the clause had been changed by a person and the page not rebuilt.
- The restructure showed a gap in `sor lock <part>`: the old entries of an item that moved out stayed in the lock, because
  a part's footprint only covered its current items. Fixed (SPEC §16) and tested.

## Bugfixes and tickets (2026-10-19)
Decided with the user: a bug report, for example a Jira ticket, is handled inside the format that exists, without bugfix
documents. My default was to add no new keyword; the user then agreed to `proves:` (below).
- **Where a bug is recorded:** on a test, as `bug: <ticket id or words>`. Not on the clause (its text is locked, so an id
  there forces a recompile and goes stale; "the spec says how it works now"), not in code comments (marker → clause → test →
  ticket is the chain), and the history is whatever version control the project uses (environment agnostic).
- **The ticket is input, not authority.** Three questions before an edit: is it a bug against a clause, must the clause
  change, must the code change. A ticket that contradicts a clause gets an `open:` question for the owner, never a rewrite,
  and the agent never writes back to the ticket system unless asked. The cases are in the skill's `reference/bugs.md`.
- **A gap found on the way, fixed:** the guard knew a test only by the name of its item, but SPEC §8 says a test proves
  everything its `expect:` refers to. A bug fix that added a second test (own `do:`, own `bug:`) was refused. Now
  `Project.tests_of` is the one relation: the guard, `sor status` ("fixing") and a scoped lock use it. A value or row
  reference counts for the item that owns it; a `do:` reference does not.
- **Found while verifying (real headless Brave, solar-system copy):** a second test could only be linked through a value
  or a table row, because `expect: {item}` alone is accepted by `sor check` and the guard but is not a line `sor test` can
  run ("cannot read"). In the example 20 of 40 rules have neither, and 2 of the 7 "split this test" notes are on such rules.
- **Built, after the user said yes: `proves: {clause}` on a test.** The format already links a code test to its clauses
  with `@clause test <ids>`; a spec test had only the accident of a value reference. `proves:` is read as a reference
  (braces), so it needs no parser of its own: the lock records it, the test goes stale when the clause changes, and a
  broken one is a problem. `Project.proof_links` is the one place that says what a test proves (name, `expect:` /
  `measure:` references with their aliases `then:` `should:` `shows:`, and `proves:`); the guard, status, scoped lock,
  clause coverage, `sor test <item>` and `sor show <item>` all ask it. `sor check` also reports `proves:` on a rule, on a
  value or a part, `proves:` without a reference, and `expect: {ref}` alone (pointing to `proves:`). A test named after
  nothing needs `proves:` or `bug:`. `Test.steps` needed the keyword too: unknown, it was glued onto the line above.
  Not changed: claims still hold only an item's own test; strength testing mutates values and ignores `proves:`, so it
  cannot tell a `proves:` line that checks nothing, as with `@clause test`.
- **Wider than before, on purpose:** in the example, `year` is proven by `test:year`, `clock/test:speed` (it refers to
  `{year.days}`) and `targets/web/test:probes`, so a new or changed one of those frees `year`'s code. That is SPEC §8 read
  literally. Claims still hold only an item's own test.
- **Borrowed:** from Kiro, the test that fails before the fix and passes after ([bugfix specs](https://kiro.dev/docs/specs/bugfix-specs/));
  from Spec Kit, assessing before fixing ([README](https://github.com/github/spec-kit)), as the triage above.
- **Not borrowed:** Kiro's `bugfix.md` and Spec Kit's per-bug folders (the delta-folder model rejected earlier), OpenSpec
  deltas, CodeSpeak's change requests (consumed, no history), BMAD's prose note and Tessl's HTML comment (not executable).
  Kiro's "SHALL CONTINUE TO" is already covered by the lock plus the existing tests and `unchanged`.
- **Not claimed:** a wording-only clause fix locks without touching the code because the lock trusts the caller. That is a
  convenience and not a safety property: the tool cannot tell a wording fix from a change of behaviour.

## Loose tests (2026-10-19)
A person may write a test loosely ("test that the moon circles around") and the AI builds the real test from it. The user
asked for a pointer to the `## Tests` section; I recommended a pointer to the person's line instead (below) and the user did
not object. The user did say yes to the warning for loose text.
- **Why a line and not the section:** a bullet is an item with a lock entry. Rewording it makes `sor status` flag the test and
  name the test code (`@clause test bodies/moon`) to look at again; a pointer to the section could not say which line changed.
  This is the plain format that already existed (SPEC §15): an unnamed bullet is a draft, the AI tidies it.
- **A gap closed:** a sentence outside any bullet (or a line that continues a bullet without indent) belonged to no item and
  was ignored without a word, so editing it was invisible. `sor check` now notes it as `loose text` (a note, never a block;
  `--strict` makes it exit 2). Fenced blocks, HTML comments, deeper headings and rules are not loose. A draft test used to
  say "orphan test **~4ef269**"; it is now `unnamed test`, quotes the person's words and says to name it after the rule it
  proves. A draft test is still a problem until then, so `sor lock` waits for the AI's tidy step: the intended order.
- **Found by checking with the advisor:** (1) the header reads the title, one `Why:` sentence and settings, so a second line
  under the title was dropped silently too; `loose text` now covers it. It fires on three parts of the VS Code extension's
  spec whose `Why:` sentence wraps onto a second line (`preview.md`, `project.md`, `state.md`): that second line was never
  locked. Left for that project's owner to join. (2) SPEC said nothing can point at a draft, but a marker naming one was
  accepted; its id changes whenever the words do, so `sor check` now refuses it ("name it first"). (3) A loose test in a
  project with a web target showed as FAILED in `sor test` (it has no `do:` / `expect:` lines), and `--run-tests` could not
  take the framework's result next to it. Built after the user's yes: such a test is EXTERNAL (not run, not failed) and
  `--run-tests --results F` takes its result from F, for external tests only. Checking it showed that the hand-written test
  file is not read at all when the web target declares only the page, so the folder must be declared (`{path: test/}`),
  and every line in it needs a marker; the skill says so. External tests do not count toward `sor test`'s clause coverage.
- **Not built:** a marker that points at a section. The test code points at an item (`@clause test <part>/<name>`), and
  `@clause test <part>` stays refused.

## Coverage of the tool (2026-10-19)
`sh tools/coverage.sh` measures `tools/` over its own tests, subprocesses included (`.coveragerc`, a `sitecustomize` that
starts coverage, `coverage` only in an ignored `.venv-coverage`: the tool itself stays standard-library only). From 81.7% the
suite alone went to 92.7% (lines and branches together). Ranked by what a regression would break, not by line count:
`sor status --json` with findings (the extension reads it), the text forms of `sor markers` and `sor show`, the lock's
refusals (shared code, `--confirm` outside the scope), what `sor check` says about markers and anchors, Python and nested
`code:` anchors, alias values in the lock, `git blame`, and the messages for a test written wrong (checked by compiling, no
browser). The first run of the new tests found a bug: `sor show` on a table row id crashed (fixed).
- **Left uncovered on purpose:** the browser code (`cdp.py` is 27% in the suite, about 85% with one real `sor test` run, and
  the same lines of `testrun`), and defensive branches (OSError and temp-file cleanup, Windows, very large WebSocket frames,
  decode errors in the marker scanner). An opt-in browser test that skips without Chrome is the way to cover the first group.
- No `pragma: no cover` was added.

## The skill, restructured (2026-10-20)
A review of the skill for density (14 findings) led to a restructure, planned and checked twice with the advisor before it
was applied. `SKILL.md` went from 129 lines and 2,000 words to 127 and about 1,710, the description from 566 to 362
characters (above the 320 aimed for), the longest body line from 250 to 167.
- **Shape:** one "Which situation?" table instead of one section per situation; a routine as a list instead of a
  paragraph; the Locking table holds only the three forms of the command, the constraints are a list; the Rules are
  three groups. "Plain-written clauses" and the loose-test paragraph moved to `reference/plain-clauses.md`.
- **Dropped on purpose (veto any):** the sentence `Never say "the lock still holds"` (the bullet on explaining the tool's
  words stays), the final "Report which clauses changed" bullet (the routine says it), the lists of note kinds and of
  status blocks (they went stale, as the review showed), the legacy names `sor/CLAUSES.md` and `clauses-lock.json` in
  the description. The advisor found three more instructions dropped by mistake (fix what fails before locking, the
  `manual:` way out for a test nobody can run yet, that `sor check` reports unfilled placeholders): restored.
- **Checked with fresh headless agents**, old skill against new, same flags, a fresh copy of the example each time:
  the Jupiter change with and without naming Spec of Record, a new project in an empty folder, and the Jupiter change
  with an unnamed test bullet planted (it reaches `plain-clauses.md`). All 16 runs ended with the specs, code and lock
  in agreement, claims released, and no code written for the new project. `sor status` between the clause edit and the
  code edit was done in 3 of 6 old runs and 3 of 7 new runs (the Jupiter runs and the planted-bullet runs; the
  planted-bullet part is read from the call sequences), so both arms skipped it about as often. The sample cannot tell
  the arms apart, and cost per run was flat ($0.34 to $0.49). Not exercised: bugs, existing code, keeping a person's
  change, parallel agents.
- **The description must stay scoped to Spec of Record projects.** A tightening pass listed "start a new project",
  "work beside other agents" and "change what the software does" as separate triggers, and in a plain folder the prompt
  "Start a new project: a small command-line todo list in Python" then loaded the skill and created a `sor/` folder in
  2 of 2 runs. With the qualifier (mention, or a `sor/SPECOFRECORD.md`, and the work is one of the three) it did so in
  0 of 2; "Make the title bigger" in a plain page loaded it in 0 of 4 runs, "Put this page under Spec of Record" in 2 of
  2, and the Jupiter change without any mention still loads it (2 of 2). Do not drop the qualifier again to save words.

## What the engine runs left (2026-10-20)
The engine passes (`FINDINGS.md`, passes 3 to 6) and a second review of the skill were walked through one by one, each
probed with one command in a temporary project, never in the engine project itself.
- **Changed:** (1) A skeleton made with `--why` may be written whole once, like a plain one: the hook reads the sentence
  from the file's `Why:` line and makes the skeleton again with it, so the exception is gone from the skill. The one
  thing a Write can now erase unnoticed is an edit to that line alone. (2) `sor parts [PART ...]` shows those parts and the
  parts inside them, as `sor check` does; the engine's 200-part index was cut off by the harness. (3) `claim` and `lock`
  say what to write instead when an id has the root in front (`SPECOFRECORD/year`, `ROOT/year`; root items have no
  prefix). (4) Docs: the skill says `--as` is for claim, lock and release only; `parallel-agents.md` says to claim
  items, not whole parts, when others work in the same part; `plain-clauses.md` says what `loose text` is and when a loose
  test gets `do:`/`expect:` lines and when it goes in the project's framework; a docs test ties the output the skill quotes
  (refusal prefixes, `REFUSED`, `unnamed test`, `loose text`, `tests (N)`, `<fill in:`) to the tool's source.
- **Built after a yes (2026-10-20), the two design questions:**
  - **`value twice`.** `sor check` notes a `{name: value}` that another part defines with the same name and the same text
    (case and spacing aside), at each definition and naming the others, with both ways out: keep one and refer to it, or
    rename if they are different quantities. Not counted: tests, table cells, `{v: = x}` aliases, generated parts, and the
    same name with a different text. The different-text case was left out on purpose: measured on the real projects it
    gives 6 permanent notes on solar-system (`min`, `max`, `size`, `days`, `start`) and would flag the glossary fields of
    the engine (`term`, `meaning`, `owner`), which can never be fixed. With the rule as built: 0 notes on solar-system,
    the extension spec and the final engine snapshot; 9 on the engine after pass 1 (63 parts, 4 names); 93 at
    the end of pass 2 (201 parts, 44 names), the state the third pass deduplicated, the copies the agents found with a script.
  - **A scoped lock waits for its own items.** A problem of one item's own text (`broken`, `needs`, `proves`, `expect`) in
    an item the lock does not cover no longer keeps the lock from happening, even in the same file; the lock says how many
    it left out, writes only its own entries, and `sor status` and `sor check` still list the problem. It is narrower than
    what was agreed ("ignore a problem in an item outside the lock"): a draft test (`unnamed test`) and an unfilled
    `<fill in …>` still block wherever they sit, because "Loose tests" records that a draft test keeps `sor lock` waiting
    for the tidy step, and a placeholder outside the scope is nearly always someone's half-filled skeleton. A problem that
    is no item's own text (a heading written twice, a name used twice) and `lock --all` still block. A refusal names the
    agent that holds the item the line lies in. Overrule by moving a kind into or out of `ITEM_LOCAL` in `cli.py`.
- **Already fixed before (passes 1 and 2 are all closed):** `sor` on the PATH, Write over a skeleton, `never run` and
  `heading` and `duplicate` notes (a second `## Approach` and a repeated test name are reported, probed), release by
  name, child-part locks, the expired-claim message, part and item names sharing one set of ids (in the cheat sheet),
  the `--as` error naming the commands that take it, the 80-word limit, `sor check PART`, the broken-pipe traceback,
  "did you mean" on references, references in table cells, refusals naming only the blocked ids, `{part/item.value}` in
  the cheat sheet, the 30-minute claim lifetime in the docs.
- **By design, not changed:** table rows are items, so `sor changes` lists a changed row (it is what a claim, a marker
  and a lock key point at); `open:` lines are unchecked on purpose; a claim on a part holds its items (SPEC §16); claim
  times are shown in local time like `date` (not reproduced); a `{name: value}` counts as two words against the 80 (words
  are split at spaces); a reference to a part that is still a skeleton resolves, and `sor check` reports its
  placeholders anyway; the 7-rule cap shows as a note; "broken {x}" already says it looked for an item, row, value or part.
- **Design questions, not built, need a yes:** a check for references that point upward (what "upward" means is
  project-specific: the engine's `layers` rule); a child part named like a top-level part shadowing it; a rename-value
  command.
- **Not tool problems:** the harness refusing compound commands, heredocs and `sed -i` in background sub-agents.

## Tests that CI proves (2026-10-21)
A generic tool cannot assume every test runs on the machine of the person who locks: an integration test reads a database
replica for an hour, a rendering test needs a GPU, a UI test must pass on three operating systems. Before this, a lock was refused
until every test that is not manual had a passing result, so such tests either blocked every lock or were faked. Decided with the user;
the three questions it left open were settled by defaults, to overturn if wrong:
- **One line, `runs on:`, not `needs:` and not a generic tag.** `needs` already means "what a part uses from other parts" (SPEC §7), and
  a tag that skips mixes labelling with skipping: the first `db` or `smoke` label would drop a test from every local run. `runs on:`
  names where a test can run and carries no other meaning; a test without it always runs, so a forgotten line costs time and never
  hides a test. Several environments are separated by commas, names one machine must have together by a plus (`linux+db`).
- **The lock records `deferred` from the spec alone, and never a result of a job.** The lock has no timestamps and no measurements, and
  benchmark results already never go into it (SPEC §8); a Windows pass next to a Linux failure would break both and every job would
  rewrite the same lines. So the build record keeps what was agreed locally, and what each job proved goes into its own evidence file.
  Rejected: carrying a pass forward in the lock until the test or its code changes (as manual confirmations are); it puts a result of
  one machine in a file all machines share, and the fingerprint it needs is the evidence's, not the lock's.
- **Evidence: one file per job, a fingerprint per test, no timestamps.** `{job, provides, results}`; the fingerprint hashes the test, what it
  refers to, and the text, rows, values and code of every clause it proves (the manual-confirmation check looks only at the clause the
  test is named after, which is not enough for a test that proves others with `proves:`). Jobs never write the same file. Whether the files
  are committed or kept as CI artifacts is the team's choice; the tool reads files and folders either way.
- **`sor verify` is the gate** (exit 0, 1 for a missing, stale or failed environment, 2 for bad input). A current failure is not outvoted by another
  job's pass. Neither `sor status` nor `sor check --strict` could be the gate: `sor status` reports tests that had not passed without
  changing its exit code, and the notes of `sor check` say nothing about results.
- **Found in review, fixed:** a `runs on:` line under anything but a test is plain text, not a problem, so an existing rule that says
  `  runs on: macOS 14` stays valid; `sor lock` names the tests that just became deferred, because one line is all it takes to leave a test
  to CI; `sor verify` searches folders all the way down, as an artifact download makes one folder per artifact; a job's results file may
  hold tests that are not kept, whatever their status; a job name that is not a string, or is a Windows device name, is refused.
  Open: evidence files have no format version and no reference to the commit or CI run they came from, and the fingerprint does not cover
  code a test only uses as input.
- **Not done, to decide later:** a scoped `sor lock --run-tests` still runs every test and drops the results outside the scope (running only the
  tests a lock needs would make clause-coverage budgets fail on a partial run); a failure only CI sees does not free the code of a bug fix, because
  the edit guard reads the lock; benchmark metrics and `each: N ×` generators are still not built, which is where a quick-and-extended split would
  matter most.

## Still open
- `tools/sor.py` checks, locks, reports status, runs web tests and measures coverage for
  this format (SPEC §15). The old `fdd` prototype (previous syntax) is not in this folder.
- The example's `quality` clause asks for 90% clause coverage and gets 90.5%, with one confirmed check: `test:delivery`
  was confirmed by a person (`sor lock --run-tests --confirm test:delivery`) and stays confirmed while its text is
  unchanged. Three tests can only be done by a person: `clock/test:real-time`, `looks/test:light` and `test:devices`
  (by hand or by eye); `out-of-scope` and `quality` cannot be proven by a test.
- Code stays in its own files, not inside the spec files: clauses-first is enforced by the
  tools instead (drift in `sor status`, a refused `sor lock`, and the edit hook), and
  `sor show` gives the one-document view.
- The cheat sheet is over 70 lines: over its own one-screen rule, because the worked example needs room.
- Fixed in the example: reset now keeps play/pause and only "when the app opens" starts
  running; the time display starts at "Year 0, day 0".

## Lessons from a first real project (a game engine, built by the AI from a few words)
- The plugin copy in `<project>/.claude/skills/` holds `@clause` examples. With no code path declared yet the
  scanner read the whole project, so it reported 133 problems and recorded glue entries for the plugin's own
  files. Fix: dot folders are never scanned.
- A file that is only glue (`engine/__init__.py`) belongs to no clause, so a scoped lock never accepted it and
  `sor status` stayed pending; the AI then used `lock --all`. Fix: such glue goes with every scoped lock, and a scoped
  lock says what is still pending outside it, so `--all` is not the way out.
- The lock path was printed relative to the shell's folder (`../../../clauses/...`): now relative to the project.
- The AI told the user "the lock still holds", and the user asked "which lock?". The skill now says to speak of
  the agreed state, and to explain the file only when asked.
