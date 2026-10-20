# Solar system in BMad Method — notes

**Version:** BMad Method **v6.12.4** (branch `V6.12`, stable on npm; `main` is a v7 alpha). The layout
named in the task (`docs/prd.md`, `docs/stories/1.1.story.md` with *QA Results*, `core-config.yaml`, SM/QA
agents) is **v4**. v6.12 uses `_bmad/config.toml`, `_bmad-output/{planning,implementation}-artifacts/`, and
5 agents (Analyst, PM, UX, Architect, Dev). Story prep, review and QA are skills now. `bmad-create-story` and
`bmad-dev-story` (*Dev Agent Record*) are deprecated shims, so the story files here are `bmad-build` specs.
**Files:** config.toml, brief.md, prd.md, ARCHITECTURE-SPINE.md, epics.md (15 stories; 1.3/2.2/3.1 full),
sprint-status.yaml, 3 × `spec-*.md`. Not written: `.memlog.md` files, review reports. **Guesses:** config value
form, no `bmad-ux` run (visual rules in PRD §6), Playwright, specs drafted ahead ("Approve and stop").

## Order a developer runs
`npx bmad-method install` → `bmad-product-brief` (Analyst) → `bmad-prd` (PM; Create, then Validate) →
[`bmad-ux`] → `bmad-architecture` (Architect) → `bmad-create-epics-and-stories` (PM) → `bmad-sprint-planning`
(readiness PASS/CONCERNS/FAIL, then `sprint-status.yaml`) → per story, fresh chat: `bmad-build 1-1` (clarify →
plan → human approves spec → implement → review subagents → present) → [`bmad-code-review`,
`bmad-qa-generate-e2e-tests`] → `bmad-retrospective` per epic. `bmad-help` suggests the next step.

## What carries over
- **Fully, as prose plus numbers:** every value (sizes, colors, 1.1×, 0.3–6×, 56/28 px, slider 0–100
  start 40, (s/100)² years/s, 0.1 s cap, 300 stars, 20 s comet, 10 px reach), the out-of-scope list,
  and every `do/expect` test, rewritten as FR "Consequences" and Given/When/Then ACs. Build's I/O matrix
  carries the tolerances (± 1 px, ± 1%). `manual:` → spec "Manual checks". `bug:` → a regression note in
  the FR, or a `type: bugfix` spec. `because:` → Design Notes or the architecture memlog.
- **One writer per state, probes, draw order, units:** ADs in the spine (`Binds/Prevents/Rule`).
  Good fit: the spine format is made for exactly these.
- **Only as prose, not mechanically:** value references (`{year.days}`, `{camera/zoom-step.factor}`) become
  repeated literals ("365", "1.1"), so a change has to be copied by hand. `each:` loops become prose.
  `measure: fact-coverage ≥ 90%` becomes an NFR/SM with no tool behind it in BMM (TEA's
  `bmad-testarch-trace` is an optional extra module). Code↔requirement links (`@fact` regions, line
  markers) are gone: the spec's *Code Map* points spec→file, and nothing points file→FR.
- **Lost:** a lock of what was built from what (`fact-lock.json`), and "status" saying which
  requirements changed since the last build.

## Checked by a program vs. left to the agent
- **Scripts (deterministic):** `lint_spine.py` (placeholders, AD ids, AD fields, version pins);
  `sprint_plan.py` (parse epics → keys, merge without downgrade, validate/repair, dry-run drift);
  `memlog.py` (append-only decision log); config resolution; the epic-context cache goes stale when
  any planning file is newer.
- **Agent judgement (LLM):** PRD validation rubric, the readiness gate, adversarial/edge-case/
  verification-gap reviewers, the build "Matrix Test Audit" (every matrix row has a passing test; never
  edit an expectation to fit the code), and the "frozen-after-approval" rule. These are prompt rules,
  not hooks: nothing stops an edit outside the spec's scope. Writing and running the tests is up to the
  Dev agent, too.
- **BMad is stronger at:** elicitation and pushback, human approval gates, reviewer lenses, retros,
  team process, trackers. FACT has little of this.

## Later change: "make Jupiter bigger"
- **BMad:** the light path is `bmad-build "make Jupiter bigger"`, a freeform spec plus a code edit. PRD
  FR-1 still says 16, and nothing reports the drift. The disciplined path is `bmad-prd` (Update intent:
  edit the FR-1 table, logged to the memlog), then a new build spec. Mid-sprint, use `bmad-correct-course`.
  Finished specs stay frozen as history, and they are not re-checked. The existing test
  "sun > Jupiter" catches a size above 28, but only if the agent runs the suite.
- **FACT:** edit the `bodies/planets` Jupiter row → `fact status` lists that row's marker → the hook
  refuses code edits elsewhere → `fact test` and `fact lock`. The same discipline is enforced, not asked for.
- **Rough edge (6.12.4 source):** PRD/spine land in run folders (`prds/prd-…/prd.md`,
  `architecture/…/ARCHITECTURE-SPINE.md`), but epics discovery globs `{planning_artifacts}/*prd*.md`;
  the agent must find them or ask.

## Sources
- https://github.com/bmad-code-org/BMAD-METHOD/tree/V6.12 (`src/bmm-skills/`: module.yaml, module-help.csv, the
  prd/brief/spine/epics/sprint-status/spec templates, bmad-build steps, v6-shims) · https://docs.bmad-method.org/
  (plan/choose-a-planning-path, plan/break-work-into-stories-and-track-it, build/test-completed-work)
