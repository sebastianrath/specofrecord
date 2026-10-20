# Implementation Plan

- [ ] 1. Write the failing regression test "pause after click" (use(pause), press(Space),
  expect paused is false) and confirm it fails on the current build
  - _Requirements: 18.4_
- [ ]* 2. Write property test: for any control clicked last, Space toggles pause exactly once
  - **Validates: Requirements 18.4**
- [ ] 3. Handle Space on window with preventDefault; keep the button click path unchanged
  - _Requirements: 18.3, 18.4_
- [ ] 4. Checkpoint - Ensure all tests pass, including the unchanged-behavior tests
