# Web
Where the viewer runs, and the hooks the tests use. Kept by the AI: people don't need to read it.

## Rules
- **path** — the page is {path: out/index.html}.

## Approach
- **test-run** — tests run in headless Chrome; coverage comes from Chrome's built-in coverage.

## Contract
- gives **probes** — members of `window.__probe`; a member that is a function is called with
  the test's arguments. The first `do` freezes real time; after that only `step(seconds)` moves
  the clock (by exactly seconds × speed, no cap; not while paused).
  read: time, paused, speed, zoom, pan, selected, bodies, body(name), startAngles, labels,
    strokes, layout, hud, panel, errors, comet, stars, colorOf(name)
  do: step(seconds), slider(v), setPaused(on), click(x, y), clickBody(name), clickNear(name, px),
    zoomSteps(n), zoomAt(name, n), pinch(n), drag(dx, dy), press(key), use(control), resize(w, h),
    showComet()
  before each test: resize(1280, 720) · use(reset) · slider(40) · setPaused(false)
- gives **meanings** — names are lowercase; `body(name)` → `{x, y, r}`; `labels` → boxes;
  `strokes` → `{orbitLines, selectionRing, nameText}`; `layout` → `{gapTop, gapBottom}` between
  the nearest orbit, body or name and the edges, and `{orbitTop, orbitBottom}` between the
  outermost orbit and the edges; `comet` → `{x, y}` of its head or null;
  `stars` → `{x, y}` of every star; `panel` → `{shown, text, fact, picture}` (picture: the asset name shown, or null);
  `colorOf(name)` → the color a body, `sky`, `orbits`, `names`, `ring`, `time`, `comet` (its head),
  `panel` (its background) or `controls` (their text) is really painted in, as uppercase #RRGGBB,
  or #RRGGBBAA when see-through; null when that part isn't drawn; `hud` → the time text;
  `clickNear(name, px)` clicks px further from the sun than the body's center; `pinch(n)` moves
  two touch points around the screen center apart by n zoom steps (negative: together);
  `clickBody` sends a real click; `use` takes pause, reset, orbits or names.

## Tests
- **probes** — `step` moves the clock by exactly seconds × speed, with no cap.
  do: slider(100) · remember time · step(1)
  expect: time changed by {year.days} ± 0
- **path** — the page at out/index.html opens without errors.
  expect: count(errors) = 0
- **meanings** — readings have the promised shapes.
  expect: body(earth).r > 0
  expect: layout.gapTop > 0
  expect: count(labels) > 0
  expect: panel.shown is false
