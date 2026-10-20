# Camera

Decides which part of the solar system is visible, and how big. The camera alone owns
zoom and pan. Nobody else changes them.

## Targets

[@generate](../../src/camera.js)

## Capabilities

- Bars: the top 56 px and the bottom 56 px stay free at the start.
- Fit: at the start, the outermost orbit plus 28 px of room for its planet and name fits
  between the bars, at most 1 px per space unit. A base scale fits the system between the
  bars and zoom multiplies it. The base scale is recomputed when the window changes size,
  in width and height.
  [@test](../../tests/camera/fit.test.js)
  - At each of 1280x720, 800x600 and 640x480: `layout.gapTop ≥ 56`,
    `layout.gapBottom ≥ 56`, `layout.orbitTop = 56 + 28 ± 0.5`, and
    `layout.orbitBottom = 56 + 28 ± 0.5`.
- Start: zoom is 1x, with the sun in the middle of the screen.
- Zoom step: one wheel notch or pinch step zooms by 1.1x, and the point under the pointer
  stays put. [@test](../../tests/camera/zoom-step.test.js)
  - Store `body("earth")`, then run `zoomAt("earth", 1)`. Zoom is 1.1, and Earth's x moved
    by 0 ± 1.
  - Then `zoomAt("earth", -1)` and `pinch(1)` give a zoom of 1.1.
- Wheel input: one wheel notch is one zoom step. After `zoomSteps(1)`, zoom is 1.1.
  [@test](../../tests/camera/input.test.js)
- Limits: zoom stays between 0.3x and 6x. After `zoomSteps(200)`, zoom is 6. After
  `zoomSteps(-400)`, zoom is 0.3. [@test](../../tests/camera/limits.test.js)
- Drag: dragging moves the view. A press that moves less than 4 px is a click.
  [@test](../../tests/camera/drag.test.js)
  - After `drag(50, 0)`, `pan.x` moved by 50 ± 0.5.
  - After `drag(3, 0)`, `pan` is unchanged.
- To screen: turns a space point into a screen point and back. A body's place on screen
  follows the view: after `drag(30, 0)`, `body("mars").x` moved by 30 ± 0.5.
  [@test](../../tests/camera/to-screen.test.js)

## API

```js { .api }
export function toScreen(p: {x:number,y:number}): {x:number,y:number};
export function toSpace(p: {x:number,y:number}): {x:number,y:number};
export function getZoom(): number;
export function getPan(): {x:number,y:number};
export function zoomAt(screenPoint: {x:number,y:number}, steps: number): void;
export function panBy(dx: number, dy: number): void;
export function resize(w: number, h: number): void;
export function reset(): void;   // zoom 1x, sun centered
export const BAR_TOP = 56, BAR_BOTTOM = 56;
```

## Dependencies

- [@use](./bodies.spec.md): the outermost orbit.
