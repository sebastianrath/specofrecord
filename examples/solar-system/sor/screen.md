# Screen
Why: What you see and what you can do with it.

## Rules
- **ui-colors** — Orbits, names, the selection ring, the panel, the time, the controls and the comet
  use the design's colors: {design/ui}, {design/comet}.

## Approach
- **parts** — {view} moves the camera, {scene} draws the sky and the lines, {select} picks a body, {hud} holds the controls and the clock.
- **draw-order** — Draw order: sky, stars, comet, orbits, sun, planets, moon, ring, names, time.
- Closest center, NOT a fixed order! At start zoom the moon's click area covers Earth, so a fixed order made Earth unclickable (real bug).
- Glow, shading, ring tilt, fonts: builder's choice. Base scale is recomputed on resize, zoom multiplies on top.

## Tests
- **ui-colors** — orbits, names and time use the design colors
  expect: colorOf(orbits) = {design/ui/orbit.value}
  expect: colorOf(names) = {design/ui/label.value}
  expect: colorOf(time) = {design/ui/time.value}
- **ui-colors-select** — the selection ring and the panel use the design colors
  proves: {ui-colors}
  do: clickBody(jupiter)
  expect: colorOf(ring) = {design/ui/selection.value}
  expect: colorOf(panel) = {design/ui/panel-bg.value}
- **ui-colors-comet** — the controls and the comet use the design colors
  proves: {ui-colors}
  do: showComet()
  expect: colorOf(controls) = {design/ui/controls-text.value}
  expect: colorOf(comet) = {design/comet/head.value}
