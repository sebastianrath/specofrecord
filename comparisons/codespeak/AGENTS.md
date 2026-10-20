# Solar System Viewer: notes for agents

## Setup
- Node.js 20 or newer. `npm install` installs `puppeteer` (dev dependency, used only by tests).

## Tests
- Run all tests: `node --test tests/`
- Tests open `out/index.html` from disk (`file://`) in headless Chrome and talk to the page only
  through `window.__probe`, as the spec's "Test hooks" section defines it. Never read internal
  variables of the page.
- Each test starts with `resize(1280, 720)`, `use(reset)`, `slider(40)`, `setPaused(false)`.
- Line coverage comes from Puppeteer's `page.coverage` (JS coverage of the inline script),
  converted to LCOV by `tests/coverage-to-lcov.mjs`.

## Conventions
- Never weaken a test to make it pass; fix the page instead.
- Tolerances in the spec ("± 0.5") are part of the requirement; do not widen them.
