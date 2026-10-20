---
title: 'Story 1.3: Clock and orbital motion'
type: 'feature'
created: '2026-10-16'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-solar-system-2026-10-16/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The bodies from Story 1.2 sit still; there is no simulated time, so nothing moves and
no later story (time display, speed slider, comet) has a clock to read.

**Approach:** Add the `clock` module (sole owner of time, paused, speed) and make `bodies` compute
positions from it: clockwise circles, angle = start + 2π × time ÷ orbit days; the moon around
Earth's current position. Wire `probe.step` and the frozen-time rule from AD-4.

## Boundaries & Constraints

**Always:** time in days; speed = (slider ÷ 100)² years per second, year = 365 days; slider range
0–100, start 40; real-time frames capped at 0.1 s; only `clock` writes time/paused/speed (AD-2);
`probe.step(s)` advances exactly `s × speed` years with no cap, never while paused (AD-4).

**Never:** no slider UI or Pause button here (Story 2.1 — set speed via `probe.slider` only); no
elliptical orbits; no easing or smoothing of positions.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start | page opened or `use(reset)` | `time` = 0, `paused` false | N/A |
| Stand still | `slider(0)`, `step(1)` | `time` unchanged | N/A |
| Half speed | `slider(50)`, `step(4)` | `time` +365 ± 1% | N/A |
| Top speed | `slider(100)`, `step(1)` | `time` +365 ± 1%; `time` = 365 exactly from 0 | N/A |
| Probe has no cap | `slider(100)`, `step(1)` | `time` +365 ± 0 | N/A |
| Earth year | `slider(100)`, `step(1)` | `body(earth).x` back to start ± 1 | N/A |
| Moon month | `slider(100)`, `step(0.073972602739726)` | `offset(moon, earth)` x and y ± 0.5 | N/A |
| Paused | `press(Space)`, `step(2)` | `time` unchanged | N/A |
| Start places | `step(5)` | `startAngles` unchanged | N/A |
| Hidden tab | real frame with dt = 30 s | adds only 0.1 s × speed | manual check |

</frozen-after-approval>

## Code Map

- `out/index.html` `<script>` → `bodies` (from Story 1.2) -- add `positionAt(time)`; reuse the
  `startAngles` array, do not re-randomise
- `out/index.html` `<script>` → new `clock` module between `bodies` and `camera` (spine order)
- `out/index.html` `<script>` → `probe` (from Story 1.1) -- add `time`, `paused`, `speed`, `step`,
  `slider`, `setPaused`, `press('Space')`; `startAngles` read already exists
- `out/index.html` `<script>` → animation loop -- call `clock.tick(dt)` before `scene.draw()`
- `tests/probe.spec.ts` -- one test per matrix row, named after the FR

## Tasks & Acceptance

**Execution:**
- [ ] `out/index.html` -- add `clock` with `time`, `paused`, `speed`, `tick(dt)`, `setSlider(v)`,
  `setPaused(on)`, `reset()` -- FR-5..FR-8, AD-2
- [ ] `out/index.html` -- `bodies.positionAt(time)` with clockwise angle and moon-around-Earth -- FR-4
- [ ] `out/index.html` -- Space key toggles `clock.paused` on `window` keydown -- FR-7
- [ ] `out/index.html` -- `probe.step`, `probe.slider`, `probe.setPaused`, frozen real time after the
  first probe call -- AD-4, AD-5
- [ ] `tests/probe.spec.ts` -- tests for every I/O matrix row except the manual one -- NFR-7

**Acceptance Criteria:**
- Given the app has run for 5 s, when errors are read, then `count(errors)` = 0 (NFR-2).
- Given Story 1.2's tests, when the suite runs, then they still pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `npx playwright test tests/probe.spec.ts -g "FR-4|FR-5|FR-6|FR-7"` -- expected: all pass
- `npx playwright test` -- expected: whole suite passes

**Manual checks (if no CLI):**
- Open `out/index.html`, switch to another tab for 30 s, come back: planets continue from where they
  were, no visible jump (FR-8).
