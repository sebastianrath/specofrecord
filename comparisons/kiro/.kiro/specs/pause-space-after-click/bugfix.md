# Bugfix: Space does not toggle pause after a control was clicked

Reference: issue #3. Feature spec: Requirement 18.4 in
#[[file:.kiro/specs/solar-system-viewer/requirements.md]]

## Current behavior
WHEN the user clicks the Pause button and then presses Space, the focused button receives the
key, and the Viewer stays paused (or toggles twice).

## Expected behavior
WHEN the user clicks the Pause button and then presses Space, THE Viewer SHALL toggle pause
exactly once, so that it is running again (`paused is false`).

## Unchanged behavior
- WHEN no control has focus and the user presses Space, THEN the Viewer SHALL CONTINUE TO
  toggle pause once.
- WHEN the user clicks the Pause button, THEN the Viewer SHALL CONTINUE TO toggle pause and
  show "Play" or "Pause".
- WHEN a checkbox or the slider has focus and the user presses Space, THEN the Viewer SHALL
  CONTINUE TO toggle pause and SHALL NOT also toggle the checkbox.

## Regression test
use(pause) · press(Space) → paused is false. **Validates: Requirement 18.4**
