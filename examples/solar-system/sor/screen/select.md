# Select
Why: Click a body, see its ring and its panel.

## Rules
- **click** — Click counts within the body's size on screen, at least {min: 10px} tho (tiny planets!). Two in reach? Closest center wins.
  code: out/index.html#selectAt
- **miss** — Click on nothing → nothing selected, panel hides.
- **ring** — Selected body gets a white ring, {width: 2px} wide, {gap: 4px} away from the body.
- **panel** — Info panel, top right: the body's picture from the design ({design/assets}), name, fun fact, orbit time like "88 days" or "11.9 years" (once it's a year or more). Sun has no orbit time.
  code: out/index.html#orbitTime

## Tests
- **miss** — click venus → venus selected. then empty space → nothing selected
  do: clickBody(venus)
  expect: selected is "venus"
  do: click(3, 300)
  expect: selected is null
- **click** — zoomed all the way out → mercury, earth and moon still clickable (1280x720 and 800x600, 10x each)
  zoomed out → 9px outside neptune counts, 12px doesn't
  each: size in 1280x720, 800x600
  each: 10 rounds
  do: zoomSteps(-400) · step(0.37)
  do: clickBody(mercury)
  expect: selected is "mercury"
  do: clickBody(earth)
  expect: selected is "earth"
  do: clickBody(moon)
  expect: selected is "moon"
  do: clickNear(neptune, 9)
  expect: selected is "neptune"
  do: clickNear(neptune, 12)
  expect: selected is null
- **panel** — click jupiter → panel says "Jupiter" and its orbit time in years
  do: clickBody(jupiter)
  expect: panel.text contains "Jupiter"
  expect: panel.picture is "jupiter"
  expect: panel.text contains "years"
