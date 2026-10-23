# Starting a project: steps, structure, style and examples

## Contents
- The steps
- What the first specs contain
- Style
- After writing: check, lock, report
- Tests
- The smallest example: hello world
- A larger example: a 2D game engine

Use this when the user says what they want to build and asks for the first specs. Write the specs, check them, lock
them and report in plain words. Do not ask the user to run anything.

## The steps
1. If the goal is truly unclear, ask one short question. Otherwise do not ask.
2. Write the specs: a root `sor/SPECOFRECORD.md` and one part file per subsystem, short and in plain words.
   `sor new --root` and `sor new <part>` write skeletons with `<fill in: ...>` placeholders, which `sor check` reports
   until you replace them. A fresh skeleton may be filled in whole with Write, once, while it is still exactly what
   `sor new` wrote (with or without `--why`); after that use Edit, one clause at a time. There is no `sor init`.
3. Check, lock and report (see "After writing").
4. A large project stops here, so the user can read the specs. Write code only when asked, or when the project is tiny
   like hello world. Code then follows "A change asked in words" in `SKILL.md`.

## What the first specs contain
- **A root file, `sor/SPECOFRECORD.md`:** the title, one plain sentence saying why the project exists, then
  - `## Rules`: the few top-level goals (speed, size, how easy it is to use), and an `out-of-scope` clause saying what
    the project will not do;
  - `## Approach`: an item `parts` listing the subsystems in one line each, and how they fit together.
- **One part file per subsystem:** `sor/<part>.md`, with a title, one sentence saying why the part exists, and
  `## Rules`, `## Contract` (`gives` what others may call), `## Tests`. Add `## Approach` only for a real design decision.
- **Only what is needed to start.** Three to six parts is plenty for a large project. Leave out what is not decided and
  say so in your report, instead of inventing it.

## Style (the user has to be able to read it)
- Short plain sentences, no jargon the user did not use. One idea per bullet.
- Every bullet has a name, `- **name** - text`: lowercase words joined by `-`.
- A file fits on one screen and stays within the limits in `format-cheatsheet.md`. If a part needs more, give it children: keep
  `rendering.md` and add `rendering/culling.md` in a folder next to it. Choose child part names that do not repeat an item
  of the parent: parts and items share one set of ids, and `sor new` refuses a part name that is already an item. A rule you
  want to split out into its own part: rename the rule first.
- A big spec grows in depth, not width. When a part has more child parts than the limit in `format-cheatsheet.md` (`sor check`
  notes it as `too wide`), group the children that change together or share an owner under a part of their own:
  `rendering.md`, `rendering/lighting.md`, `rendering/lighting/shadows.md`. The group is a real part with its own `Why:` and
  rules, and lists its children in its `parts` item (SPEC §6). Choose the groups before you write many parts: ids are paths, a part
  that moves gets a new id, and there is no rename command. Outside its siblings a part is referred to by its whole path
  (`{rendering/lighting/shadows.budget}`). A plain folder with no file also groups parts, but cannot be referred to. `sor parts
  --tree` shows the result.
- Put numbers in braces with their unit (`{budget: 16 ms}`) only when a clause or a test relies on them.
- A test is named after the clause it proves, so a clause has one test of its own; a second one says `proves: {clause}`. Tests that
  cannot run yet carry `manual:` and a reason.

## After writing
1. `sor check` until it reports 0 problems.
2. Claim the root and every part (`sor claim ROOT rendering input assets`), lock them (`sor lock`, see "Locking" in
   `SKILL.md`) and release (`sor release --all`). On the very first lock of a project nobody else works in,
   `sor lock --all` does the same without claiming.
3. Report in plain words, for example: "I wrote the first specs for the engine: rendering, input and assets, each one
   short page in `sor/`. The goals are 60 frames per second and a first sprite in 20 lines. 3D, networking and an
   editor are out of scope. The tests are written but cannot run yet, because there is no code to run them on. I would
   build rendering first. Want me to?"

## Tests
`sor test` runs web targets itself: a target part, `sor/targets/<name>.md`, says where the code is and what a test can
read. A target of another language runs its tests through a command it names (below). For anything that has neither,
write the tests as clauses and mark the ones that cannot run yet with `manual:`. Tell the user once, in plain words, why
they will not run yet. Do not invent a target that suggests they run. A clause without a test is guidance, not a failure.

**A project without a web target (a native engine, a library).** A test with `do:` and `expect:` steps stays `manual:`:
they are written steps that nobody can run yet. A person, or the project's own test framework once code exists, runs them;
the lock records them as manual and unconfirmed. Say so honestly: `sor test` has no runner for such a project. Without the
`manual:` line, `sor check` notes the test as one nothing will run, and `sor lock` refuses it for want of a result. The way
to a real result later is a test in the project's own framework and `sor lock --results F`, where F is a JSON file of
results written from a run of the framework: with no web target it gives the result of any test that is not `manual:`. A project that
says its targets (`Targets:`) and has test code in more than one language gives one result for each: `{"part/test:name@py": "pass"}`.
Mark the test's code `// @clause test <id>` in a folder a target declares as code (`{path: tests/}`) so that the code is
tied to its bullet and guarded (see `reference/plain-clauses.md`, and SPEC §8 on tests written in your own framework).
The tool reads no framework's own output.

**A project with a test framework of its own, once its code exists (a command line tool, a desktop app).** Until then its
tests stay `manual:`, as above, and you write no target. When the code and the framework are there, give it a target that
says how the tests run, and drop the `manual:` lines of the tests the framework covers: the tool then runs them itself and
the lock records the results as coming from a target command. `sor/targets/py.md`:

```
# Py
Why: where the Python code lives and how its tests run.

## Rules
- **code** - The code is {path: src/}.
- **test-code** - The tests are {path: tests/}.
- **runner** - The tests run with {run: python3 tests/sor_runner.py}, which writes {results: out/results-py.json}.
```

`tests/sor_runner.py` is a small script that runs the framework and writes `{"part/test:name": "pass"}` (or `"fail"`) for
each test bullet, because the tool reads no framework's own output; the script decides which framework test belongs to
which bullet (a `clause` attribute on the test class will do). `tests/` is a declared code folder, so every line in it
sits in a region: wrap the runner in `# @clause glue` ... `# @clause end` and mark the test code `# @clause test <id>`,
or `sor check` reports `code outside any @clause region`. `sor test --targets py` runs the runner, and `sor lock
--run-tests --targets py` locks with the results. The command is text in a spec file, so the user is asked before either
runs: say in a line what the command is and wait. SPEC §9 has the whole rule (more targets, `lcov:`, the checks `sor check`
makes).

**A web target next to a target with a test command (a page and the logic behind it).** The root file names the target whose
tests run through a command, `Targets: unit`, and the web target's part, `sor/targets/web.md`, says `Targets: web` under its
`Why:` line. Without that line the clauses of the web target apply to `unit` too, and `sor lock` refuses them with `no code ...
it applies to unit`, because the page (`web/index.html`) belongs to the web target and not to `unit`. The refusal names the
target that has the code: write that target's name in `Targets:` of the part that holds only clauses of that target (the line
limits every clause in the part, and in the root file it is the default of the project, so a clause of the root file moves to a
part of its own first). Do not answer it with `--allow-behind`, which says the code comes later. The browser tests of the web target say `runs on: browser` and stay out of the lock (`reference/ci-evidence.md`).

## The smallest example: hello world
Two files. `sor/SPECOFRECORD.md`:

```
# Hello
Show a greeting on a web page.

## Rules
- **greeting** - The page says {text: Hello, world}.
- **delivery** - One file, {path: out/index.html}. It opens from disk.
```

and `out/index.html`:

```
<!-- @clause glue -->
<!doctype html>
<html><body>
<!-- @clause end -->
<!-- @clause greeting delivery -->
<h1>Hello, world</h1>
<!-- @clause end -->
<!-- @clause glue -->
</body></html>
<!-- @clause end -->
```

To change the greeting later: edit the clause in `sor/SPECOFRECORD.md` first, then the code, then lock.

## A larger example: a 2D game engine
`sor/SPECOFRECORD.md`:

```
# Tiny Engine
A small 2D game engine that other people can build games on.

## Rules
- **speed** - A game on the engine runs at {fps: 60 frames per second} on a normal laptop.
- **easy** - A new user draws a moving sprite in under {first-sprite: 20 lines}.
- **out-of-scope** - 3D, networking, an editor.

## Approach
- **parts** - {rendering} draws the world, {input} reads the player, {assets} loads files.
  A game asks all three, once per frame.
```

`sor/rendering.md`:

```
# Rendering
Draw the game world on the screen, one frame at a time.

## Rules
- **frame** - A frame takes at most {budget: 16 ms}.
- **order** - Things drawn later appear on top of things drawn earlier.

## Contract
- gives **draw** - `draw(sprite, x, y)` puts a sprite on the screen for this frame.

## Tests
- **order** - a later sprite covers an earlier one.
  manual: needs a screen to look at
```

`sor/input.md`:

```
# Input
Tell the game what the player is pressing.

## Rules
- **latency** - A key press reaches the game within {delay: 1 frame}.

## Contract
- gives **pressed** - `pressed(key)` says whether a key is down in this frame.

## Tests
- **latency** - pressing a key is seen in the next frame.
  manual: needs a keyboard
```

`sor/assets.md`:

```
# Assets
Load pictures and sounds from files.

## Rules
- **missing** - A file that is not there gives an error that names the file.

## Contract
- gives **load** - `load(path)` returns the picture or sound at that path.

## Tests
- **missing** - loading a file that does not exist names it in the error.
  manual: needs a game to run it in
```
