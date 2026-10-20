# PRD: Solar System viewer

SpecLock has no spec format of its own. A team writes a plain PRD like this one, and SpecLock
reads it with the Spec Compiler (MCP tool `speclock_compile_spec`). The compiler turns it into
text locks, typed locks, decisions and notes in `.speclock/brain.json`. This file carries over
every fact, number and test from `examples/solar-system/fact/`.

Goal: a calm, good-looking way to watch the planets move and learn one fact about each.
Owner: sebastian

## Product
- Calm, like a planetarium: dark sky, soft glow, nothing jumps or overlaps.
- Every body can be clicked to show one true fun fact, one sentence long.
- The page runs without errors or warnings.
- One year is Earth's orbit time (365 days).
- px are screen pixels and never grow with zoom. Space units are sizes in the solar system and
  grow with zoom.
- Quality: at least 90% of requirements proven by a test, and at least 80% line coverage.
- Out of scope: elliptical orbits, true scale, sound, textures, other moons, saving state.

## Architecture
- Six parts: bodies, clock, camera, scene, controls, selection.
- Only the clock changes time. Only the camera changes zoom and pan. The scene only reads.
  (Why: one owner per piece of state lets agents work on parts in parallel.)
- Delivery: one HTML file at `out/index.html` with everything inside. It works opened from
  disk, with no network.
- Test hooks: `window.__probe` (read: time, paused, speed, zoom, pan, selected, bodies,
  body(name), startAngles, labels, strokes, layout, hud, panel, errors, comet, stars;
  do: step, slider, setPaused, click, clickBody, clickNear, zoomSteps, zoomAt, pinch, drag,
  press, use, resize, showComet). The first `do` freezes real time. After that only
  `step(seconds)` moves the clock, by exactly seconds × speed, with no cap and not while paused.
  Before each test: resize(1280, 720), use(reset), slider(40), setPaused(false).
- Tests run in headless Chrome; coverage comes from Chrome's built-in coverage.

## Bodies
- Sun: size 28, color #FFC93C.
- Planets (size, orbit radius in space units, orbit time in days, color):
  Mercury 4/60/88/#B1ADA7, Venus 7/90/225/#E8C98A, Earth 7/125/365/#4F8FE6,
  Mars 5/160/687/#D1623A, Jupiter 16/230/4333/#D9A66C, Saturn 13/300/10759/#E3CF8E,
  Uranus 10/365/30687/#8FD3D9, Neptune 10/420/60190/#4468D6.
  Saturn has a ring that is not part of its size.
- Moon: circles Earth, size 2, orbit 14, 27 days, color #CCCCCC.
- Every planet and the moon starts at a random place, picked once per run.
- Motion: clockwise circles. angle = start + full turn × (time ÷ own orbit time). The moon
  circles Earth's current position.

## Clock
- Starts at 0 days and running.
- Speed slider from 0 to 100, starting at 40. Speed = (slider ÷ 100)² years per second.
- While paused, time does not move.
- Each frame adds real seconds × speed; after a long gap (hidden tab) at most 0.1 s counts.

## Camera
- Top 56 px and bottom 56 px bars stay free at the start.
- At the start the outermost orbit, plus 28 px room, fits between the bars, at most 1 px per
  space unit. A base scale is recomputed on window resize, in width and height.
- Start: zoom 1x, sun in the middle of the screen.
- One wheel notch or pinch step zooms by 1.1x; the point under the pointer stays put.
- Zoom stays between 0.3x and 6x.
- Dragging moves the view; a press that moves less than 4 px is a click.

## Scene
- Sky #05060F, 300 softly twinkling stars that ignore zoom and pan.
- Orbits: faint 1 px circles for planets and moon, while switched on.
- A glowing sun; planets brighter on the side facing the sun; Saturn's ring passes behind and
  in front of it. Glow, shading, ring tilt and fonts are the developer's choice.
- Selected body: white ring, 2 px wide, 4 px outside the body.
- Names: 12 px, under the bodies, while switched on. When two overlap, the one closer to the
  sun stays. The moon's name shows once it is 30 px from Earth.
- Time display top left: "Year 0, day 0" at start, counting years and days.
- A small comet with a faint tail crosses every 20 s; its path is in space units.
- Draw order: sky, stars, comet, orbits, sun, planets, moon, selected ring, names, time.

## Controls
- Slider sets the speed. A Pause/Play button; Space does the same, even right after any
  control was clicked. Checkboxes "Orbits" and "Names", both on at start.
- Reset: time back to 0, view back to start, nothing selected. Speed, play/pause and the
  checkboxes stay.
- One small bar at the left of the bottom bar.

## Selection
- A click counts for a body within its on-screen size, but at least 10 px.
- If several bodies are in reach, the nearest center wins (not a fixed order: at start zoom the
  moon's click area covers Earth).
- Panel top right: name, fun fact, orbit time ("88 days", or "11.9 years" from one year up).
  The sun shows no orbit time.
- A click on empty space selects nothing and hides the panel.

## Acceptance tests
Each is a scenario against `window.__probe`. Numbers as above.
1. Clicking Mars shows the panel. 2. step(5) gives 0 errors. 3. Fact coverage ≥ 90%, line
coverage ≥ 80%. 4. zoomSteps(5): strokes unchanged, Earth's radius grows. 5. Sun radius > 0
and 0 errors on open. 6. 10 bodies exist. 7. Start angles unchanged after step(5).
8. Slider 100, step(1): Earth x back within ±1. 9. Sun drawn bigger than Jupiter.
10. Slider 100, step(0.073972602739726): moon offset from Earth back within ±0.5 in x and y.
11. Each of the 10 bodies: clicking shows a 1-sentence fact. 12. Each of the 10 bodies can be
clicked by name and becomes selected. 13. At 1280x720, 800x600, 640x480: gaps ≥ 56 px top and
bottom; outermost orbit at 56 + 28 px ± 0.5 from each bar. 14. zoomAt(earth, 1): zoom 1.1,
Earth x within ±1; then zoomAt(earth, -1), pinch(1): zoom 1.1. 15. zoomSteps(200) → 6;
zoomSteps(-400) → 0.3. 16. drag(50, 0) moves pan by 50 ± 0.5; drag(3, 0) leaves pan unchanged.
17. drag(30, 0) moves Mars by 30 ± 0.5. 18. Slider 0: time unchanged over 1 s; slider 50: a
year in 4 s ± 1%; slider 100: a year in 1 s ± 1%. 19. Space, step(2): time unchanged.
20. Real-time cap of 0.1 s: manual. 21. After reset: time 0, not paused. 22. Slider 100,
step(1): time = 365. 23. Orbits and Names off: no orbit lines, 0 labels. 24. Click Pause then
Space: running (regression for bug #3). 25. zoomSteps(4), drag, slider(70), reset: zoom 1, speed
kept. 26. slider(50): speed 0.25 ± 0.001. 27. Orbits off → no lines; on → 1 px.
28. 300 stars, unchanged by zoom and drag (regression: first build drew no stars).
29. Lit sun/planets/Saturn ring: manual, by eye (regression: first build drew flat circles).
30. 20 rounds at slider 100: 0 label overlaps. 31. Jupiter selected, zoom min→max: strokes
unchanged. 32. Slider 100, step(1): HUD contains "Year 1". 33. Comet moves 50 ± 1 with
drag(50, 0). 34. Jupiter panel contains "Jupiter" and "years". 35. At 1280x720 and 800x600,
10 rounds each, min zoom, step(0.37): Mercury, Earth and Moon each clickable.
36. Click Jupiter, click (3, 300): nothing selected. 37. Min zoom: click 9 px outside Neptune
selects it, 12 px does not. 38. Click Venus: selected. 39. No network requests from disk:
manual. 40. One wheel notch: zoom 1.1. 41. Slider 100, step(1): time changes by exactly 365.
42. Probe shapes: Earth r > 0, gapTop > 0, labels > 0, panel hidden. 43. Sharp on dense
screens: manual.
