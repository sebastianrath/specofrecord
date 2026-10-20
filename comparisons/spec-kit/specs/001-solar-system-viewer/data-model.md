# Data Model: Solar System Viewer

**Feature**: 001-solar-system-viewer | **Date**: 2026-10-16

## Body (static table + one random field)

| Field | Type | Rule |
|---|---|---|
| name | string | lowercase id: sun, mercury … neptune, moon |
| size | number (space units) | from spec Body Catalogue; Saturn's ring not included |
| orbit | number (space units) | 0 for sun; moon's orbit is around Earth |
| days | number | orbit time; Earth's 365 defines one year |
| color | hex string | from Body Catalogue |
| fact | string | exactly one sentence, true |
| startAngle | radians | random once per run, read-only afterwards (FR-004) |
| parent | name or null | `earth` for the moon, `sun` for planets |

Values: see spec.md → Body Catalogue (single source; this file does not repeat them).
*(Guess: real `/speckit.plan` output usually copies the table here as well.)*

**Position(t)**: angle = startAngle + 2π × t / days (clockwise on screen); centre = parent's position(t).

## Clock — owner: clock module

| Field | Type | Rule |
|---|---|---|
| time | days | starts 0; changed only by clock |
| paused | bool | starts false |
| slider | 0..100 | starts 40 |
| speed | years/s | (slider / 100)² |

Transitions: frame → `time += min(dt, 0.1) × speed × 365` unless paused; Space/button → toggle paused; reset → time = 0 (speed, paused kept).

## View — owner: camera module

| Field | Type | Rule |
|---|---|---|
| zoom | number | starts 1; clamped to [0.3, 6] |
| pan | {x, y} px | starts {0, 0} (sun centred) |
| base | px per space unit | derived from window size (research R3), ≤ 1 |

Transitions: wheel/pinch step → zoom × 1.1^n about pointer; drag ≥ 4 px → pan += delta; reset → zoom 1, pan 0.

## Switches — owner: controls module

orbits: bool (true), names: bool (true). Reset keeps them.

## Selection — owner: selection module

selected: body name or null. Click → nearest in reach or null; reset → null.
