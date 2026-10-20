# Quickstart: Solar System Viewer

## Run

Open `out/index.html` by double-click (file://). No server, no install.

## Automated validation

```bash
npm install          # puppeteer only
node --test tests/   # all contract + integration tests
node --test tests/coverage.test.js   # SC-001 ≥ 90% FRs tested, SC-002 ≥ 80% lines
```

## Manual validation (cannot run headless)

| # | Requirement | Steps | Expected |
|---|---|---|---|
| M1 | FR-034 offline | Turn networking off, open the file, watch DevTools → Network | Page works, 0 requests |
| M2 | FR-020 look | Watch for 30 s | Sun glows, planets lit from the sun's side, Saturn's ring crosses in front of and behind it |
| M3 | FR-010 frame cap | Set slider to 100, switch to another tab for 30 s, come back | Planets continue from where they were; no jump |
| M4 | FR-035 sharpness | Open on a screen with devicePixelRatio > 1 | Orbit lines and names are crisp |

Record results in the PR description.
