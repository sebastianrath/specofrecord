## Context

Body sizes are in space units and grow with zoom (solar-system-viewer "Units"). Jupiter's
orbit radius is 230; its neighbours are Mars at 160 and Saturn at 300, so a size of 20 does not
make orbits or bodies touch.

## Goals / Non-Goals

**Goals:** Jupiter visibly the biggest planet. **Non-Goals:** true scale (out of scope).

## Decisions

- Size 20 (guess). Anything from 17 to 27 keeps bodies "Sun" true; 20 is a clear step up from
  Saturn's 13 without crowding the name below Jupiter.

## Risks / Trade-offs

- A bigger body has a bigger click area (selection "Click reach"); "Nearest body wins" keeps
  neighbouring bodies clickable.
- No scenario checks Jupiter's size itself; only "sun bigger than Jupiter" would notice a
  value above 28.
