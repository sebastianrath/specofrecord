---
name: workflow
description: Guides work in a Spec of Record project, where the specification is kept as clauses in a sor/ folder and the code is built from them. Covers changing a clause and its code, locking the result, starting a new project from a few words, and working beside other agents. Use whenever the user mentions Spec of Record or sor, when a project has sor/SPECOFRECORD.md (or the older sor/CLAUSES.md), `@clause` markers or a clauses-lock.json, or when the user asks to change what the software does in such a project. The user states intent and the agent runs the sor commands.
allowed-tools: Bash(sor *)
---

# Working in a Spec of Record project

The clauses in a `sor/` folder are the source of truth, and the code is built from them. Every line
of code sits in a `@clause <id>` ... `@clause end` region (or ends with a line marker such as
`// @clause bodies/planets/Mars`) that names the clause it came from.

The tool is the `sor` command (the plugin puts it on the PATH). If the shell cannot find it, run
`python3 "${CLAUDE_SKILL_DIR}/../../tools/sor.py"` instead. Run it from the project folder (the one
holding `sor/`), or pass `-C <folder>`. The format is in `reference/format-cheatsheet.md`.

| Command | Does |
|---|---|
| `sor status` | what changed since the last lock: **recompile** (clauses to build), **review** (check they still hold), **drift** (code changed, its clause did not), **claims** (who works on what) |
| `sor show <part or id>` | a part's clauses with their code underneath |
| `sor markers <id or file:line>` | where a clause's code is, or which clauses a line serves |
| `sor parts` | an index of every part: why it exists, its size, its open questions (`--tree`: the hierarchy). Run it first in a project you do not know |
| `sor needs [part]` | what a part uses from other parts, found from its `{references}` |
| `sor changes` | the pending changes in words: Added, Changed, Removed, Fixes |
| `sor new <part>` / `sor new --root` | a skeleton file with `<fill in: ...>` placeholders, which `sor check` reports until they are filled in. A part name must not be an item's name (see `reference/new-project.md`) |
| `sor check [<parts>]` | every problem in the spec files and the markers, and notes (too long, a test nothing will run, `open:` questions) that do not change its exit code. With parts, only those and the parts inside them: use it while others work |
| `sor test` | runs the clauses' tests (headless Chrome for web projects) |
| `sor claim <ids>` / `sor release --all` | say you work on these clauses / give them up |
| `sor lock` | accept what you claimed, with its code and test results (the forms are in "Locking") |

## The user states intent; you do the routine
The user says what to build or change, in their own words, and mentions Spec of Record once. They never run or ask for
`sor` commands, checks, locks or status: that is your job, every time. Finish each unit of work with `sor check` (fix
every problem), `sor test` when the project has a test runner, `sor lock` for what you claimed, and `sor release --all`
(a sub-agent adds its own `--as`, see "Claims"). Then tell the user in plain words what you wrote or changed: the
clauses, the code, the test results and anything left undecided (the `open:` questions). Leave out command output unless
something failed. Do not use the tool's words on the user without saying what they mean. "Lock" is the saved record of
what was agreed (`sor/sor-lock.json`): say "I saved the agreed state" or "the specs and the code agree", and explain the
file only if asked. Never say "the lock still holds". Start with `sor status`: drift that is already there is a person's
change to the code (see "Code a person changed").

## Starting a new project
"I want to build X, write the first specs following Spec of Record" means exactly that, and nothing else is asked of the
user. There is no `sor init`. Read `reference/new-project.md` and follow it (steps, structure, style, how to lock and
report, examples). Write the specs and stop: write code only when asked, or when the project is tiny like hello world.

## Putting existing code under a spec
"I'm about to change X, put it under Spec of Record" in a project that already has code means that area only, never the
whole project. The steps are in `reference/existing-code.md`: read it first.

## A change asked in words ("make Jupiter bigger")
1. Find the clause: `sor show <part>`, or `sor markers <file:line>` for a line of code.
2. Claim it (see "Claims"), then change the clause first: a value, a table row, an item, or a new
   item. For a bug report or a ticket, read `reference/bugs.md` first: if the clause is right, add
   or change a test that proves it, with a `bug:` line, instead.
3. Run `sor status`. "recompile" lists the clauses to build, "review" what to check.
4. Change only the code in the `@clause` regions status names. The edit hook refuses code changes
   whose clause did not change, and its message says which clause to change.
5. Run `sor test` and fix what fails (it needs a web target; without one, skip it). Then lock what you claimed, as in
   "Locking".

## Locking
`sor lock` saves the agreed state: the clauses, their code and their test results. With no ids it locks what you
claimed and the changed parts under a claimed part; `sor lock <ids>` locks only the ids you name. Pick the form that fits:

| Situation | Run |
|---|---|
| Your claimed clauses, and the project has a web target | `sor lock --run-tests` |
| Your claimed clauses, no web target | `sor lock` when every test is `manual:`; `sor lock --results F` when the project's own framework runs them |
| The very first lock of a project nobody else works in | `sor lock --all` (with `--run-tests` when there is a web target) |
| Other agents hold claims | lock only your own clauses; `--all` is refused while they hold claims |
| Failures that were already there | add `--allow-incomplete` and say so; it does not cover a test of code shared with a changed clause |
| A person checked a `manual:` test | `sor lock --confirm <test>`: for people, never for you |

A lock is refused while a test that is not `manual:` has no passing result: the `tests (N)` block of `sor status` lists
them and says the way out (for a test nobody can run yet, a `manual:` line saying what a person checks). The lock also
takes the code of the clauses and the glue files with it (a file that is only glue, such as `__init__.py`, goes with
every lock). If `sor status` still lists something afterwards, claim that clause or part and lock it.

## Claims
Claims say who works on which clauses. They are advisory, so make them a habit even when you seem to be alone.
- Before you edit a clause or its code: `sor claim <id> ...`. To add a clause, claim the part that will hold it. A claim
  also holds the code regions marked with the clause. It lasts 30 minutes (`--ttl 2h` for longer).
- If it prints REFUSED (exit 3), do not edit that clause or its code, and do not look for a way around it (never delete
  `sor/.sor-claims*`). Say who holds it; take another clause, wait and retry, or ask the user. Nothing was claimed, free ids too.
- Release when you are done, and before you stop even if the work failed: `sor release --all`. The tool tells you when
  your claims ran out (at `sor lock` with no ids, or `sor release`): claim again and re-read the clause before you go on.
- A sub-agent passes its own `--as <name>` on every claim, lock and release: `sor release --all` without a name frees
  every claim of the session, its siblings' too, so only the parent runs it. More: `reference/parallel-agents.md`.

## Clauses a person changed ("build it")
Start at step 3 of "A change asked in words": `sor status` lists exactly what changed since the last lock.

## Code a person changed ("keep my change")
A person may edit code themselves, because they know better. The edit guard watches only your own edits, so theirs goes
through and shows up as **drift** in `sor status`. Drift that was already there when you started is theirs: keep their
code and bring the clause in line. The steps are in `reference/code-a-person-changed.md`: read it first.

## Plain-written clauses (tidy)
Clauses may be written in plain sentences: bullets under the title, Tests and Notes, no names. Before building, tidy
them: add a `**name** - ` in front of each bullet that code or a test points at, wrap a number a test uses in braces
(`{max: 6x}`), and write the precise `do:` / `expect:` lines under the person's own test line. Never reword their
sentences and never add a test they didn't write; propose those instead. `code: path#name` under a rule points at the
function that implements it. A loose test ("test that the moon circles around") is a bullet in Tests, named after its
rule (or add `proves: {rule}`). With no `do:` / `expect:` write it in the project's framework under
`// @clause test <part>/<name>`, in a folder a target declares (`{path: test/}`). `sor test` then shows it as EXTERNAL;
lock with `sor lock --results F` (F: its result; with a web target also `--run-tests`).

## Rules
- The edit guard governs only the spec folder, the declared code paths and files that contain `@clause` markers.
  Everything else (a website, docs, config, notes) is not governed: edit it normally. A refusal starts with
  "Clauses come first", "Someone else is working on this", "Do not rewrite", or (for the lock and claims files) a
  message with "is written only by". A hook *error* (a message that the hook could not run) is a broken setup, not a
  refusal: tell the user, and do not work around a refusal.
- Never edit `sor-lock.json` or `sor/.sor-claims.json`; `sor lock` and `sor claim` write them.
- Edit spec files with Edit, one clause at a time, and re-read the clause right before. Never rewrite a spec file with
  Write (it erases what others changed since you read it), except a fresh `sor new` skeleton (not one made with `--why`): fill that in whole, once.
- Every code line sits in a `@clause <id>` region, or ends with a line marker. (Code under a `Source: code at <path>`
  part is written by hand and needs none.)
- Write choices the clauses left open into the notes in the page's glue comment.
- An `open: <question>` line under an item (not a test) is a question nobody has answered. Do not choose an answer:
  build only what is not in question, and tell the user the question in plain words. You can write one yourself for a
  point the user left undecided. `sor check` lists them, and a part that outgrows the limits in
  `reference/format-cheatsheet.md`, as notes: fix every problem. Report a note only for a part you wrote or changed in
  this task, and mention the notes that were already there at most once, never in every report. Split a part only when
  you are writing it now or when asked, never as a side effect of other work.
- `sor test` is the independent check the spec asks for: run it, but never weaken a test to make it
  pass, and never confirm a `manual:` test (`sor lock --confirm` is for people).
- Report which clauses changed, which code changed, and the test results.
