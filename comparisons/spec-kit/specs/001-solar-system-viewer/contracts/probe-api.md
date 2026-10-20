# Contract: Test Probe (`window.__probe`)

The only interface the tests use. Members that are functions are called with the test's arguments.

## Time control

The first action call freezes real time. After that only `step(seconds)` moves the clock, by
exactly seconds × speed (no 0.1 s cap), and not while paused.

## Before each test

`resize(1280, 720)` · `use('reset')` · `slider(40)` · `setPaused(false)`

## Readings

| Member | Shape |
|---|---|
| time, paused, speed, zoom | number / bool |
| pan | {x, y} |
| selected | lowercase name or null |
| bodies | array of {name, x, y, r} |
| body(name) | {x, y, r} in screen px |
| startAngles | {name: radians} |
| labels | array of boxes {x, y, w, h} |
| strokes | {orbitLines, selectionRing, nameText} px, or null when not drawn |
| layout | {gapTop, gapBottom} nearest orbit/body/name to edges; {orbitTop, orbitBottom} outermost orbit to edges |
| hud | the time text |
| panel | {shown, text, fact} |
| errors | array of console errors and warnings |
| comet | {x, y} of head, or null |
| stars | array of {x, y} |

## Actions

`step(seconds)`, `slider(v)`, `setPaused(on)`, `click(x, y)`, `clickBody(name)` (real click),
`clickNear(name, px)` (px further from the sun than the centre), `zoomSteps(n)`, `zoomAt(name, n)`,
`pinch(n)` (two touches around screen centre, n steps apart; negative = together), `drag(dx, dy)`,
`press(key)`, `use(control)` with control ∈ pause, reset, orbits, names, `resize(w, h)`, `showComet()`.

## Contract tests

1. **Given** slider 100, **When** `step(1)`, **Then** time changed by exactly 365 days (±0).
2. **Given** a fresh page, **Then** `body('earth').r > 0`, `layout.gapTop > 0`, `labels.length > 0`, `panel.shown === false`.
3. **Given** a fresh page, **When** `zoomSteps(1)`, **Then** zoom = 1.1.
