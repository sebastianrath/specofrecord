# camera Specification

## Purpose
Decide which part of the solar system is visible and how big. The camera is the only part
that changes zoom and pan. Depends on bodies "Planet data" for the outermost orbit.

## Requirements

### Requirement: Fit to bars
The top 56 px and bottom 56 px (the bars) SHALL stay free at the start. At the start the
outermost orbit, plus 28 px room for its planet and name, SHALL fit between the bars, at most
1 px per space unit. A base scale does this fit and zoom multiplies it; the base scale SHALL be
recomputed when the window changes size, in width and height.

#### Scenario: Nothing touches a bar at every test size
- **GIVEN** the window size is each of 1280x720, 800x600, 640x480
- **WHEN** the page is laid out
- **THEN** layout.gapTop ≥ 56
- **AND** layout.gapBottom ≥ 56
- **AND** layout.orbitTop = 84 ± 0.5
- **AND** layout.orbitBottom = 84 ± 0.5

### Requirement: Start view
At the start the zoom SHALL be 1x with the sun in the middle of the screen.

#### Scenario: Reset returns to the start zoom
<!-- guess: FACT tests this only through controls "Reset"; repeated here so the requirement
     has a scenario. -->
- **WHEN** zoomSteps(4), use(reset)
- **THEN** zoom = 1

### Requirement: Zoom step
One wheel notch or one pinch step SHALL zoom by a factor of 1.1; the point under the pointer
SHALL stay put.

#### Scenario: One step over Earth keeps Earth under the pointer
- **WHEN** remember body(earth), zoomAt(earth, 1)
- **THEN** zoom = 1.1
- **AND** body(earth).x changed by 0 ± 1

#### Scenario: One pinch step zooms by one step
- **WHEN** zoomAt(earth, 1), zoomAt(earth, -1), pinch(1)
- **THEN** zoom = 1.1

### Requirement: Zoom limits
Zoom SHALL stay between 0.3x and 6x.

#### Scenario: Zooming forever stays inside the limits
- **WHEN** zoomSteps(200)
- **THEN** zoom = 6
- **AND WHEN** zoomSteps(-400)
- **THEN** zoom = 0.3

### Requirement: Drag
Dragging SHALL move the view; a press that moves less than 4 px SHALL count as a click.

#### Scenario: Dragging moves the view
- **WHEN** remember pan, drag(50, 0)
- **THEN** pan.x changed by 50 ± 0.5

#### Scenario: A press that barely moves does not drag
- **WHEN** remember pan, drag(3, 0)
- **THEN** pan unchanged

### Requirement: To-screen mapping
The camera SHALL turn a space point into a screen point and back, following zoom and pan.

#### Scenario: A body's screen place follows the view
- **WHEN** remember body(mars), drag(30, 0)
- **THEN** body(mars).x changed by 30 ± 0.5
