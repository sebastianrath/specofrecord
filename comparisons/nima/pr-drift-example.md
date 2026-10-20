# Example: a PR that changes the zoom step without changing the spec

Legend: **[doc]** documented at docs.getnima.io · **[guess]** our reconstruction.

## The PR

- Branch `SS-4-snappier-zoom`, title "SS-4: snappier zoom". **[guess: key prefix]**
- Diff, one line in `out/index.html`:

  ```diff
  -const ZOOM = { factor: 1.1, min: 0.3, max: 6 };
  +const ZOOM = { factor: 1.25, min: 0.3, max: 6 };
  ```
- No spec edited (specs live in nima, not in the repo, so a PR cannot change one anyway).

## What nima does

1. **Link the PR to a ticket.** The branch rule wants the key after a slash
   (`feature/SS-4-…`), so it misses here; the title rule hits. Card SS-4 = spec
   "Camera". The first linked PR moves the spec `approved → in_progress`. **[doc]**
2. **Pick the spec to check.** Card link first, so `matchStrategy: "card_link"`, spec Camera.
   The Web target spec also says "1.1x" but is not checked: only the card's spec is.
   **[doc: card link first; guess: that only one spec is checked]**
3. **Run the drift check** on open, and again on every push, reopen and merge. **[doc]**
   How the verdict is made is not documented. Comparing a code diff to prose sections and
   returning `not_addressed` for untouched sections is, in practice, a model judgement.
   **[guess]**
4. **Post or update a PR comment** titled "PRD Drift Check" with a verdict per section. **[doc]**
5. **Notify the spec owner's watch**, since a section is `drifted` on an open PR. **[doc]**

## The comment (layout guessed; title, per-section table and verdict names documented)

> ### PRD Drift Check — Camera
>
> | Section | Verdict | Note |
> |---|---|---|
> | Customer Voice | not_addressed | |
> | Problem | not_addressed | |
> | Approaches Considered | aligned | still base scale × zoom |
> | Proposed Solution | **drifted** | spec: one notch zooms by 1.1x; PR: 1.25x |
> | Acceptance Criteria | **drifted** | "zoomAt(earth, 1) → zoom = 1.1" no longer holds |
> | Edge Cases | not_addressed | |
> | Effort | not_addressed | |
> | Risks & Tech Debt | not_addressed | |
> | Not Doing | not_addressed | |

## The record behind it (`get_spec_delivery` → `pullRequests[].drift`)

```json
{
  "pullRequestId": "…",
  "status": "completed",
  "hasDrift": true,
  "matchStrategy": "card_link",
  "commitSha": "…",
  "checkedAt": "2026-10-16T09:12:00Z",
  "sections": [
    { "section": "Proposed Solution", "verdict": "drifted" },
    { "section": "Acceptance Criteria", "verdict": "drifted" },
    { "section": "Problem", "verdict": "not_addressed" }
  ]
}
```
Field names and verdict values **[doc]**; the shape of each `sections[]` item **[guess]**.

## What happens next

- **Nothing blocks the merge.** The docs describe a comment only, no GitHub check run, and do
  not say drift changes spec status. **[doc: what is described; guess: that nothing else happens]**
- **If 1.25x is wanted**, someone with `documents:write` (owner/admin) replaces the Camera
  markdown (`PUT /documents/{id}/markdown`, snapshot first), changing "1.1x" in Proposed
  Solution and "zoom = 1.1" in Acceptance Criteria by hand, and also "1.1x" in the Web target
  spec, which nothing would flag. A new push re-runs the check. There is no MCP tool to edit
  a spec. **[doc]**
- **If 1.1x is right**, the PR is fixed and pushed; the comment updates in place. **[doc]**
- **If merged as is**, the spec moves to `shipped` once its last open PR merges. **[doc]**
  The test `camera.zoom-step` would fail in CI, but only if the team wrote and runs it: nima
  neither runs tests nor reads their results. **[doc: no test running is described]**

## What the same change looks like in FACT, for contrast

The edit hook refuses the code edit because `camera/zoom-step` did not change; `fact status`
shows nothing to build; `fact test` fails `camera/zoom-step` and `targets/web/input`, which
both read the same value `{camera/zoom-step.factor}`. All deterministic, all local, and all
blind to intent: FACT cannot tell a wrong number from a meant-but-unrecorded one either.
