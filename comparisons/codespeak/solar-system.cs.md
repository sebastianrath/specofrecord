// Comparison file: the FACT example examples/solar-system written as a CodeSpeak spec.
// Lines starting with // are CodeSpeak comments (documented syntax) and are not part of the spec.
// "GUESS:" marks a choice the CodeSpeak docs do not show.
//
// GUESS: one spec, not one per FACT part. CodeSpeak modules (imports) map one spec to its own
// managed files; FACT delivers one HTML file with everything inside, so splitting into
// bodies.cs.md, clock.cs.md, ... would need one generated file per module plus a bundling step
// that the FACT example does not have. The FACT parts survive as ## sections instead.

# Solar System Viewer

A calm, good-looking single web page for watching the planets move and learning one true fun
fact about each body. It should feel like a planetarium: dark sky, soft glow, nothing jumps or
overlaps. The page runs without errors or warnings in the browser console.

## Technology

- Pure HTML + CSS + JavaScript, drawn on a `<canvas>`. No frameworks, no build step.
- **IMPORTANT:** deliver exactly one file, `out/index.html`, with all CSS and JavaScript inline.
  It must work when opened straight from disk (`file://`) with no network requests at all
  (no CDN, no web fonts).
- 1 px means one CSS pixel. Drawing must stay sharp on screens with more than one device pixel
  per CSS pixel.
- Input: mouse and touch. One mouse-wheel notch is exactly one zoom step.
- Put your own notes and assumptions in one comment block at the top of `out/index.html`.

## Units

- "px" are screen pixels; they never grow with zoom (line widths, font sizes, gaps).
- "space units" are sizes and distances in the solar system; they grow with zoom.
- One "year" is Earth's orbit time, 365 days.

## Out of scope

Do not build: elliptical orbits, true scale, sound, textures, moons other than Earth's moon,
saving state between visits.

## Architecture

- Parts: bodies (sun, planets, moon and where they are), clock (time and speed), camera (what
  is visible), scene (everything drawn), controls (slider, pause, reset), selection (click to
  learn).
- Each frame: the clock advances time, then the scene draws every body's position through the
  camera's space-to-screen transform.
- **IMPORTANT:** one writer per piece of state. Only the clock changes time, paused and speed.
  Only the camera changes zoom and pan. The scene only reads.

## Bodies

- Sun: size 28 space units, color `#FFC93C`.
- Planets, with size and orbit radius in space units and orbit time in days:

  | Planet  | Size | Orbit | Days  | Color   |
  |---------|------|-------|-------|---------|
  | Mercury | 4    | 60    | 88    | #B1ADA7 |
  | Venus   | 7    | 90    | 225   | #E8C98A |
  | Earth   | 7    | 125   | 365   | #4F8FE6 |
  | Mars    | 5    | 160   | 687   | #D1623A |
  | Jupiter | 16   | 230   | 4333  | #D9A66C |
  | Saturn  | 13   | 300   | 10759 | #E3CF8E |
  | Uranus  | 10   | 365   | 30687 | #8FD3D9 |
  | Neptune | 10   | 420   | 60190 | #4468D6 |

  Saturn has a ring that is not part of its size.
- Moon: circles Earth's current position; size 2, orbit 14, orbit time 27 days, color `#CCCCCC`.
- Every body, the sun too, has one true fun fact that is exactly one sentence long.
- Each planet and the moon starts at a random angle, picked once per page load and never
  changed while the page runs.
- Motion: clockwise circles. angle = start angle + full turn × (time in days ÷ own orbit days).

## Clock

- When the page opens, time is 0 days and running.
- Speed slider from 0 to 100, starting at 40. Speed = (slider ÷ 100)² years per second.
- While paused, time does not move.
- Each frame adds (real seconds since the last frame × speed). After a long gap, such as a
  hidden tab, count at most 0.1 s, so the planets never jump when the tab comes back.

## Camera

- Base scale: at the start, the outermost orbit plus 28 px of room (for its planet and name)
  fits between the top and bottom bars, at most 1 px per space unit. Recompute the base scale
  when the window changes size, in width and height. Zoom multiplies the base scale.
- Bars: the top 56 px and the bottom 56 px of the screen stay free at the start.
- Start: zoom 1x, sun in the middle of the screen.
- One wheel notch or one pinch step zooms by a factor of 1.1; the point under the pointer
  stays where it is.
- Zoom stays between 0.3x and 6x.
- Dragging moves the view. A press that moves less than 4 px is a click, not a drag.

## Scene

- Sky: blue-black `#05060F` with 300 softly twinkling stars that ignore zoom and pan.
- Orbits: faint 1 px circles for the planets and the moon, while the "Orbits" switch is on.
- Bodies: a glowing sun; planets brighter on the side facing the sun; Saturn's ring passes
  behind and in front of the planet. Glow, shading, ring tilt and fonts are your choice.
- Selected body: a white ring, 2 px wide, 4 px outside the body.
- Names: 12 px names under the bodies while the "Names" switch is on. When two names would
  overlap, the one closer to the sun stays. The moon's name shows only once the moon is at
  least 30 px from Earth on screen.
- Time display, top left: "Year 0, day 0" at the start, counting years and days.
- Comet: a small comet with a faint tail crosses the solar system every 20 s. Its path is in
  space units, so it moves and zooms with the planets.
- Draw order: sky, stars, comet, orbits, sun, planets, moon, selected ring, names, time.

## Controls

One small bar at the left of the bottom bar with:
- the speed slider described in Clock;
- a button that reads "Pause" or "Play". The Space key does the same, even right after any
  control was clicked (controls must not keep the keyboard focus for Space);
- checkboxes "Orbits" and "Names", both on at the start;
- a Reset button: time back to 0, view back to the camera start, nothing selected. Speed,
  play/pause and the checkboxes stay as they are.

## Selection

- A click selects a body when it lands within the body's on-screen size, but at least 10 px.
- If several bodies are in reach, the one whose center is nearest the click wins. Do not use a
  fixed priority order: at the start zoom the moon's click area covers Earth, and a fixed order
  made Earth unclickable.
- Panel, top right: the body's name, its fun fact and its orbit time ("88 days" below one year,
  "11.9 years" from one year up). The sun shows no orbit time.
- A click on empty space selects nothing and hides the panel.

## Test hooks

The page exposes `window.__probe` for automated tests. Names of bodies are lowercase.

- Readings: `time` (days), `paused`, `speed` (years per second), `zoom`, `pan` (`{x, y}`),
  `selected` (name or null), `bodies` (list), `body(name)` → `{x, y, r}` on screen,
  `startAngles`, `labels` (list of `{x, y, w, h}` name boxes), `strokes` →
  `{orbitLines, selectionRing, nameText}` in px (null when not drawn), `layout` →
  `{gapTop, gapBottom}` between the nearest drawn orbit, body or name and the screen edges, and
  `{orbitTop, orbitBottom}` between the outermost orbit and the edges, `hud` (the time text),
  `panel` → `{shown, text, fact}`, `errors` (console errors and warnings so far), `comet` →
  `{x, y}` of its head or null, `stars` → list of `{x, y}`.
- Actions: `step(seconds)`, `slider(v)`, `setPaused(on)`, `click(x, y)`, `clickBody(name)`
  (a real click at the body), `clickNear(name, px)` (a click px further from the sun than the
  body's center), `zoomSteps(n)`, `zoomAt(name, n)`, `pinch(n)` (two touch points around the
  screen center move apart by n zoom steps, together when negative), `drag(dx, dy)`,
  `press(key)`, `use(control)` with control one of pause, reset, orbits, names,
  `resize(w, h)`, `showComet()`.
- **IMPORTANT:** the first action freezes real time. After that only `step(seconds)` moves the
  clock, by exactly seconds × speed, with no 0.1 s cap, and not while paused.

## Acceptance tests

// GUESS: the CodeSpeak docs do not document a test section format. The stylistic guidelines
// recommend example scenarios and XML tags, so tests are written as <test> blocks that the
// build is asked to turn into real tests under tests/. Generated tests use the hooks above.

Write automated tests in `tests/` that open `out/index.html` from disk in headless Chrome and
drive it only through `window.__probe`. Before each test: `resize(1280, 720)`, `use(reset)`,
`slider(40)`, `setPaused(false)`. "≈ x ± d" means within d of x.

<test name="page">
- Clicking Mars shows the panel.
- After `step(5)` there are 0 errors.
- On open, the sun's on-screen radius is > 0 and there are 0 errors.
- Zooming 5 steps in grows Earth's radius but leaves `strokes` unchanged.
</test>

<test name="bodies">
- There are exactly 10 bodies.
- `startAngles` are unchanged after `step(5)`.
- Slider 100, then `step(1)`: Earth's x is back where it was, ± 1.
- The sun's radius is bigger than Jupiter's.
- Slider 100, then `step(0.073972602739726)` (one moon month): the moon's offset from Earth is
  unchanged in x and y, ± 0.5.
- For each of sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune, moon:
  `clickBody(name)` selects that name, and `panel.fact` is exactly one sentence.
</test>

<test name="clock">
- Slider 0, `step(1)`: time unchanged.
- Slider 50, `step(4)`: time grows by 365 days ± 1%.
- Slider 100, `step(1)`: time grows by 365 days ± 1%.
- Slider 100, `step(1)`: time grows by exactly 365 days (± 0), as the test hooks promise.
- Press Space, `step(2)`: time unchanged.
- After reset: time is 0 and paused is false.
- Slider 100, `step(1)` after reset: time is 365.
// Not automatable (FACT: manual): the 0.1 s cap after a long gap needs a real clock.
</test>

<test name="camera">
- At sizes 1280x720, 800x600 and 640x480: `layout.gapTop` ≥ 56 and `layout.gapBottom` ≥ 56;
  `layout.orbitTop` and `layout.orbitBottom` are each 84 ± 0.5.
- `zoomAt(earth, 1)`: zoom is 1.1 and Earth's x is unchanged ± 1. Then `zoomAt(earth, -1)`,
  `pinch(1)`: zoom is 1.1.
- `zoomSteps(1)`: zoom is 1.1.
- `zoomSteps(200)`: zoom is 6. Then `zoomSteps(-400)`: zoom is 0.3.
- `drag(50, 0)`: pan.x grows by 50 ± 0.5. Then `drag(3, 0)`: pan unchanged.
- `drag(30, 0)`: Mars's x grows by 30 ± 0.5.
</test>

<test name="scene">
- `zoomSteps(5)`, `drag(30, 0)`: there are 300 stars and their positions are unchanged.
- 20 rounds of slider 100, `step(1)`: no two `labels` overlap.
- Click Jupiter, `zoomAt(jupiter, -400)`, remember strokes, `zoomAt(jupiter, 400)`: strokes
  unchanged.
- Slider 100, `step(1)`: `hud` contains "Year 1".
- `showComet()`, `drag(50, 0)`: comet.x grows by 50 ± 1.
// Not automatable (FACT: manual): glow, sun-side shading and Saturn's ring are judged by eye.
// FACT records "bug: the first build drew no stars / flat circles"; CodeSpeak has no place
// for that history except git and change requests.
</test>

<test name="controls">
- `use(orbits)`, `use(names)`, `step(0)`: `strokes.orbitLines` is null and there are 0 labels.
- `use(pause)` then `press(Space)`: paused is false. (Regression test for issue #3.)
- `zoomSteps(4)`, `drag(50, 50)`, slider 70, `use(reset)`: zoom is 1 and speed is unchanged.
- Slider 50: speed is 0.25 ± 0.001.
- `use(orbits)`: `strokes.orbitLines` is null. `use(orbits)` again: it is 1.
</test>

<test name="selection">
- `clickBody(jupiter)`: panel text contains "Jupiter" and "years".
- At sizes 1280x720 and 800x600, 10 rounds each of `zoomSteps(-400)`, `step(0.37)`:
  clicking mercury, earth and moon selects each of them.
- `clickBody(jupiter)`, `click(3, 300)`: selected is null.
- `zoomSteps(-400)`, `clickNear(neptune, 9)`: selected is neptune. `clickNear(neptune, 12)`:
  selected is null.
- `clickBody(venus)`: selected is venus.
- `panel.shown` is false after reset; `count(labels)` > 0; `layout.gapTop` > 0.
</test>

// Not automatable (FACT: manual): opening the file with networking off; sharpness on a
// screen with device pixel ratio > 1.
// FACT "quality": ≥ 90% of facts proven by a test has no CodeSpeak equivalent; ≥ 80% line
// coverage maps to `codespeak coverage --target 80` (see NOTES.md for the language caveat).
