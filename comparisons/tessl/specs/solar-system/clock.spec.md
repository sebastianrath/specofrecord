# Clock

Simulated time, so that years can pass in seconds. The clock alone owns time, paused and
speed. Nobody else changes them.

## Targets

[@generate](../../src/clock.js)

## Capabilities

- Start: when the app opens, time is 0 days and running. After a reset, `time` is 0 and
  `paused` is false. [@test](../../tests/clock/start.test.js)
- Speed: a slider runs from 0 to 100 and starts at 40. Speed = (slider ÷ 100)² years per
  second, where a year is 365 days.
  [@test](../../tests/clock/speed.test.js)
  - At slider 0, after `step(1)` the time is unchanged.
  - At slider 50, after `step(4)` the time moved by 365 days ± 1%.
  - At slider 100, after `step(1)` the time moved by 365 days ± 1%.
- Time is counted in days: after `slider(100)` and `step(1)`, `time` is 365.
  [@test](../../tests/clock/time.test.js)
- Pause: while paused, time does not move. Run `press("Space")`, store `time`, run `step(2)`,
  and check that the time is unchanged. [@test](../../tests/clock/pause.test.js)
- Real time: each frame adds (real seconds since the last frame × speed). After a long gap,
  such as a hidden tab, at most 0.1 s counts, so the planets do not jump when the tab comes
  back. No test link: this needs a real clock, and the test hooks freeze time. It is checked
  by hand.

## API

```js { .api }
export function getTime(): number;          // days
export function isPaused(): boolean;
export function getSpeed(): number;         // years per second
export function setSlider(v: number): void; // 0..100
export function setPaused(on: boolean): void;
export function reset(): void;              // time back to 0; speed and paused stay
export function tick(realSeconds: number): void;   // capped at 0.1 s
export function step(seconds: number): void;       // test hook: exact, no cap, not while paused
```
