---
status: final
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-solar-system-2026-10-16/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-solar-system-2026-10-16/ARCHITECTURE-SPINE.md
---

# solar-system - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for solar-system, decomposing the
requirements from the PRD and Architecture requirements into implementable stories.

> Comparison note: in a real run every story below carries full Given/When/Then criteria. Here
> only Stories 1.3, 2.2 and 3.1 are written out; the rest are listed by title with their FRs.

## Requirements Inventory

### Functional Requirements

FR-1 Body table (10 bodies, sizes/orbits/days/colors) · FR-2 Fun facts (1 true sentence each) ·
FR-3 Start places (random, once per run) · FR-4 Motion (clockwise circles; moon around Earth) ·
FR-5 Clock start (0 days, running) · FR-6 Speed ((slider/100)² years/s, slider 0–100 start 40) ·
FR-7 Pause · FR-8 Real-time stepping (cap 0.1 s) · FR-9 Fit (bars 56/56 px, room 28 px, ≤ 1 px per
unit) · FR-10 Start view (1×, sun centered) · FR-11 Zoom step (1.1×, anchored at pointer) ·
FR-12 Zoom limits (0.3×–6×) · FR-13 Drag (< 4 px is a click) · FR-14 Sky (#05060F, 300 stars) ·
FR-15 Orbit lines (1 px) · FR-16 Body rendering · FR-17 Selection ring (2 px, 4 px gap) ·
FR-18 Names (12 px, no overlap, moon at 30 px) · FR-19 Time display · FR-20 Comet (every 20 s) ·
FR-21 Speed slider · FR-22 Pause/Play + Space · FR-23 Switches · FR-24 Reset · FR-25 Reach (≥ 10 px) ·
FR-26 Nearest wins · FR-27 Panel · FR-28 Miss · FR-29 Selected body

### NonFunctional Requirements

NFR-1 Calm · NFR-2 No errors · NFR-3 Units (px fixed, space units zoom) · NFR-4 Delivery (one
offline file) · NFR-5 Sharpness · NFR-6 Input (mouse, touch, 1 notch = 1 step) · NFR-7 Testability ·
NFR-8 Quality (≥ 90% requirements tested, ≥ 80% lines)

### Additional Requirements

From the architecture spine: AD-1 single file; AD-2 one writer per state; AD-3 `toScreen`/`toSpace`
only; AD-4 capped tick + `probe.step`; AD-5 `window.__probe` contract and before-each reset; AD-6
draw order; AD-7 devicePixelRatio canvas.

### UX Design Requirements

None (no UX document; visual rules are in the PRD).

### FR Coverage Map

| Requirement | Story |
|---|---|
| NFR-2, NFR-4, NFR-5, NFR-7, AD-1, AD-5, AD-7 | 1.1 |
| FR-1, FR-2 (data), FR-3 | 1.2 |
| FR-4, FR-5, FR-6, FR-7, FR-8, AD-4 | 1.3 |
| FR-9, FR-10 | 1.4 |
| FR-14, FR-15, FR-16, AD-6 | 1.5 |
| FR-18 | 1.6 |
| FR-19 | 1.7 |
| FR-20 | 1.8 |
| FR-21, FR-22 | 2.1 |
| FR-11, FR-12, NFR-3, NFR-6 | 2.2 |
| FR-13 | 2.3 |
| FR-23, FR-24 | 2.4 |
| FR-25, FR-26, FR-28, FR-29 | 3.1 |
| FR-2 (display), FR-27 | 3.2 |
| FR-17 | 3.3 |
| NFR-1, NFR-8 | checked at the Epic 3 retrospective |

## Epic List

1. Watch the solar system move — open the file and see the planets circle on a calm sky.
2. Steer time and the view — speed, pause, zoom, drag, switches, reset.
3. Click to learn — select any body and read its fun fact.

## Epic 1: Watch the solar system move

Open `out/index.html` from disk and watch the 10 bodies circle, with time counting up.

### Story 1.1: Offline page shell and test hooks
(NFR-2, NFR-4, NFR-5, NFR-7, AD-1, AD-5, AD-7)

### Story 1.2: Body table, fun facts and start places
(FR-1, FR-2, FR-3)

### Story 1.3: Clock and orbital motion

As a viewer,
I want simulated time to run at a speed I can trust,
So that I can watch years pass in seconds and see each planet return to its place.

**Acceptance Criteria:**

**Given** the page has just opened or been reset
**When** I read the clock
**Then** time is 0 days
**And** it is running (not paused)

**Given** the slider is at 0
**When** 1 s is stepped
**Then** time is unchanged

**Given** the slider is at 50
**When** 4 s are stepped
**Then** time has advanced by 365 days ± 1%

**Given** the slider is at 100
**When** 1 s is stepped
**Then** time has advanced by exactly 365 days
**And** Earth's on-screen x is where it started ± 1 px

**Given** the slider is at 100
**When** 27/365 s (0.073972602739726 s) is stepped
**Then** the moon's offset from Earth is unchanged ± 0.5 px in x and y

**Given** the clock is paused with Space
**When** 2 s are stepped
**Then** time is unchanged

**Given** the app has run for 5 s
**When** I read the start angles
**Then** they are the same as at the start

**Given** a real browser tab was hidden for a long time
**When** it becomes visible again
**Then** at most 0.1 s of real time is counted for that frame (manual check)

### Story 1.4: Camera fit and start view
(FR-9, FR-10)

### Story 1.5: Sky, stars, orbit lines and lit bodies
(FR-14, FR-15, FR-16, AD-6)

### Story 1.6: Names without overlap
(FR-18)

### Story 1.7: Time display
(FR-19)

### Story 1.8: Comet
(FR-20)

## Epic 2: Steer time and the view

Change the speed, pause, zoom, drag, switch layers off and reset.

### Story 2.1: Speed slider and Pause/Play
(FR-21, FR-22 — including regression bug #3: Space after a clicked control)

### Story 2.2: Zoom with wheel and pinch

As a viewer,
I want to zoom in on the spot under my pointer,
So that I can look closer at one planet without losing it.

**Acceptance Criteria:**

**Given** the start view
**When** I zoom one wheel notch over Earth
**Then** zoom is 1.1
**And** Earth's on-screen x is unchanged ± 1 px

**Given** the start view
**When** I pinch one step outward
**Then** zoom is 1.1

**Given** any view
**When** I zoom in 200 steps
**Then** zoom is 6
**When** I then zoom out 400 steps
**Then** zoom is 0.3

**Given** the start view
**When** I zoom in 5 steps
**Then** orbit line width, selection ring width and name size are unchanged
**And** Earth's radius on screen is larger

### Story 2.3: Drag to pan
(FR-13)

### Story 2.4: Orbit and name switches, and reset
(FR-23, FR-24)

## Epic 3: Click to learn

Click any body to select it and read one true fact.

### Story 3.1: Click selection — reach, nearest wins, miss

As a viewer,
I want a click to pick the body I meant, even a tiny one,
So that every body, the moon included, can be learned about at any zoom.

**Acceptance Criteria:**

**Given** the start view
**When** I click Venus
**Then** the selected body is Venus

**Given** the screen is 1280×720 or 800×600, at the smallest zoom, after 0.37 s
**When** I click Mercury, then Earth, then the moon
**Then** each click selects that body
**And** this holds in 10 repeated runs (random start places)

**Given** the smallest zoom
**When** I click 9 px further from the sun than Neptune's center
**Then** Neptune is selected
**When** I click 12 px further out
**Then** nothing is selected

**Given** Jupiter is selected
**When** I click empty space at (3, 300)
**Then** nothing is selected

### Story 3.2: Info panel with fun facts
(FR-2, FR-27, and FR-28's "hides the panel" — the panel does not exist before this story)

### Story 3.3: Selection ring
(FR-17)
