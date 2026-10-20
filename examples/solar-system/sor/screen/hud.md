# HUD
Why: The clock top left and the controls bottom left.

## Rules
- **time** — Top left says "Year 0, day 0" and counts up.
  code: out/index.html#hudText
- **controls** — Bottom left: speed slider, Pause button ("Pause" / "Play"), checkboxes "Orbits" and "Names" (both on), Reset.
- **space** — Space = pause too. Even right after you clicked a button!
- **reset** — Reset: time to day 0, view back to start, nothing selected. Keeps speed, pause and checkboxes.
  code: out/index.html#resetButton

## Tests
- **controls** — at the start orbits and names are on and it's running
  expect: strokes.orbitLines = {scene/orbits.width}
  expect: strokes.nameText = {scene/names.size}
  expect: paused is false
- **time** — one year at full speed → says "Year 1"
  do: slider(100) · step(1)
  expect: hud contains "Year 1"
- **space** — click Pause, press space → running again (bug #3)
  do: use(pause) · press(Space)
  expect: paused is false
  bug: #3
- **reset** — zoom, drag, change speed, reset → view is back, speed the same
  do: zoomSteps(4) · drag(50, 50) · slider(70) · remember speed · use(reset)
  expect: zoom = {view/zoom.start}
  expect: speed unchanged
