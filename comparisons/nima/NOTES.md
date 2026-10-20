# nima vs FACT: the solar system project

Files: `specs/00…07-*.md` (one nima spec per FACT page), `links.json` (spec metadata, tickets,
code and test links), `pr-drift-example.md` (zoom step 1.1x → 1.25x, spec unchanged).

## How a developer works with it
nima is a hosted, private-beta service (waitlist), not a file format. It is built for a feedback
loop: Signal (Slack, Linear, Sentry…) → Beacon (ranked cluster) → a person promotes it → nima writes
a codebase-grounded Spec → promote to a ticket → PR → Closed (customer notified). A greenfield
project has no signals, so here each spec is created by hand (`POST /documents` type `spec`,
`PUT …/markdown`), which owners/admins only may do and which skips the section validator. The
specs live in nima, not in git; agents read them over MCP (`list_specs`, `get_document_markdown`,
`get_spec_delivery`, `blast_radius`, `search_code`) but no MCP tool edits a spec. Status
(draft → approved → in_progress → shipped) is driven by promotion, PR links and merges.

## Which FACT facts and tests carry over
- All facts, numbers, tables, the "because" lines (as Decisions / rejected approaches) and the
  out-of-scope list carry over as prose in nima's fixed sections. Nothing was dropped.
- All 43 tests carry over as Acceptance Criteria checklist items, with their do/expect steps written
  out. The `[test: …]` tags and `tests/*.spec.js` names are our convention; nima has no
  criterion → test link and does not run tests. Manual tests are just unticked boxes.
- Lost in translation: value references (`{year}` = Earth's 365 days, `{camera/zoom-step.factor}`
  used by two pages) become copied literals that can drift apart silently; `bug:` lines become
  regression notes (nima's bug path is a generated repair spec born from a signal); the quality
  bar (90% facts proven, 80% lines run) is text nobody measures; `@fact` markers have no equivalent.
- nima's required Effort and Risks sections have no FACT source; filled with "low" / "none recorded"
  and marked as such. Customer Voice is the owner's Why line, since there are no customers.

## What is checked automatically, and how
- Deterministic (documented): symbol/import indexing (parser, 12 languages, default branch only),
  `blast_radius` / `get_data_model` (no model calls), PR → ticket matching by key in branch/title/
  body, status transitions, test discovery by path name.
- Model judgement: PR → ticket fallback (AI match ≥ 0.7, documented), signal labelling and beacon
  placement (documented). The drift check itself (per-section `aligned` / `drifted` /
  `not_addressed`) is not documented as either; comparing a diff to prose sections is in practice
  an LLM call. It posts a PR comment; no check run or merge block is described.
- Left to the agent/team: writing and running the tests, keeping copied numbers consistent across
  specs, editing the spec when the drift was intended.
- For this project specifically: the code is JS inside one HTML file and HTML is not an indexed
  language, so nima sees no symbols; every spec links to the same file, and the drift check's
  fallback spec match ("a spec mentioning a segment of a changed path") would be ambiguous.

## Honest comparison
- nima's strength is what FACT lacks entirely: the why-chain from customer evidence to spec to PR
  to "shipped", review of intent in natural language (it can notice a change that breaks a
  sentence no test covers, e.g. "nothing jumps"), and team workflow (Slack, tickets, watches).
- FACT's strength is a deterministic, local, versioned check: a changed value fails its test and
  the edit hook refuses code without a fact change. But FACT checks only what its tests express;
  "calm" or "one true fun fact" are no better guarded there than in nima.
- Different targets: nima assumes 15–200 engineers with a tracker and incoming feedback; FACT
  assumes an agent building a small program from facts. This example suits FACT's shape better.

## Documented vs. guessed
Documented: spec sections and their rules, statuses, API/MCP names, drift record fields and
verdicts, "PRD Drift Check" comment, PR matching, indexing limits. Guessed: the comment layout,
the `sections[]` item shape, `codebaseFiles` format, ticket prefix, that only the card's spec is
checked, that drift never blocks merge, and that the drift check is an LLM. Not tested hands-on.

## Sources
- https://getnima.io/ · https://getnima.io/blog/spec-first-vs-spec-anchored/
- https://docs.getnima.io/docs/index.html · …/docs/concepts/anatomy-of-a-spec/
- https://docs.getnima.io/docs/concepts/delivery/ · …/docs/concepts/code-intelligence/
- https://docs.getnima.io/docs/concepts/knowledge-graph/ · …/docs/concepts/how-nima-decides/
- https://docs.getnima.io/docs/api/specs/ · …/docs/mcp-server/pipeline-tools/ · …/docs/integrations/github/
- https://github.com/getnima/skills
