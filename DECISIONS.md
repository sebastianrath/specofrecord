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
  Evidence files now have a format number and may say which commit and CI run wrote them (see "Evidence has a format number"). Open: the
  fingerprint does not cover code a test only uses as input. A tool that hashes code differently gives other fingerprints (the Python rule did), so the evidence of a
  project that upgrades reads as stale until its jobs run again; that is by design, and the jobs write it fresh.
- **Not done, to decide later:** a scoped `sor lock --run-tests` still runs every test and drops the results outside the scope (running only the
  tests a lock needs would make clause-coverage budgets fail on a partial run); a failure only CI sees does not free the code of a bug fix, because
  the edit guard reads the lock; benchmark metrics and `each: N ×` generators are still not built, which is where a quick-and-extended split would
  matter most.

## Code is hashed by the rule of its file type (2026-10-21)
Shown in a temporary project, in any Python project under SoR: moving `return t` into a `for` loop changed what a function returns, and
`sor status` said "clauses, code and lock agree"; editing only a `#` comment inside a region was drift. The lock hashed every file with
one C-family rule: it stripped `//`, `/* */` and `<!-- -->` lines and all indentation. Found while exploring more than one code target
(`proposals/multi-target.md`), but it is a bug of single-target projects, so it is fixed first and on its own. Decided with the user:
- **The rule follows the type of the file, not the target.** A single target can mix types (C++ and Objective-C++, HTML and JS and CSS), and
  adding `#` to the comment pattern for everyone would hide `#define` and `#include` changes in C. Python keeps its nesting, counted in levels
  so a consistent change from 2 spaces to 4 is not a change. Shell, Ruby, Perl, R and TOML get `#` comments, SQL, Lua and Haskell get `--`.
  Every type not listed keeps the old rule, and a test pins three hashes made before the change.
- **A lock written under the old rule is not drift.** `sor lock` refuses on drift, so without a way through a Python project would be stuck on
  the day it upgrades. An entry whose code is unchanged under the old rule is read as unchanged, `sor status` says how many there are, and
  `sor lock --rehash` rewrites exactly those hashes: no text, refs or result is touched and nothing is accepted. Rejected: a version number in
  the lock (a lock format version is the next phase of the multi-target proposal, and an old tool must refuse a newer lock), and rewriting
  on every lock (it would accept other agents' unfinished work).
- **The cost, said in the status note and the SPEC.** Until the rewrite, a change that only the old rule ignores (a Python line moved into a
  loop) is read as unchanged, because the old hash cannot tell it from the original.
- **Version skew, shown:** the new tool reads an old lock correctly, but an old tool reads a lock the new one wrote as drift on every Python
  region and refuses to lock. Older copies are normal (a project keeps its own copy of the tool, and the editor extension prefers it), and an
  evidence fingerprint of a test that proves Python clauses differs between the two, so a job and a gate on different versions would show
  STALE. Update every copy together; a lock format version, which makes an old tool refuse with a message, is the next phase of the proposal.
- **`sor status --json` does not say that hashes wait for the rewrite**, only the text does, because the JSON keys are pinned by a contract test.
  The skill does not name `--rehash` either; it is a one-time migration.
- **Not covered:** YAML and Makefiles, where indentation is meaning too; Ruby and Perl block comments; comments over several lines in SQL, Lua
  and Haskell. Python is read with a small scanner and not with `tokenize`, because a region is often a fragment (a method, a branch) that
  `tokenize` refuses; the tests use `tokenize` as the judge instead (`tools/test_sor_normalize_oracle.py`).
- **Found in review, fixed:**
  - *Python:* a string that a backslash at the end of the line continues left the scanner blind to the lines after it (a bracket in it opened a
    statement that never ended, a `#` line in it was dropped); a closer of one quote is now found by its own length; a region that dips below its
    first line is counted in levels below it (`-1:`) and no longer takes that line as its new first, which hid a change to the first line;
    a coding cookie is code.
  - *Other types:* `#` lines inside here-documents and strings that go over several lines (shell, Ruby, Perl, TOML) are text. The scanner assumes
    a quote is open whenever it cannot tell, which can only keep a comment as code. `--` lines that Haskell reads as an operator (`-->`) are code,
    and the one-line `/* */` comment the old rule dropped is still dropped in SQL. Ruby magic comments are code.
  - *Lines:* a line ends only at a line feed or carriage return, as in an editor; `splitlines` also split at a form feed, so every region after one
    had line numbers no editor shows (a form feed on its own line is common in GNU C). The lock hash differs only for a form feed or separator
    inside a line of a region, which is rare.
  - *Migration:* `sor lock IDS` reads the old lock upgraded, so a clause that shares code and has no change of its own is not pulled in, and the old rule
    is worked out only when a hash differs (`sor status` took 0.17 s against 0.11 s on 480 Python regions, and each scan now works its hashes out once); `--rehash` without a lock says there is none.
  - *Evidence:* the fingerprint covers the code marked with a row and the test's own rows and values; `sor test --strength` takes `--provides` and
    `--all` like `sor test`; a results file that is `null` or missing is refused.
  - *Docs:* the README no longer links the page that was removed.

## The lock has a format number (2026-10-21)
Phase 1 of `proposals/multi-target.md`: a later phase changes the shape of the lock (a line per clause and target), and an older tool
would read those lines as removed entries or as drift. Built on the user's go-ahead for Phase 1; the shape of the marker and the hook's
behavior come from trying the tool as it was and from the advisor's review. Nothing in the lock changes yet.
- **Format 1 has no marker, and nothing writes one yet.** A lock made before the number existed is format 1, and a single-target project
  keeps the same bytes (a test renders both real locks and compares). Only a later format opens the file with `"*format": N`.
- **The marker is a number, not an entry, and its key starts with `*`.** Shown with the tool as it was: a marker written as an entry is
  listed by an older `sor status` as "removed" and silently dropped by the next `sor lock`, which would also drop per-target lines (and
  an older `status` says "delete its code" for a removed line that has code). A plain number makes the older tool stop with an
  `AttributeError` on `status`, `lock` and `changes` before it writes anything. No item name can start with `*` (names stop at `*`) and
  every other key has a prefix of its own. A part file whose name starts with `*` is not refused; reserved names are Phase 2's checks.
- **One check, in the one place the lock is read.** `lockfile.read` raises `LockFormatError` for a number it does not know or one that is no
  whole number from 1 up; `main` prints it to stderr and exits 2. That covers `status`, every form of `lock` (the scoped re-read too),
  `--rehash`, `changes`, and `test` when it runs tests. `write` re-reads the file's marker right before it replaces it, so a newer tool's
  lock written in between is not overwritten. A lock that cannot be read at all is still replaced, as before. The caller chooses the
  number it writes (`write(..., fmt=N)`); the marker is not kept from what was read, because Phase 3 decides from the entries.
- **The edit hook refuses edits to code** with the same message, since it cannot tell what drifted; clause edits stay free, and reading code
  answers without the list of pending changes.
- **Known cost, shown:** a tool older than the number stops with a Python error, not a message, and nothing now can change that. Its edit
  hook fails open (exit 1, the error on stderr, the edit goes through), so on a newer lock an old copy's guard is off. Only the number
  helps a lock from the tools that have it: update every copy (project, plugin, extension) before a format above 1 is written. The VS Code
  extension runs `sor markers --json` and `sor status --json` together, so a lock it cannot read blanks the lenses of that project and the
  reason appears only in the "Spec of Record" output channel.
- **Not versioned:** the claims file, evidence files (their missing format number and provenance are still open) and `markers --json`,
  which has its own `version`.

## Evidence has a format number (2026-10-21)
The lock got a format number in Phase 1; evidence files, the other file a later phase changes, get one before anyone has committed any.
- **The same pattern as the lock.** Format 1 is `{job, provides, results}` with no marker, so a job that changes nothing writes the same
  bytes. A later format opens with `"format": N`, and a tool that reads a number it does not know refuses with exit 2 and a message to update.
- **Provenance is format 2.** `--commit SHA` and `--run ID` (explicit flags: no timestamps, and no environment variable is read) write
  `"format": 2` and `"from": {commit, run}`. Both are tokens, not free text: a commit is 7 to 64 hexadecimal digits, a run id letters,
  digits, dots, dashes and underscores. `sor verify` names them next to the job and has them under `sources` in `--json`. The gate does not
  use them: a result counts by its fingerprint, not by the commit it ran on.
- **Old readers refuse loudly.** The reader of a tool from before the number accepts exactly three keys, so it refuses a format 2 file
  (exit 2, "exactly the keys job, provides and results") instead of misreading it; shown by running `sor verify` of the tool before this change
  on a format 2 file. That is the wanted property, and the reason provenance
  is a format and not an optional extra key.
- **Not done:** the claims file is still unversioned. Claims last 30 minutes, so a file from another version rarely meets a reader.

## Targets own folders, and a region says which one (2026-10-21)
Phase 2 of `proposals/multi-target.md`. It reads and reports; the lock is untouched (a test compares a two-target project's lock keys with the
snapshot and finds no target in them). Checked first against `examples/solar-system`, `editors/vscode` and a large outside project (one target
each, no `Source: code at`, no `@` in any name): `sor check`, `sor status --json` and `sor markers --json` give the same output as before,
apart from the new field.
- **A file belongs to the target whose path is the longest prefix.** One target may have several paths (the web target has a page and a folder
  of tests; the outside project's has `src/` and `src/tests/`), which is not an overlap. A deeper path of another target wins. Only the same
  path named by two targets is a problem, and then no file belongs to either.
- **The region field is `targetName`, not `target`.** `target` is already in the index for an anchor region (the `code: path#name` text),
  and the extension compares it. `version` stays 2; the extension ignores a field it does not read.
- **What is a problem and what is not.** Always: a reserved target name (`glue`, `test`, `ROOT`), the same path in two targets, a part name
  that starts with `*` (it would collide with the lock's marker key). Only with two targets or more: a `Source: code at` area in no target's
  path, and a `runs on:` environment named like a target. Those two would break a one-target project for nothing, so it is told none of it.
- **`no code for target` is a note, one per target,** `N clause(s) have code in py but none in ts`. A clause with no code anywhere (a rule
  such as `out-of-scope`), glue and test code are not counted, or every project would be flooded. It is a note and not a status line, so the
  JSON of `sor status` (pinned by a contract test) gets no new key.
- **`@` in names is not restricted here.** Phase 3 reports a collision of `clause@target` with a real key when it happens, as it does for any
  id, instead of forbidding a character now in projects that may use it.
- `sor check` now hands its scan to the notes, so a project with several targets is not scanned twice.

## The hashing rules are pinned by rows any implementation can run (2026-10-21)
`proposals/multi-target.md` ends with the aim of a TypeScript copy of the tool, so that an editor needs no Python. Two copies that disagree on
a hash would read each other's lock as drift, so the rules are written down as data before there is a second copy.
- **`vectors/hashing.json`, language neutral,** with six kinds of rows: the style of a path, the splitting of lines, the normalization of
  code, the hash of the regions of a clause (order, join and rule per file type), the hash of a text, and the exact text of a lock file.
  The rows number in the dozens, each with a name so a failure names it. It sits outside `tools/` on purpose: that folder is copied into the plugin and the
  extension, and the rows are for implementations, not for users of one.
- **Written by hand, hashed independently.** The expected texts were derived from the rules, and each hash was computed with SHA-256 alone.
  The three hashes the tool had pinned (TypeScript, C, HTML) came out the same, which is the check that the rows are not just the tool's output
  copied back. Mutation checks (a changed join, separator, line splitter, level rule or style table) each fail named rows.
- **Pins what is, quirks included.** A line that starts with `/*` and ends with `*/` is a comment even with code between: a known limit of the
  C-family rule that locks already depend on, so it is a row, marked as a limit.
- `markers.code_hash` is the one function that hashes the regions of a clause, so the rows test the real path and not a copy of it.
- **Not covered:** the evidence fingerprint and the status of a clause, which need a parsed project; a port needs the model first.

## Code per target in the lock: lines, `built`, and "behind" (2026-10-21)
Phase 3, first slice, of `proposals/multi-target.md`. Built on the decisions of that day: a line per clause and target, a root default with part
overrides, and a lock that refuses while a target is behind unless a flag allows it. Checked on a scratch copy of a large outside project
(274 parts, 1142 regions): adding `Targets: native` shows only the root file as changed, locking writes 460 lines (the lock grows 8%),
a second lock gives the same bytes, and `sor status` takes 0.5 s.
- **File shape, memory shape.** In the file a clause keeps `text` and `refs`, and each target with code has its own line `K@t` (`kind: code`,
  `of`, `target`, `code`, `built`); the clause has no `code`, so two agents on two languages write different lines. In memory `read` folds the
  lines into the clause's entry (`entry['targets']`) and sets its `code` to a digest of the targets', and `write` unfolds them. That is why
  `checked_manual`, the evidence fingerprint, status, the scope of a lock, the hook and claims did not change: each still compares one `code`.
  Rejected: a joined `code` kept on the clause line (a lock of one language would accept the other's unfinished code, and two agents would
  write the same line) and lines everywhere in the code of the tool (every reader of `code` rewritten).
- **The format follows the entries.** `render` writes format 2, with its marker, exactly when a clause has lines, and refuses a caller that
  names a lower number; a project with no lines keeps format 1 and its bytes (the render test of both real locks covers it). Tests and glue
  keep one joined hash, and code in no target's path is under the target `*`, which no part name can start with.
- **Opt-in by the root file.** `Targets: py, ts` in `SPECOFRECORD.md` turns it on; a part's `Targets:` overrides it for the part and the parts
  inside. Two targets without the line keep the old lock. A lock made before is read as it is (one joined hash per clause, no drift, nothing
  behind) and a clause moves to lines when it is next locked, trusting its code then (`built` = the text). A lock may hold both kinds, and a
  project that drops the line is read the same way back.
- **Behind.** A target that applies to a clause is behind when its line's `built` is not the locked text. Locking gives a target `built` = the
  text only if its code is new or changed since the last lock, so a language nobody touched falls behind when the clause changes, and a language
  a person changed stays current. `sor status` lists it with the recompile group (a finding with the target in its detail, so the JSON has no new
  key); drift names the languages that moved; rebuilding a language that is behind is "behind (being rebuilt)" and not drift, so the edit guard lets
  it through while drift in a second language is refused (the guard compares a finding by its key and detail).
- **The lock refuses, a flag allows.** `sor lock` names the targets that would stay behind. `--allow-behind ts` locks the clause anyway and `ts`
  stays listed until its code changes. There is no way to say that a language already fits a changed clause, which is the conservative choice
  and the user's to override: a wording change costs a code change in every language, or the flag. The skill tells an agent to rebuild, and to use
  the flag only when the user says so.
- **Not done, and why.** Per-target test results (a test's result per language, `--results id@py`) and per-target claims and locks (one agent
  per language on one clause) are the next slices. Both change what "a test passed" and "a clause is locked" mean, and the second needs a lock
  of one language to accept the clause's text, which is not decided. They are open in the proposal.
- **A table's cells are part of the clause.** The text hash of an item holds the names of its rows and not their cells, and a table's code is
  usually marked with the item, so `built` is compared with the item's text plus the text of each row that has no lines of its own. Without it
  a spec-only change to a cell left every language current (shown, then fixed, and tested). A row with lines of its own is behind on its own, and
  marking a row after the item was locked counts as a change of the item. A part's own regions are not widened to the rules of its items.
- **Tests of a clause that is behind.** `sor status` does not list them as waiting for a result (`pending_tests` leaves `behind` out): the
  clause cannot be locked while it is behind, and the lock that clears it resets and requires the results of what it locks, as it does for a
  changed clause. Per-target results, which would say in which language a test passed, are the open slice.
- **Known:** the VS Code extension does not know the status `behind`: its `classOf` returns nothing for it and the finding is skipped (as it
  already is for `built`, `fixing` and `glue`), so a clause that is only behind shows as agreed in its lenses and status bar (the JS is its own
  project and not changed here). A key `K@t` that is also the name of something else is a problem in `sor check`. Evidence fingerprints change when a project starts
  keeping its code per target, so its jobs write the evidence again.
- `Region.normalized` works out a region's normalized code once; both hashes of a clause need it, and `sor status` on that project went from
  0.73 s to 0.5 s.

## The Python scanner reads f-strings (2026-10-21)
Shown on Python 3.13: `f"{s.replace("(", "")}"` is valid since 3.12, and the scanner took it for the string `f"{s.replace("`, a loose `(`, and a
string again. The `(` stayed open, so every later line of the region counted as the continuation of a statement, got no level, and moving
`return None` into the `if` above it gave the same hash. Only indentation was blind, and only for the rest of that region; changed words were
still seen, and the standard library hardly ever does this (500 files, none of the 165 with f-strings broke either scanner).
- **The end of an f-string is found by reading its fields.** A frame stack replaces the one open quote: a string, the text of an f-string, the
  code of a replacement field with the brackets open in it, and a format spec. Inside a field a quote starts a string of its own (an f-string
  too, from its prefix), a colon outside brackets starts the spec, `{` in a spec opens a field, and `#` starts a comment to the end of the line.
  `{{`, `}}` and `\N{NAME}` are text. The end of a name such as `if` in `if"x"` is not a prefix. For what Python 3.9 reads, it gives the answers
  it gave.
- **Template strings too.** Python 3.14 adds `t"..."` (PEP 750, prefixes `t`, `T`, `rt` and `tr`), which "support the full syntax of PEP 701", so
  they are read like f-strings. Python 3.14 has not been run here, and the scanner reads only text, so the tests do not need it.
- **A lock made before may show drift once.** A Python region that holds a field spanning lines, or a reused quote with an unbalanced bracket,
  hashes differently now. `--rehash` knows only the old C-family rule, so relocking is the way out. No lock known here has such a region, and
  for everything else Python 3.9 reads the answers are the ones they were.
- A comment line inside a field that spans lines is kept as text, while one inside ordinary brackets is dropped: editing such a comment shows
  as a change, and it can never hide one.
- **Proved against the tokenizer on both Pythons.** The oracle test no longer skips files with f-strings on 3.12 and later, compares the
  tokenizer's pieces of f-string text like string tokens, and has four programs only 3.12 and later read. They fail with the old scanner.
  Unit tests and five vector rows (language neutral) pin the cases.

## Code is hashed by a table of types, and a type nobody listed is safe (2026-10-21)
Tried on 36 languages, the tool had three kinds of hole beyond false alarms: types where indentation is meaning (Haskell, F#, Nim, YAML) hid a
line moved out of a block; a comment-looking line inside a multi-line string was dropped from the hash (a `// query` line in a JavaScript
template literal, `/* */` in a Go raw string, `<!-- -->` in a JavaScript template literal); and every type that was not listed got the
rule that can do both. No project here had hit the second one: a scan of the three real projects found none. The work is per style, not per
language: there are four families, and a port writes them once.
- **A style is `family[-keep][+kinds]` and one table has a row per kind of file** (extensions, style, marker starters). Families: `c`, `hash`,
  `dash`, `python` and `safe` (no comments dropped). `-keep` counts indentation as written, less what all the lines kept start with
  (see the review fixes below for tabs), and does not collapse spaces. `+tick`, `+triple`, `+triple1` name the multi-line strings the type has.
- **The default is `safe`: nothing is hidden except blank lines and trailing spaces.** More false alarms for a type nobody listed, never a
  change that goes unseen. Every C-family type the real projects use was listed first (`.html`, `.js`, `.cpp`, `.h`, `.mm` and the rest), or the
  default would have turned them noisy. `.html` keeps plain `c`: prose backticks in HTML must not open a string.
- **Inside a tracked string one thing changes: its lines are never comments.** Blank lines, indentation and runs of spaces inside it are still not
  seen, as in a Python docstring, so hashes change only where the hole was hit. Verbatim strings would be a separate, wider change (they would
  rehash every region with a template literal). The tracker skips `//` comments and `/* */` blocks before it looks for a quote, takes a string that
  closes on its line as one line, and reads an unclosed `"` or `'` as an apostrophe. Wrongly inside keeps comment lines (a false alarm); wrongly
  outside is what a regular expression with a quote in it can cause, and is a known limit.
- **Go has its own kind, `+rawtick`:** a backslash inside a Go raw string is a backslash, so a string such as `` `C:\` `` ends there. With
  escapes the next raw string would read as outside and its comment-looking lines would be dropped. Found by a test written for it: the
  closer pattern had an extra backslash that made every escape a no-op, now fixed for all kinds and tested for `\"` and `\`` and `\'`.
- **`BUILD` and `WORKSPACE` are Bazel's only exactly as written.** A script called `build` is a shell script and stays safe.
- **YAML is safe, not `hash`:** a `#` line inside a `|` block scalar is text, and `#` at the start of a line cannot be told from a comment
  without a YAML parser. Makefiles are safe too.
- **Not tracked, said in the SPEC:** C++ raw strings, PHP heredocs, C# verbatim strings, Rust strings over lines, SQL strings. Each needs its own
  small rule; a project that hits one can ask for it.
- **Migration.** The rule `--rehash` knows is still the old one for every file (C family). A file that moved to another style, or gained a string
  rule, migrates the way Python did: an entry whose code is unchanged under that rule gets the new hash, and a change only the old rule
  ignored is not seen until then. A Haskell lock made while `.hs` was read without its indentation (the Phase 0 tool) needs one relock.
- **Measured:** `sor check`, `sor status --json` and `sor markers --json` give the same output as before on all three real projects, back to
  back; `sor status` on the large copy takes 0.5 s; a style with no string kinds gives text identical to plain `c` for code without any.

## A marker may follow more comment starters, per type and per target (2026-10-21)
Five of the 36 languages tried could not be marked at all: the tool saw no region and called every line unmarked (Erlang `%`, MATLAB `%`,
Fortran `!`, Visual Basic `'`, OCaml `(*`; batch files `REM` too).
- **Per type, not global.** `MARK` is searched in every file, so a global `'` would turn `x = '@clause end has no lens'` into a line marker that
  names ids that do not exist, and that blocks the lock (the extension's own test has such a line). A type's extra starters sit in the same
  table row as its style (`LANGUAGES`). `REM` and `::` count only at the start of a line.
- **A target may declare more: `{comment: %}`** in its Rules, one to three characters, none a letter, a digit, a space, `@`, `{` or `}`.
  It adds and never takes away; `sor check` reports a malformed one. This is the answer for a language nobody listed, instead of guessing
  a starter in every unknown file, which would turn lines of the doc files under a code root into markers.
- **A starter is a run.** The old pattern matched `;; @clause` at the second `;`, so the text before it was not blank and the line read as a
  line marker, and `;; @clause end` became a problem. `///` (Rust, C#, Swift) and `##` did the same. They are one starter now.
- `(* … *)` strips the closing `*)` as `*/` and `-->` were.
- **Not changed:** the VS Code extension keeps its own list of marker comment styles to hide and fold marker lines, so a line with a new starter
  is not hidden or folded there. The regions come from the tool and are right. That JS is its own project and was not edited.
- Vectors: 27 rows for `parse_marker`, among them the string case, `;;`, `///`, REM at the start only, and declared starters.

## Review fixes to the table of types and the markers (2026-10-21)
A full review of the styles and the markers (12 findings; three of them reproduced before fixing) changed these things.
- **A tab is no longer eight spaces in the safe and keep styles.** Indentation is kept as written, less the characters all the lines kept start
  with: spaces are counted, a tab or another whitespace character is written out (`\u0009:b`). A Makefile recipe with a tab turned into eight
  spaces used to hash the same and no longer runs, which broke the promise "nothing hidden but blank lines and trailing spaces". Python keeps
  eight columns, as Python 3 reads it, and the SPEC says so.
- **A region that ends inside a string or a block comment has lost its place** and drops no line. One lone backtick in JSX text used to flip
  the tracker, so a later template literal read as outside and its comment-looking lines were dropped (reproduced). Now such a region keeps
  them: a false alarm at worst. Two strays in one region still go unseen, and the SPEC lists JSX text and regular expressions as limits.
- **A style is checked.** An unknown kind (`c+ticks`), a trailing `+`, or kinds on a family that has none raise instead of switching the
  protection off in silence; a test runs every style in the table, and another fails when an extension is listed in two rows.
- **More types are listed** so that the long tail is not noisy: XML and its dialects, templates (ERB, Razor, Handlebars, MDX, Astro), CUDA, the
  shader stages, WGSL and `.inl` are C family, GraphQL is `hash`.
- **A target cannot declare a quote as a starter.** `{comment: '}` made `x = '@clause a/b'` a marker with the id `a/b'` (reproduced).
- **One place reads a marker** (`_split_marker`), and a vectors test runs every marker row through `scan_text` as well as `parse_marker`.
- **The vectors generator is in the repository** (`vectors/make_hashing.py`, with `--check`), and a test fails when the file is not what it
  writes. The rows that list the table are generated from the tool's table, so they stop the table changing without the file changing; they
  cannot prove it right, and the README says so. New rows pin the whitespace Python strips, tabs, and the lost place.
- **Not changed:** the three quote scanners (Python, `#` languages, C family strings) stay separate. A shared lexer would be a larger change
  than the review warranted; instead each scanner has a test of the same backslash case, since the escape bug that hid for a day was in one of them.

## A JavaScript copy of the hashing rules (2026-10-21)
The proposal ends with a copy of the tool that an editor can run without Python. This is the first slice of it, in `tools/js/`.
- **JavaScript, not TypeScript.** The extension's own spec says plain JavaScript on Node, no build step, VS Code 1.80 or newer (Node 16). A
  TypeScript copy would need a compile step it may not have. The copy is CommonJS with no dependencies, and it runs on Node 16.20 and on 26.
- **Only the rules the vectors cover.** The style of a path, the splitting of lines, the normalization of code in every style, markers (parsed
  and scanned), the hash of the regions of a clause, the hash of a text, the digest of the targets of a clause, and folding, unfolding and
  writing the text of the lock. There is no project reader, folder scan or command line yet.
- **It is not shipped yet.** `plugins/sync-tools.sh` copies only the Python files. A copy with no command would put code in the extension's
  package that nothing runs, and the extension's `code` rule lists what the package may hold.
- **Python's text rules sit in one module** (`pytext.js`). Where JavaScript differs from Python the copy follows Python, because a lock written by
  one has to read as unchanged by the other. Whitespace is what `str.strip()` removes (not `trim()` or `\s`, which differ at U+001C to U+001F,
  U+0085 and U+FEFF), a word character is a Unicode letter, digit or `_` (JavaScript's `\b` is ASCII only), a dot matches everything but a line
  feed (so U+2028 is text), and strings and lock keys sort by code point (JavaScript sorts by UTF-16 unit and puts U+1F600 below U+FF5E).
- **Written by hand, not built from clauses.** The tool has no `sor/` project of its own, so its rules are not clauses and the copy is not
  generated from any. Nothing but tests ties the two copies, and the SPEC pins the rules in prose (§10, §11). This is the gap the multi-target
  work was built for, and it is open (below).
- **How the two copies are kept from drifting.** The same rows run on both. Breaking the JavaScript on purpose in 33 places showed that the
  rows alone missed 13 real ones (U+0085, a letter after `@clause`, U+2028 in a comment or a marker, a tab after spaces, `\{` and `\N{` in
  f-strings, a name ending in `f` before a string, a `#` inside a word in shell, a format spec holding `#` or a quote, the order of astral keys),
  so 21 rows were added. The Python tool fails on the new rows too when it is broken at the matching places (tried at six). A test in the
  Python suite (`tools/test_sor_js.py`) also puts the repository's own code through every style in both tools, plain and with characters put in at
  random, and compares markers, scans and lock texts. With it, every one of the 33 breakages fails a test except one that changes nothing (the common
  prefix of the indentations does not depend on which string it starts from).
- **Limits.** The test is skipped, with a message, when `node` is missing. The rows and the cross-check only reach what they try. Letters and
  digits that Unicode added after the older of the two versions that Python and Node carry can be word characters in one and not the other. The
  JavaScript is not measured for coverage, since that needs a package from npm. Paths are read with `/` as the separator.

## The note about missing code respects `Targets:` (2026-10-22)
Found by trying the case "a clause that only concerns Python" on a throwaway project: a part with `Targets: py` locked and reported nothing behind for
`ts`, but `sor check` still said `1 clause(s) have code in py but none in ts` for its clause.
- **Why no test caught it.** The note was written in Phase 2, before a part could limit its targets. Phase 3 connected `Targets:` to the lock only
  (`lagging_targets`), and no test put the note and an override in one project. Earlier the same day `Project.applicable_targets` was deleted as dead
  code; it being unused was a sign that nothing but the lock asked which targets apply, and nobody asked who else should.
- **The fix.** The note counts only the targets that apply to the clause. A project whose root says nothing keeps the old note for every target.
  The pieces are shared so the next change does not write them a third time: `Project.owner_part_id` (the climb that `claims.owner_part` had),
  `Project.targets_applying_to(key)` and `Scan.targets_with_code()`.
- **`sor status` prints the note too,** as a `note:` line after the groups and the "agree" line. It is not a pending change, it changes no exit code and
  adds nothing to `--json`, because the extension reads that JSON.
- **The refusal for `behind` no longer prints a ready-to-copy flag.** It says to rebuild the code and names `--allow-behind <language>` only for the
  case where the user has said the language is rebuilt later. The flag is the user's call, and a message that hands it over invites its use.
- **Audit of the other readers.** `lagging_targets`, the `changed … code not updated yet` detail and `--allow-behind` follow `Targets:`. The lock still
  writes a line for code in a target that does not apply to its clause, and nothing reports it. Left as it is.
- **Next.** A lock of a clause that applies to a language but has no code there refuses unless `--allow-behind` allows it (decided by the owner), built
  on `targets_applying_to` and `targets_with_code`.

## A lock asks for code in every language that applies (2026-10-22)
Decided by the owner on 2026-10-22: a clause that applies to a language (`Targets:`) but has no code there refuses at lock, unless `--allow-behind` allows it.
- **Which clauses are asked.** Only a project that says its targets, and only a clause that is new, changed or built now (a clause locked without code that
  gets its first code), by the status findings `new`, `changed` and `built`. A clause locked earlier is not asked, so a project that adds a second language is
  not refused for everything it has. A review (`stale`, `shared`) and a fix against a failing test are not asked either. A change to the code alone is
  drift, which a lock refuses anyway.
- **One definition of "has no code".** The refusal reads `Scan.targets_with_code()` and `Project.targets_applying_to()`, the same pieces as the note of
  `sor check` and `sor status`, so the two always agree on which clause lacks which language.
- **The flag means more.** `--allow-behind T` now also covers "no code yet". The language has no line in the lock, so it is never listed as behind; what keeps
  it visible is the note of `sor status`, worked out from the files (no lock format change).
- **Cost.** A clause that was allowed to lack a language is asked again every time it changes, with the same flag. That is what a clause limited with
  `Targets: py` on its part avoids; `Targets:` on a single clause was left out (see Still open).
- **The message** says to add the code or limit the part, and names `--allow-behind <language>` only for when the user has said it comes later.

## `--allow-behind` asks the user first (2026-10-22)
Decided by the owner on 2026-10-22, because the flag now covers "no code yet" as well and becomes a normal way out of a refusal.
- **A hook on Bash** (`sor hook pre-bash`, wired in the plugin's `hooks.json` and in this repository's `.claude/settings.json`) returns `ask` for a `sor lock`
  that carries `--allow-behind`, in the plain form, as `--allow-behind=ts`, as the shortest prefix argparse takes (`--allow-b`), and behind `&&`, `|`, `;`, a
  new line, `$( )`, `env`, `timeout` and a Python launcher, and inside `bash -c` and `eval`. The reason names the clauses and the languages.
- **It reads the command, not the text.** The program of a command has to be `sor` or `sor.py`, so a grep for the flag, a commit message and an
  `echo` pass: the agent greps for it in the docs all the time, and a prompt for each would teach the user to click through. A line it cannot read (an
  open quote) that holds `lock` and the flag counts, because a guard that errs the other way would not guard.
- **The cost is paid only by a mention.** The registered command first looks at the text in the shell (about 15 ms for every other Bash call);
  Python (about 120 ms) starts only for a command that contains `allow-b`.
- **A here-document is skipped when it only writes data.** `cat > x.sh <<'EOF'` with a `sor lock --allow-behind` line inside asks nothing, because the
  lines are written to a file, not run; `bash <<EOF` and `sh -s <<EOF` are read, since there the lines are commands.
- **What it does not cover:** a person's terminal (deliberately), another agent than Claude Code, a script that Claude writes and then runs, `ssh`, and a
  program word behind an option with a value (`sudo -u bob sor lock ...`). I
  did not verify how Claude Code's bypass-permissions mode treats a hook's `ask`; the documentation excerpt I read did not say.
- **Changing this repository's `.claude/settings.json` changes the sessions held in it** (new sessions at least), so every Bash call there now runs the
  filter, and a `sor lock --allow-behind` run by hand through Claude here asks.
- **A gate in CI** is documented in `reference/ci-evidence.md`: `sor status` exits 1 for anything pending, so it belongs on the release branch.
- **Consequences of the refusal rule worth knowing.** The first lock of a project that declares `Targets: py, ts` from the start and builds Python first
  refuses every Python-only clause, one line each, so the agent has to stop and ask at that very lock. A summary line instead of one per clause could
  come later.

## The session-start note says what is pending (2026-10-22)
Decided by the owner on 2026-10-22: a new session is told about changes an earlier session left pending.
- **What it says.** After the parts index, one line `Pending since the last lock: …` (every finding `sor status` lists apart from the information group:
  new, changed, removed, behind, stale, shared, drift, built and fixing, each with its detail, at most 900 characters and then "and N more") and one line `Claims in force: …`. Both are facts. The tool cannot tell which session left a change,
  so it says "since the last lock", and drift keeps its meaning (a person changed the code).
- **When it is silent.** The pending line is left out for a project in agreement, for a project with no lock yet (every clause would be new, and the agent
  runs `sor status` anyway) and on any failure: a lock this copy cannot read or a broken part leaves the plain note, never an error in the hook. The claims
  line does not depend on the lock: agents can work in parallel before the first one.
- **Cost.** One scan and one status, about 70 ms on the solar-system example; the plugin's timeout for the hook is 10 s.
- **The skill** says in its routine to tell the user once what is pending that the agent did not start (an existing line, edited in place).

## A claim ends with its session or after an idle time (2026-10-22)
Decided by the owner on 2026-10-22: no fixed lifetime in an agentic workflow. A timer from the moment of the claim ended work that was still going on.
- **Two values per claim.** `idle` is the window in seconds (null for none) and `last` the time of the last activity; `until` stays and is `last + idle`
  (2100-01-01 for none, a date every tool reads, not null and not year 9999). Everything that compares a claim with the clock still reads `until`, so a tool from
  before `idle` reads the same file, keeps the fields it does not know when it rewrites it (it writes the dicts it read), and gives a claim made by the new
  tool the fixed end of its last renewal. The claims file has no version.
- **`--ttl` is now the idle window,** same syntax, plus `never`. Without it, the root file's `Claims: idle 30m` (`idle 2h`, `idle never`), else 30 minutes. The
  line is a header like `Targets:`, so a change to it marks the root file as changed. `sor check` reports a line it does not understand, and one outside the root.
- **What renews.** A claim is renewed by its session: every hook call that carries the session id (an edit, a read) and every `sor` command run with
  `CLAUDE_CODE_SESSION_ID`. A person at a terminal who names themselves renews by name at `sor lock --as NAME`. This is narrower than "every `sor` call"
  on purpose: the editor extension runs `status --json` on every refresh with no session, and if that renewed claims it would keep a dead chat's claim alive
  for ever and the idle window would never fire. A claim that already ran out is never renewed (someone else may hold the clause now; its holder is told
  at the next lock or release, as before), and a claim of an older tool has no `idle` and keeps its fixed end.
- **Cheap.** Nothing happens without a claims file, the file is read without the mutex, and it is rewritten under the mutex, re-read, only for a claim whose
  last activity is more than 5 minutes old, or more than half a short window. So a claim can end up to 5 minutes before its window is over, and the docs say so.
  A command that renews nothing never makes the file, and the edit hook does not parse the project to renew.
- **Renewal is best effort.** A busy claims file or a folder that cannot be written costs the command or the hook nothing: `sor status` keeps its exit code,
  a read its note, an edit its check. Every command run with a session renews, through one call in `main()` (the hook commands renew from their payload).
- **A session end frees its claims** (`sor hook session-end`, a `SessionEnd` hook with a 5 second timeout; the default budget of that event is 1.5 s). It
  releases the claims whose session is the one in the payload, for any reason, in the project found from the folder the session ends in, so a session started
  above its project (a monorepo root) keeps its claims until the idle window runs out. A crash skips the hook, and the idle window covers that. A claim with no window is cleared only by release, `--force`, or its session ending.
- **The messages** say what ends a claim: "claims end after 30 min idle by default", and a claim is described with its last activity and when it ends if
  nothing more happens.

## Lock format 3 and `--already-fits` (2026-10-22)
Decided by the owner on 2026-10-22: a language whose code already fits a changed clause is cleared by a flag of `sor lock`, which any caller may use and
which is recorded on the language's line; the hook that asks before `--allow-behind` asks before this too.
- **`sor lock greet/hello --already-fits ts`** marks `ts` as built for the clause as it is now, with no code edit, and writes `"fits": true` on its line. It
  is not `--allow-behind`: that one says "not rebuilt yet" and leaves the language listed; this one says "checked, needs no change" and clears it.
- **It refuses** a language that is also named by `--allow-behind`, a name that is no target, a project that keeps no code per language, and a call in which
  no clause being locked has that language behind. It does not allow a language with no code for a clause (that stays `--allow-behind`'s, and the refusal for
  no code still comes).
- **It ends when it stops being true.** A rebuild of that code, or the next change to the clause, drops it (`built_for` drops a `fits` whose `built` is not the
  clause's text now). While it holds, `sor status` keeps a `note:` for each confirmed language, with no exit code and nothing in `--json`; a clause that has a
  change of its own is not named, because its pending change is the news.
- **A lock line holds every field it has.** `fold` copied only `code` and `built`, so a reader of format 2 would have dropped a new field without a word. A line
  now carries all its fields but `kind`, `of` and `target`, and the lock is **format 3** exactly when a line holds a field besides `code` and `built`. A
  targeted project that never confirms anything stays in format 2 with the same bytes; an older tool refuses a format 3 lock with the message to update. The
  vectors file is format 3 (the fold rule changed), with rows for a confirmed line, every field coming back, and the format a lock needs.
- **The hook** reads `--already-fits`, `--already-fits=ts` and the shortest prefix argparse takes (`--alr`) like `--allow-behind`, and says what each does.
- **Version skew.** A targeted project that confirms a language moves to format 3 at that lock. The installed 0.9.8 extension and the game-engine project's own copy
  of the tool refuse it with the message to update.

## A lock stops when what it read has moved (2026-10-22)
Found while the owner asked whether two agents could ever race on a clause. One agent working alone cannot race with itself, but claims are advisory, the edit hook
only runs inside Claude Code, and subagents share one session, so a second chat, a person, a background job or (from stage 6) a language agent can be at work on
the same files.
- **What was already safe.** The lock and claims files are written whole through a temp file and a rename, the claims file is changed under a mutex and re-read,
  and a scoped lock re-reads the lock under its mutex and merges only its own keys.
- **A lost update.** `sor lock --all` wrote the whole lock it had worked out from the lock it read at the start, and a scoped lock replaced its own keys: another
  lock that landed in between was overwritten, results and manual confirmations included. Now, under the mutex, the lock is read again and the lock stops, writing
  nothing, if it differs from what this one began with (for `--all`) or if any of its own keys does (for a scoped lock). A line of a language counts as part of
  its clause.
- **A snapshot that was not atomic.** Spec files and code files are read one after the other, so an edit in between could be locked as clause text and code that
  never existed together, and `sor status` would then call it drift, a person's change. The files are stamped (`mtime_ns`, size) before anything is read, and
  stamped again under the mutex; the lock stops when a spec file or a code file of what it locks has changed. It does not hold the mutex for a second scan: the
  mutex counts as stale after 10 seconds and a waiter may break it. A file that is touched without a change also stops it, and the answer is to run it again.
- **A claim made meanwhile** stops a lock of the whole project too, with the usual message.
- **Left as it is, and documented:** two waiters may break each other's stale mutex after a crash, and the edit hook cannot tell the subagents of one session apart.
- **A rule for the per-language lock (stage 6).** `sor lock greet/hello@py` merges at the level of the line under the mutex: it writes only Python's line into the
  entry it has just read and keeps TypeScript's, and the check above looks at that line only. Replacing the whole entry would let two language agents overwrite
  each other.

## A test keeps a result for each language it has test code in (2026-10-22)
Decided by the owner on 2026-10-22: test results are per target, where the test has test code.
- **Lines for tests.** In a project that says its targets, a test with `@clause test` code in a language gets a line `part/test:name@py` there, like a clause. The
  line holds `code`, `built` and, for a test that needs a result from the project's own framework, `result`. A line with `result` makes the lock format 3. A
  test that is `manual:` or left to CI keeps its result on its entry, and its lines hold none, so a lock with only such tests stays in format 2.
- **One result for every reader.** The result of the test is worked out from its lines when the lock is read (`fail` if one failed, `pass` if all passed, else
  `none`) and is not written on the entry. `sor status`, the hook, the views, evidence and the extension's JSON read `entry['result']` as they always did.
- **`--results`.** `id@py` is one language's result. A plain id is the result of the only language with test code for it, and is refused, with the lines named,
  when two have; a language with no test code for the test is refused. A language with no test code needs no result. The lock refusal and the `tests` block name
  the line that has not passed, and the example in the way out is a line.
- **Results come with each lock,** as they always did: a line does not carry the result of an earlier lock, so a lock of everything asks again.
- **Not done:** the same for `--run-tests` with a web target (a web test has no marked code, so it has no lines; the filter now lets `id@lang` through for the
  tests it calls external, and no test exercises it, since it needs the headless browser); and evidence per language (stage 7).
- **A changed test is behind like a clause.** Its lines have `built`, so when the text of a test changes and its test code in a language does not, that language is
  behind: `sor status` says `code not updated yet in py, ts`, the lock refuses until the test code is rebuilt, `--allow-behind` allows it and `--already-fits`
  clears it (the result is given as usual). A test that is `manual:` and has marked code behaves the same. That is the rule "a test has lines like a clause", not a
  separate decision; it was confirmed on a throwaway project and is pinned by tests.
- **`sor status` names the lines** of a test that needs a result for each language (`part/test:name@py`), and its example is a line, which the lock accepts.
- **Evidence fingerprints** of a test with test code in a targeted project change once: its `code` is now the digest of its lines. Stage 7 redoes them.

## One language of a clause, claimed and locked on its own (2026-10-22)
Asked by the owner as "how can I avoid drift, e.g. one agent claims `@py` and the other forgets it", and as a question about races between two agents on
one clause. The answer is that each language is its own claim and its own lock line, and that a lock of one language can only write what that language owns.
- **`greet/hello@py` is an id** in a project that says its targets. A claim of it holds the clause's line in that language, the line of the clause's own test
  in that language, and the code regions in that language's files. It records `pins: [clause]`, because the code relies on the clause's text: it conflicts with a
  claim of the whole clause, with a claim of the same language and with an edit of the clause's text, and not with another language of the clause. A claim of
  the whole clause holds every language (`footprint` adds the lines). The edit hook looks only at the edited file's regions for a code edit, so a claim of
  `@py` never refuses a TypeScript edit of the same clause (found by a test: it first returned all regions of the touched clause).
- **`sor lock greet/hello@py` writes that language's lines and the glue of its files, and nothing else.** The clause's own line is never rewritten (decided before),
  so the lock needs the clause locked as it reads now and says "lock it first" otherwise. It merges the line into the entry it reads under the mutex, and
  stops with "run it again" when the clause's line, that language's line, its glue or a file of that language moved since it read. Another language landing
  in between is not in the way, and both lines survive (a test runs a TypeScript lock inside a Python lock). The files stamped are those of that language only.
- **The test of a language has to pass again when its code is locked.** A plain lock asks for results only of tests that are pending, which for a changed clause
  is all of them, at the moment the whole clause is locked. A language is rebuilt after that, so the lock of it asks for a result of the clause's test in that
  language (`greet/test:hello@ts`), or `--allow-incomplete`. This is stronger than the plain lock on purpose: the earlier result was for the old code.
- **A language that is left behind does not need a result yet.** Found by the advisor's review of the order above: a whole-clause lock with `--allow-behind ts`
  asked for a result of the clause's test in TypeScript, which would run against TypeScript code nobody had rebuilt, so the order only worked with a made-up result or
  `--allow-incomplete`. A test line of a language that `--allow-behind` names, and in which the test or its clause is behind, now stays `none` in that lock, and
  `sor status` keeps listing it. A language that is not behind does not wait, whatever `--allow-behind` names. It is the owner's to veto: the lock of the language
  asks for the result before it writes anything, so the proof waits and is not dropped.
- **`--already-fits ts` works for one language** and is recorded as before. `--allow-behind` is refused with a lock of one language, for it already leaves out the
  others, and `--already-fits` is refused in a command that also names whole clauses (two commands, each says what it does).
- **Found while building it, and fixed in status.** (1) The first code of a language that a clause was locked without (`--allow-behind ts` for want of code) was
  drift, so the only way to add it was to change the clause. It is now `behind` with `ts (first code)`, which the edit hook allows. (2) A clause that shares a
  code region with a clause that is `behind` was drift when that region was rebuilt, for `behind` did not count as a reason for the region to change. It does now,
  and the sharing clause is `shared`, as it is for a changed clause.
- **Nudges.** A lock of one language says which other languages of the clause are still behind or have no code, and how to finish them. `sor release` of a language
  says when it has code that is not locked. Nothing is enforced: claims stay advice, and `sor status` and the session-start note go on listing what is pending.
- **Not done.** `Targets:` per single clause; evidence per target (stage 7); the editor extension (stage 8).

## Evidence is per language for a test that has test code in a language (2026-10-22)
Stage 7 of `proposals/multi-target.md`, decided by the owner earlier as "results per target where test code exists".
- **Keys.** A deferred test (`runs on:`) whose entry has lines (test code in a language) takes a result `test@py` for each of them. The rule for which language a
  result belongs to is one function of the lock (`result_language`), now used by `sor lock`, `sor lock greet/hello@py` and `sor evidence`, so the three cannot disagree.
- **Fingerprint.** `test@py` hashes the test's text and references, its test code and the text of the clauses it proves with their code in that language only. A TypeScript edit leaves Python evidence current, an edit of the clause or of the test's text makes every language stale. The one for the test as a
  whole is kept for a test with no test code per language, as it was for every test before, so an untargeted project and a test without lines have the same
  fingerprints byte for byte (checked on `examples/solar-system` and `editors/vscode` against main: `sor test --list --json` and `sor verify` are identical).
- **The evidence file does not change format.** Its keys and fields are the same; the keys of the results gain `@` and the fingerprint means something narrower. An
  older `sor verify` never matches `test@py` and reports the test as missing (exit 1); a new one reads an old file's fingerprint as stale. Neither direction can turn
  into a false pass, which is the rule that made the lock a new format when a line gained a field.
- **One-time churn.** Every targeted project with deferred tests that have test code fails its gate once after the upgrade, until its jobs write the new keys.
  A plain id for a test that now takes one result for each language is not "a test that no longer exists": `sor verify` names it (`renamed` in `--json`) and the keys
  to write.
- **Not done.** `sor test --list --json` still has one `fingerprint` for a test (the whole one). A job in a language that runs the test code of one language alone
  gives the results of that language, and nothing in the tool stops a job from giving results for a language it did not run: evidence is as trustworthy as the job.

## The editor extension knows more than one language (2026-10-22)
Stage 8 of `proposals/multi-target.md`, in `editors/vscode`, an extension that is itself a Spec of Record project: the clauses changed first, then the code, then the lock.
- **`behind` is recompile.** The extension did not know the status, so a clause whose language was built for an older text had no gutter mark, no flag on its lens, no
  word in the hover and no count in the status bar. It maps like new, changed and removed.
- **A marker line may start with any comment starter.** The extension hid a marker line only after `//`, `#`, `--`, `;`, `/*` or `<!--`. The rule is now one punctuation
  character repeated (`//`, `---`, `%`, `!`, `'`, `::`), an opener (`/*`, `(*`, `<!--`) or `rem`. A first version took one to four punctuation characters of any
  kind; mutation checks showed it hid `}// @clause end` (code followed directly by a marker) and stopped at four dashes, so it was tightened and the real VS Code
  run was repeated (27 of 27 again). A comment starter a target declares that is not one of these shapes is still not hidden. It is only asked on the first and last
  line of a region the tool named.
- **The lens and the list of regions name the language only when there are several.** `2 code regions (py, ts)` and `py x/y` in the list; code in one target looks as before.
- **Tested without VS Code.** `test/regions.js` cuts the code of a clause out of `src/extension.js` (between its `@clause` lines) and runs it alone, so the test reads the text the
  clause marks. The extension's own clause that its code is one file stays true.
- **The real integration test was run, on the owner's yes.** `npm ci` in `editors/vscode` (a git-ignored `node_modules`) and `test/run.js` on a copy of the solar-system
  example with the installed VS Code: 27 checks passed (exit 0) before the change and the same 27 after. The results given to the lock are those of that run and of
  `test/regions.js`; the tests that say `manual:` stay unconfirmed, as they were.
- **Version 0.9.9, not published.** Its bundled tool reads lock format 3 and the claims of one language, which the installed 0.9.8 refuses. Packaging and publishing are the owner's.
- **Not done.** Coverage per target; the extension asks the tool for nothing per language beyond `targetName`.

## Still open
- The tool is not under Spec of Record. Its hashing, marker and lock rules could be clauses with `Targets: py, js`, so that a change to a clause
  leaves the other language behind and a lock refuses until both follow (`proposals/multi-target.md`). Until then the vectors and the
  cross-check are the only guard.
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
