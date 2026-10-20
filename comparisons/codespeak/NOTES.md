# Solar system in CodeSpeak: notes

Files: `codespeak.json`, `AGENTS.md`, `solar-system.cs.md`. `codespeak init` would also create
`.codespeak/` (internal state) and `.gitignore`; they are left out here. A build would produce
`out/index.html`, `tests/*.mjs` and `package.json`. Generated code carries no markers, so
there is no excerpt to show.

## Commands
- `uv tool install codespeak-cli` · `codespeak login` · `codespeak init`
- `codespeak build` (generate + run tests + fix loop) or `codespeak impl` (no tests)
- `codespeak test --auto-configure --spec solar-system.cs.md` (writes the runner command)
- `codespeak test --max-iterations 5` · `codespeak coverage --target 80 --max-iterations 5`
- A code bug with a correct spec (FACT `bug: #3`): `codespeak change -m "Space after clicking
  Pause does not resume"` (stored as `change-request.cs.md`).
- Changing a requirement: edit the spec, `codespeak build` (only changed specs rebuild).

## Guesses (not shown in the docs)
- Shape of `test_runner_configurations` (per-spec object); key names `run_all_tests_command` and
  `run_all_tests_with_coverage_command` are from error messages in the docs.
- Writing tests as `<test>` blocks in the spec; the docs only advise scenarios and XML tags.
- One spec instead of six: imports map specs to separate managed files, and FACT wants one file.

## What carries over
- All numbers, the body table, colors, behaviors, out-of-scope list: as plain Markdown prose.
- Every automated FACT test: as a prose scenario. The probe API: as a prose section.
- `because:` reasons: as inline sentences (the moon/Earth click note, the hidden-tab cap).
- FACT `quality.lines 80%`: `codespeak coverage --target 80`. But coverage is documented as
  Python-only (0.3.2 post) and LCOV-based; a browser page's inline JS needs a custom LCOV step.

## What does not, or only as prose
- Fact ids and value references (`{zoom-step.factor}`, `{year.days}`): no syntax. Numbers are
  copied (84 = 56 + 28 written out by hand), so one change must be repeated in several places.
- Contracts (`gives`/`needs`/`owns`, one-writer): prose only; the modularity post says interface
  checking between imports is future work.
- `manual:` tests and their confirmation: comments only; nothing tracks that a person checked.
- `bug:` history on a test: no place; change requests are one-off and consumed.
- `fact-coverage ≥ 90%` (share of facts proven by a test): no equivalent.
- Test strength (does a test fail when a value changes): no equivalent.
- Tracing a code line to a requirement (`@fact` markers, `fact markers file:line`): none;
  traceability is per spec file (managed files), not per requirement.

## Checked by the tool vs. left to the agent
- Tool: spec diff since last build (unchanged specs skipped), import order and cycles, which
  files a spec manages (`strictManagedFilesControl` blocks writes elsewhere), running the test
  command and looping until green or out of iterations, coverage percentage toward a target.
- Agent (LLM): turning prose scenarios into test code, so whether a generated test checks
  "± 0.5" or "unchanged" faithfully is not verified by any tool; deciding which code a spec
  diff touches; keeping numbers consistent. In FACT the `do:/expect:` lines are executed
  directly by `fact test`, so test fidelity does not depend on the agent there.
- In CodeSpeak the agent also fixes failures during `build`/`test`; nothing in the docs stops it
  from editing generated tests, so AGENTS.md asks it not to weaken them.
- CodeSpeak advantages worth noting: much less ceremony to write (plain Markdown, one comment
  syntax), a ready fix loop and coverage loop, `takeover` to start from existing code, and
  explicit code-bug vs spec-bug workflow (`change`). It is Alpha Preview.

## Sources
- https://codespeak.dev/docs/getting-started/quickstart
- https://codespeak.dev/docs/getting-started/testing-workflow
- https://codespeak.dev/docs/getting-started/coverage
- https://codespeak.dev/docs/programming-system/imports
- https://codespeak.dev/docs/programming-system/managed-files
- https://codespeak.dev/docs/programming-system/comments
- https://codespeak.dev/docs/programming-system/stylistic-guidelines
- https://codespeak.dev/docs/programming-system/spec-driven-evolution
- https://codespeak.dev/docs/reference (build, test, coverage, change, codespeak-json,
  agents-md, spec-file-naming)
- https://codespeak.dev/docs/glossary
- https://codespeak.dev/blog/modularity-20260309 · https://codespeak.dev/blog/coverage-20260302
