# Controls

Lets people steer time and the view: one small bar at the left of the bottom bar
(see camera.spec.md).

## Targets

[@generate](../../src/controls.js)

## Capabilities

- Slider: sets the clock speed (clock.spec.md). Halfway is a quarter year per second.
  After `slider(50)`, `speed` is 0.25 ± 0.001. [@test](../../tests/controls/slider.test.js)
- Pause: a button that reads "Pause" or "Play". The Space key does the same, even right
  after any control was clicked. After `use("pause")` and `press("Space")`, `paused` is false.
  [@test](../../tests/controls/pause.test.js) { .locked }
  <!-- FACT: "bug: #3". This regression test is marked { .locked } so that Tessl keeps it
       and does not regenerate it. GUESS: placing the tag right after the link follows the
       docs' wording; we have seen no rendered example. -->
- Checkboxes: "Orbits" and "Names", both on at the start. With both turned off, there are
  no orbit lines and no names: after `use("orbits")`, `use("names")` and `step(0)`,
  `strokes.orbitLines` is null and there are 0 `labels`.
  [@test](../../tests/controls/checkboxes.test.js)
- Switches: the orbit switch turns orbit lines off and on again. After one `use("orbits")`,
  `strokes.orbitLines` is null. After a second, it is 1 (px, from scene.spec.md).
  [@test](../../tests/controls/switches.test.js)
- Reset: time goes back to 0 and the view back to the camera start, with nothing selected.
  Speed, play/pause and the checkboxes stay as they are. Run `zoomSteps(4)`,
  `drag(50, 50)` and `slider(70)`, store `speed`, then run `use("reset")`. Zoom is 1 and
  `speed` is unchanged. [@test](../../tests/controls/reset.test.js)

## API

```js { .api }
export function mount(barElement: HTMLElement): void;
export function getSwitches(): { orbits: boolean, names: boolean };
```

## Dependencies

- [@use](./clock.spec.md)
- [@use](./camera.spec.md)
- [@use](./selection.spec.md)
