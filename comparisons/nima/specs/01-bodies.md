<!--
nima spec (hand-created, type "spec"). Ticket SS-2. codebaseFiles: ["out/index.html"].
See 00-viewer.md for which parts of this shape are documented and which are our convention.
-->
# Bodies

## Customer Voice
> No signals (greenfield). Owner: "The fixed facts about the sun, the planets and the moon,
> and where they are."

## Problem
The viewer needs one agreed table of every body's size, orbit, orbit time, color and fun fact,
and a rule for where each body is at any time.

## Approaches Considered
### Clockwise circles from a random start
- angle = start place + full turn × (time ÷ own orbit time). The moon circles Earth's
  current position.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

## Proposed Solution
- **sun** — size 28, color #FFC93C.
- **planets** — sizes and orbits in space units, orbit times in days. Saturn has a ring that
  is not part of its size.

  | Planet | Size | Orbit | Days | Color |
  |---|---|---|---|---|
  | Mercury | 4 | 60 | 88 | #B1ADA7 |
  | Venus | 7 | 90 | 225 | #E8C98A |
  | Earth | 7 | 125 | 365 | #4F8FE6 |
  | Mars | 5 | 160 | 687 | #D1623A |
  | Jupiter | 16 | 230 | 4333 | #D9A66C |
  | Saturn | 13 | 300 | 10759 | #E3CF8E |
  | Uranus | 10 | 365 | 30687 | #8FD3D9 |
  | Neptune | 10 | 420 | 60190 | #4468D6 |
- **moon** — circles Earth: size 2, orbit 14, 27 days, color #CCCCCC.
- **fun-facts** — every body, the sun too, has one true fun fact, 1 sentence long.
- **start-places** — each planet and the moon starts at a random place, picked once per run.
- Gives **table** (every body's name, size, orbit, orbit time, color, fun fact) and
  **positions** (where each body is at any time). Needs the Clock's time passed.

## Acceptance Criteria
- [ ] The sun, 8 planets and the moon exist: count(bodies) = 10. [test: bodies.planets]
- [ ] Start places never change while the app runs: remember startAngles, step(5) →
      startAngles unchanged. [test: bodies.start-places]
- [ ] After one year Earth is back where it started: slider(100), remember body(earth),
      step(1) → body(earth).x changed by 0 ± 1. [test: bodies.positions]
- [ ] The sun is drawn bigger than any planet: body(sun).r > body(jupiter).r. [test: bodies.sun]
- [ ] After one moon month the moon is back on the same side of Earth: slider(100),
      remember offset(moon, earth), step(0.073972602739726) → offset x and y changed by
      0 ± 0.5. [test: bodies.moon]
- [ ] Clicking any body shows its fun fact in 1 sentence, for each of sun, mercury, venus,
      earth, mars, jupiter, saturn, uranus, neptune, moon. [test: bodies.fun-facts]
- [ ] Every body in the table can be found and clicked by its name: for each of the 10 names,
      clickBody(name) → selected is name. [test: bodies.table]

## Edge Cases
- **Saturn's ring** — the ring could be counted as size and break click reach or fit.
  **Desired outcome:** the ring is not part of Saturn's size.
- **Moon month** — 27 days at top speed is 27 ÷ 365 s (the 0.0739… above).
  **Desired outcome:** the moon returns to the same side of Earth.

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded. Fun facts must be true; nothing checks that automatically.

## Not Doing
- Elliptical orbits, true scale, other moons (see Solar System viewer).
