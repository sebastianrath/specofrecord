# Solar System
Why: Watch the planets go round, click one, get a fun fact. Thats it.
Owner: sebastian. Run: open out/index.html
Design: design/tokens.json, exported from https://www.figma.com/design/dWBbuElrInc7hOc6yaxdxP

## Rules
- **from-design** — Colors and pictures come from the Figma design (see Design above), never made up.
  Change a color in Figma, export it to design/, then rebuild. {design}
  Refined by {looks/colors}, {screen/ui-colors}, {screen/scene/sky}, {screen/select/panel}.
- **calm** — Calm, like a planetarium. Dark sky, soft glow. Nothing jumps, nothing overlaps.
  Refined by {screen/scene/sky}, {screen/scene/names}, {screen/view/fit}.
- **no-errors** — No errors in the console. None.
- **delivery** — One file: out/index.html, everything inside. Opens from disk, no internet.
- **devices** — Sharp on retina too (1px = 1 CSS pixel). Mouse and touch both work.
- **year** — A year = Earth going round the sun once = {days: 365 days}.
- **quality** — {rules: 90%} of the rules need a passing test. {lines: 80%} of the code has to run in the tests.

## Approach
- **parts** — {clock} runs time and speed, {bodies} says what is out there, {looks} how each body is drawn, {screen} what you see and do.
- **out-of-scope** — NOT doing: oval orbits, real scale, sound, textures, other moons, saving stuff.
- Every frame: clock ticks (real seconds × speed) → positions → camera → draw.
- Only the clock changes time, only the camera changes zoom. Drawing just reads.
- Tests talk to the page through `window.__probe`. Run in headless Chrome, coverage from Chrome too.
- Markers: `<!-- @clause -->` in HTML, `/* @clause */` in CSS, `// @clause` in JS. Builder's notes in a comment at the top.

## Tests
- **no-errors** — page opens → the sun is there, no errors after a few seconds
  do: step(5)
  expect: body(sun).r > 0
  expect: count(errors) = 0
- **year** — step(1) at full speed → exactly one year, 365 days
  do: slider(100) · remember time · step(1)
  expect: time changed by {year.days} ± 0
- **delivery** — wifi off, open from disk → works, no network requests (by hand)
  by hand: open the file with networking off
- **devices** — sharp on a retina screen (by hand)
  by hand: needs a screen with more than one device pixel per CSS pixel
- **quality** — coverage is at least 90% / 80%
  measure: clause-coverage ≥ {quality.rules}
  measure: line-coverage ≥ {quality.lines}
