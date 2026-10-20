# selection Specification

## Purpose
Click a body to learn one thing about it. Uses bodies "Body table" and camera "To-screen
mapping".

## Requirements

### Requirement: Click reach
A click SHALL count for a body when it is within the body's on-screen size, but at least 10 px.

#### Scenario: Just outside a tiny body counts, further out does not
- **WHEN** zoomSteps(-400), clickNear(neptune, 9)
- **THEN** selected is "neptune"
- **AND WHEN** clickNear(neptune, 12)
- **THEN** selected is null

### Requirement: Nearest body wins
If several bodies are in reach, the body whose center is nearest to the click SHALL win;
distance decides, not a fixed order. Reason: at the start zoom the moon's click area covers
Earth, and a fixed order made Earth unclickable.

#### Scenario: At the smallest zoom every body can still be clicked
- **GIVEN** the window size is each of 1280x720, 800x600, repeated for 10 rounds
- **WHEN** zoomSteps(-400), step(0.37), clickBody(mercury)
- **THEN** selected is "mercury"
- **AND WHEN** clickBody(earth)
- **THEN** selected is "earth"
- **AND WHEN** clickBody(moon)
- **THEN** selected is "moon"

### Requirement: Info panel
The top right SHALL show a panel with the body's name, its fun fact and its orbit time, as days
("88 days") below one year (365 days) and as years ("11.9 years") from one year up. The sun
SHALL show no orbit time.

#### Scenario: Jupiter's panel shows its name and years
- **WHEN** clickBody(jupiter)
- **THEN** panel.text contains "Jupiter"
- **AND** panel.text contains "years"

### Requirement: Miss
A click on empty space SHALL select nothing and hide the panel.

#### Scenario: A click on empty space selects nothing
- **WHEN** clickBody(jupiter), click(3, 300)
- **THEN** selected is null

### Requirement: Selected
The system SHALL give which body is selected, if any.

#### Scenario: A click on a body selects it
- **WHEN** clickBody(venus)
- **THEN** selected is "venus"
