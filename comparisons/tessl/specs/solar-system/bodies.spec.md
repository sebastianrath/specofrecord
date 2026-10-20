# Bodies

The fixed facts about the sun, the planets and the moon, and where each one is at any time.

## Targets

[@generate](../../src/bodies.js)

## Capabilities

### Table
- Sun: size 28, color #FFC93C.
- Planets: sizes and orbits are in space units, orbit times in days. Saturn has a ring
  that is not part of its size.

  | Planet | Size | Orbit | Days | Color |
  |---|---|---|---|---|
  | Mercury | 4 | 60 | 88 | #B1ADA7 |
  | Venus | 7 | 90 | 225 | #E8C98A |
  | Earth | 7 | 125 | 365 | #4F8FE6 |
  | Mars | 5 | 160 | 687 | #D1623A |
  | Jupiter | 16 | 230 | 4333 | #D9A66C |
  | Saturn | 13 | 300 | 10759 | #E3CF8E |
  | Uranus | 10 | 365 | 30687 | #8FD3D9 |
  | Neptune | 10 | 420 | 60190 | #4468D6 |
- Moon: it circles Earth. Size 2, orbit 14, 27 days, color #CCCCCC.
- Fun facts: every body, the sun too, has one true fun fact that is exactly 1 sentence long.
- There are 10 bodies: the sun, 8 planets and the moon. `bodies` has 10 entries.
  [@test](../../tests/bodies/count.test.js)
- The sun is drawn bigger than any planet: `body("sun").r > body("jupiter").r`.
  [@test](../../tests/bodies/sun.test.js)
- Each body in the table can be found and clicked by its lowercase name. For each of sun,
  mercury, venus, earth, mars, jupiter, saturn, uranus, neptune and moon,
  `clickBody(name)` makes `selected` equal to that name. [@test](../../tests/bodies/table.test.js)
- Clicking any body shows its fun fact as one sentence. For each of the 10 names,
  `clickBody(name)` gives a `panel.fact` with exactly 1 sentence.
  [@test](../../tests/bodies/fun-facts.test.js)

### Start places
- Each planet and the moon starts at a random angle. The angles are picked once per run.
- Start places never change while the app runs. Store `startAngles`, run `step(5)`, and
  check that `startAngles` is unchanged. [@test](../../tests/bodies/start-places.test.js)

### Positions
- Motion: bodies move in clockwise circles, with angle = start angle + 2π × (time in
  days ÷ own orbit days). The moon circles Earth's current position.
- After one year, Earth is back where it started. Run `slider(100)`, store `body("earth")`,
  run `step(1)`, and check that `x` moved by 0 ± 1. [@test](../../tests/bodies/positions.test.js)
- After one moon month (27 days), the moon is back on the same side of Earth. Run
  `slider(100)` and store the moon's offset from Earth. Then run `step(0.073972602739726)`
  (27 ÷ 365 s), and check that the offset's x and y each moved by 0 ± 0.5.
  [@test](../../tests/bodies/moon.test.js)

## API

```js { .api }
// GUESS at shape: FACT leaves internal APIs to the compiler, but a Tessl spec normally
// pins the public API of its file.
/** @type {Array<{name:string,size:number,orbit:number,days:number,color:string,funFact:string,ring?:boolean,around?:string}>} */
export const BODIES;
/** Random start angle per planet and the moon; called once per run. */
export function pickStartAngles(random = Math.random): Record<string, number>;
/** Space-unit position of every body at the given time (days). */
export function positions(timeDays: number, startAngles: Record<string, number>): Record<string, {x:number, y:number}>;
```

## Dependencies

- [@use](./clock.spec.md): reads the time that has passed.
