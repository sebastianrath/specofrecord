---
title: 'Story 2.2: Zoom with wheel and pinch'
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

**Problem:** The view is fixed at the start fit (Story 1.4); a viewer cannot look closer at a planet.

**Approach:** Give `camera` a `zoomBy(steps, anchor)` that multiplies zoom by 1.1 per step, clamps to
0.3–6, and adjusts pan so the space point under the anchor stays on the same screen pixel. Wire the
mouse wheel (one notch = one step) and two-finger pinch to it.

## Boundaries & Constraints

**Always:** only `camera` writes zoom and pan (AD-2); all space→screen conversion through
`camera.toScreen` (AD-3); line widths, name size and selection-ring width stay constant in px (NFR-3);
one wheel notch = exactly one step regardless of `deltaY` magnitude (NFR-6).

**Never:** no smooth/animated zoom; no keyboard zoom; no change to the base-scale fit rule.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| One notch | `zoomSteps(1)` from start | `zoom` = 1.1 | N/A |
| Anchored | `zoomAt(earth, 1)` | `zoom` = 1.1; `body(earth).x` unchanged ± 1 | N/A |
| Pinch | `zoomAt(earth, -1)` then `pinch(1)` | `zoom` = 1.1 | N/A |
| Upper limit | `zoomSteps(200)` | `zoom` = 6 | clamp, no error |
| Lower limit | then `zoomSteps(-400)` | `zoom` = 0.3 | clamp, no error |
| Units | `zoomSteps(5)` | `strokes` unchanged; `body(earth).r` larger | N/A |

</frozen-after-approval>

## Code Map

- `out/index.html` `<script>` → `camera` (Story 1.4) -- add `zoomBy(steps, anchorScreenPt)`;
  reuse `toSpace`/`toScreen`; do not touch `fitBaseScale()`
- `out/index.html` `<script>` → input handlers -- `wheel` (passive: false, preventDefault) and
  `touchstart/touchmove` for two touches
- `out/index.html` `<script>` → `probe` -- add `zoom`, `zoomSteps`, `zoomAt`, `pinch`, `strokes`
- `tests/probe.spec.ts` -- FR-11, FR-12, NFR-3, NFR-6 tests

## Tasks & Acceptance

**Execution:**
- [ ] `out/index.html` -- `camera.zoomBy` with 1.1ⁿ, clamp [0.3, 6], anchor-preserving pan -- FR-11, FR-12
- [ ] `out/index.html` -- wheel handler: sign of `deltaY` → ±1 step at pointer -- NFR-6
- [ ] `out/index.html` -- pinch handler: distance ratio → whole steps around the touch midpoint -- FR-11
- [ ] `out/index.html` -- probe members listed in the Code Map -- AD-5
- [ ] `tests/probe.spec.ts` -- one test per matrix row -- NFR-7

**Acceptance Criteria:**
- Given Story 3.3 is not built yet, when `strokes` is read, then `selectionRing` may be null; the
  units test compares only non-null members. `[GUESS: ordering of stories; recheck after 3.3]`

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `npx playwright test -g "FR-11|FR-12|NFR-3|NFR-6"` -- expected: all pass
- `npx playwright test` -- expected: whole suite passes

**Manual checks (if no CLI):**
- On a touch device, pinch over Saturn: Saturn stays under the fingers.
