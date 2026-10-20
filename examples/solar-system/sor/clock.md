# Clock
Why: time moves at the speed on the slider, and stops when paused.

## Rules
- **start** — Time starts at day {day: 0}, running.
- **slider** — Speed slider goes {min: 0} to {max: 100}, starts at {start: 40}.
- **speed** — Speed = (slider / 100)² years per second. So 50 = a quarter year/s, 100 = one year/s.
  code: out/index.html#yearsPerSecond
- **pause** — Paused = time doesn't move at all.
- **real-time** — Tab was hidden a while? Count max {cap: 0.1s}, so nothing jumps.
  code: out/index.html#tick

## Tests
- **speed** — slider 0 → stands still. 50 → a year takes 4s. 100 → 1 year per second
  do: slider(0) · remember time · step(1)
  expect: time unchanged
  do: slider(50) · remember time · step(4)
  expect: time changed by {year.days} ± 1%
- **pause** — paused for 2s → nothing changes
  do: press(Space) · remember time · step(2)
  expect: time unchanged
- **real-time** — long break → only 0.1s counts (by hand, test hooks freeze time)
  by hand: needs a real clock; the test hooks freeze time
- **start** — after a reset it's day 0 and running
  expect: time = {start.day}
  expect: paused is false
- **slider** — the slider can't go past 100 or below 0
  do: slider(150)
  expect: speed ≈ 1 ± 0.001
  do: slider(-5)
  expect: speed ≈ 0 ± 0.001
