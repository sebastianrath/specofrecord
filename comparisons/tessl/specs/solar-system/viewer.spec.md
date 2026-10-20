# Solar System viewer

<!-- Legacy Tessl Framework syntax (CLI <= 0.28), from the launch post and Böckeler's article:
     link-style tags [@generate](path), [@test](path), [@use](spec), an `{ .api }` code block,
     and one spec -> one generated file. GUESS: the section headings (Targets / Capabilities /
     API / Dependencies) follow the docs' wording. No complete official example is public. -->

One page that runs offline. Users watch the planets move and click any body to learn one
fun fact about it. Project-wide rules (calm, units, year, one writer, out of scope) are in
AGENTS.md.

## Targets

[@generate](../../src/index.html)

<!-- Tessl generates one file per spec, but the delivery rule asks for ONE html file with
     everything inside. So src/index.html loads the other generated files with classic
     <script src> tags, which work from file://. `npm run bundle` (not Tessl) then inlines
     them into out/index.html. GUESS: we found no documented Tessl way to generate several
     specs into one file. -->

## Capabilities

### Page
- Builds the page: a full-window canvas, the controls bar and the info panel. Scripts load
  in this order: bodies, clock, camera, selection, controls, scene, probe. Each frame runs
  clock tick → scene draw.
- The page opens and draws the solar system without errors:
  `body("sun").r > 0` and `errors` is empty. [@test](../../tests/viewer/opens.test.js)
- No errors or warnings: after `step(5)`, `errors` is empty.
  [@test](../../tests/viewer/no-errors.test.js)
- Learn: clicking a planet shows its panel. After `clickBody("mars")`, `panel.shown` is true.
  [@test](../../tests/viewer/learn.test.js)
- Units: zooming in grows the bodies but not the lines and names. Store `strokes` and
  `body("earth")`, run `zoomSteps(5)`, then check that `strokes` is deep-equal to before and
  `body("earth").r` grew by more than 0. [@test](../../tests/viewer/units.test.js)

### Web delivery
- Delivery: out/index.html holds everything. It works opened straight from disk, with no
  network. No test link: this is checked by hand, by opening the file with networking off.
- Pixels: 1 px is one CSS pixel. Drawing stays sharp on dense screens, because the canvas
  backing store is scaled by devicePixelRatio. No test link: this needs a screen with more
  than one device pixel per CSS pixel.
- Input: mouse and touch both work. One wheel notch is one zoom step (camera.spec.md).
- Test run: tests run in headless Chrome. Coverage comes from Chrome's built-in coverage.

### Quality
- At least 90% of requirements have a `[@test]` link, and at least 80% of lines are covered.
  No test link: Tessl has no coverage or fact-coverage check (see AGENTS.md).

## Dependencies

- [@use](./bodies.spec.md)
- [@use](./clock.spec.md)
- [@use](./camera.spec.md)
- [@use](./scene.spec.md)
- [@use](./controls.spec.md)
- [@use](./selection.spec.md)
- [@use](./probe.spec.md)
