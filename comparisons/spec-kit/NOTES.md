# Solar system in GitHub Spec Kit — notes

Files here: `.specify/memory/constitution.md` and `specs/001-solar-system-viewer/` (spec, checklists/requirements,
plan, research, data-model, contracts/probe-api, quickstart, tasks): ~730 lines, against ~370 lines of FACT facts.
These files are trimmed by hand. A real agent run would likely write 1,200–2,000 lines (fuller research, a data-model
that repeats the body table, a longer quickstart, ~60–80 tasks), plus about 20 files of scripts and templates
that `specify init` copies into `.specify/` and the agent folder. Those files are not copied here.

## Commands a developer runs
```
uv tool install specify-cli            # or: uvx --from git+https://github.com/github/spec-kit.git specify init
specify init solar-system --integration claude     # older releases: --ai claude
/speckit.constitution  "one offline file, calm, test-first via probes, one writer per state, …"
/speckit.specify       "<the description in spec.md Input>"   -> branch + specs/001-…/spec.md + checklists/requirements.md
/speckit.clarify       (≤5 questions, answers go into ## Clarifications)
/speckit.plan          "HTML+canvas, no deps, Puppeteer tests"  -> plan, research, data-model, contracts/, quickstart
/speckit.tasks  ->  /speckit.analyze (read-only consistency report)  ->  /speckit.implement  ->  /speckit.converge (repeat)
```
In Claude Code, recent releases install these as skills named `/speckit-specify` and so on. Older releases and most docs use the dotted names.
I could not confirm which release made the change.

## What carries over and what does not
- **Expressed well:** all numbers. Every fact became an FR-### (37 in total), and the body table sits in spec.md.
  All 43 FACT tests carried over: 38 as Given/When/Then acceptance scenarios or contract tests, 4 manual tests as
  quickstart rows M1–M4, and the quality measures as SC-001 and SC-002. `because:` lines became Clarifications and research Rationale.
  `out-of-scope` went into Assumptions. Approach items (journey, draw order, base scale) went into plan.md and research.md.
  `one-writer` and `calm` became constitution principles.
- **Prose only:** cross-references and derived values. FACT writes `{days: = bodies/planets/Earth.days}` and `{bars.top}`.
  Spec Kit writes "365" or "56 px" again in each file that needs it: spec, research R3, data-model and the tests.
  Nothing links those copies.
- **Prose only:** acceptance scenarios are not executable. An agent turns them into test code in T008–T035, so the
  tolerances (±1 %, ±0.5 px) survive only if the agent copies them correctly.
- **No slot:** `bug:` lines ("first build drew no stars", #3). I kept #3 as a note in a scenario. Spec Kit's opt-in
  `bug` extension (`.specify/bugs/<slug>/`) is the nearest match (guess: it suits this use).
- **Missing:** per-part Contract `gives`/`needs`/`owns`. The spec template has no such section, so ownership went into the constitution
  and data-model as prose. The spec template also forbids "HOW", so the probe API went to contracts/. That is a judgement call.
- **Missing:** `[P]` parallelism. It is defined per file. The single-HTML-file target makes every implementation task sequential,
  although FACT's parts split cleanly. A multi-file `src/` with a build step would allow parallel work, but the "no build" rule rules that out.

## Automatic checks vs. checks the agent does
Scripts (`create-new-feature`, `setup-plan`, `check-prerequisites`) only create folders, set branches and number features, and check that
files exist. Everything else is a prompt the agent follows. That covers the spec quality checklist, the ≤3 [NEEDS CLARIFICATION] rule,
the Constitution Check gate, `/speckit.analyze` (FR→task coverage, ambiguity, constitution conflicts, read-only, doc-only), the implement checklist gate,
`[X]` marking, "tests pass", and `/speckit.converge`. converge judges the code against the spec and appends tasks for missing, partial,
contradicting or unrequested work. No tool hashes the spec, maps code lines back to requirements, blocks unrelated edits, finds weak tests
or computes the "90 % of facts tested" figure (T038 is a self-written guess). FACT does all of these mechanically
(`status`, `@fact` markers, the edit hook, `test --strength`, `lock`). On the other hand, FACT's tests use its own runner and probe
format, while Spec Kit's tests are ordinary project tests that need no extra tool.

## A later change: "make Jupiter bigger"
- Living-spec model: edit the Jupiter row in spec.md (and data-model.md if the table was copied there). Reconcile plan and tasks
  by hand or with the agent, run `/speckit.analyze`, then `/speckit.implement` and `/speckit.converge`. The agent must
  find the size in `out/index.html` itself, because no marker points to it. The agent also has to notice that the sun-size scenario
  (sun.r > jupiter.r) still holds, and that nothing else (labels, reach) shifts.
- Flow-forward model: write a new `specs/002-bigger-jupiter/` with its own spec, plan and tasks. That is heavy for one number.
  The current value then lives only in code plus the newest spec, while 001 keeps the old value as history.
- Either way nothing records the spec version the code was built from. Drift is found only when someone runs converge or analyze.
  In FACT, `fact status` names the changed row and the one marked line to change.

## Sources
- https://github.com/github/spec-kit (README, commands, extensions)
- https://github.com/github/spec-kit/tree/main/templates — spec-, plan-, tasks-, constitution-template.md
- https://github.com/github/spec-kit/tree/main/templates/commands (specify, clarify, plan, analyze, implement, converge)
- https://raw.githubusercontent.com/github/spec-kit/main/docs/guides/evolving-specs.md
- https://github.github.com/spec-kit/guides/existing-projects.html
- https://github.com/recodeee/gitguardex/pull/587 (shows the `.claude/skills/speckit-*` hyphen naming)
