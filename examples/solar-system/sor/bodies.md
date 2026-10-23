# Bodies
Why: The sun, 8 planets and the moon. Sizes and orbits are space units, not pixels.

## Rules
- **sun** — Sun: size {size: 28}. Sits in the middle, doesn't move. It glows.
- **planets** — Planets (days = one trip round the sun):

| Planet  | Size | Orbit | Days  |
|---------|------|-------|-------|
| Mercury | 4    | 60    | 88    |
| Venus   | 12    | 90    | 225   |
| Earth   | 7    | 125   | 365   |
| Mars    | 5    | 160   | 687   |
| Jupiter | 16   | 230   | 4333  |
| Saturn  | 13   | 300   | 10759 |
| Uranus  | 10   | 365   | 30687 |
| Neptune | 10   | 420   | 60190 |
- **moon** — Moon: size {size: 2}, orbit {orbit: 14}, {days: 27 days}. Circles wherever Earth is right now.
- **motion** — Everything moves clockwise, in circles.
  code: out/index.html#positions
- **start-places** — Random start spot for each planet and the moon. Pick once on load, then keep it!
  code: out/index.html#startAngles

## Approach
- angle = start spot + full turn × (time / days)

## Tests
- **planets** — 10 bodies: sun, 8 planets, moon. The sun is bigger than jupiter
  expect: count(bodies) = 10
  expect: body(sun).r > body(jupiter).r
- **sun** — the sun stays put while time runs
  do: remember body(sun) · slider(100) · step(3)
  expect: body(sun) unchanged
- **moon** — after 27 days the moon is back on the same side of earth
  do: slider(100) · remember offset(body(moon), body(earth)) · step(0.073972602739726)
  expect: offset(body(moon), body(earth)).x changed by 0 ± 0.5
  expect: offset(body(moon), body(earth)).y changed by 0 ± 0.5
- **motion** — after exactly 1 year earth is back where it started
  do: slider(100) · remember body(earth) · step(1)
  expect: body(earth).x changed by 0 ± 1
- **start-places** — start spots never change while it runs
  do: remember startAngles · step(5)
  expect: startAngles unchanged
