<!--
nima spec document (Markdown body as stored by PUT /documents/{id}/markdown).
Created by hand with POST /documents {"title": "Solar System viewer", "type": "spec"}:
a greenfield project has no signals, so no beacon exists and nima did not write this.
Section names and rules (Chosen: yes, Desired outcome, Level) are from the documented
"Anatomy of a spec". Hand-written Markdown is not run through the section validator.
The "[test: ...]" tags in Acceptance Criteria are OUR convention, not a nima feature.
Owner (ownerId): sebastian. Ticket after promote: SS-1 (key prefix guessed).
-->
# Solar System viewer

## Customer Voice
> No signals: greenfield project. Owner's words instead:
> "A calm, good-looking way to watch the planets move and learn one fact about each."

## Problem
There is no simple offline page that shows the sun, the eight planets and the moon moving,
lets people steer time and the view, and teaches one true fact per body.

## Approaches Considered
### Six parts, one writer per piece of state
- Parts: Bodies (sun, planets, moon), Clock (time and speed), Camera (what is visible),
  Scene (everything drawn), Controls (slider, pause, reset), Selection (click to learn).
  Each part has its own spec (SS-2 … SS-7); delivery is spec SS-8 "Web target".
- Journey: on open, start places are picked (Bodies) → time runs (Clock) → each frame the
  Scene draws the body positions through the Camera's space-to-screen mapping. The user
  drags and zooms (Camera), clicks (Selection) and steers (Controls).
- Only the clock changes time; only the camera changes zoom and pan; the scene only reads.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

## Proposed Solution
- **calm** — feels like a planetarium: dark sky, soft glow, nothing jumps or overlaps
  (made concrete in Scene "sky" and "names", Camera "fit").
- **learn** — every body can be clicked to show one true fun fact (Selection "panel").
- **no-errors** — the page runs without errors or warnings.
- **year** — one year is Earth's orbit time: 365 days. (Copied from the Bodies spec;
  nima has no way to reference that table cell, so the two can drift apart.)
- **units** — px are screen pixels and never grow with zoom; space units are sizes in the
  solar system and grow with zoom.
- **quality** — at least 90% of the requirements are proven by a test and 80% of the
  code lines are exercised.
- Gives **viewer**: one page that runs offline, delivered as the Web target spec describes.
  Needs the Web target's test probes for every test below.

## Acceptance Criteria
- [ ] Clicking a planet shows its panel: clickBody(mars) → panel.shown is true. [test: viewer.learn]
- [ ] The page runs with no errors: step(5) → count(errors) = 0. [test: viewer.no-errors]
- [ ] Requirement coverage ≥ 90% and line coverage ≥ 80%. [test: viewer.quality]
      (nima measures neither; this line is only text to it.)
- [ ] Zooming in grows the bodies but not the lines and names: remember strokes and
      body(earth), zoomSteps(5) → strokes unchanged, body(earth).r changed by > 0. [test: viewer.units]
- [ ] The page opens and draws the solar system: body(sun).r > 0 and count(errors) = 0. [test: viewer.viewer]

## Edge Cases
- **Zoom at the extremes** — lines and names could scale with zoom.
  **Desired outcome:** px sizes stay fixed at every zoom (see units).

## Effort
**Level:** low
(FACT records no effort; filled only because the section is required for generated specs.)

## Risks & Tech Debt
> None recorded in the source requirements.

## Decisions
- One owner per piece of state — because it lets agents work on parts in parallel.

## Not Doing
- Elliptical orbits, true scale, sound, textures, other moons, saving state (out of scope).
