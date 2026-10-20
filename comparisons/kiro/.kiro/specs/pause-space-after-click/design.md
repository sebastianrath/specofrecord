# Design Document

## Root cause (guess, before investigation)
A clicked `<button>` keeps focus; Space then fires the button's own click as well as, or
instead of, the page's key handler.

## Fix
Listen for Space on `window` in the capture phase, call `preventDefault()`, and toggle pause
through `Clock.setPaused`. Blur nothing; leave the button's click handler as it is.

## Testing
Regression test from bugfix.md, plus the unchanged-behavior cases as tests.
