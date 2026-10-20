# solar-system-viewer Specification

## Purpose
Cross-cutting requirements for the Solar System viewer: a calm, planetarium-like page to watch
the planets move and learn one true fun fact about each body.

## Requirements

### Requirement: Calm presentation
The viewer SHALL feel like a planetarium: dark sky, soft glow, and nothing jumps or overlaps.
This is refined by scene "Sky", scene "Names" and camera "Fit to bars".

#### Scenario: Calm is covered by its refinements
<!-- guess: FACT has no own test for "calm"; it is refined by other facts. OpenSpec needs a
     scenario per requirement, so this one points at the refining scenarios. -->
- **WHEN** the scenarios of scene "Sky", scene "Names" and camera "Fit to bars" are run
- **THEN** all of them pass

### Requirement: Learn about every body
Every body SHALL be clickable and SHALL then show one true fun fact (see selection "Info panel").

#### Scenario: Clicking a planet shows its panel
- **WHEN** clickBody(mars)
- **THEN** panel.shown is true

### Requirement: No errors
The page SHALL run without errors or warnings.

#### Scenario: Running produces no errors
- **WHEN** step(5)
- **THEN** count(errors) = 0

### Requirement: Year length
One year SHALL be Earth's orbit time, 365 days (the "Days" value of Earth in bodies "Planet
data"). Every place that says "year" uses this value.

#### Scenario: One year at top speed is 365 days
<!-- guess: FACT has no test for this fact; this reuses web-delivery "Deterministic test clock". -->
- **WHEN** slider(100), remember time, step(1)
- **THEN** time changed by 365 ± 0

### Requirement: Units
Sizes in px (screen pixels) SHALL never grow with zoom; sizes in space units SHALL grow with zoom.

#### Scenario: Zooming grows bodies but not lines and names
- **WHEN** remember strokes, remember body(earth), zoomSteps(5)
- **THEN** strokes unchanged
- **AND** body(earth).r changed by > 0

### Requirement: Test quality
At least 90% of the requirements SHALL be proven by an automated scenario and at least 80% of
the code lines SHALL be exercised by the scenarios.

#### Scenario: Coverage thresholds
- **WHEN** the full scenario suite runs with Chrome coverage
- **THEN** requirement coverage ≥ 90%
- **AND** line coverage ≥ 80%

### Requirement: Viewer page
The viewer SHALL be one page that runs offline, delivered as web-delivery describes, and SHALL
expose the test probes from web-delivery that every scenario uses.

#### Scenario: The page opens and draws
- **WHEN** the page is opened
- **THEN** body(sun).r > 0
- **AND** count(errors) = 0
