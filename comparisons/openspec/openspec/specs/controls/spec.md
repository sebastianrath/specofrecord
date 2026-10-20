# controls Specification

## Purpose
Let people steer time and the view: a speed slider, pause and play, orbit and name switches,
and reset. Uses clock "Time in days", camera "Fit to bars" and selection "Selected".

## Requirements

### Requirement: Speed slider
A slider SHALL set the speed as clock "Speed" defines. All controls SHALL sit in one small bar
at the left of the bottom bar.

#### Scenario: Halfway is a quarter year per second
- **WHEN** slider(50)
- **THEN** speed = 0.25 ± 0.001

### Requirement: Pause button
A button SHALL read "Pause" or "Play" and toggle pause; the Space key SHALL do the same, even
right after any control was clicked.

#### Scenario: Click Pause, then press Space
<!-- regression: issue #3 -->
- **WHEN** use(pause), press(Space)
- **THEN** paused is false

### Requirement: Checkboxes
There SHALL be two checkboxes, "Orbits" and "Names", both on at the start.

#### Scenario: Both off hides orbit lines and names
- **WHEN** use(orbits), use(names), step(0)
- **THEN** strokes.orbitLines is null
- **AND** count(labels) = 0

### Requirement: Reset
Reset SHALL set time back to 0, the view back to camera "Start view", and select nothing.
Speed, play/pause and the checkboxes SHALL stay as they are.

#### Scenario: Reset restores the view and keeps the speed
- **WHEN** zoomSteps(4), drag(50, 50), slider(70), remember speed, use(reset)
- **THEN** zoom = 1
- **AND** speed unchanged

### Requirement: Switches
The controls SHALL give whether orbits are on or off and whether names are on or off.

#### Scenario: The orbit switch turns orbit lines off and on again
- **WHEN** use(orbits)
- **THEN** strokes.orbitLines is null
- **AND WHEN** use(orbits)
- **THEN** strokes.orbitLines = 1
