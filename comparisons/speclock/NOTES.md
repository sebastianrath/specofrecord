# Solar system in SpecLock: notes

SpecLock does not generate or trace code. It stores rules ("locks") and checks planned agent
actions and commits against them. So this folder is the SpecLock setup a team would add to the
solar-system project: `docs/PRD.md` (requirements, input), `CLAUDE.md` (imperative rules that
`protect` extracts), `.speclock/brain.json` (54 locks, 5 decisions, 4 notes), `.speclock/policy.yml`,
`.claude/settings.json` (plugin), `SPECLOCK.md` (stub of a fixed template), and
`excerpts/out-index.guarded-header.html`.

In this repo the two Claude Code files are stored as `CLAUDE.md.example` and
`.claude/settings.json.example`, so Claude Code never loads them here. In a real project they
drop the `.example`; every mention of them below means the real names.

## Commands a developer runs
    npx speclock setup --goal "A calm way to watch the planets move and learn one fact about each"
    npx speclock protect                     # CLAUDE.md -> locks, installs hooks, advisory mode
    # in Claude Code: speclock_compile_spec on docs/PRD.md (MCP tool; needs an LLM key)
    npx speclock lock "Keep zoom limited to between 0.3x and 6x" --tags camera
    npx speclock decide "Nearest center wins for clicks" --tags selection
    npx speclock hook install                # git pre-commit: audit-semantic --pre-commit
    npx speclock check "make Jupiter bigger" # agent is told to run this before every change
    npx speclock enforce hard                # or protect --strict, once advisory output looks right
    npx speclock lock remove <id>            # how a requirement changes ("unlock")
    npx speclock doctor / list-locks / coverage / drift
Tests run in the team's own runner (headless Chrome, `window.__probe`); SpecLock has no test command.

## What KIT can express
- Every FACT fact as a sentence: text locks (prohibitions, "keep X", "must Y"). All values in
  bodies/clock/camera/scene/controls/selection/web made it into a lock, decision or note.
- Numbers as typed locks (range, numerical, temporal): zoom 0.3-6x, step 1.1x, slider 0-100,
  0.1 s gap cap, 10 px reach, 10 bodies, 300 stars, 90% / 80% coverage.
- FACT's `because:` lines as decisions; open choices ("look is the compiler's choice") as notes.
- Out-of-scope as one NEVER lock; "one writer" as three NEVER locks.

## What has no place (kept only as prose in PRD.md / notes)
- Tests. No do/expect, no `each:`, no tolerances, no `manual:`, no `bug:` link. The 43 tests
  are a numbered list in the PRD; whether they exist or pass is not tracked.
- Links between items ({year} = Earth.days, test values taken from facts). A lock that says
  "zoom 1.1x" and a test that says 1.1 are independent strings; changing one does not flag the other.
- The body table as data. It is one lock plus a note string; no rows, no per-row identity.
- Parts, Contract (gives/needs/owns) and the `__probe` interface, beyond a sentence each.
- Code traceability: no @fact regions or line markers, so no "which requirement is behind this
  line" and no "which code must be rebuilt now". No lock file, no changed-since-last-build list.
- Coverage gates (90% facts / 80% lines): typed locks hold the numbers, but nothing measures them.

## Checked automatically vs. left to the agent
Automatic (plugin PreToolUse hook on Write|Edit|Bash, and the pre-commit hook): the planned edit
or diff is compared to lock text by heuristics plus, optionally, an LLM; in advisory mode the
agent gets a warning, in hard mode the action is denied above 70% confidence. Overrides need a
reason and go into an HMAC-chained `events.log`. Files carrying SPECLOCK-GUARD fail the pre-commit audit.
Not automatic: typed locks are only compared when someone calls `speclock_check_typed` with a
value; nothing reads 1.1 out of the code. Auto-guard picks files by keyword (auth, db, payment,
api, config), so it guards nothing here; guarding `out/index.html` by hand would freeze the only
app file. Whether the code is correct is not checked at all; that rests on the agent and the
team's tests. The conflict check is semantic matching, so it can miss or over-flag
(e.g. "make Jupiter bigger" vs. the body-table lock depends on wording).
Where SpecLock is stronger than FACT: it enforces rules for any agent/host (Cursor, Copilot,
Gemini, git hook, CI action) with no project format to learn, and keeps a tamper-evident audit trail.

## Guesses (not shown in the docs)
- brain.json shape and ids follow src/core/storage.js and memory.js; `source: "compiler"` on
  compiled locks and the exact split into locks/typed locks/notes are guesses at compiler output.
- policy.yml top-level fields (`version`, `name`) taken from policy.js defaults, partly guessed.
- `.claude/settings.json` uses Claude Code's standard plugin keys; SpecLock documents only
  `/plugin install`. `.speclock/context/latest.md`, events.log and the git hook are generated, not written here.
- `protect` may also sync rules into CLAUDE.md/AGENTS.md; not checked how it merges.

## Sources
https://github.com/sgroy10/speclock (README); under https://raw.githubusercontent.com/sgroy10/speclock/main/ :
src/core/{storage,memory,engine,guardian,enforcer,hooks,policy,spec-compiler}.js, src/cli/index.js,
src/mcp/server.js, hooks/hooks.json, scripts/claude-hook.js
