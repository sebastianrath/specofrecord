# Research: Solar System Viewer

**Feature**: 001-solar-system-viewer | **Date**: 2026-10-16

## R1. Rendering

- **Decision**: Canvas 2D, backing store scaled by `devicePixelRatio`.
- **Rationale**: 300 stars + glow are cheap on canvas; DPR scaling keeps 1 px = 1 CSS px and sharp (FR-035).
- **Alternatives considered**: SVG (DOM cost for twinkling stars), WebGL (overkill, harder to test strokes).

## R2. Time stepping

- **Decision**: `requestAnimationFrame`; `dt = min(realSeconds, 0.1)`; `time += dt × speed × 365`.
- **Rationale**: FR-010 cap; a hidden tab must not make planets jump.
- **Alternatives considered**: fixed-step accumulator (adds catch-up jumps, which the spec forbids).

## R3. Base scale and fit

- **Decision**: `base = min(1, (h − 56 − 56 − 2·28) / (2·420), (w − 2·28) / (2·420))`, recomputed on `resize`.
- **Rationale**: FR-011 and FR-016; capped at 1 px per space unit.
- **Alternatives considered**: CSS transform scaling (would scale px-sized strokes, breaking FR-017).

## R4. Zoom about the pointer

- **Decision**: new pan = pointer − (pointer − pan) × (newZoom / oldZoom), zoom clamped to [0.3, 6]; wheel `deltaY` sign = one notch; pinch maps distance ratio to 1.1x steps.
- **Rationale**: FR-013, FR-014, FR-036.
- **Alternatives considered**: zoom about screen centre (violates "point under the pointer stays put").

## R5. Hit testing

- **Decision**: candidates = bodies with distance ≤ max(on-screen radius, 10 px); pick minimum distance.
- **Rationale**: FR-030/FR-031; a fixed priority order made Earth unclickable under the moon (Clarifications).
- **Alternatives considered**: z-order picking.

## R6. Label overlap

- **Decision**: lay out names from the sun outward; skip a label whose box intersects one already placed; the moon's label only when |moon − earth| ≥ 30 px.
- **Rationale**: FR-022.

## R7. Testing hook

- **Decision**: `window.__probe` (see contracts/probe-api.md). The first probe action freezes real time; afterwards only `step(seconds)` moves the clock, by exactly seconds × speed with no cap.
- **Rationale**: Deterministic tests; Constitution III.
- **Alternatives considered**: fake timers via Puppeteer `clock` (less control over rAF).

## R8. Open choices left to the implementer

Glow, planet shading, Saturn ring tilt, fonts, star twinkle curve, comet path and tail look,
fun-fact wording. *(Guess: a real `/speckit.plan` run would record these as decisions too, adding 50–100 lines.)*
