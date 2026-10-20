---
title: Solar System Viewer
status: final
created: 2026-10-16
updated: 2026-10-16
---

# Product Brief: Solar System Viewer

## Executive Summary

A single web page that shows the sun, the eight planets and Earth's moon circling on a dark sky.
It is meant to feel like a planetarium: calm, good-looking, nothing jumping or overlapping. You
can speed time up until a year passes in a second, zoom and drag to look closer, and click any
body to read one true fun fact about it.

It is a small, personal project: one HTML file that opens straight from disk, with no install
and no network.

## The Problem

Most solar-system visualisations are either true-scale (the planets vanish into empty space) or
busy, game-like 3D scenes. There is no quiet, legible view that lets you simply watch the planets
move and learn one thing about each.

## The Solution

A 2D top-down view with circular orbits, sizes chosen for legibility rather than true scale, a
speed slider (0–100, starting at 40; at 100 one year per second), pause/play, zoom and pan,
switches for orbit lines and names, a reset button, and a click-to-learn panel with one
one-sentence fun fact per body. A small comet crosses the scene every 20 seconds.

## What Makes This Different

Restraint. It deliberately leaves out true scale, elliptical orbits, textures, sound, other moons
and saving state, so what is there can be calm and correct.

## Who This Serves

The owner (sebastian), and anyone curious who opens the file: they want to watch, not configure.
Success for them is "I left it running and learned something".

## Success Criteria

- Every body (10) can be clicked and shows a true fun fact.
- The page runs without errors or warnings.
- At least 90% of the requirements are proven by an automated test; at least 80% of the code is
  exercised by the tests.

## Scope

In: the 10 bodies, simulated time with speed and pause, zoom/pan, orbit and name switches, reset,
click selection with a panel, a comet, one offline HTML file.

Out: elliptical orbits, true scale, sound, textures, other moons, saving state.
