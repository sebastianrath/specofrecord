# View
Why: Where the camera looks and how big things are.

## Rules
- **fit** — On load everything fits between the top and bottom bar ({bar: 56px} each), with {room: 28px} room for the outer planet and its name. Never more than {most: 1px} per space unit.
  code: out/index.html#baseScale
- **zoom** — Starts at zoom {start: 1x}, sun in the middle. Zoom stays between {min: 0.3x} and {max: 6x}.
- **zoom-step** — Wheel notch or pinch step = zoom {factor: 1.1x}. Whatever's under the mouse stays under it.
  code: out/index.html#zoomAt
- **drag** — Drag moves the view. Moved less than {click: 4px}? That's a click, not a drag.
- **units** — Planets and orbits get bigger when you zoom. Lines and text stay the same size.

## Tests
- **fit** — at 1280x720, 800x600, 640x480 → nothing touches the bars
  each: size in 1280x720, 800x600, 640x480
  expect: layout.gapTop ≥ {fit.bar}
  expect: layout.gapBottom ≥ {fit.bar}
- **fit-orbit** — at 1280x720, 800x600, 640x480 → outer orbit exactly 28px away
  proves: {fit}
  each: size in 1280x720, 800x600, 640x480
  expect: layout.orbitTop = {fit.bar} + {fit.room} ± 0.5
  expect: layout.orbitBottom = {fit.bar} + {fit.room} ± 0.5
- **zoom** — zoom in forever → stops at 6x. out forever → 0.3x. 1 wheel notch → 1.1x
  do: zoomSteps(200)
  expect: zoom = {zoom.max}
  do: zoomSteps(-400)
  expect: zoom = {zoom.min}
- **zoom-step** — zoom over earth → earth stays under the mouse
  do: remember body(earth) · zoomAt(earth, 1)
  expect: zoom = {zoom-step.factor}
  expect: body(earth).x changed by 0 ± 1
- **zoom-pinch** — a pinch step zooms by the same factor
  proves: {zoom-step}
  do: pinch(1)
  expect: zoom = {zoom-step.factor}
- **drag** — drag 50px → view and mars and the comet move 50px
  do: showComet() · remember pan · remember body(mars) · remember comet · drag(50, 0)
  expect: pan.x changed by 50 ± 0.5
  expect: body(mars).x changed by 50 ± 0.5
  expect: comet.x changed by 50 ± 1
- **drag-click** — drag 3px → nothing moves
  proves: {drag}
  do: remember pan · drag(3, 0)
  expect: pan unchanged
- **units** — select jupiter, zoom all the way out and in → ring, lines and names stay the same size
  do: clickBody(jupiter) · zoomAt(jupiter, -400) · remember strokes · remember body(earth) · zoomAt(jupiter, 400)
  expect: strokes unchanged
  expect: body(earth).r changed by > 0
  expect: strokes.selectionRing = {select/ring.width}
