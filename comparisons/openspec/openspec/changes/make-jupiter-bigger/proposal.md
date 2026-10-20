## Why

Jupiter is the largest planet, but at size 16 it hardly stands out next to Saturn (13).
Making it clearly bigger makes the view read more naturally while staying smaller than the sun.

## What Changes

- Jupiter's size in bodies "Planet data" goes from 16 to 20 space units (guess: the request
  said only "bigger"; 20 keeps it below the sun's 28, so bodies "Sun" still holds).
- No other planet, orbit, color or behavior changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bodies`: requirement "Planet data" changes one table value (Jupiter size 16 → 20).

## Impact

- Code: the body table in out/index.html.
- Scenarios to re-run: bodies "Sun" (sun bigger than Jupiter), scene "Names" (no overlaps at
  top speed), selection "Nearest body wins" (Jupiter's larger click area).
