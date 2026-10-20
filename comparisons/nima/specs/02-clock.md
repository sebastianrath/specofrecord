<!--
nima spec (hand-created, type "spec"). Ticket SS-3. codebaseFiles: ["out/index.html"].
-->
# Clock

## Customer Voice
> No signals (greenfield). Owner: "Simulated time, so years can pass in seconds."

## Problem
Planets move too slowly in real time to see; time must be simulated, steerable and pausable.

## Approaches Considered
### Frame time × speed, capped
- Each frame adds (real seconds since the last frame × speed). After a long gap, like a hidden
  tab, at most 0.1 s counts.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

### Frame time × speed, uncapped
- Effort: low. Risk: a hidden tab makes the planets jump when it comes back.
**Chosen:** no

## Proposed Solution
- **start** — when the app opens, time is 0 days and running.
- **speed** — a slider from 0 to 100, starting at 40. Speed = (slider ÷ 100)² years per second
  (a year is 365 days, see Solar System viewer).
- **pause** — while paused, time does not move.
- Gives **time**: time passed in days, paused or running, and the current speed.
- Owns **state**: time, paused and speed; nobody else changes them.

## Acceptance Criteria
- [ ] Slider at 0 stands still; at 50 a year takes 4 s; at 100 one year passes per second:
      slider(0), step(1) → time unchanged; slider(50), step(4) → time changed by 365 ± 1%;
      slider(100), step(1) → time changed by 365 ± 1%. [test: clock.speed]
- [ ] Paused for 2 s, time does not move: press(Space), step(2) → time unchanged. [test: clock.pause]
- [ ] (manual) The 0.1 s cap after a long gap — needs a real clock; the test hooks freeze
      time. [test: clock.real-time, manual]
- [ ] After a reset the clock is at time 0 and running (paused is false). [test: clock.start]
- [ ] Time is counted in days: slider(100), step(1) → time = 365. [test: clock.time]

## Edge Cases
- **Hidden tab** — a long gap between frames.
  **Desired outcome:** at most 0.1 s of real time counts.

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded.

## Decisions
- Cap at 0.1 s — because a hidden tab must not make the planets jump when it comes back.

## Not Doing
- Uncapped frame time (see Approaches Considered).
