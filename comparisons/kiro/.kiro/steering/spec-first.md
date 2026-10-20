---
inclusion: always
---

# Spec first

The spec in `.kiro/specs/solar-system-viewer/` is the source of truth. For any change asked in
words ("make Jupiter bigger"):

1. Find the acceptance criterion that holds the value (the bodies table is Requirement 1).
2. Change `requirements.md` first. If design.md repeats the value, update it too.
3. Choose **Sync Files** in tasks.md (or ask for the affected tasks to be reopened).
4. Only then edit `out/index.html`, and only the blocks for that requirement.
5. Run `npm test`. Do not weaken or delete a test to make it pass. Do not mark a manual
   verification task done; a person does that.
6. Report which requirements changed, which code changed, and the test results.

If the code is wrong and the requirement is right, that is a bug: open a Bugfix spec
(bugfix.md) instead of changing the requirement.

The hooks in `.kiro/hooks/` enforce part of this; see `spec-first-guard.json`.
