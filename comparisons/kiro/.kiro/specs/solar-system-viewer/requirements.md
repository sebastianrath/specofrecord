# Requirements Document

## Introduction

The Solar System viewer is one web page that shows the sun, the eight planets and Earth's moon
moving on circular orbits. It should feel like a planetarium: dark sky, soft glow, nothing
jumps or overlaps. Every body can be clicked to show one true fun fact. The page runs offline,
from one HTML file, without errors or warnings.

Out of scope: elliptical orbits, true scale, sound, textures, moons other than Earth's,
saving state.

## Glossary

- **Viewer**: the whole page, `out/index.html`.
- **Body**: the sun, a planet or the moon (10 in total).
- **Space unit**: a length in the solar system (sizes, orbits). Space units grow with zoom.
- **px**: one CSS pixel on screen. Lengths given in px never grow with zoom.
- **Year**: Earth's orbit time, 365 days (Requirement 1, table row Earth).
- **Bars**: the top 56 px and the bottom 56 px of the window, kept free at the start.
- **Clock**: the component that owns simulated time, the paused flag and the speed.
- **Camera**: the component that owns zoom and pan.
- **Scene**: the component that draws everything; it only reads state.
- **Panel**: the info box in the top right corner.
- **Probe**: the test hooks on `window.__probe` (design.md, "Test hooks").

## Requirements

### Requirement 1: Bodies

**User Story:** As a viewer, I want the sun, the planets and the moon at fixed sizes, orbits and
colors, so that the system looks the same every time.

#### Acceptance Criteria

1. THE Viewer SHALL show exactly 10 bodies: the sun, Mercury, Venus, Earth, Mars, Jupiter,
   Saturn, Uranus, Neptune and the moon.
2. THE Viewer SHALL draw the sun with size 28 space units and color #FFC93C.
3. THE Viewer SHALL give each planet the size, orbit radius (space units), orbit time (days)
   and color in this table:

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

4. THE Viewer SHALL draw Saturn with a ring that is not part of its size.
5. THE Viewer SHALL move the moon around Earth's current position with size 2, orbit radius
   14, orbit time 27 days and color #CCCCCC.
6. THE Viewer SHALL draw the sun bigger on screen than any planet.

### Requirement 2: Fun facts

**User Story:** As a curious viewer, I want one fun fact per body, so that I learn something at
a glance.

#### Acceptance Criteria

1. THE Viewer SHALL hold one true fun fact for every body, the sun included.
2. THE Viewer SHALL keep every fun fact to exactly 1 sentence.

### Requirement 3: Motion

**User Story:** As a viewer, I want the planets to start at different places and move steadily,
so that each visit looks a little different but never jumps.

#### Acceptance Criteria

1. WHEN the Viewer opens, THE Viewer SHALL pick a random start angle for each planet and the
   moon, once.
2. WHILE the Viewer runs, THE Viewer SHALL keep the start angles unchanged.
3. THE Viewer SHALL move every planet clockwise on a circle, at angle = start angle +
   full turn x (time / own orbit time), and the moon the same way around Earth's current
   position.
4. WHEN one year of time has passed, THE Viewer SHALL show Earth back at its start position,
   within 1 px.
5. WHEN 27 days of time have passed, THE Viewer SHALL show the moon back on the same side of
   Earth, within 0.5 px in x and in y.

### Requirement 4: Clock and speed

**User Story:** As a viewer, I want years to pass in seconds and to control how fast, so that I
can watch the orbits.

#### Acceptance Criteria

1. WHEN the Viewer opens, THE Clock SHALL start at time 0 days, running.
2. THE Clock SHALL advance at (slider / 100)^2 years per second, where the slider runs from 0
   to 100 and starts at 40.
3. WHILE the slider is at 0, THE Clock SHALL not move.
4. WHILE the slider is at 100, THE Clock SHALL advance one year (365 days) per second.
5. WHILE paused, THE Clock SHALL not move.
6. THE Clock SHALL count time in days and report time, paused and current speed.
7. IF more than 0.1 s of real time passed since the last frame (for example a hidden tab),
   THEN THE Clock SHALL count only 0.1 s.
8. THE Clock SHALL be the only component that changes time, paused and speed.

### Requirement 5: Camera fit and start

**User Story:** As a viewer, I want the whole system to fit on screen at the start, so that I
see every planet without searching.

#### Acceptance Criteria

1. WHEN the Viewer opens, THE Camera SHALL be at zoom 1x with the sun in the middle of the
   screen.
2. WHEN the Viewer opens, THE Camera SHALL fit the outermost orbit plus 28 px of room (for its
   planet and name) between the bars, at most 1 px per space unit.
3. WHEN the window changes size, in width or height, THE Camera SHALL recompute the fit.
4. WHEN the Viewer opens at 1280x720, 800x600 or 640x480, THE Scene SHALL draw nothing inside
   the top 56 px or the bottom 56 px, and the outermost orbit SHALL sit 56 + 28 px from the
   top and the bottom edge, within 0.5 px.

### Requirement 6: Zoom

**User Story:** As a viewer, I want to zoom toward a point, so that I can look closer at a
planet.

#### Acceptance Criteria

1. WHEN the user turns the wheel one notch or pinches one step, THE Camera SHALL multiply the
   zoom by 1.1 (in) or divide it by 1.1 (out).
2. WHEN the Camera zooms, THE Camera SHALL keep the space point under the pointer at the same
   screen position, within 1 px.
3. THE Camera SHALL keep the zoom between 0.3x and 6x.
4. THE Camera SHALL be the only component that changes zoom and pan.

### Requirement 7: Drag

**User Story:** As a viewer, I want to drag the view, so that I can look at another part of the
system.

#### Acceptance Criteria

1. WHEN the user drags by (dx, dy), THE Camera SHALL move the view by (dx, dy), within 0.5 px.
2. IF a press moves less than 4 px before release, THEN THE Camera SHALL treat it as a click
   and not move the view.
3. WHEN the view moves, THE Scene SHALL draw every body at its new screen position.

### Requirement 8: Units

**User Story:** As a viewer, I want lines and text to stay crisp at any zoom, so that the page
stays calm.

#### Acceptance Criteria

1. WHEN the zoom changes, THE Scene SHALL grow or shrink sizes given in space units with it.
2. WHEN the zoom changes, THE Scene SHALL keep lengths given in px (line widths, name size,
   ring gap) unchanged.

### Requirement 9: Sky

#### Acceptance Criteria

1. THE Scene SHALL fill the background with #05060F.
2. THE Scene SHALL draw 300 softly twinkling stars that do not move with zoom or pan.

### Requirement 10: Orbits

#### Acceptance Criteria

1. WHILE orbits are switched on, THE Scene SHALL draw a faint 1 px circle for every planet's
   orbit and the moon's orbit.
2. WHILE orbits are switched off, THE Scene SHALL draw no orbit lines.

### Requirement 11: Body drawing

#### Acceptance Criteria

1. THE Scene SHALL draw the sun with a glow.
2. THE Scene SHALL draw each planet brighter on the side facing the sun.
3. THE Scene SHALL draw Saturn's ring passing behind and in front of Saturn.

### Requirement 12: Selection ring

#### Acceptance Criteria

1. WHILE a body is selected, THE Scene SHALL draw a white ring 2 px wide, 4 px outside the
   body's edge.

### Requirement 13: Names

#### Acceptance Criteria

1. WHILE names are switched on, THE Scene SHALL draw each body's name at 12 px under it.
2. IF two names would overlap, THEN THE Scene SHALL show only the one closer to the sun.
3. WHILE the moon is less than 30 px from Earth on screen, THE Scene SHALL hide the moon's
   name.
4. WHILE names are switched off, THE Scene SHALL draw no names.

### Requirement 14: Time display

#### Acceptance Criteria

1. THE Scene SHALL show the time in the top left as "Year N, day D", reading
   "Year 0, day 0" at the start and counting years (365 days) and days.

### Requirement 15: Comet

#### Acceptance Criteria

1. THE Scene SHALL send a small comet with a faint tail across the solar system every 20 s.
2. THE Scene SHALL place the comet's path in space units, so that it moves and zooms with the
   planets.

### Requirement 16: Selection

**User Story:** As a curious viewer, I want to click a body, so that I can read about it.

#### Acceptance Criteria

1. WHEN the user clicks within a body's on-screen size, or within 10 px of its center if that
   is larger, THE Selection SHALL select that body.
2. IF several bodies are in reach of a click, THEN THE Selection SHALL select the one whose
   center is nearest to the click.
3. WHEN the user clicks empty space, THE Selection SHALL select nothing and hide the panel.
4. WHILE the zoom is at its minimum, THE Selection SHALL still let the user click every body,
   Mercury, Earth and the moon included.

### Requirement 17: Info panel

#### Acceptance Criteria

1. WHEN a body is selected, THE Viewer SHALL show the panel in the top right with the body's
   name, its fun fact and its orbit time.
2. WHERE the orbit time is less than one year, THE Viewer SHALL show it in days ("88 days");
   otherwise in years with one decimal ("11.9 years").
3. WHERE the selected body is the sun, THE Viewer SHALL show no orbit time.
4. WHEN the Viewer opens, THE Viewer SHALL hide the panel.

### Requirement 18: Controls

**User Story:** As a viewer, I want a small control bar, so that I can steer time and the view.

#### Acceptance Criteria

1. THE Viewer SHALL show one small control bar at the left of the bottom bar.
2. THE Viewer SHALL offer a speed slider that sets the speed as in Requirement 4.2.
3. THE Viewer SHALL offer a button that reads "Pause" while running and "Play" while paused.
4. WHEN the user presses Space, THE Viewer SHALL toggle pause like the button does, even right
   after any control was clicked.
5. THE Viewer SHALL offer "Orbits" and "Names" checkboxes, both on at the start.
6. WHEN the user presses Reset, THE Viewer SHALL set time to 0, the view to zoom 1x with the
   sun in the middle, and select nothing, and SHALL keep the speed, play/pause and the
   checkboxes as they are.

### Requirement 19: Delivery

#### Acceptance Criteria

1. THE Viewer SHALL be one HTML file at `out/index.html` with everything inside.
2. WHEN opened straight from disk with no network, THE Viewer SHALL work and make no network
   requests.
3. THE Viewer SHALL treat 1 px as one CSS pixel and stay sharp on screens with more than one
   device pixel per CSS pixel.
4. THE Viewer SHALL accept mouse and touch input; one wheel notch SHALL be one zoom step.
5. WHEN the Viewer runs, THE Viewer SHALL log no errors and no warnings.

### Requirement 20: Testability

**User Story:** As a developer, I want test hooks and coverage targets, so that the spec is
checked independently of the code.

#### Acceptance Criteria

1. THE Viewer SHALL expose the Probe described in design.md, "Test hooks".
2. WHEN a test performs its first action, THE Probe SHALL freeze real time, so that only
   `step(seconds)` moves the clock, by exactly seconds x speed, with no 0.1 s cap, and not
   while paused.
3. THE test suite SHALL validate at least 90% of these acceptance criteria with a test.
4. THE test suite SHALL exercise at least 80% of the code lines.
