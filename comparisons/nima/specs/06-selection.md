<!--
nima spec (hand-created, type "spec"). Ticket SS-7. codebaseFiles: ["out/index.html"].
-->
# Selection

## Customer Voice
> No signals (greenfield). Owner: "Click a body to learn one thing about it."

## Problem
Bodies are small and close together; a click must reliably pick the body the person meant.

## Approaches Considered
### Nearest center wins
- Distance decides, not a fixed order.
- Effort: low. Reuses: nothing. Risks: none recorded.
**Chosen:** yes

### Fixed priority order
- Risk: at the start zoom the moon's click area covers Earth, so Earth becomes unclickable.
**Chosen:** no

## Proposed Solution
- **reach** — a click counts for a body within its on-screen size, but at least 10 px.
- **nearest** — if several bodies are in reach, the one whose center is nearest wins.
- **panel** — top right: name, fun fact and orbit time ("88 days", or "11.9 years" from one
  year — 365 days — up). The sun shows no orbit time.
- **miss** — a click on empty space selects nothing and hides the panel.
- Gives **selected**: which body is selected, if any. Needs Bodies table, Camera to-screen.

## Acceptance Criteria
- [ ] Click Jupiter: the panel shows "Jupiter" and its orbit time in "years". [test: selection.panel]
- [ ] At the smallest zoom every body can still be clicked: at 1280x720 and 800x600, 10 rounds
      each of zoomSteps(-400), step(0.37), then clickBody(mercury|earth|moon) → selected is
      that body. [test: selection.nearest]
- [ ] A click on empty space selects nothing: clickBody(jupiter), click(3, 300) →
      selected is null. [test: selection.miss]
- [ ] At the smallest zoom a click 9 px outside Neptune still counts, 12 px does not:
      zoomSteps(-400), clickNear(neptune, 9) → "neptune"; clickNear(neptune, 12) → null.
      [test: selection.reach]
- [ ] A click on a body selects it: clickBody(venus) → selected is "venus". [test: selection.selected]

## Edge Cases
- **Moon over Earth** — at the start zoom the moon's reach covers Earth.
  **Desired outcome:** the nearer center wins, Earth stays clickable.

## Effort
**Level:** low
(Not in FACT; required section.)

## Risks & Tech Debt
> None recorded.

## Decisions
- Nearest wins — because a fixed order made Earth unclickable.

## Not Doing
- Fixed priority order (see Approaches Considered).
