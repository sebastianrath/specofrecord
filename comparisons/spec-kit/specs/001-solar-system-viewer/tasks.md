---
description: "Task list for Solar System Viewer"
---

# Tasks: Solar System Viewer

**Input**: Design documents from `/specs/001-solar-system-viewer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Requested (Constitution III). Test tasks come first in each story and MUST fail before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

Note: every implementation task edits the same file, `out/index.html`, so implementation tasks
are never [P]; only test files can be written in parallel.

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create `out/`, `tests/contract/`, `tests/integration/`, `tests/helpers/` per plan.md
- [ ] T002 Create `package.json` with devDependency puppeteer and script `test: node --test tests/`
- [ ] T003 [P] Write `tests/helpers/probe.js`: open `file://…/out/index.html`, apply the before-each from contracts/probe-api.md, collect console errors/warnings, start JS coverage

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T004 Skeleton `out/index.html`, everything inline, no network (FR-034): full-window canvas scaled by devicePixelRatio (FR-035), rAF loop, empty module sections in plan order
- [ ] T005 Body table with values from spec Body Catalogue and one-sentence fun facts in `out/index.html` (FR-001–FR-003)
- [ ] T006 `window.__probe` with every reading and action in contracts/probe-api.md, freezing real time on first action in `out/index.html`
- [ ] T007 [P] Contract tests 1–3 from contracts/probe-api.md in `tests/contract/probe.test.js`

**Checkpoint**: probe answers; contract tests pass for the members that exist.

---

## Phase 3: User Story 1 - Watch the solar system move (Priority: P1) 🎯 MVP

**Goal**: Sky, bodies, orbits, names, time display and comet, fitted between the bars.

**Independent Test**: Open with no interaction; US1 scenarios 1–10 pass.

### Tests for User Story 1 ⚠️

- [ ] T008 [P] [US1] Scenarios 1, 4, 5 (Earth part), 6 in `tests/integration/bodies.test.js`
- [ ] T009 [P] [US1] Scenario 3 at 1280×720, 800×600, 640×480 in `tests/integration/camera.test.js`
- [ ] T010 [P] [US1] Scenarios 2, 5 (hud), 7, 8, 9, 10 in `tests/integration/scene.test.js`

### Implementation for User Story 1

- [ ] T011 [US1] Start angles and circular clockwise motion, moon around Earth (FR-004, FR-005)
- [ ] T012 [US1] Clock: time 0, running, slider-40 speed, 0.1 s frame cap (FR-006, FR-007, FR-008, FR-010)
- [ ] T013 [US1] Camera base scale and fit, recomputed on resize; space→screen and back (FR-011, FR-012, FR-016, FR-017)
- [ ] T014 [US1] Sky #05060F and 300 twinkling screen-fixed stars (FR-018)
- [ ] T015 [US1] Orbit circles 1 px; glowing sun, sun-side shading, Saturn ring in front/behind (FR-019, FR-020)
- [ ] T016 [US1] 12 px names with overlap rule and moon 30 px rule (FR-022)
- [ ] T017 [US1] Time display "Year N, day D" top left (FR-023)
- [ ] T018 [US1] Comet every 20 s in space units with faint tail (FR-024)
- [ ] T019 [US1] Draw order per plan.md; zero console errors (FR-037)

**Checkpoint**: MVP — the page shows the moving solar system.

---

## Phase 4: User Story 2 - Steer time (Priority: P2)

### Tests for User Story 2 ⚠️

- [ ] T020 [P] [US2] Scenarios 1–4 in `tests/integration/clock.test.js`
- [ ] T021 [P] [US2] Scenarios 5 (regression #3) and 6 in `tests/integration/controls.test.js`

### Implementation for User Story 2

- [ ] T022 [US2] Control bar at the left of the bottom bar with slider 0–100 (FR-025, FR-029)
- [ ] T023 [US2] Pause/Play button and Space key, Space working after any control had focus (FR-009, FR-026)
- [ ] T024 [US2] Reset: time 0, start view, no selection; keep speed, pause, switches (FR-028)

---

## Phase 5: User Story 3 - Explore the view (Priority: P2)

### Tests for User Story 3 ⚠️

- [ ] T025 [P] [US3] Scenarios 1–5 in `tests/integration/camera.test.js`
- [ ] T026 [P] [US3] Scenario 6 in `tests/integration/scene.test.js`

### Implementation for User Story 3

- [ ] T027 [US3] Wheel zoom 1.1x per notch about the pointer, clamped 0.3x–6x (FR-013, FR-014, FR-036)
- [ ] T028 [US3] Pinch zoom with touch (FR-013, FR-036)
- [ ] T029 [US3] Drag to pan with 4 px click threshold (FR-015)

---

## Phase 6: User Story 4 - Learn by clicking (Priority: P3)

### Tests for User Story 4 ⚠️

- [ ] T030 [P] [US4] Scenarios 1–7 in `tests/integration/selection.test.js`

### Implementation for User Story 4

- [ ] T031 [US4] Hit test: reach max(size, 10 px), nearest centre wins (FR-030, FR-031)
- [ ] T032 [US4] Panel top right: name, fact, "N days" / "N.N years", none for sun (FR-032)
- [ ] T033 [US4] Empty click clears selection and hides panel (FR-033)
- [ ] T034 [US4] Selection ring 2 px, 4 px outside the body (FR-021)

---

## Phase 7: User Story 5 - Declutter (Priority: P3)

- [ ] T035 [P] [US5] Scenarios 1–2 in `tests/integration/controls.test.js`
- [ ] T036 [US5] "Orbits" and "Names" checkboxes, both on (FR-027, FR-019, FR-022)

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T037 [P] `tests/coverage.test.js`: fail if JS line coverage < 80% (SC-002)
- [ ] T038 [P] Same file: fail if fewer than 90% of FR-IDs appear in a test name or quickstart M-row (SC-001) *(guess: Spec Kit has no tool for this; a project would write one)*
- [ ] T039 Run quickstart.md manual checks M1–M4 and record results
- [ ] T040 Run `/speckit.converge` and implement any appended tasks

---

## Dependencies & Execution Order

- Setup → Foundational (T004–T006 block everything) → US1 → US2, US3 (either order) → US4 → US5 → Polish.
- Within each story: tests first, seen failing, then implementation in listed order.
- Parallel: test files only (T003, T007, T008–T010, T020–T021, T025–T026, T030, T035, T037–T038).

## Implementation Strategy

MVP = Phases 1–3. Then add one story at a time, running `node --test tests/` after each checkpoint.
Commit after each task or logical group.
