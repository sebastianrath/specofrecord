# Test probe

The hooks that every test uses, exposed as `window.__probe`. A member that is a function is
called with the test's arguments. This is FACT's targets/web "probes" and "meanings"
contract, made into its own generated file.

## Targets

[@generate](../../src/probe.js)

## Capabilities

- Freezing: the first action freezes real time. After that only `step(seconds)` moves the
  clock, by exactly seconds × speed, with no cap, and not while paused. After `slider(100)`
  and `step(1)`, `time` moved by exactly 365 (± 0).
  [@test](../../tests/probe/step.test.js)
- Before each test (the shared Vitest `beforeEach`, tests/setup.js): `resize(1280, 720)`,
  `use("reset")`, `slider(40)`, `setPaused(false)`.
- Meanings: names are lowercase.
  - `body(name)` gives `{x, y, r}`.
  - `labels` is a list of boxes.
  - `strokes` gives `{orbitLines, selectionRing, nameText}`.
  - `layout` gives `{gapTop, gapBottom}`: the gaps between the nearest orbit, body or name
    and the edges. It also gives `{orbitTop, orbitBottom}`: the gaps between the outermost
    orbit and the edges.
  - `comet` is `{x, y}` of the comet's head, or null.
  - `stars` is `{x, y}` for every star.
  - `panel` is `{shown, text, fact}`.
  - `hud` is the time text.
  - `clickNear(name, px)` clicks px further from the sun than the body's center.
  - `pinch(n)` moves two touch points around the screen center apart by n zoom steps
    (negative n moves them together).
  - `clickBody` sends a real click.
  - `use` takes pause, reset, orbits or names.
- Readings have the promised shapes: `body("earth").r > 0`, `layout.gapTop > 0`, at least
  one label, and `panel.shown` is false. [@test](../../tests/probe/meanings.test.js)

## API

```js { .api }
window.__probe = {
  // read
  time, paused, speed, zoom, pan, selected, bodies, body(name), startAngles, labels,
  strokes, layout, hud, panel, errors, comet, stars,
  // do
  step(seconds), slider(v), setPaused(on), click(x, y), clickBody(name), clickNear(name, px),
  zoomSteps(n), zoomAt(name, n), pinch(n), drag(dx, dy), press(key), use(control),
  resize(w, h), showComet(),
};
```

## Dependencies

- [@use](./clock.spec.md)
- [@use](./camera.spec.md)
- [@use](./scene.spec.md)
- [@use](./selection.spec.md)
- [@use](./controls.spec.md)
- [@use](./bodies.spec.md)
