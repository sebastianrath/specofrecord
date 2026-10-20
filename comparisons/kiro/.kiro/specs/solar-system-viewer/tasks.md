# Implementation Plan

<!-- Guess: checkbox syntax, "_Requirements: x.y_" lines, "- [ ]*" for optional test tasks and
"Checkpoint" tasks follow specs Kiro generates; the docs describe tasks but not their syntax. -->

- [ ] 1. Set up the page and the test harness
  - Create `out/index.html` with inline CSS/JS, one canvas scaled by devicePixelRatio, and the
    notes comment at the top
  - Set up headless Chrome tests and coverage (`npm test`, `npm run coverage`)
  - Add `window.__probe` with frozen time and `step(seconds)` as in design.md "Test hooks"
  - _Requirements: 19.1, 19.3, 19.5, 20.1, 20.2_

- [ ] 2. Bodies
  - [ ] 2.1 Add the table of 10 bodies with sizes, orbits, days, colors and one-sentence facts
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.1, 2.2_
  - [ ] 2.2 Add random start angles, picked once, and clockwise circular motion; moon around
    Earth
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ]* 2.3 Write tests planets, sun, positions, moon, start-places
    - **Property 1: Start angles are stable**
    - **Validates: Requirements 1.1, 1.6, 3.2, 3.4, 3.5**

- [ ] 3. Clock
  - [ ] 3.1 Time in days from 0, running; speed (slider/100)^2 years/s; pause; 0.1 s cap
    - _Requirements: 4.1, 4.2, 4.5, 4.6, 4.7, 4.8_
  - [ ]* 3.2 Write tests speed, pause, clock start, time, probes
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 20.2**

- [ ] 4. Camera
  - [ ] 4.1 Base scale that fits Neptune's orbit + 28 px between the 56 px bars, max 1 px per
    unit, recomputed on resize
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ] 4.2 Zoom by 1.1 per wheel notch or pinch step around the pointer, clamped to 0.3-6
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 19.4_
  - [ ] 4.3 Drag to pan; presses under 4 px are clicks; `toScreen` / `toSpace`
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ]* 4.4 Write tests fit (3 sizes), zoom-step, pinch, limits, drag, to-screen, input
    - **Property 2: Zoom stays in range**
    - **Property 3: Zoom keeps the anchor**
    - **Validates: Requirements 5.2, 5.4, 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 19.4**

- [ ] 5. Checkpoint - Ensure all tests pass, ask the user if questions arise

- [ ] 6. Scene
  - [ ] 6.1 Sky #05060F and 300 twinkling stars in screen space
    - _Requirements: 9.1, 9.2_
  - [ ] 6.2 Orbits (1 px), glowing sun, sun-side shading, Saturn's ring behind and in front
    - _Requirements: 1.4, 10.1, 10.2, 11.1, 11.2, 11.3_
  - [ ] 6.3 Selection ring (2 px, 4 px gap), names (12 px, closer-to-sun wins, moon name from
    30 px), time display "Year N, day D"
    - _Requirements: 12.1, 13.1, 13.2, 13.3, 13.4, 14.1_
  - [ ] 6.4 Comet every 20 s on a path in space units
    - _Requirements: 15.1, 15.2_
  - [ ]* 6.5 Write tests units, sky, names (20 rounds), selected, hud, comet, checkboxes,
    switches
    - **Property 4: px lengths ignore zoom**
    - **Property 5: Stars ignore the view**
    - **Property 7: Names never overlap**
    - **Validates: Requirements 8.1, 8.2, 9.2, 10.1, 10.2, 12.1, 13.2, 13.4, 14.1, 15.2**

- [ ] 7. Selection and panel
  - [ ] 7.1 Hit test with 10 px minimum reach, nearest center wins, miss clears
    - _Requirements: 16.1, 16.2, 16.3, 16.4_
  - [ ] 7.2 Panel top right: name, fact, orbit time in days or years, none for the sun
    - _Requirements: 17.1, 17.2, 17.3, 17.4_
  - [ ]* 7.3 Write tests learn, fun-facts, table, panel, nearest, miss, reach, selected
    - **Property 6: Every body is clickable**
    - **Validates: Requirements 2.2, 16.1, 16.2, 16.3, 16.4, 17.1, 17.2, 17.4**

- [ ] 8. Controls
  - [ ] 8.1 Bar at the left of the bottom bar: slider (0-100, start 40), Pause/Play, Space on
    window, Orbits and Names (on), Reset
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_
  - [ ]* 8.2 Write tests slider, reset, pause after click
    - **Validates: Requirements 18.2, 18.4, 18.6**

- [ ] 9. Quality gate
  - [ ] 9.1 Run coverage; at least 80% of lines exercised
    - _Requirements: 20.4_
  - [ ] 9.2 Check that at least 90% of acceptance criteria appear in a test's Validates line
    - _Requirements: 20.3_
  - [ ] 9.3 Write tests no-errors (step 5), viewer, meanings
    - _Requirements: 19.5, 20.1_

- [ ] 10. Manual verification (a person ticks these)
  - [ ] 10.1 Real-time cap: hide the tab for a minute, planets must not jump
    - _Requirements: 4.7_
  - [ ] 10.2 Look: sun glows, planets lit from the sun's side, Saturn's ring crosses it
    - _Requirements: 11.1, 11.2, 11.3_
  - [ ] 10.3 Open from disk with networking off; no requests
    - _Requirements: 19.2_
  - [ ] 10.4 Sharp on a dense screen
    - _Requirements: 19.3_

- [ ] 11. Final checkpoint - Ensure all tests pass, ask the user if questions arise
