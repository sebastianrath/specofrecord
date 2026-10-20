<!--
Sync Impact Report
- Version change: (template) → 1.0.0
- Added principles: I–V (all new)
- Added sections: Quality Gates, Development Workflow
- Templates requiring updates: plan-template.md ✅ (Constitution Check reads these gates), tasks-template.md ✅ (tests are requested, so test tasks are kept)
- Follow-up TODOs: none
-->

# Solar System Viewer Constitution

## Core Principles

### I. One Offline File

The product is a single HTML file with every script and style inline. It MUST work when opened
straight from disk with networking turned off. No build-time or run-time downloads, no external
fonts, no CDN.

### II. Calm Like a Planetarium

The page MUST feel calm: dark sky, soft glow, nothing jumps or overlaps. Any change that makes
something jump (time, view, labels) is a defect, not a style choice.

### III. Test-First Through Probes (NON-NEGOTIABLE)

Every testable requirement gets an automated test, written before its implementation and seen to
fail first. Tests drive the page only through the `window.__probe` hooks described in
`contracts/probe-api.md`. Requirements that cannot run headless (by-eye look, dense screens, real
clock gaps) MUST be listed as manual checks in `quickstart.md`.

### IV. One Writer per Piece of State

Only the clock changes time, pause and speed; only the camera changes zoom and pan; drawing code
only reads. Rationale: one owner per piece of state lets agents implement parts in parallel.

### V. Simplicity and Scope

Circular orbits, not to scale, no sound, no textures, no other moons, nothing saved between runs.
Features outside the spec are rejected in review (and reported as "unrequested" by
`/speckit.converge`).

## Quality Gates

- At least 90% of functional requirements are covered by an automated or listed manual test.
- At least 80% of the page's JavaScript lines are exercised by the test suite (Chrome coverage).
- The page runs with zero console errors or warnings.

## Development Workflow

- Specs change before code. A behaviour change starts with an edit to `spec.md`
  (living-spec model), then `plan.md` / `tasks.md` are reconciled and `/speckit.analyze` is run.
- `/speckit.converge` is run after every `/speckit.implement` until it reports Converged.

## Governance

This constitution supersedes other practices. Amendments need a version bump, a line in the Sync
Impact Report and an updated Constitution Check in open plans. Reviews verify compliance.

**Version**: 1.0.0 | **Ratified**: 2026-10-16 | **Last Amended**: 2026-10-16
