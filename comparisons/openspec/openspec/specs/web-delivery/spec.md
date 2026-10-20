# web-delivery Specification

## Purpose
Where the viewer runs, how it is delivered as one file, and the test probes that every
automated scenario in the other specs uses.

## Requirements

### Requirement: Single-file delivery
The viewer SHALL be one HTML file at out/index.html with everything inside; it SHALL work
opened straight from disk, with no network.

#### Scenario: Opens from disk offline (manual)
- **WHEN** the file is opened from disk with networking off
- **THEN** the page works and makes no network requests

### Requirement: Pixels
1 px SHALL be one CSS pixel, and drawing SHALL stay sharp on dense screens.

#### Scenario: Sharp on a dense screen (manual)
- **GIVEN** a screen with more than one device pixel per CSS pixel
- **WHEN** a person looks at the page
- **THEN** lines, bodies and names are sharp

### Requirement: Input
The page SHALL accept mouse and touch; one wheel notch SHALL be one zoom step.

#### Scenario: One wheel notch is one zoom step
- **WHEN** zoomSteps(1)
- **THEN** zoom = 1.1

### Requirement: Probe interface
The page SHALL expose window.__probe; a member that is a function is called with the test's
arguments. Readings: time, paused, speed, zoom, pan, selected, bodies, body(name), startAngles,
labels, strokes, layout, hud, panel, errors, comet, stars. Actions: step(seconds), slider(v),
setPaused(on), click(x, y), clickBody(name), clickNear(name, px), zoomSteps(n), zoomAt(name, n),
pinch(n), drag(dx, dy), press(key), use(control), resize(w, h), showComet().

#### Scenario: Every listed member exists
<!-- guess: FACT has no own test for the member list; every other scenario uses it. -->
- **WHEN** the page is opened
- **THEN** window.__probe has every reading and action listed above

### Requirement: Deterministic test clock
The first probe action SHALL freeze real time; after that only step(seconds) SHALL move the
clock, by exactly seconds × speed, with no cap, and not while paused. Before each scenario the
harness SHALL run resize(1280, 720), use(reset), slider(40), setPaused(false).

#### Scenario: step moves the clock exactly
- **WHEN** slider(100), remember time, step(1)
- **THEN** time changed by 365 ± 0

### Requirement: Probe reading shapes
Names SHALL be lowercase. body(name) gives {x, y, r}; labels gives boxes; strokes gives
{orbitLines, selectionRing, nameText}; layout gives {gapTop, gapBottom} between the nearest
orbit, body or name and the edges, and {orbitTop, orbitBottom} between the outermost orbit and
the edges; comet gives {x, y} of its head or null; stars gives {x, y} of every star; panel
gives {shown, text, fact}; hud gives the time text.

#### Scenario: Readings have the promised shapes
<!-- FACT's "meanings" fact is split in two here because OpenSpec warns on requirement text
     over 500 characters. -->
- **WHEN** the page is opened
- **THEN** body(earth).r > 0
- **AND** layout.gapTop > 0
- **AND** count(labels) > 0
- **AND** panel.shown is false

### Requirement: Probe action meanings
clickNear(name, px) SHALL click px further from the sun than the body's center; pinch(n) SHALL
move two touch points around the screen center apart by n zoom steps (negative: together);
clickBody SHALL send a real click; use SHALL take pause, reset, orbits or names.

#### Scenario: clickNear and pinch behave as described
<!-- guess: reuses checks from selection "Click reach" and camera "Zoom step". -->
- **WHEN** zoomSteps(-400), clickNear(neptune, 12)
- **THEN** selected is null
- **AND WHEN** use(reset), pinch(1)
- **THEN** zoom = 1.1
