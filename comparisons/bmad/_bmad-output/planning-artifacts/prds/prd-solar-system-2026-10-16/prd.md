---
title: Solar System Viewer
status: final
created: 2026-10-16
updated: 2026-10-16
---

# PRD: Solar System Viewer

## 0. Document Purpose
For the owner and the downstream BMad skills (`bmad-architecture`, `bmad-create-epics-and-stories`,
`bmad-build`). Built on `briefs/brief-solar-system-2026-10-16/brief.md`. Vocabulary is fixed by the
Glossary (§3); features in §4 carry globally numbered FRs with testable consequences; cross-cutting
NFRs are in §5. No UX document exists; visual requirements are in §4.4 and §6.
`[ASSUMPTION: no separate bmad-ux run — the visual rules are few enough to live here.]`

## 1. Vision
A calm, good-looking way to watch the planets move and learn one fact about each. It should feel
like a planetarium: dark sky, soft glow, nothing jumps or overlaps.

## 2. Target User

### 2.1 Jobs To Be Done
- Watch the solar system move without setting anything up (open a file, it runs).
- Learn one true thing about a body by clicking it.
- Speed time up or stop it, and look closer at one part.

### 2.3 Key User Journeys
- **UJ-1. Sebastian opens the file and watches.** He double-clicks `index.html` with networking off;
  the planets are already circling at slider 40, the time reads "Year 0, day 0" and counts up.
- **UJ-2. He clicks Jupiter to learn something.** The panel top right shows "Jupiter", a one-sentence
  fun fact and "11.9 years". Clicking empty space hides it.
- **UJ-3. He zooms in on Earth and drags around.** The wheel zooms around the pointer; Earth stays
  under it; lines and names keep their size. Reset brings back the start view.

## 3. Glossary
- **Body** — the sun, one of the 8 planets, or the moon. Exactly 10 bodies.
- **Space unit** — a length in the solar system (body size, orbit radius, comet path). Grows with zoom.
- **px** — one CSS pixel on screen. Never grows with zoom (line widths, text, gaps, click reach).
- **Day** — the unit of simulated time.
- **Year** — Earth's orbit time: 365 days.
- **Simulated time** — days passed since start or reset. Changed only by the Clock.
- **Speed** — years of simulated time per real second; set by the Slider.
- **Slider** — speed control from 0 to 100.
- **Zoom** — multiplier on the Base scale. **Pan** — screen offset of the view. Changed only by the Camera.
- **Base scale** — px per space unit that makes the system fit between the Bars.
- **Bars** — screen strips kept free at the start: top 56 px, bottom 56 px.
- **Fun fact** — one true sentence about a Body.
- **Panel** — the info box top right for the Selected body.
- **Selected body** — the body last clicked, or none.
- **Time display** — the text top left, e.g. "Year 0, day 0".

## 4. Features

### 4.1 Bodies
**Description:** The fixed facts about each Body and where it is at any Simulated time. Sizes are
for legibility, not true scale.

#### FR-1: Body table
The system has exactly these 10 Bodies (size and orbit in space units, orbit time in days):

| Body | Size | Orbit | Days | Color |
|---|---|---|---|---|
| Sun | 28 | – | – | #FFC93C |
| Mercury | 4 | 60 | 88 | #B1ADA7 |
| Venus | 7 | 90 | 225 | #E8C98A |
| Earth | 7 | 125 | 365 | #4F8FE6 |
| Mars | 5 | 160 | 687 | #D1623A |
| Jupiter | 16 | 230 | 4333 | #D9A66C |
| Saturn | 13 | 300 | 10759 | #E3CF8E |
| Uranus | 10 | 365 | 30687 | #8FD3D9 |
| Neptune | 10 | 420 | 60190 | #4468D6 |
| Moon | 2 | 14 (around Earth) | 27 | #CCCCCC |

Saturn has a ring that is not part of its size.

**Consequences (testable):**
- Exactly 10 bodies exist.
- The sun is drawn bigger than any planet (sun radius > Jupiter radius on screen).
- Every body can be found and selected by its lowercase name.

#### FR-2: Fun facts
Every Body, the sun too, has one true Fun fact, exactly 1 sentence long. Realizes UJ-2.

**Consequences (testable):**
- For each of the 10 bodies, clicking it shows a fact of exactly 1 sentence.

#### FR-3: Start places
Each planet and the moon starts at a random angle, picked once per run.

**Consequences (testable):**
- Start angles are unchanged after 5 s of running.

#### FR-4: Motion
Bodies move on clockwise circles: angle = start angle + full turn × (Simulated time ÷ own orbit
days). The moon circles Earth's current position.

**Consequences (testable):**
- With the Slider at 100, after 1 s Earth's x is back where it started (± 1 px).
- With the Slider at 100, after 27/365 s (0.073972602739726 s) the moon's offset from Earth is
  unchanged (± 0.5 px in x and y).

### 4.2 Clock
**Description:** Simulated time, so years can pass in seconds. The Clock is the only writer of
Simulated time, paused state and Speed.

#### FR-5: Clock start
When the page opens (and after Reset), Simulated time is 0 days and running.

**Consequences (testable):** after reset, time = 0 and not paused.

#### FR-6: Speed
Slider from 0 to 100, starting at 40. Speed = (Slider ÷ 100)² years per second.

**Consequences (testable):**
- Slider 0: time does not move in 1 s.
- Slider 50: Speed is 0.25 (± 0.001); one Year (365 days) takes 4 s (± 1%).
- Slider 100: one Year passes per second (± 1%); after exactly 1 s, time = 365 days.

#### FR-7: Pause
While paused, Simulated time does not move.

**Consequences (testable):** paused (via Space) for 2 s, time is unchanged.

#### FR-8: Real-time stepping
Each frame adds (real seconds since the last frame × Speed). After a long gap (hidden tab) at most
0.1 s counts, so planets never jump when the tab comes back.

**Consequences (testable):** manual check — needs a real clock.

### 4.3 Camera (view)
**Description:** Which part of the system is visible, and how big. The Camera is the only writer of
Zoom and Pan.

#### FR-9: Fit
At the start, the outermost orbit plus 28 px room (for its planet and name) fits between the Bars,
at most 1 px per space unit. Recomputed when the window changes size, in width and height.

**Consequences (testable):** at 1280×720, 800×600 and 640×480: nothing drawn is within 56 px of the
top or bottom edge; the outermost orbit is exactly 56 + 28 = 84 px from the top and bottom edges
(± 0.5 px).

#### FR-10: Start view
Zoom 1×, sun in the middle of the screen.

#### FR-11: Zoom step
One wheel notch or one pinch step zooms by 1.1×; the point under the pointer stays put. Realizes UJ-3.

**Consequences (testable):**
- One step over Earth: Zoom = 1.1, Earth's x unchanged (± 1 px).
- One pinch step from 1×: Zoom = 1.1.

#### FR-12: Zoom limits
Zoom stays between 0.3× and 6×.

**Consequences (testable):** 200 steps in → Zoom = 6; 400 steps out → Zoom = 0.3.

#### FR-13: Drag
Dragging moves the view; a press that moves less than 4 px is a click, not a drag.

**Consequences (testable):**
- Drag by 50 px → Pan.x +50 (± 0.5); Mars moves 30 px on screen for a 30 px drag (± 0.5).
- Drag by 3 px → Pan unchanged.

### 4.4 Scene
**Description:** Everything drawn. The scene only reads state.

#### FR-14: Sky
Blue-black background (#05060F) with 300 softly twinkling stars that ignore Zoom and Pan.

**Consequences (testable):** 300 stars; after 5 zoom steps and a 30 px drag, star positions unchanged.
**Notes:** regression — the first build drew no stars.

#### FR-15: Orbit lines
Faint 1 px circles for the planets and the moon, while switched on.

#### FR-16: Body rendering
A glowing sun; planets brighter on the side facing the sun; Saturn's ring passes behind and in front
of it. **Consequences:** manual check by eye. **Notes:** regression — the first build drew flat circles.

#### FR-17: Selection ring
A white ring, 2 px wide, 4 px outside the Selected body.

**Consequences (testable):** after selecting Jupiter, zooming fully out then fully in leaves orbit
line width, ring width and name size unchanged.

#### FR-18: Names
12 px names under the bodies, while switched on. When two would overlap, the one closer to the sun
stays. The moon's name shows once the moon is 30 px from Earth on screen.

**Consequences (testable):** at Slider 100, checked once a second for 20 s, no two names overlap.

#### FR-19: Time display
Top left: "Year 0, day 0" at the start, counting Years and days.

**Consequences (testable):** after one Year at Slider 100 the text contains "Year 1".

#### FR-20: Comet
A small comet with a faint tail crosses the system every 20 s; its path is in space units, so it
moves and zooms with the planets.

**Consequences (testable):** dragging the view 50 px moves the comet head 50 px (± 1).

**Feature-specific NFRs:** draw order sky, stars, comet, orbits, sun, planets, moon, selection ring,
names, time display.

### 4.5 Controls
**Description:** Let people steer time and the view. One small bar at the left of the bottom Bar.

#### FR-21: Speed slider
Sets Speed per FR-6.

#### FR-22: Pause / Play
A button reading "Pause" or "Play"; the Space key does the same, even right after any control was
clicked.

**Consequences (testable):** click Pause, then press Space → running. (Regression: bug #3 — Space
did nothing after a button had focus.)

#### FR-23: Switches
Checkboxes "Orbits" and "Names", both on at the start.

**Consequences (testable):**
- Both off: no orbit lines and no names drawn.
- Orbits off then on: orbit lines drawn again at 1 px.

#### FR-24: Reset
Time back to 0, view back to the start view (FR-10), nothing selected. Speed, play/pause and the
switches stay as they are.

**Consequences (testable):** after 4 zoom steps, a 50,50 drag and Slider 70, Reset gives Zoom = 1
and the same Speed.

### 4.6 Selection
**Description:** Click a body to learn one thing about it. Realizes UJ-2.

#### FR-25: Reach
A click counts for a body within its on-screen size, but at least 10 px.

**Consequences (testable):** at the smallest Zoom, a click 9 px outside Neptune's center (away from
the sun) selects Neptune; at 12 px it selects nothing.

#### FR-26: Nearest wins
If several bodies are in reach, the one whose center is nearest wins (distance decides, not a
fixed order — at the start Zoom the moon's reach covers Earth).

**Consequences (testable):** at 1280×720 and 800×600, smallest Zoom, after 0.37 s, repeated 10
runs: clicking Mercury, Earth and the moon selects each of them.

#### FR-27: Panel
Top right: name, Fun fact and orbit time ("88 days", or "11.9 years" from one Year up). The sun
shows no orbit time.

**Consequences (testable):** clicking Mars shows the Panel; clicking Jupiter shows text containing
"Jupiter" and "years".

#### FR-28: Miss
A click on empty space selects nothing and hides the Panel.

**Consequences (testable):** select Jupiter, then click at (3, 300) → no Selected body.

#### FR-29: Selected body
A click on a body selects it. **Consequences (testable):** click Venus → Selected body is Venus.

## 5. Cross-Cutting NFRs
- **NFR-1 Calm:** nothing jumps or overlaps (refined by FR-9, FR-14, FR-18).
- **NFR-2 No errors:** the page runs without console errors or warnings (5 s of running → 0 errors).
- **NFR-3 Units:** px never grow with Zoom; space units do. 5 zoom steps in → line widths and
  name size unchanged, Earth's radius larger.
- **NFR-4 Delivery:** one HTML file at `out/index.html`, everything inline, works opened from disk
  with no network (manual check with networking off).
- **NFR-5 Sharpness:** 1 px is one CSS pixel; drawing stays sharp on dense screens (manual check).
- **NFR-6 Input:** mouse and touch; one wheel notch is one zoom step (= 1.1×).
- **NFR-7 Testability:** every testable consequence above runs as an automated test; the page
  exposes test hooks for this (shape fixed in the architecture).
- **NFR-8 Quality:** ≥ 90% of FRs/NFRs proven by an automated test; ≥ 80% line coverage.

## 6. Aesthetic and Tone
Planetarium: dark sky, soft glow. Exact glow, shading, ring tilt and fonts are left to the builder.

## 7. Non-Goals (Explicit)
Elliptical orbits, true scale, sound, textures, other moons, saving state.

## 8. MVP Scope
### 8.1 In Scope
Everything in §4 and §5. The whole PRD is the MVP.
### 8.2 Out of Scope for MVP
See §7.

## 9. Success Metrics
**Primary**
- **SM-1:** Share of FR/NFR consequences with a passing automated test — target ≥ 90%. Validates NFR-8.
- **SM-2:** Line coverage of `out/index.html` in the test run — target ≥ 80%. Validates NFR-8.

**Counter-metrics (do not optimize)**
- **SM-C1:** Number of tests. Tests that cannot fail on a wrong value do not count. Counterbalances SM-1.

## 10. Open Questions
1. Which 10 fun facts? The PRD requires "true, one sentence" but does not fix the wording.

## 11. Assumptions Index
- §0 — no separate UX document.
- §6 — visual details are the builder's choice.
