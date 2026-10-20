# Implementation Plan: Solar System Viewer

**Branch**: `001-solar-system-viewer` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-solar-system-viewer/spec.md`

## Summary

A single offline HTML page that draws the sun, 8 planets and the moon on a 2D canvas, moving on
circles driven by a simulated clock (365 days per second at top speed), with drag/zoom, a control
bar and click-to-learn panels. Six modules inside one `<script>`: bodies, clock, camera, scene,
controls, selection. Tests drive the page through a `window.__probe` hook in headless Chrome.

## Technical Context

**Language/Version**: HTML5, CSS, JavaScript (ES2020), no transpiler

**Primary Dependencies**: None at runtime. Tests: Node 20, Puppeteer (headless Chrome), `node:test`

**Storage**: N/A (nothing saved, spec Assumptions)

**Testing**: `node --test tests/` driving `out/index.html` through `window.__probe`; line coverage from Chrome's built-in JS coverage (`page.coverage`)

**Target Platform**: Current desktop and mobile browsers with Canvas 2D; opened via `file://`

**Project Type**: Single static web page

**Performance Goals**: 60 fps on a mid-range laptop with 300 stars and 10 bodies

**Constraints**: One file, offline, zero console errors/warnings, sharp on devicePixelRatio > 1

**Scale/Scope**: 10 bodies, 1 comet, 300 stars, 6 modules, ~600 lines

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. One Offline File | PASS | Everything inline in `out/index.html`; no fetch, no fonts, no CDN |
| II. Calm Like a Planetarium | PASS | Frame-gap cap (FR-010), label overlap rule (FR-022), fixed px sizes (FR-017) |
| III. Test-First Through Probes | PASS | `contracts/probe-api.md`; test tasks precede implementation in tasks.md; 4 manual checks in quickstart.md |
| IV. One Writer per State | PASS | Clock owns time/paused/speed, camera owns zoom/pan; scene reads only (see data-model.md) |
| V. Simplicity and Scope | PASS | No out-of-scope items planned |
| Gate: ≥90% FRs tested, ≥80% lines | PENDING | Measured in T046 |

Post-design re-check: PASS (no violations; Complexity Tracking empty).

## Project Structure

### Documentation (this feature)

```text
specs/001-solar-system-viewer/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/
│   └── probe-api.md     # Phase 1 output (/speckit.plan command)
├── checklists/
│   └── requirements.md  # /speckit.specify output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
out/
└── index.html           # the whole product: markup, style, script (modules as sections)

tests/
├── helpers/probe.js     # opens out/index.html in Puppeteer, applies before-each, exposes __probe
├── contract/probe.test.js
├── integration/
│   ├── bodies.test.js
│   ├── clock.test.js
│   ├── camera.test.js
│   ├── scene.test.js
│   ├── controls.test.js
│   └── selection.test.js
└── coverage.test.js     # SC-001/SC-002 gate
package.json             # devDependencies: puppeteer
```

**Structure Decision**: Single static page. Module boundaries are sections of one `<script>` in
`out/index.html`, in this order: bodies, clock, camera, scene, controls, selection, probe.

### Frame journey and draw order

Open: start angles are picked → the clock runs → each frame the scene draws body positions
through the camera's space→screen transform. Draw order: sky, stars, comet, orbits, sun,
planets, moon, selection ring, names, time.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
