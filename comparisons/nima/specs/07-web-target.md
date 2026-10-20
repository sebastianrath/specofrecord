<!--
nima spec (hand-created, type "spec"). Ticket SS-8. codebaseFiles: ["out/index.html"].
FACT's "markers" approach (@fact comments in code) has no nima equivalent and is dropped
on purpose: nima links code by file path, ticket key and its own index, not by markers.
-->
# Web target

## Customer Voice
> No signals (greenfield). Owner: "Where the viewer runs, and how its code is delivered,
> traced and tested."

## Problem
The viewer must run from a single file with no network, and expose stable hooks so tests
can drive it deterministically.

## Approaches Considered
### Single file, headless-Chrome tests
- Implementer's notes and assumptions go in a comment at the top of the file.
- Tests run in headless Chrome; coverage comes from Chrome's built-in coverage.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

## Proposed Solution
- **delivery** — one HTML file at out/index.html with everything inside; it works opened
  straight from disk, with no network.
- **pixels** — 1 px is one CSS pixel; drawing stays sharp on dense screens.
- **input** — mouse and touch; one wheel notch is one zoom step (1.1x, see Camera).
- **probes** — members of `window.__probe`; a member that is a function is called with the
  test's arguments. The first action freezes real time; after that only `step(seconds)` moves
  the clock (by exactly seconds × speed, no cap; not while paused).
  - read: time, paused, speed, zoom, pan, selected, bodies, body(name), startAngles, labels,
    strokes, layout, hud, panel, errors, comet, stars
  - do: step(seconds), slider(v), setPaused(on), click(x, y), clickBody(name),
    clickNear(name, px), zoomSteps(n), zoomAt(name, n), pinch(n), drag(dx, dy), press(key),
    use(control), resize(w, h), showComet()
  - before each test: resize(1280, 720), use(reset), slider(40), setPaused(false)
- **meanings** — names are lowercase; `body(name)` → `{x, y, r}`; `labels` → boxes;
  `strokes` → `{orbitLines, selectionRing, nameText}`; `layout` → `{gapTop, gapBottom}`
  between the nearest orbit, body or name and the edges, and `{orbitTop, orbitBottom}` between
  the outermost orbit and the edges; `comet` → `{x, y}` of its head or null; `stars` → `{x, y}`
  of every star; `panel` → `{shown, text, fact}`; `hud` → the time text; `clickNear(name, px)`
  clicks px further from the sun than the body's center; `pinch(n)` moves two touch points
  around the screen center apart by n zoom steps (negative: together); `clickBody` sends a real
  click; `use` takes pause, reset, orbits or names.

## Acceptance Criteria
- [ ] (manual) The page opens from disk with no network requests — checked by opening the file
      with networking off. [test: web.delivery, manual]
- [ ] One wheel notch is one zoom step: zoomSteps(1) → zoom = 1.1. [test: web.input]
- [ ] `step` moves the clock by exactly seconds × speed, with no cap: slider(100), step(1) →
      time changed by 365 ± 0. [test: web.probes]
- [ ] Readings have the promised shapes: body(earth).r > 0, layout.gapTop > 0,
      count(labels) > 0, panel.shown is false. [test: web.meanings]
- [ ] (manual) Drawing stays sharp on a screen with more than one device pixel per CSS pixel.
      [test: web.pixels, manual]

## Edge Cases
- **Opened from disk** — any CDN or fetch breaks it.
  **Desired outcome:** zero network requests.

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded.
