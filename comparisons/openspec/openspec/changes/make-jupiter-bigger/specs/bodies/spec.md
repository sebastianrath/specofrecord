## MODIFIED Requirements

### Requirement: Planet data
The planets SHALL have these sizes and orbit radii (space units), orbit times (days) and colors.
Saturn SHALL have a ring that is not part of its size.

|Planet|Size|Orbit|Days|Color|
|---|---|---|---|---|
|Mercury|4|60|88|#B1ADA7|
|Venus|7|90|225|#E8C98A|
|Earth|7|125|365|#4F8FE6|
|Mars|5|160|687|#D1623A|
|Jupiter|20|230|4333|#D9A66C|
|Saturn|13|300|10759|#E3CF8E|
|Uranus|10|365|30687|#8FD3D9|
|Neptune|10|420|60190|#4468D6|

#### Scenario: Sun, eight planets and the moon exist
- **WHEN** the page is opened
- **THEN** count(bodies) = 10
