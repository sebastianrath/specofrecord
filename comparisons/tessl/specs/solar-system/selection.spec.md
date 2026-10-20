# Selection

Click a body to learn one thing about it.

## Targets

[@generate](../../src/selection.js)

## Capabilities

- Selected: a click on a body selects it. After `clickBody("venus")`, `selected` is
  "venus". [@test](../../tests/selection/selected.test.js)
- Reach: a click counts for a body within its on-screen size, but at least 10 px.
  At the smallest zoom, a click just outside a tiny body still counts, and further out it
  does not. After `zoomSteps(-400)`, `clickNear("neptune", 9)` selects "neptune" and
  `clickNear("neptune", 12)` selects nothing. [@test](../../tests/selection/reach.test.js)
- Nearest: if several bodies are in reach, the one whose center is nearest wins. Distance
  decides, not a fixed order, because at the start zoom the moon's click area covers Earth,
  and a fixed order made Earth unclickable.
  [@test](../../tests/selection/nearest.test.js)
  - At 1280x720 and at 800x600, repeated for 10 rounds: run `zoomSteps(-400)` and
    `step(0.37)`, then check that `clickBody("mercury")`, `clickBody("earth")` and
    `clickBody("moon")` each select that body.
- Panel: top right, it shows the name, the fun fact and the orbit time ("88 days", or
  "11.9 years" from 365 days up). The sun shows no orbit time. After `clickBody("jupiter")`,
  `panel.text` contains "Jupiter" and "years". [@test](../../tests/selection/panel.test.js)
- Miss: a click on empty space selects nothing and hides the panel. After
  `clickBody("jupiter")` and `click(3, 300)`, `selected` is null.
  [@test](../../tests/selection/miss.test.js)

## API

```js { .api }
export function pick(screenPoint: {x:number,y:number}): string | null;
export function getSelected(): string | null;
export function clear(): void;
```

## Dependencies

- [@use](./bodies.spec.md)
- [@use](./camera.spec.md)
