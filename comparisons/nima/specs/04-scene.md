<!--
nima spec (hand-created, type "spec"). Ticket SS-5. codebaseFiles: ["out/index.html"].
-->
# Scene

## Customer Voice
> No signals (greenfield). Owner: "Draw everything, calm and clear, like a planetarium."

## Problem
Everything must be drawn in a calm, readable way, in a fixed order, at every zoom.

## Approaches Considered
### One draw pass in fixed order
- Order: sky, stars, comet, orbits, sun, planets, moon, selected ring, names, time.
- Look is a sketch: glow, shading, ring tilt and fonts are the implementer's choice.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

## Proposed Solution
- **sky** — blue-black (#05060F), 300 softly twinkling stars that ignore zoom and pan.
- **orbits** — faint 1 px circles for the planets and the moon, while switched on.
- **bodies** — a glowing sun; planets brighter on the side facing the sun; Saturn's ring
  passes behind and in front of it.
- **selected** — a white ring, 2 px wide, 4 px outside the selected body.
- **names** — 12 px names under the bodies, while switched on; when two would overlap, the one
  closer to the sun stays; the moon's name shows once it is 30 px from Earth.
- **time** — top left: "Year 0, day 0" at the start, counting years (365 days) and days.
- **comet** — a small comet with a faint tail crosses the solar system every 20 s; its path is
  in space units, so it moves and zooms with the planets.
- Needs Bodies positions, Camera to-screen, Controls switches, Selection selected.

## Acceptance Criteria
- [ ] All 300 stars are there, and zooming or dragging does not move them: zoomSteps(5),
      drag(30, 0) → count(stars) = 300, stars unchanged. [test: scene.sky]
      Regression: the first build drew no stars.
- [ ] (manual, by eye) The sun glows, planets are lit from the sun's side, Saturn's ring
      crosses it. Regression: the first build drew flat circles. [test: scene.bodies, manual]
- [ ] At top speed names never overlap, checked once a second for 20 s:
      20 × (slider(100), step(1) → overlaps(labels) = 0). [test: scene.names]
- [ ] At the smallest and largest zoom, lines and names keep their size: clickBody(jupiter),
      zoomAt(jupiter, -400), remember strokes, zoomAt(jupiter, 400) → strokes unchanged.
      [test: scene.selected]
- [ ] After one year at top speed the display reads year 1: slider(100), step(1) →
      hud contains "Year 1". [test: scene.time]
- [ ] Dragging the view moves the comet with it: showComet(), drag(50, 0) → comet.x changed
      by 50 ± 1. [test: scene.comet]

## Edge Cases
- **Two names overlap** — **Desired outcome:** the one closer to the sun stays.
- **Moon close to Earth** — **Desired outcome:** the moon's name shows only once it is 30 px
  from Earth.

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded.

## Not Doing
- Textures, sound (see Solar System viewer).
