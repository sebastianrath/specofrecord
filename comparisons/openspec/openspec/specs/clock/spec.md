# clock Specification

## Purpose
Simulated time, so that years can pass in seconds. The clock is the only part that changes
time, paused state and speed.

## Requirements

### Requirement: Clock start
When the app opens, time SHALL be 0 days and the clock SHALL be running.

#### Scenario: After a reset the clock is at its start
- **WHEN** the standard setup has run (it includes use(reset))
- **THEN** time = 0
- **AND** paused is false

### Requirement: Speed
Speed SHALL be set by a slider from 0 to 100 that starts at 40.
Speed = (slider ÷ 100)² years per second.

#### Scenario: Slider at 0 stands still
- **WHEN** slider(0), remember time, step(1)
- **THEN** time unchanged

#### Scenario: Slider at 50 takes 4 seconds per year
- **WHEN** slider(50), remember time, step(4)
- **THEN** time changed by 365 ± 1%

#### Scenario: Slider at 100 passes one year per second
- **WHEN** slider(100), remember time, step(1)
- **THEN** time changed by 365 ± 1%

### Requirement: Pause
While paused, time MUST NOT move.

#### Scenario: Paused for 2 seconds
- **WHEN** press(Space), remember time, step(2)
- **THEN** time unchanged

### Requirement: Real-time advance
Each frame SHALL add (real seconds since the last frame × speed). After a long gap, such as a
hidden tab, at most 0.1 s SHALL count, so the planets do not jump when the tab comes back.

#### Scenario: Cap after a long gap (manual)
- **GIVEN** a real clock (the test probes freeze time, so this cannot be automated)
- **WHEN** the tab is hidden for several seconds and shown again
- **THEN** the planets move by at most 0.1 s × speed in the first frame

### Requirement: Time in days
The clock SHALL give the time passed in days, whether it is paused or running, and the
current speed. Only the clock SHALL change time, paused and speed.

#### Scenario: One year at top speed is a year of days
- **WHEN** slider(100), step(1)
- **THEN** time = 365
