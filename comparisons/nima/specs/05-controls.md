<!--
nima spec (hand-created, type "spec"). Ticket SS-6. codebaseFiles: ["out/index.html"].
FACT's "bug: #3" on the pause test has no direct home: nima's bug path is a separate,
generated "bug-repair spec" (Repair Evidence / Repair Verification) born from a signal.
Here it is kept as a regression note on the criterion.
-->
# Controls

## Customer Voice
> No signals (greenfield). Owner: "Let people steer time and the view."

## Problem
People need to change speed, pause, hide lines and names, and get back to the start.

## Approaches Considered
### One small bar
- One small bar at the left of the bottom bar (the Camera's 56 px bottom bar).
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

## Proposed Solution
- **slider** — sets the speed from the Clock's speed rule (0 to 100, start 40).
- **pause** — a button that reads "Pause" or "Play"; the Space key does the same, even right
  after any control was clicked.
- **checkboxes** — "Orbits" and "Names", both on at the start.
- **reset** — time back to 0, view back to the Camera start (zoom 1x, sun centered), nothing
  selected. Speed, play/pause and the checkboxes stay as they are.
- Gives **switches**: orbits on or off, names on or off.
- Needs Clock time, Camera bars, Selection selected.

## Acceptance Criteria
- [ ] Both checkboxes off: no orbit lines and no names: use(orbits), use(names), step(0) →
      strokes.orbitLines is null, count(labels) = 0. [test: controls.checkboxes]
- [ ] Click Pause, then press Space: running again: use(pause), press(Space) → paused is false.
      Regression for bug #3. [test: controls.pause]
- [ ] After zooming, dragging and a new speed, reset restores the view and keeps the speed:
      zoomSteps(4), drag(50, 50), slider(70), use(reset) → zoom = 1, speed unchanged.
      [test: controls.reset]
- [ ] Halfway is a quarter year per second: slider(50) → speed ≈ 0.25 ± 0.001. [test: controls.slider]
- [ ] The orbit switch turns orbit lines off and on again: use(orbits) → strokes.orbitLines
      is null; use(orbits) → strokes.orbitLines = 1. [test: controls.switches]

## Edge Cases
- **Space right after a click** — the focused control could swallow the key.
  **Desired outcome:** Space still toggles pause (bug #3).

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded.

## Not Doing
- Saving state (see Solar System viewer).
