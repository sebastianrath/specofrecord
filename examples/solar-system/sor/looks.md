# Looks
Why: every body is drawn in its design color, lit from the sun, with its fun fact.

## Rules
- **colors** — Every body is drawn in its color from the design: the sun and moon from
  {design/body}, the planets from {design/planet}, Saturn's ring from {design/saturn}.
- **light** — Planets are brighter on the side facing the sun.
- **ring** — Saturn has a ring, behind AND in front of it. Doesn't count as size tho.
- **fun-facts** — Every body gets one fun fact, sun and moon too. One short sentence ({sentences: 1}), and it has to be TRUE.
  code: out/index.html#FUN_FACTS

## Tests
- **colors** — the sun and the inner planets are drawn in their design colors
  expect: colorOf(sun) = {design/body/sun.value}
  expect: colorOf(earth) = {design/planet/earth.value}
  expect: colorOf(mars) = {design/planet/mars.value}
- **colors-outer** — neptune and the moon are drawn in their design colors
  proves: {colors}
  expect: colorOf(neptune) = {design/planet/neptune.value}
  expect: colorOf(moon) = {design/body/moon.value}
- **ring** — saturn's ring doesn't make it bigger: saturn is drawn smaller than jupiter, bigger than uranus
  expect: body(saturn).r < body(jupiter).r
  expect: body(saturn).r > body(uranus).r
- **fun-facts** — click each body → its fact is one sentence
  each: name in sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune, moon
  do: clickBody(name)
  expect: sentences(panel.fact) = {fun-facts.sentences}
- **light** — by eye: glow, light side, ring (first build was flat circles)
  by eye: the sun glows, planets are lit from the sun's side, Saturn's ring crosses it
