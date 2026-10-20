# Solar System viewer: agent context

<!-- `tessl init` writes AGENTS.md and KNOWLEDGE.md (the memory bank). The text below is
     project content carried over from FACT.md that no single spec owns. GUESS: the exact
     template Tessl writes here is not public; only the file names are documented. -->

## Purpose
A calm, good-looking way to watch the planets move and learn one fact about each.
Owner: sebastian.

## Project-wide rules (apply to every spec in specs/solar-system/)
- **Calm**: it feels like a planetarium. Dark sky, soft glow, nothing jumps or overlaps.
  The details are in scene.spec.md (sky, names) and camera.spec.md (fit).
- **Units**: px are screen pixels and never grow with zoom. Space units are sizes in the
  solar system and grow with zoom.
- **Year**: one year is Earth's orbit time, 365 days (see bodies.spec.md). If Earth's
  days change, change every 365 in the specs as well, because Tessl has no cross-spec values.
- **One writer**: only the clock changes time, only the camera changes zoom and pan, and the
  scene only reads. One owner per piece of state lets agents work on parts in parallel.
- **No errors**: the page runs without errors or warnings.
- **Out of scope**: elliptical orbits, true scale, sound, textures, other moons, saving state.

## Quality bar
At least 90% of requirements are proven by a linked `[@test]`, and 80% of lines are
exercised (Chrome coverage, from the Vitest + Puppeteer run). Tessl does not measure either
number. The agent and reviewer check them by hand.

## Stack
- Plain JavaScript, no framework, canvas drawing.
- Tests: Vitest + Puppeteer (headless Chrome), one test file per `[@test]` link, under tests/.
  GUESS: Tessl only shows Vitest in its examples. The browser driver is our choice.
- Delivery: the single file out/index.html, built by `npm run bundle`, which inlines the
  src/ files. Tessl does not do this step (see viewer.spec.md).

## Parts
Each part has one spec and one generated file:
bodies → src/bodies.js · clock → src/clock.js · camera → src/camera.js ·
scene → src/scene.js · controls → src/controls.js · selection → src/selection.js ·
probe → src/probe.js · viewer → src/index.html
