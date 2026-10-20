<!--
nima spec (hand-created, type "spec"). Ticket SS-4. codebaseFiles: ["out/index.html"].
This is the spec the drift example (../pr-drift-example.md) is checked against.
-->
# Camera

## Customer Voice
> No signals (greenfield). Owner: "Decide which part of the solar system is visible, and how big."

## Problem
The whole system must fit the screen at the start, and people must be able to zoom and drag
without losing their place.

## Approaches Considered
### Base scale × zoom
- A base scale fits the system between the bars; zoom multiplies it. Recomputed when the
  window changes size, in width and height.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

## Proposed Solution
- **fit** — at the start the outermost orbit, plus 28 px room for its planet and name, fits
  between the bars, at most 1 px per space unit.
- **start** — zoom 1x, sun in the middle of the screen.
- **zoom-step** — one wheel notch or pinch step zooms by 1.1x; the point under the pointer
  stays put.
- **limits** — zoom stays between 0.3x and 6x.
- **drag** — dragging moves the view; a press that moves less than 4 px is a click.
- Gives **to-screen** (space point to screen point and back) and **bars** (top 56 px and
  bottom 56 px stay free at the start).
- Owns **view**: zoom and pan; nobody else changes them. Needs the Bodies table's outermost orbit.

## Acceptance Criteria
- [ ] At 1280x720, 800x600 and 640x480 nothing drawn touches a bar: layout.gapTop ≥ 56,
      layout.gapBottom ≥ 56, layout.orbitTop = 56 + 28 ± 0.5, layout.orbitBottom = 56 + 28 ± 0.5.
      [test: camera.fit]
- [ ] One step over Earth keeps Earth under the pointer: zoomAt(earth, 1) → zoom = 1.1 and
      body(earth).x changed by 0 ± 1; zoomAt(earth, -1), pinch(1) → zoom = 1.1. [test: camera.zoom-step]
- [ ] Zooming forever stays inside the limits: zoomSteps(200) → zoom = 6;
      zoomSteps(-400) → zoom = 0.3. [test: camera.limits]
- [ ] Dragging moves the view; a press that barely moves does not: drag(50, 0) → pan.x changed
      by 50 ± 0.5; drag(3, 0) → pan unchanged. [test: camera.drag]
- [ ] A body's place on screen follows the view: drag(30, 0) → body(mars).x changed by
      30 ± 0.5. [test: camera.to-screen]

## Edge Cases
- **Window resize** — a fixed base scale would leave the system off-fit.
  **Desired outcome:** the base scale is recomputed in width and height.
- **Tiny drag** — a press that moves 3 px.
  **Desired outcome:** it is a click, the view does not move.

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded.

## Not Doing
- True scale (see Solar System viewer).
