# Solar system in Kiro: notes

Files: `.kiro/steering/{product,tech,structure,spec-first}.md`; feature spec
`.kiro/specs/solar-system-viewer/{requirements,design,tasks}.md`; bugfix spec
`.kiro/specs/pause-space-after-click/{bugfix,design,tasks}.md` (FACT's `bug: #3`);
hooks `.kiro/hooks/{spec-first-guard,requirements-changed,run-tests-on-stop}.json`.
Format choice: the brief named `*.kiro.hook` with `askAgent`. That is the IDE 0.x format.
Current docs say IDE 1.0 moved hooks to `.kiro/hooks/*.json` with `"version": "v1"`,
`when`/`then` and action types `command`/`agent`, so I used that. CLI V3 documents another
shape (`hooks[]`, `trigger: "PreToolUse"`, `action`). Marked guesses: the tasks.md syntax
(`- [ ]*`, `_Requirements:_`, Checkpoint), the property layout in design.md, the tool-name
pattern `write`, and the stdin field that carries the written path.

## How a developer works (IDE)
Spec panel, then **+**, then Feature spec (Requirements-First). Describe the viewer in chat
and Kiro drafts requirements.md. You edit and approve it ("Analyze Requirements" is
optional), then Kiro drafts design.md and tasks.md. **Generate Steering Docs** writes
product/tech/structure. You run tasks with "Start task" or **Run all Tasks**, which runs
independent tasks in parallel waves. Hooks are managed in the Agent Hooks panel.

## What carries over
- **Fully:** every number (bodies table, 1.1x, 0.3-6x, 4 px, 56/28 px, slider 0-100 start
  40, (s/100)^2 years/s, 0.1 s cap, 300 stars, 20 s comet, 10 px reach), as EARS criteria.
  All 40-odd FACT tests appear as rows in the design.md test table and as test tasks.
  The bug also has a natural home: a Bugfix spec with current, expected and "SHALL CONTINUE
  TO" behavior. FACT has no equivalent of that.
- **Only as prose:** FACT's tests are an executable `do/expect` DSL run by `fact test`.
  In Kiro they are table rows and properties that the agent turns into test code. Whether
  that code checks "± 0.5" is up to the agent. Derived values (`{year} = Earth.days`, test
  expects that reference `{bars.top}`) become copied literals (365, 56, 84). Editing one
  copy leaves the others stale. The Approach/Contract split, `because:` rationales,
  `owns`/one-writer and `needs` are free text in design.md. "90% of facts proven" became
  "90% of acceptance criteria validated", which a task checks by hand.
- **Manual tests:** these become unchecked tasks marked "a person ticks these". Nothing
  stops the agent from ticking them. FACT's `--confirm` is also only a convention, but it
  is recorded in the lock.

## What Kiro checks automatically vs. what relies on the agent
- **Automatic:** hooks fire on events. `spec-first-guard` blocks a write to `out/` when no
  file under `.kiro/specs/` differs from HEAD (a non-zero exit blocks Pre Tool Use).
  `run-tests-on-stop` runs `npm test` and sends failures back to the agent. Task status and
  Sync Files track which tasks are done. Property-based tests shrink failing inputs.
- **Agent-dependent:** everything that links code to criteria. Kiro has no code markers, no
  lock file and no hash of the spec. The `// Req 6.1` comments are a steering convention.
  The requirements-changed hook only asks the agent to update design and tasks.
- **How close the guard gets:** about halfway. It enforces "some spec file changed
  first", but any edit to the spec unlocks every line of code. It cannot tell whether the
  code edit matches that edit. Once the spec is committed it blocks legitimate "build it"
  work. Per the docs, file and task triggers fire only on agent edits, so a person's edits
  are never checked. FACT's edit hook knows which `@fact` region belongs to which fact and
  which facts changed since the lock. That is what Kiro lacks.

## Later change: "make Jupiter bigger"
The agent (steered by spec-first.md) edits Req 1.3's table row (Size 16 to e.g. 20). The
guard now allows the code write. If the agent edited the file, requirements-changed fires
and the agent updates design.md (the Req 1.6 "sun > jupiter" check is still valid, since
sun 28 > 20). Sync Files reopens task 2.1. The agent finds the Jupiter row in
`out/index.html` by searching, not via a marker, edits it, and run-tests-on-stop runs the
tests. Nothing would notice if the agent changed the code but forgot the table, as long as
any spec file was dirty. Nothing would notice if it changed the table and forgot the code,
because no test pins Jupiter's size. In FACT, `fact status` names the `bodies/planets/Jupiter`
row and its line marker, and the lock records that it was rebuilt.

**Credit to Kiro:** it needs less format discipline, and EARS is a widely known notation.
It has a guided IDE flow with approvals, parallel task waves, PBT with shrinking, bugfix
specs, and hooks on many more events.

## Sources
kiro.dev/docs/specs/ (+ feature-specs/, best-practices/, correctness/), kiro.dev/docs/steering/,
kiro.dev/docs/hooks/ (+ types/, actions/), kiro.dev/docs/ide/0x-reference/,
kiro.dev/docs/cli/v3/hooks-migration/, kiro.dev/blog/automate-your-development-workflow-with-agent-hooks/
