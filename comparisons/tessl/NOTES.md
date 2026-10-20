# Solar system in Tessl: notes

The specs here use the **Tessl Framework** spec-as-source format: `specs/<project>/*.spec.md`,
the tags `[@generate]`, `[@test]` and `[@use]`, `{ .api }` blocks, and one spec per generated
file (the Framework's rule as Böckeler's review reports it; Tessl's launch post only shows one
`[@generate]` pointing at one file). The Framework was closed beta and is now marked "legacy". Tessl's docs say the
Framework was removed from the current CLI, and the last CLI that has it is 0.28.0 (CLI
changelog, 0.50.3, 2025-11-14: work on the Framework paused, its functionality no longer
included). The
current product is the registry plus **tiles**. The `tessl-labs/spec-driven-development`
tile keeps `.spec.md` files but adds YAML frontmatter (`name`, `description`, `targets:`, a
list of file paths or globs, so one spec can cover many files), uses `[@test] path` links, and leaves code writing to your agent. There is no `tessl build`
there. Moving these specs to the tile format would mean swapping `[@generate]` for
`targets:` frontmatter. Guesses are marked in comments.

## Commands
    npm i -g @tessl/cli@0.28.0 && tessl login && tessl init   # writes .tessl/, AGENTS.md, KNOWLEDGE.md
    tessl build specs/solar-system/clock.spec.md               # regenerate one file (GUESS: path argument form)
    npx vitest run                                              # run the linked tests (Vitest + Puppeteer, our choice)
    npm run bundle                                              # NOT Tessl: inline src/* into out/index.html
    # tile flavour instead: tessl install tessl-labs/spec-driven-development, then ask the
    # agent to "verify the spec". It runs validate-specs.sh and check-spec-links.sh.

A generated file would start like this (header text from Böckeler's article):

    // GENERATED FROM SPEC - DO NOT EDIT
    export function tick(realSeconds) { ... }

## What carries over
- **Fully**: every number (table rows, 1.1x, 0.3x-6x, slider 0-100 starting at 40, 56/28 px,
  300 stars, 20 s, 10 px), every requirement, and all 43 FACT tests: 38 as prose next to
  a `[@test]` link, and the 4 manual tests plus the coverage measure as prose with no link. Per-file APIs go in `{ .api }`
  blocks, and the probe contract fits there well.
- **Prose only**: the do/expect steps. Tessl has no test language, so the agent writes each
  Vitest file from the sentence, and the sentence is the only check that the file matches.
  FACT's `±` tolerances, `each:` loops and `remember … unchanged` become words.
- **Lost or weaker**:
  - No named values or cross-file references (`{year.days}`, `{camera/zoom-step.factor}`):
    365, 1.1 and 56 are copied by hand into several specs and can drift apart.
  - `bug:` lines become HTML comments. `{ .locked }` stops a regression test from being
    regenerated, but it does not record the bug.
  - The `quality` measures (90% fact coverage, 80% line coverage) have no place in a spec.
    They are prose in AGENTS.md and nothing checks them.
  - "Why", "because" and Approach entries are just paragraphs. Owner and out-of-scope are
    prose in AGENTS.md.
  - The rule of one HTML file with everything inside clashes with the Framework's one spec
    per generated file. This needed a split into 8 generated files plus a hand-written
    bundle step. The tile's `targets:` globs would probably not need it (not tried).
- **Things Tessl has that FACT lacks**: `tessl document --code` reverse-engineers a spec
  from existing code, and `[@describe]` documents code without owning it, which helps
  brownfield adoption. It also has a registry of library tiles, so agents use real APIs.

## Checked automatically vs. left to the agent
- **Tessl (Framework)**: generates the whole target file and stamps the DO-NOT-EDIT header.
  It resolves `[@use]` and `[@test]` links. It keeps `{ .locked }` tests. Whether it checks
  for stale specs or regenerates only what changed is not documented. Our guess is that
  `tessl build` regenerates on request.
- **Tile flavour**: two shell scripts check frontmatter, that targets exist, and that
  `[@test]` files exist. Everything else is skill instructions for the agent: drift between
  spec and code, whether each test really checks its sentence, and the spec-before-code
  approval step.
- **Not checked by Tessl**: no lock or hash of the specs, so "what changed since the last
  build" is git's job. No edit-time guard, only the DO-NOT-EDIT comment. No coverage numbers.
- **Trace below file level**: Framework: the link is the whole generated file. That follows
  from one file per spec; Tessl does not state it either way. Tile: `targets:` names files and
  globs and `[@test]` links name files; the format has no requirement ids and no pointer to a
  function, line or single test (checked in `docs/spec-format.md`, 2026-10-19).
- Non-determinism: Böckeler reports different code from the same spec across builds. FACT
  has the same issue, because its compiler is also an LLM.

## Sources
- https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html (Böckeler, hands-on Tessl)
- https://tessl.io/blog/tessl-launches-spec-driven-framework-and-registry (spec example fragments)
- https://docs.tessl.io/reference.md (ask endpoint: legacy format, `.locked`/`.impl`, Framework removed after 0.28.0)
- https://github.com/tesslio/spec-driven-development-tile (spec-format.md, tile.json, scripts, skills)
- https://www.cognix-studio.com/blog/spec-driven-development-tessl/ (third-party: layout, tessl.json, Vitest)
- https://codemyspec.com/blog/tessl-review (third-party: beta status, 1:1, non-determinism)
