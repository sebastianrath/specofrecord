---
title: 'Story 3.1: Click selection — reach, nearest wins, miss'
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

**Problem:** Bodies cannot be selected, so the panel (Story 3.2) and ring (Story 3.3) have nothing
to show. Tiny bodies at low zoom are almost impossible to hit.

**Approach:** Add the `selection` module (sole owner of the selected body). On a click (a press that
moved < 4 px, from Story 2.3), collect every body whose screen distance to the click is within
max(on-screen radius, 10 px) and select the one whose center is nearest; none in reach → select
nothing.

## Boundaries & Constraints

**Always:** reach = max(body's on-screen radius, 10 px) in px, independent of zoom (AD-3); distance
decides, never a fixed body order — at start zoom the moon's reach covers Earth; only `selection`
writes `selected` (AD-2).

**Never:** no hover highlight; no keyboard selection; the panel itself is Story 3.2.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Direct hit | `clickBody(venus)` | `selected` = "venus" | N/A |
| By name, all 10 | `clickBody(name)` for each body | `selected` = name | N/A |
| Crowded, smallest zoom | 1280×720 and 800×600; `zoomSteps(-400)`, `step(0.37)`; click mercury, earth, moon; 10 runs | each selects itself | N/A |
| Just inside min reach | `zoomSteps(-400)`, `clickNear(neptune, 9)` | `selected` = "neptune" | N/A |
| Outside reach | `clickNear(neptune, 12)` | `selected` = null | N/A |
| Miss | `clickBody(jupiter)`, `click(3, 300)` | `selected` = null | N/A |

</frozen-after-approval>

## Code Map

- `out/index.html` `<script>` → new `selection` module after `controls` (spine order) --
  `pick(screenPt)`, `selected`, `clear()`
- `out/index.html` `<script>` → pointer handlers (Story 2.3) -- on click, call `selection.pick`
- `out/index.html` `<script>` → `controls.reset` (Story 2.4) -- call `selection.clear()` (FR-24)
- `out/index.html` `<script>` → `probe` -- add `selected`, `click`, `clickBody`, `clickNear`
- `tests/probe.spec.ts` -- FR-25, FR-26, FR-28, FR-29, and FR-1's "clickable by name"

## Tasks & Acceptance

**Execution:**
- [ ] `out/index.html` -- `selection.pick`: candidates within reach, nearest center wins -- FR-25, FR-26
- [ ] `out/index.html` -- click on empty space clears the selection -- FR-28
- [ ] `out/index.html` -- probe `clickBody` dispatches a real pointer event at the body's screen
  center; `clickNear` offsets away from the sun -- AD-5
- [ ] `tests/probe.spec.ts` -- one test per matrix row; the crowded case loops sizes × 10 runs -- NFR-7

**Acceptance Criteria:**
- Given any selection, when `use(reset)` runs, then `selected` is null.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

A first-match loop in table order makes Earth unclickable at start zoom (the moon's 10 px reach
covers it). Collect all candidates, then sort by distance:

```js
const hits = bodies.all.filter(b => dist(pt, toScreen(b)) <= Math.max(b.screenR, 10));
selected = hits.sort((a, b) => dist(pt, toScreen(a)) - dist(pt, toScreen(b)))[0]?.id ?? null;
```

## Verification

**Commands:**
- `npx playwright test -g "FR-25|FR-26|FR-28|FR-29|FR-1"` -- expected: all pass, 10/10 crowded runs
- `npx playwright test` -- expected: whole suite passes
