# Scene

Draws everything, calm and clear, like a planetarium. The scene only reads state. It never
changes time, zoom or pan.

## Targets

[@generate](../../src/scene.js)

## Capabilities

- Draw order: sky, stars, comet, orbits, sun, planets, moon, selected ring, names, time.
- Sky: the sky is blue-black (#05060F), with 300 softly twinkling stars that ignore zoom
  and pan. Store `stars`, run `zoomSteps(5)` and `drag(30, 0)`, then check that there are
  300 stars and that `stars` is unchanged. [@test](../../tests/scene/sky.test.js)
  <!-- FACT records "bug: the first build drew no stars". Tessl has no bug field. -->
- Bodies: a glowing sun. Planets are brighter on the side facing the sun. Saturn's ring
  passes behind and in front of it. Glow, shading, ring tilt and fonts are the generator's
  choice. No test link: this is judged by eye.
  <!-- FACT: "bug: the first build drew flat circles". -->
- Orbits: faint 1 px circles for the planets and the moon, drawn while switched on.
- Selected: a white ring, 2 px wide, drawn 4 px outside the selected body. Lines and names
  keep their size at the smallest and largest zoom. Run `clickBody("jupiter")` and
  `zoomAt("jupiter", -400)`, store `strokes`, run `zoomAt("jupiter", 400)`, and check that
  `strokes` is unchanged. [@test](../../tests/scene/selected.test.js)
- Names: 12 px names under the bodies, drawn while switched on. When two would overlap,
  the one closer to the sun stays. The moon's name shows once the moon is 30 px from Earth.
  At top speed, names never overlap: for 20 rounds, run `slider(100)` and `step(1)`, then
  check that the overlaps among `labels` are 0. [@test](../../tests/scene/names.test.js)
- Time: top left, the text reads "Year 0, day 0" at the start and counts years (365 days)
  and days. After `slider(100)` and `step(1)`, `hud` contains "Year 1".
  [@test](../../tests/scene/time.test.js)
- Comet: a small comet with a faint tail crosses the solar system every 20 s. Its path is
  in space units, so it moves and zooms with the planets. Run `showComet()`, store `comet`,
  run `drag(50, 0)`, and check that `comet.x` moved by 50 ± 1.
  [@test](../../tests/scene/comet.test.js)

## API

```js { .api }
export function draw(ctx: CanvasRenderingContext2D, state: {
  time: number, positions: Record<string,{x:number,y:number}>, selected: string|null,
  showOrbits: boolean, showNames: boolean }): void;
/** Readings for the probe: strokes, labels, layout, stars, comet. */
export function readings(): object;
export function showComet(): void;   // test hook
```

## Dependencies

- [@use](./bodies.spec.md)
- [@use](./camera.spec.md)
- [@use](./controls.spec.md)
- [@use](./selection.spec.md)
