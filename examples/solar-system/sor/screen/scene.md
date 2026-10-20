# Scene
Why: The sky, the orbit lines, the names and the comet.

## Rules
- **sky** — Sky is blue-black, the design's sky color {design/sky/background}, with {stars: 300} stars that twinkle a bit. Stars DON'T move when you zoom or drag.
  code: out/index.html#drawSky
- **orbits** — Orbits: thin faint {width: 1px} circles, planets and moon. Only when "Orbits" is on.
- **names** — Names: {size: 12px}, under each body, only when "Names" is on. Two overlap? The one closer to the sun stays. Moon's name only once it's {moon: 30px} away from Earth.
  code: out/index.html#placeNames
- **comet** — A small comet with a faint tail flies across every {every: 20s}. It lives in space, so it moves and zooms with the planets.
  code: out/index.html#launchComet

## Tests
- **sky** — 300 stars, zoom or drag doesnt move them (first build had zero stars lol)
  do: remember stars · zoomSteps(5) · drag(30, 0)
  expect: count(stars) = {sky.stars}
  expect: colorOf(sky) = {design/sky/background.value}
  expect: stars unchanged
- **orbits** — orbits off → no lines, on again → back, 1px. names off → no names
  do: use(orbits)
  expect: strokes.orbitLines is null
  do: use(orbits)
  expect: strokes.orbitLines = {orbits.width}
  do: use(names) · step(0)
  expect: count(labels) = 0
- **names** — full speed 20s, check every second → names never overlap
  each: 20 rounds
  do: slider(100) · step(1)
  expect: overlaps(labels) = 0
- **comet** — show the comet, drag the view → the comet moves along
  do: showComet() · remember comet · drag(50, 0)
  expect: comet.x changed by 50 ± 1
