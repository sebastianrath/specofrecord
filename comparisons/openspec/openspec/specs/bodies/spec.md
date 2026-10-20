# bodies Specification

## Purpose
The fixed facts about the sun, the eight planets and the moon, and where each of them is at any
moment. Depends on clock "Time in days".

## Requirements

### Requirement: Sun
The sun SHALL have size 28 space units and color #FFC93C.

#### Scenario: The sun is the biggest body
- **WHEN** the page is opened
- **THEN** body(sun).r > body(jupiter).r

### Requirement: Planet data
The planets SHALL have these sizes and orbit radii (space units), orbit times (days) and colors.
Saturn SHALL have a ring that is not part of its size.

|Planet|Size|Orbit|Days|Color|
|---|---|---|---|---|
|Mercury|4|60|88|#B1ADA7|
|Venus|7|90|225|#E8C98A|
|Earth|7|125|365|#4F8FE6|
|Mars|5|160|687|#D1623A|
|Jupiter|16|230|4333|#D9A66C|
|Saturn|13|300|10759|#E3CF8E|
|Uranus|10|365|30687|#8FD3D9|
|Neptune|10|420|60190|#4468D6|

#### Scenario: Sun, eight planets and the moon exist
- **WHEN** the page is opened
- **THEN** count(bodies) = 10

### Requirement: Moon
The moon SHALL circle Earth with size 2 space units, orbit radius 14 space units, orbit time
27 days and color #CCCCCC.

#### Scenario: After one moon month the moon is on the same side of Earth
- **WHEN** slider(100), remember offset(body(moon), body(earth)), step(0.073972602739726)
- **THEN** offset(body(moon), body(earth)).x changed by 0 ± 0.5
- **AND** offset(body(moon), body(earth)).y changed by 0 ± 0.5

### Requirement: Fun facts
Every body, the sun included, SHALL have one true fun fact that is exactly 1 sentence long.

#### Scenario: Every body shows a one-sentence fact
- **GIVEN** name is each of sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune, moon
- **WHEN** clickBody(name)
- **THEN** sentences(panel.fact) = 1

### Requirement: Start places
Each planet and the moon SHALL start at a random place on its orbit, picked once per run.

#### Scenario: Start places never change while running
- **WHEN** remember startAngles, step(5)
- **THEN** startAngles unchanged

### Requirement: Positions
The system SHALL give where each body is at any time. Bodies move on clockwise circles:
angle = start place + full turn × (time ÷ own orbit time). The moon SHALL circle Earth's
current position.

#### Scenario: After one year Earth is back where it started
- **WHEN** slider(100), remember body(earth), step(1)
- **THEN** body(earth).x changed by 0 ± 1

### Requirement: Body table
The system SHALL provide every body's name, size, orbit, orbit time, color and fun fact to the
other parts.

#### Scenario: Every body can be found and clicked by name
- **GIVEN** name is each of sun, mercury, venus, earth, mars, jupiter, saturn, uranus, neptune, moon
- **WHEN** clickBody(name)
- **THEN** selected is name
