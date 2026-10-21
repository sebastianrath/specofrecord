---
name: specofrecord
description: Guides work in a Spec of Record project, whose specification is clauses in a sor/ folder (root sor/SPECOFRECORD.md) and whose code carries @clause markers. Use when the user mentions Spec of Record or sor, or the project has sor/SPECOFRECORD.md, and the work is to change what the software does, start a new project from a few words, or work beside other agents.
allowed-tools: Bash(sor *)
---

# Working in a Spec of Record project

The clauses in a `sor/` folder are the source of truth, and the code is built from them. Every line of code sits in a
`@clause <id>` ... `@clause end` region (or ends with a line marker such as `// @clause bodies/planets/Mars`).

The tool is the `sor` command (the plugin puts it on the PATH). If the shell cannot find it, run
`python3 "${CLAUDE_SKILL_DIR}/../../tools/sor.py"` instead. Run it from the project folder (the one holding `sor/`), or
pass `-C <folder>`. The format is in `reference/format-cheatsheet.md`.

## Which situation?
| You see | Go to |
|---|---|
| "I want to build X, write the first specs" | `reference/new-project.md` |
| "put X under Spec of Record", in a project that has code | `reference/existing-code.md` (that area only) |
| "make Jupiter bigger": any change to what the software does | "A change asked in words", below |
| a bug report or a ticket | `reference/bugs.md` |
| "build it", after a person changed clauses | step 3 of the change: `sor status` lists what changed |
| "keep my change", or drift that was there before you started | "Code a person changed", below |
| plain sentences: bullets without **names**, or `sor check` says `unnamed test` or `loose text` | `reference/plain-clauses.md` |
| other agents work at the same time | `reference/parallel-agents.md` |
| a test that needs a place (an OS, a GPU, a database) or must run in CI | `reference/ci-evidence.md` |

A new project: nothing else is asked of the user, and there is no `sor init`. Write the specs and stop: write code
only when asked, or when the project is tiny like hello world.

## Commands
| Command | Does |
|---|---|
| `sor status` | what changed since the last lock: recompile, review, drift, claims |
| `sor check [<parts>]` | every problem in the spec and the markers, plus notes; with parts, only those and the parts inside them: use it while others work |
| `sor test` | runs the clauses' tests (headless Chrome, web projects only) |
| `sor claim <ids>` / `sor release --all` | say you work on these clauses / give them up |
| `sor lock` | accept what you claimed, with its code and test results (the forms are in "Locking") |
| `sor new <part>` / `sor new --root` | a skeleton with `<fill in: ...>` placeholders, which `sor check` reports until filled; a part name must not be an item's name (`reference/new-project.md`) |
| `sor show <id>`, `sor markers <id or file:line>` | a part's clauses with their code; where a clause's code is, or which clause a line serves |
| `sor parts [--tree] [<parts>]` | an index of every part, or of those and the parts inside them: run it first in a project you do not know |
| `sor needs [part]`, `sor changes` | what a part uses from other parts; the pending changes in words |
| `sor evidence …`, `sor verify` | what a CI job proved about tests that say `runs on:`, and the gate over it (`reference/ci-evidence.md`) |

## Your routine
The user says what to build or change, in their own words, and mentions Spec of Record once. They never run or ask for
`sor` commands: that is your job, every time.
- Start with `sor status`: drift that was already there is a person's change to the code (see "Code a person changed").
- Finish each unit of work with `sor check` (fix every problem), `sor test` when the project has a test runner, `sor lock`
  for what you claimed, and `sor release --all` (a sub-agent: see "Claims").
- Then tell the user in plain words what you wrote or changed: the clauses, the code, the test results and anything left
  undecided (the `open:` questions). Leave out command output unless something failed.
- Explain the tool's words when you use them: say "I saved the agreed state" or "the specs and the code agree", and
  explain the file `sor/sor-lock.json` only if asked.

## A change asked in words ("make Jupiter bigger")
1. Find the clause: `sor show <part>`, or `sor markers <file:line>` for a line of code.
2. Claim it (see "Claims"), then change the clause first: a value, a table row, an item, or a new item. For a bug report
   or a ticket, read `reference/bugs.md` first: if the clause is right, add or change a test that proves it, with a
   `bug:` line, instead.
3. Run `sor status`. "recompile" lists the clauses to build, "review" what to check.
4. Change only the code in the `@clause` regions status names. The edit hook refuses code changes whose clause did not
   change, and its message says which clause to change.
5. Run the tests the project can run (`sor test` needs a web target) and fix what fails, then lock what you claimed, as in
   "Locking".

## Locking
`sor lock` saves the agreed state: the clauses, their code and their test results. With no ids it locks what you claimed
and the changed parts under a claimed part; `sor lock <ids>` locks only the ids you name.

| Situation | Run |
|---|---|
| Your claimed clauses, and the project has a web target | `sor lock --run-tests` |
| Your claimed clauses, no web target | `sor lock` if every test is `manual:`, else `sor lock --results F` (your framework's results) |
| The very first lock of a project nobody else works in | `sor lock --all` (add `--run-tests` when there is a web target) |

- Other agents hold claims: lock only your own clauses; `--all` is refused while they hold claims.
- Failures that were already there: add `--allow-incomplete` and say so; it does not cover a test of code shared with a
  changed clause.
- A person checks a `manual:` test: `sor lock --confirm <test>` is for people, never for you.
- A lock is refused while a test that is not `manual:` or `runs on:` has no passing result: the `tests (N)` block of `sor status`
  lists them and says the way out (for a test nobody can run yet, a `manual:` line saying what a person checks).
- The lock takes the code of the clauses and the glue files with it (a file that is only glue, such as `__init__.py`,
  goes with every lock). If `sor status` still lists something afterwards, claim that clause or part and lock it.

## Claims
Claims say who works on which clauses. They are advisory, so make them a habit even when you seem to be alone.
- Before you edit a clause or its code: `sor claim <id> ...`. To add a clause, claim the part that will hold it. A claim
  also holds the code regions marked with the clause. It lasts 30 minutes (`--ttl 2h` for longer).
- If it prints REFUSED (exit 3), do not edit that clause or its code, and do not look for a way around it (never delete
  `sor/.sor-claims*`). A refused claim takes none of its ids, free ones included. Say who holds it; take another clause,
  wait and retry, or ask the user.
- Release when you are done, and before you stop even if the work failed: `sor release --all`. The tool tells you when
  your claims ran out (at `sor lock` with no ids, or `sor release`): claim again and re-read the clause before you go on.
- A sub-agent passes its own `--as <name>` on every claim, lock and release (no other command takes `--as`) and frees
  only its own claims. `sor release --all` without a name frees every claim of the session, its siblings' too, so only
  the parent runs it. More: `reference/parallel-agents.md`.

## Code a person changed ("keep my change")
A person may edit code themselves. The edit guard watches only your own edits, so theirs goes through and shows up as
**drift** in `sor status`. Drift that was already there when you started is theirs: keep their code and bring the clause
in line. The steps are in `reference/code-a-person-changed.md`: read it first.

## Rules
**Guard and files**
- The edit guard governs only the spec folder, the declared code paths and files that contain `@clause` markers.
  Everything else (a website, docs, config, notes) is not governed: edit it normally.
- A refusal starts with "Clauses come first", "Someone else is working on this", "Do not rewrite", or (for the lock and
  claims files) a message with "is written only by". A hook *error* (a message that the hook could not run) is a broken
  setup, not a refusal: tell the user. Never work around a refusal.
- Never edit `sor-lock.json` or `sor/.sor-claims.json`; `sor lock` and `sor claim` write them.

**Spec files and code**
- Edit spec files with Edit, one clause at a time, and re-read the clause right before. Never rewrite a spec file with
  Write (it erases what others changed since you read it), except a fresh `sor new` skeleton: fill that in whole, once.
- Every code line sits in a `@clause <id>` region, or ends with a line marker. (Code under a `Source: code at <path>`
  part is written by hand and needs none.)
- Write choices the clauses left open into the notes of the glue region.

**Questions, notes, tests**
- An `open: <question>` line under an item (not a test) is a question nobody has answered. Do not choose an answer: build
  only what is not in question, and tell the user the question in plain words. You can write one yourself for a point
  the user left undecided.
- `sor check` lists open questions, and a part that outgrows the limits in `reference/format-cheatsheet.md`, as notes.
  Report a note only for a part you wrote or changed in this task, and mention older notes at most once. Split a part
  only when you are writing it now or when asked, never as a side effect of other work.
- `sor test` is the independent check the spec asks for: never weaken a test to make it pass (moving it to `runs on:` is weakening it), and never confirm a
  `manual:` test (`sor lock --confirm` is for people).
