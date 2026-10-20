# scene Specification

## Purpose
Draw everything, calm and clear, like a planetarium. The scene only reads state; it uses
bodies "Positions", camera "To-screen mapping", controls "Switches" and selection "Selected".

## Requirements

### Requirement: Sky
The sky SHALL be blue-black (#05060F) with 300 softly twinkling stars that ignore zoom and pan.

#### Scenario: All stars are there and stay put
<!-- regression: the first build drew no stars -->
- **WHEN** remember stars, zoomSteps(5), drag(30, 0)
- **THEN** count(stars) = 300
- **AND** stars unchanged

### Requirement: Orbit lines
Planets and the moon SHALL have faint 1 px orbit circles, drawn while orbits are switched on.

#### Scenario: Orbit lines are 1 px wide
<!-- guess: FACT checks this only inside controls "Switches"; repeated here. -->
- **WHEN** the page is opened with orbits switched on
- **THEN** strokes.orbitLines = 1

### Requirement: Body rendering
The sun SHALL glow; planets SHALL be brighter on the side facing the sun; Saturn's ring SHALL
pass behind and in front of it. Draw order: sky, stars, comet, orbits, sun, planets, moon,
selected ring, names, time. Glow, shading, ring tilt and fonts are the implementer's choice.

#### Scenario: Lit bodies (manual)
<!-- regression: the first build drew flat circles -->
- **WHEN** a person looks at the page
- **THEN** the sun glows, planets are lit from the sun's side and Saturn's ring crosses Saturn

### Requirement: Selection ring
The selected body SHALL have a white ring, 2 px wide, 4 px outside the body.

#### Scenario: Lines and names keep their size at both zoom limits
- **WHEN** clickBody(jupiter), zoomAt(jupiter, -400), remember strokes, zoomAt(jupiter, 400)
- **THEN** strokes unchanged

### Requirement: Names
Bodies SHALL have 12 px names under them while names are switched on. When two names would
overlap, the one closer to the sun SHALL stay. The moon's name SHALL show once the moon is
30 px from Earth on screen.

#### Scenario: Names never overlap at top speed
- **GIVEN** 20 rounds, checked once per simulated second
- **WHEN** slider(100), step(1)
- **THEN** overlaps(labels) = 0

### Requirement: Time display
The top left SHALL show "Year 0, day 0" at the start and count years (365 days) and days.

#### Scenario: After one year the display reads year 1
- **WHEN** slider(100), step(1)
- **THEN** hud contains "Year 1"

### Requirement: Comet
A small comet with a faint tail SHALL cross the solar system every 20 s. Its path SHALL be in
space units, so it moves and zooms with the planets.

#### Scenario: Dragging moves the comet with the view
- **WHEN** showComet(), remember comet, drag(50, 0)
- **THEN** comet.x changed by 50 ± 1
