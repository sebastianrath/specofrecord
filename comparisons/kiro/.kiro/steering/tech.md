---
inclusion: always
---

# Tech

- Target: one HTML file with all CSS and JavaScript inline. It must work when opened straight
  from disk, with no network requests. No build step, no CDN, no frameworks.
- Drawing: one 2D canvas. 1 px is one CSS pixel; the canvas is scaled by `devicePixelRatio`
  so drawing stays sharp on dense screens.
- Input: mouse and touch (pointer events); one wheel notch is one zoom step.
- Tests: run in headless Chrome against `out/index.html`, through the test hooks on
  `window.__probe` (see design.md, "Test hooks"). Line coverage comes from Chrome's built-in
  coverage. Guess: Puppeteer driven by Node's built-in test runner (`node --test`).
- Commands:
  - `npm test` runs every automated test.
  - `npm run coverage` runs them with Chrome coverage and prints line coverage.
