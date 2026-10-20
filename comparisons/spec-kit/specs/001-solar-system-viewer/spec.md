# Feature Specification: Solar System Viewer

**Feature Branch**: `001-solar-system-viewer`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "A calm, good-looking web page to watch the planets move and learn one fact about each. The sun, 8 planets and the moon on circular orbits, a speed slider, pause, reset, drag and zoom, click a body to see a fun fact. One HTML file that works offline."

## Clarifications

### Session 2026-10-16

- Q: How fast is top speed on the slider? → A: One Earth year (365 days) per second; speed = (slider ÷ 100)² years per second.
- Q: At the start zoom the moon's click area covers Earth. Which body wins a click? → A: The body whose centre is nearest; never a fixed order (a fixed order made Earth unclickable).
- Q: After a hidden tab comes back, should the planets catch up? → A: No. At most 0.1 s of real time counts per frame, so nothing jumps.
- Q: Should line widths and name sizes grow with zoom? → A: No. Screen-pixel sizes stay fixed; only solar-system sizes and distances grow.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Watch the solar system move (Priority: P1)

A visitor opens the page and sees a dark, twinkling sky with the sun in the middle and the eight
planets and the moon circling it, with faint orbit lines, names, a time display and an occasional
comet. Everything fits on screen between a free strip at the top and bottom.

**Why this priority**: This is the product. Without it nothing else has meaning.

**Independent Test**: Open the page with no interaction and check the bodies, the fit, the sky and
that time advances with zero console errors.

**Acceptance Scenarios**:

1. **Given** the page has just opened, **When** it is inspected, **Then** exactly 10 bodies exist (sun, 8 planets, moon) and the sun is drawn larger than Jupiter.
2. **Given** the page is running, **When** 5 s pass, **Then** there are 0 console errors or warnings and the sun's drawn radius is > 0.
3. **Given** the window is 1280×720, 800×600 or 640×480, **When** the page opens, **Then** nothing drawn comes within 56 px of the top or bottom edge, and the outermost orbit sits exactly 56 + 28 px from each edge (±0.5 px).
4. **Given** the page is running, **When** 5 s pass, **Then** each body's random start angle is unchanged.
5. **Given** the slider is at 100, **When** 1 s passes, **Then** Earth is back at its start x (±1 px) and the time display contains "Year 1".
6. **Given** the slider is at 100, **When** one moon month passes (27/365 s), **Then** the moon's offset from Earth is unchanged (±0.5 px in x and y).
7. **Given** the page is running, **When** the user zooms 5 steps and drags 30 px, **Then** there are still 300 stars and none of them moved.
8. **Given** the comet is visible, **When** the user drags 50 px right, **Then** the comet head moves 50 px right (±1 px).
9. **Given** the slider is at 100, **When** checked once a second for 20 s, **Then** no two names ever overlap.
10. **Given** the page is open, **When** the user zooms in 5 steps, **Then** body radii grow but orbit-line, ring and name sizes are unchanged.

---

### User Story 2 - Steer time (Priority: P2)

The visitor changes the speed with a slider, pauses and resumes with a button or the Space key,
and resets to the starting picture.

**Why this priority**: Watching at one fixed speed gets dull quickly; steering time is the main interaction.

**Independent Test**: Use only the slider, Pause and Reset, and read the time.

**Acceptance Scenarios**:

1. **Given** the slider is at 0, **When** 1 s passes, **Then** time is unchanged.
2. **Given** the slider is at 50, **When** 4 s pass, **Then** time advanced 365 days (±1%), and speed reads 0.25 years/s (±0.001).
3. **Given** the slider is at 100, **When** 1 s passes, **Then** time advanced 365 days (±1%).
4. **Given** the page is running, **When** the user presses Space and 2 s pass, **Then** time is unchanged.
5. **Given** the user clicked the Pause button, **When** they press Space, **Then** the clock is running again. *(Known regression: issue #3.)*
6. **Given** the user zoomed 4 steps, dragged (50, 50) and set the slider to 70, **When** they press Reset, **Then** zoom is 1x, the speed is still the slider-70 speed, time is 0 days and the clock is running.

---

### User Story 3 - Explore the view (Priority: P2)

The visitor drags to move the view and zooms with the wheel or a pinch, toward the point under the pointer.

**Why this priority**: Inner planets are tiny at the start zoom; zoom is needed to see them.

**Independent Test**: Drag and zoom only, reading zoom, pan and a body's screen position.

**Acceptance Scenarios**:

1. **Given** the pointer is over Earth, **When** the user scrolls one notch in, **Then** zoom is 1.1x and Earth stays under the pointer (±1 px).
2. **Given** zoom is 1x, **When** the user pinches out one step, **Then** zoom is 1.1x.
3. **Given** any zoom, **When** the user zooms in 200 steps, **Then** zoom is 6x; **When** they then zoom out 400 steps, **Then** zoom is 0.3x.
4. **Given** the view, **When** the user drags 50 px right, **Then** pan moves 50 px (±0.5); **When** they press and move only 3 px, **Then** pan is unchanged.
5. **Given** the view, **When** the user drags 30 px right, **Then** Mars moves 30 px right on screen (±0.5).
6. **Given** Jupiter is selected, **When** the user zooms fully out and then fully in, **Then** orbit lines, the selection ring and names keep their pixel sizes.

---

### User Story 4 - Learn by clicking (Priority: P3)

The visitor clicks any body and a panel shows its name, one fun fact and its orbit time.

**Why this priority**: The "learn" half of the goal; the page is still useful without it.

**Independent Test**: Click each body and read the panel.

**Acceptance Scenarios**:

1. **Given** the page is open, **When** the user clicks Mars, **Then** the panel is shown.
2. **Given** the page is open, **When** the user clicks each of sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune, moon, **Then** that body is selected and the panel's fun fact is exactly 1 sentence.
3. **Given** the page is open, **When** the user clicks Jupiter, **Then** the panel contains "Jupiter" and "years".
4. **Given** the page is open, **When** the user clicks Venus, **Then** Venus is selected.
5. **Given** Jupiter is selected, **When** the user clicks empty space at (3, 300), **Then** nothing is selected and the panel hides.
6. **Given** the smallest zoom, at 1280×720 and 800×600, over 10 rounds 0.37 s apart, **When** the user clicks Mercury, Earth, then the moon, **Then** each click selects that body.
7. **Given** the smallest zoom, **When** the user clicks 9 px outside Neptune's centre (away from the sun), **Then** Neptune is selected; **When** 12 px outside, **Then** nothing is selected.

---

### User Story 5 - Declutter (Priority: P3)

The visitor turns orbit lines and names off and on.

**Why this priority**: Nice to have for a cleaner picture.

**Independent Test**: Toggle the two checkboxes and inspect what is drawn.

**Acceptance Scenarios**:

1. **Given** both checkboxes are on, **When** the user turns both off, **Then** no orbit lines and no names are drawn.
2. **Given** orbits are on, **When** the user turns them off and on again, **Then** orbit lines are gone and then back at 1 px.

### Edge Cases

- Hidden tab returns after minutes: at most 0.1 s of time is applied for that frame (FR-010).
- Window resized: the base scale is recomputed from both width and height (FR-016).
- Moon close to Earth on screen: its name only shows once it is ≥ 30 px from Earth (FR-022).
- Several bodies within click reach: nearest centre wins (FR-032).
- Press that moves a little: under 4 px it is a click, not a drag (FR-015).
- Space pressed right after a control was clicked: still toggles pause (FR-027).

## Requirements *(mandatory)*

### Functional Requirements

**Bodies**

- **FR-001**: System MUST show the sun, the 8 planets and Earth's moon (10 bodies) with the sizes, orbit radii, orbit times and colours in the Body Catalogue below. Sizes and orbits are in space units.
- **FR-002**: Saturn MUST have a ring that is not part of its size.
- **FR-003**: Every body, the sun too, MUST have one true fun fact, exactly one sentence long.
- **FR-004**: Each planet and the moon MUST start at a random angle, picked once per run and never changed while the page runs.
- **FR-005**: Bodies MUST move clockwise on circles: angle = start angle + full turn × (time ÷ own orbit time). The moon circles Earth's current position.

**Time**

- **FR-006**: A year MUST equal Earth's orbit time (365 days).
- **FR-007**: When the page opens, time MUST be 0 days and running.
- **FR-008**: A slider from 0 to 100, starting at 40, MUST set speed = (slider ÷ 100)² years per second.
- **FR-009**: While paused, time MUST NOT move.
- **FR-010**: Each frame MUST add real seconds since the last frame × speed, counting at most 0.1 s after a long gap.

**View**

- **FR-011**: At the start, the outermost orbit plus 28 px of room MUST fit between the top bar (56 px) and the bottom bar (56 px), at no more than 1 px per space unit.
- **FR-012**: The start view MUST be zoom 1x with the sun in the middle of the screen.
- **FR-013**: One wheel notch or pinch step MUST zoom by 1.1x, keeping the point under the pointer in place.
- **FR-014**: Zoom MUST stay between 0.3x and 6x.
- **FR-015**: Dragging MUST move the view; a press that moves less than 4 px MUST count as a click.
- **FR-016**: The fit MUST be recomputed when the window changes size, in width and height.
- **FR-017**: Sizes given in px are screen pixels and MUST NOT grow with zoom; space-unit sizes MUST grow with zoom.

**Drawing**

- **FR-018**: Sky MUST be blue-black (#05060F) with 300 softly twinkling stars that ignore zoom and pan.
- **FR-019**: While switched on, planets and the moon MUST have faint 1 px orbit circles.
- **FR-020**: The sun MUST glow; planets MUST be brighter on the side facing the sun; Saturn's ring MUST pass behind and in front of it.
- **FR-021**: The selected body MUST have a white ring, 2 px wide, 4 px outside the body.
- **FR-022**: While switched on, 12 px names MUST appear under the bodies; when two would overlap, the one closer to the sun stays; the moon's name shows only once the moon is 30 px from Earth.
- **FR-023**: Top left MUST show the time as "Year 0, day 0" at the start, counting years and days.
- **FR-024**: Every 20 s a small comet with a faint tail MUST cross the solar system on a path in space units (it moves and zooms with the planets).

**Controls**

- **FR-025**: The slider (FR-008) MUST set the speed.
- **FR-026**: A button reading "Pause" or "Play" MUST toggle pause; the Space key MUST do the same, even right after any control was clicked.
- **FR-027**: Checkboxes "Orbits" and "Names" MUST exist, both on at the start.
- **FR-028**: Reset MUST put time back to 0, the view back to the start view and select nothing, while keeping speed, play/pause and the checkboxes.
- **FR-029**: The controls MUST sit in one small bar at the left of the bottom bar.

**Selection**

- **FR-030**: A click MUST count for a body within its on-screen size, but at least 10 px.
- **FR-031**: If several bodies are within reach, the one whose centre is nearest MUST win.
- **FR-032**: A panel top right MUST show the name, fun fact and orbit time ("88 days" under one year, "11.9 years" from one year up); the sun shows no orbit time.
- **FR-033**: A click on empty space MUST select nothing and hide the panel.

**Platform**

- **FR-034**: The page MUST be one HTML file with everything inside that works opened from disk, with no network.
- **FR-035**: 1 px MUST be one CSS pixel and drawing MUST stay sharp on dense screens.
- **FR-036**: Mouse and touch MUST both work; one wheel notch is one zoom step.
- **FR-037**: The page MUST run without errors or warnings.

### Key Entities

- **Body**: name, size, orbit radius, orbit time (days), colour, fun fact, start angle; the moon's centre is Earth.
- **Clock**: time (days), paused, speed (years/s).
- **View**: zoom, pan; derived base scale.
- **Selection**: the selected body or none.

**Body Catalogue** (space units, days)

| Body | Size | Orbit | Days | Colour |
|---|---|---|---|---|
| Sun | 28 | – | – | #FFC93C |
| Mercury | 4 | 60 | 88 | #B1ADA7 |
| Venus | 7 | 90 | 225 | #E8C98A |
| Earth | 7 | 125 | 365 | #4F8FE6 |
| Mars | 5 | 160 | 687 | #D1623A |
| Jupiter | 16 | 230 | 4333 | #D9A66C |
| Saturn | 13 | 300 | 10759 | #E3CF8E |
| Uranus | 10 | 365 | 30687 | #8FD3D9 |
| Neptune | 10 | 420 | 60190 | #4468D6 |
| Moon (around Earth) | 2 | 14 | 27 | #CCCCCC |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of functional requirements are verified by a test (automated or a listed manual check).
- **SC-002**: At least 80% of the page's code is exercised by the tests.
- **SC-003**: Zero errors or warnings during a 5 s run and during the whole test suite.
- **SC-004**: At top speed one Earth year passes in 1 s (±1%); at half speed in 4 s (±1%).
- **SC-005**: Every one of the 10 bodies can be selected with one click at the smallest zoom, at 1280×720 and 800×600.
- **SC-006**: At top speed, names never overlap over 20 s of watching.

## Assumptions

- Out of scope: elliptical orbits, true scale, sound, textures, other moons, saving state between visits.
- Glow, shading, ring tilt and fonts are left to the implementer, within "calm like a planetarium".
- Desktop and mobile browsers with canvas support; no specific minimum browser was given.
- Fun facts are written by the implementer and must be true; no source list was requested.
