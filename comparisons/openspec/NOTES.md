# Solar system in OpenSpec: notes

Layout: `openspec/config.yaml` (project context, the 1.x replacement for `project.md`),
`openspec/specs/<capability>/spec.md` (8 capabilities, one per FACT part plus a cross-cutting one),
and `openspec/changes/make-jupiter-bigger/` (proposal, design, tasks, `.openspec.yaml`, delta spec).
Not run: `openspec validate --strict`. The CLI is not installed here and installing it needs a
download. I checked the files with a script against the rules in the source: Purpose ≥ 50 chars,
SHALL/MUST in every requirement body, body ≤ 500 chars, ≥ 1 scenario, Why 50–1000 chars.
Guesses are marked `guess:` in HTML comments.

## Commands a developer would run
    npm install -g @fission-ai/openspec@latest
    openspec init --tools claude          # writes config.yaml + .claude/skills (opsx)
    /opsx:propose make-jupiter-bigger      # agent writes proposal/design/tasks/delta (or: openspec new change ...)
    openspec validate make-jupiter-bigger --strict
    openspec show make-jupiter-bigger --deltas-only
    /opsx:apply                            # agent edits code, ticks tasks.md
    <your own test runner>                 # OpenSpec runs no tests
    openspec archive make-jupiter-bigger -y   # merges MODIFIED block into specs/bodies, moves to changes/archive/
    openspec list --specs; openspec validate --all --strict

## What maps well
- Facts with a test map to a Requirement (SHALL) with Scenarios (WHEN/THEN). All 43 FACT tests
  appear as scenarios with the same steps, numbers and tolerances.
- Changing a value is a reviewable delta. Archive applies it mechanically, and validate refuses
  a MODIFIED block that drops a scenario the current spec still has.
- Rationale (`because:`) and refinement links fit as prose in a requirement body.

## What only goes in as prose, or is lost
- Named values and references (`{factor: 1.1x}`, `{year.days}`, `= bodies/planets/Earth.days`):
  OpenSpec has no values. 365, 1.1, 56+28=84 etc. are copied as literals, so changing Earth's
  days would mean editing about 8 places by hand, and nothing flags a missed one.
- Test semantics: `each:` loops, `remember`/`changed by ± tol`, `measure:`, `bug: #3` and
  `manual:` are just bullet text or comments. OpenSpec does not parse WHEN/THEN, run them,
  separate manual from automated, or record that a person confirmed a manual check.
- Approach vs. Contract vs. Facts: all become "Requirement". `gives`/`needs`/`owns` (one-writer)
  turn into sentences, and the part dependencies are not checked.
- FACT items with no test of their own (calm, year, start view, orbit lines, probe list)
  needed a borrowed or pointer scenario, because strict mode fails a requirement with no scenario.
  FACT allows untested facts and reports them through its coverage threshold instead.
- The 500-char body limit split `meanings` and the probe API into several requirements, and
  the planet table only fits in compact form (428 chars).
- Out-of-scope, parts/journey, one-writer, units, owner: only in `config.yaml` context (prose).
- Code traceability: `@fact` markers, `fact markers file:line`, the edit hook that refuses code
  edits whose fact did not change, the notes glue comment, `fact-lock.json` drift detection
  (`fact status`: which facts changed since the last build). OpenSpec has none of these: specs
  and code are never linked, so nothing detects spec-only or code-only edits outside a change.
- Coverage gates (90% facts proven, 80% lines): stated as a requirement; nothing measures them.

## Checked automatically vs. left to the agent
Automatic (`validate`): headings and structure, SHALL/MUST, ≥ 1 scenario, empty scenarios,
duplicate or conflicting delta names, RENAMED pairing, MODIFIED dropping scenarios, Why/What
Changes present, ≤ 10 deltas, and (with `--archived`) all tasks ticked. `archive` merges deltas.
Left to the agent or person: writing code that meets the scenarios, turning scenarios into tests,
running them, keeping literal numbers consistent across specs, deciding when a change is done
(ticked tasks only), and noticing code that no longer matches a spec.

## Where OpenSpec is stronger than FACT here
Explicit change proposals with why/impact/design that stay in an archive as history; deltas
that validate before merging; slash commands and skills for many AI tools, and a mature CLI. FACT keeps
no per-change "why" beyond git history.

## Sources
https://github.com/Fission-AI/OpenSpec (README); docs/ concepts.md, cli.md, writing-specs.md,
customization.md, migration-guide.md; src/core/validation/constants.ts and validator.ts;
schemas/spec-driven/templates/ (all under https://github.com/Fission-AI/OpenSpec/blob/main/).
