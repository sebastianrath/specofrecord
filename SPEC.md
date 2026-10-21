# Spec of Record — the format

The words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY are to be read as in RFC 2119 and RFC 8174, and only
when written in capitals. In the sentences that were already here, capitals were added only where a sentence already
stated a requirement, and none was reworded, so a statement in lower case is just as binding: "never" means MUST NOT, "only X may" means nothing else MAY,
"unmarked lines fail" means they fail. §15 says which statements a tool checks.

## Cheat sheet (all you need day to day)

The spec is made of **clauses**: a clause is one rule, one number or one table row, with a name
that code and tests point at. Every part of a project — the whole project, a subsystem, a small
module — is one Markdown file of clauses, with the same shape: a short header and four
sections, always in this order.

```
# <Part name>
Why: <one sentence: why this part exists>          required
Owner: <team or person>                            optional
Source: spec | code at <path>                      optional, default: spec
Design: <tokens.json>, exported from <design file>  optional, root SPECOFRECORD.md only

## Rules      What must be true?                   goals, rules, numbers, budgets, words
## Approach   How is it built, and why that way?   design, child parts, journeys, experiments
## Contract   What does it promise and use?        gives · needs · owns
## Tests      How do we prove it?                  examples, properties, regressions, benchmarks, coverage
```

A whole part, small but complete:
```
# Todos
Why: keep a todo list from the command line.

## Rules
- **limits** — a title has 1 to {max: 200 characters}.
- **order** — the list is sorted by due date; sorting an already sorted list changes nothing.
- **list-time** — listing {todos: 10000} todos takes at most {budget: 50 ms}.
## Approach
- **storage** — one JSON file in the home folder.
  because: no server needed, and people can read it.
## Contract
- gives **add** — `add(text)` adds a todo and returns its id.
- needs {clock/now} — the time for new todos.
- owns **file** — the todo file and its fields; only this part writes it.
## Tests
- **limits** — a title that is too long is rejected.
  do: id = add(text(201))
  expect: error is "too long"
- **order** — sorting twice gives the same list as sorting once.
  each: 1000 × todos = randomTodos(50)
  expect: sort(sort(todos)) = sort(todos)
- **list-time** — listing stays within budget.
  measure: list-time p95 over 50 runs ≤ {list-time.budget}
- **delete-last** — deleting the last todo works.
  do: id = add("a") · delete(id)
  expect: count(todos) = 0
  bug: #12
```
How to read it:
1. Values carry their unit inside the braces: `{budget: 50 ms}`. Values are defined in Rules,
   Approach or Contract, never in Tests; tests refer to them (`{list-time.budget}`).
2. `needs` always names another part's `gives` (`{clock/now}`), and it must exist.
3. A test is named after the item it proves (`limits`, `order`), one test per name. A test named after nothing says
   what it proves with `proves: {limits}` (a second test for that item), or carries `bug:` (an issue id, or a few
   words) when it fixes a bug, as `delete-last` does.
4. Test lines call only what the target declares. `id = add(…)` keeps a result for later lines;
   `each: 1000 × todos = randomTodos(50)` names each generated input; `measure:` is a benchmark.
5. Indented lines are two spaces, a keyword and a colon. Approach: `because:` `try:` `score:`
   `limit:`. Tests: `each:` `do:` `expect:` `measure:` `bug:` `manual:` `proves:` `runs on:`. Any item but a test: `open:`.
   `runs on: linux, windows+gpu` leaves a test to the CI jobs that provide those environments (§8).
   Operators: `=` `≈ … ± tol` `<` `≤` `>` `≥` `is` `contains` `unchanged` `changed by`.
   The right side may add values: `{bars.top} + {fit.room}`.
6. References `{…}` are looked up from this part outward (§4); a value of another part is `{part/item.value}`, and
   an item of the root has no prefix (`{year}`, never `ROOT/year`). Generated code is marked
   `// @clause todos/limits` … `// @clause end`; also `@clause glue` and `@clause test <ids>`.
7. Unsure where something goes? Could a user or a test notice if it changed → **Rules**.
   Only the way it is done changes → **Approach**. Another part would break → **Contract**.

Files: `sor/SPECOFRECORD.md` is the project · `sor/<part>.md` a part · its children go in `sor/<part>/` next to it ·
`sor/targets/<name>.md` a platform. The lock is `sor/sor-lock.json`. Parts and items share one set of ids: a part
`scene/modes` and a rule `modes` in `scene.md` would both be `scene/modes`, so name one of them differently.

Limits (§13; `sor check` reports a breach as a note): at most 7 items per section (a table counts as one), 40 lines above
`## Tests`, 5 lines per test, 80 words per item, 12 child parts per part. More items than that: make the part a folder of
child parts; more child parts than that: group them under parts of their own.

---

## 1. Files and hierarchy
- All spec files live under `sor/` (short for Spec of Record: the folder sits next to `src/`). Code lives wherever the target says. The folder holds the clauses, and `sor-lock.json` is the lock. The one special file is the root, `sor/SPECOFRECORD.md`: every other part is a file named for what it is.
- The folder, root file and lock file names are constants in `tools/sorlib/model.py`.
- A part's id is its path under `sor/` without `.md`: `sor/camera.md` → `camera`,
  `sor/render/culling.md` → `render/culling`. Every id except the root's names its file.
- The root `sor/SPECOFRECORD.md` is the project. Its Rules are the top-level objectives. Its id is `ROOT`, in commands (`sor claim ROOT`),
  in output and as its key in the lock. That is the one id that does not name its file (§4). `CLAUSES` and `SPECOFRECORD` are accepted for it as
  well. The root file was called `CLAUSES.md` and the lock `clauses-lock.json` before the rename: both are still read (with both root files in
  `sor/` the tool refuses), and the lock is replaced by `sor-lock.json` the next time it is written.
- Depth has no limit: a child grows children the same way (`render/culling/visible.md`), and `sor parts --tree` shows the hierarchy.
- A part grows children without moving: `render.md` stays, and `render/culling.md` goes in a folder next to it. Same four sections at every
  depth; nothing new to learn at scale. A folder that only groups parts (`sor/targets/`, `sor/api/`) needs no file of its own.
  The older style, a folder's own file (`render/SPECOFRECORD.md`, or earlier `render/CLAUSES.md`), is still read as the part `render`. When two
  files claim one part, the plain `render.md` counts first and the other is a problem naming both: none replaces the other silently.
- A folder that holds a project of its own (it has its own `sor/SPECOFRECORD.md`, as in a monorepo with one project per app) is not part of the
  project around it: its code is not scanned for markers, and its ids, lock and claims are its own. A reference never crosses from one project
  to the other.
- Targets (platforms) are parts under `sor/targets/`. They use the same four sections.

## 2. Header
- `Why:` is REQUIRED and is the first line after the title.
- `Owner:` names who approves changes to this file.
- `Source: spec` (default): code is generated from this file and marked line by line.
  `Source: code at src/physics/`: the code is written by people (or AI, by hand) and is the
  truth for internals; this file holds the clauses, contract and tests that guard it.
  Use it for existing code, for hard algorithms, and while experimenting.
- `Design: design/tokens.json, exported from <Figma URL>` (root `SPECOFRECORD.md` only) names the
  design export: colors and pictures that come from a design tool, not from people typing them.
  The tool reads it as a part `design`, written by the export and never by hand. Each W3C
  design-token group is an item, each token a row with a `value` (`{design/planet/mars}`,
  `{design/planet/mars.value}`), and every `*.svg` next to it in `assets/` a row of
  `design/assets` (its text includes the file's hash, so a changed picture shows as changed).
  The compiler copies these into the code at build time, with a line marker per token, and never
  makes up a color the design has. A new export is a clause change like any other: `sor status`
  lists the tokens that changed and the code to rebuild.

## 3. Items, names and ids
- Every bullet in the four sections is an item: `- **name** — text`. Items, table rows and
  values are its clauses: each has an id, and anything that points at the spec points at one. Names are lowercase words
  joined by `-`. Text MAY continue on indented lines.
- Ids: `<part>/<name>`, e.g. `camera/limits`. A table inside an item makes one row-item per
  row, named by its first cell: `bodies/planets/Earth`. Adding or removing a row changes the item.
- Parts and items share one set of ids. The part `scene/modes` (the file `scene/modes.md`) and a rule `modes` in
  `scene.md` would both be `scene/modes`: `sor check` reports the `collision`, and `sor new` refuses a part id that is
  already an item (§15). Name one of them differently.
- A test's internal id is `<part>/test:<name>`, so it MAY share its item's name. In braces,
  `{speed}` names the item; where a test is expected (`score:`), it means that item's test.
- Renaming is a deliberate change (references, markers and the lock entry change with it; the tool does not rename for you yet, §15).
  Retiring keeps the name reserved: `- **old-zoom** — retired: replaced by {limits}.`
- `open: <question>` is an indented line under any item except a test (like `because:`), for a question nobody has
  answered yet: `open: is 6x the right upper limit?`. A question may continue on more deeply indented lines. `sor check`
  lists every one as a note. It is not part of the
  item's text for the lock, so adding or answering one does not mark the clause changed and does not unlock its code.
  The compiler MUST NOT choose an answer silently: it lists the question in its report and builds only what is not in
  question. It is not the `2 open` of `try:` (§6) nor `bug: #id open` (§8).

## 4. Values and references
- A value is written inside an item: `{max: 6x}` → `camera/limits.max`. Table cells are values
  too: `bodies/planets/Earth.days`, named by the column header.
- A number followed by a unit is a number: `6x`, `56 px`, `27 days`, `0.1 s`, `90%`, `7 characters`.
  Anything else is text.
- A value MAY stand for another value instead of copying it: `{days: = bodies/planets/Earth.days}`.
- A reference has no colon: `{limits.max}`, `{camera/limits.max}`, `{camera/limits}`, `{camera}`.
  It is looked up from where you are, outward, one level at a time up to the root:
  - at each level it matches an item in that level's own file (`{speed}`, `{year.days}`) or a
    part below that level (`{culling}`, `{culling/visible}`). Levels: this part, then its
    parent part (`web.md` for `web/page.md`), up to the root. Items of sibling parts are never matched by bare names.
  - `{culling/visible}` in `render.md` finds `render/culling`; `{year}` anywhere finds the
    root's `year`; `{physics/state}` in `render/culling.md` finds the top-level `physics`.
  - Found twice (at two levels, or as both an item and a part) is an error: write a longer
    path. Found nowhere is an error. A reference `{x}` in a table cell is a reference like any other: it is checked, and the
    item that holds the table is flagged when `x` changes. A question (`open:`) is neither checked nor a dependency,
    because it may name what is not decided yet.
  - Inside backticks, braces are plain text: `` `{x, y}` `` describes a shape, not a reference.
- By hand, without tools: an id names a file (`camera` → `sor/camera.md`; only the root's `ROOT` does not, it is `sor/SPECOFRECORD.md`), then a bold name,
  then a table row, then a value. Nothing else needs to be looked up.
- Any reference is a dependency, except one in an `open:` question: when the referenced item or value
  changes, every item that refers to it is flagged for review.

## 5. Rules — what must be true?
- Objectives at any height: "feels calm, like a planetarium" (high) and "zoom stays between
  {min: 0.3x} and {max: 6x}" (low) are both rules.
- A high-level rule names the rules that refine it: `Refined by {scene/glow}, {scene/sky}.`
  Following refinements down to tested rules is how a goal is proven.
- Budgets are rules with values: `- **frame** — a frame takes at most {budget: 16 ms}.`
- Words with a special meaning are rules, written once, as high as they are used:
  `- **year** — Earth's orbit time, {bodies/planets/Earth.days}.` Children refer to `{year}`.
- What nobody should build is a rule: `- **out-of-scope** — elliptical orbits, sound.`
- A rule with a test is binding. A rule without one is guidance: the compiler fulfils it as
  it judges best and lists its choices as assumptions.
- One optional sentence pattern keeps behaviour rules easy to scan (the EARS style): `When <trigger>, <thing> does <what>.`
  `While <state>, <thing> does <what>.` `If <unwanted case>, then <thing> does <what>.`
  It is a style, not part of the format: `sor check` does not look for it.

## 6. Approach — how is it built, and why that way?
- Design decisions: `- **base-scale** — a base scale fits the system between the bars.`
  Optional `because:` line for the reason. (This replaces separate decision records.)
- A part with children lists them in an item named `parts`, one line each, and shows how they
  work together in an item named `journey`, as steps that refer to the children's contracts.
- Experiments decide a design by trying it:
  ```
  - **culling** — which structure culls {objects: 100000} fastest?
    try: BVH · grid · loose octree · 2 open        (open: ideas the AI may add)
    score: {speed}                                  (the test of that clause ranks them)
    limit: {variants: 5} · {tokens: 1.5M} · {time: 2 h}
  ```
  The winner becomes a design item with a `because:` line naming the measured result.

## 7. Contract — what does it promise and use?
- `- gives **name** — …` something other parts may call or rely on. Nothing else is promised.
- `- needs {id}, {id} — …` what it uses from other parts. Only `gives` items may be needed, and
  they MUST exist: a `needs` that points nowhere is an error. `sor needs` derives a part's needs from the references
  in its items (§15), so the bullet is optional: it is for saying why, and several ids may share one.
- `- owns **name** — …` data or state only this part may change, with its shape. Changing the
  shape of owned stored data flags a migration.
- A guarantee others rely on ("names never overlap") is a `gives`; the same rule kept internal
  is a rule. Ask: would another part break if it changed? Then it belongs in the contract.

## 8. Tests — how do we prove it?
A test is named after the item it proves: a rule, a `gives`, an `owns` or an Approach item. It
also proves any clause or value referenced in its `expect:` or `measure:` lines; values used only
as inputs (`do:`, `each:`) prove nothing. A test named after nothing MUST carry `proves: {item}` (a second test
for that item) or `bug:` (a regression test).
**Clause coverage** counts Rules items and `gives` items: the promises.

```
- **limits** — zooming forever stays inside the limits.          (the readable line)
  each: size in 1280x720, 800x600       repeat for each case (also: "20 rounds", "1000 × s = shapes(2)")
  do: zoomSteps(200) · remember zoom    actions; remember stores a reading; `x = call()` keeps a result
  expect: zoom = {limits.max}           = ≈ ± < ≤ > ≥ is contains unchanged "changed by" (± or ≤ 0)
  measure: frame-time p95 over 600 frames ≤ {frame.budget}
  bug: #142                             a regression test (issue id or a few words); never deleted silently
  proves: {limits}                      what the test is about, when it is not named after it (a second test for the item)
  manual: needs a real GPU              cannot be automated; listed, never run
```

| Kind | Written as |
|---|---|
| Example (unit / integration / end-to-end) | `do:` + `expect:`. The level is the file's level: leaf parts unit, parents integration, root end-to-end. |
| Property | `each: 1000 × <name> = <generator>(…)` + `expect:`. Generators are declared by the target. |
| Reference (oracle) | a property whose `expect:` compares the fast result to a declared reference. |
| Regression | any test with `bug: #id`. `bug: #id open` marks a known, still-failing bug. |
| Benchmark | `measure:` against a budget value. Repeated runs; percentiles. |
| Coverage | `measure: clause-coverage …` or `measure: line-coverage …` (built-in metrics). |
| Hand-written | tests in the project's own framework (jest, pytest, cargo …), marked `@clause test <ids>`. |
| Manual | `manual: <why>`. |

- `contains` works on text and on lists (every item of the right side is in the left side).
- Several `each:` lines nest (sizes × rounds). `remember X` stores a reading; later `X.field`
  and `X changed by …` compare against it.
- A bug fix is a regression test that also states what must stay as it was: `remember` takes the reading before the
  action and `unchanged` compares against it afterwards (the syntax as the solar-system example uses it):
  ```
  - **space** — click Pause, press Space → running again, speed unchanged
    do: use(pause) · remember speed · press(Space)
    expect: paused is false
    expect: speed unchanged
    bug: #3
  ```
- **Where a bug is recorded.** On a test, as `bug: <ticket id or a few words>`: the test is executable, shows under
  Fixes in `sor changes`, and is never deleted silently. Not on the clause (it says how things work now, and its
  text is locked, so an id there would force a recompile and go stale) and not in code comments (the chain
  marker → clause → test → ticket is enough). The history is the project's own version control.
- **A second test for one item.** Test names are unique, so an item has one test of its own. Another test about the
  same item says so with `proves: {item}`, or refers to the item, one of its values or one of its rows in an
  `expect:` or `measure:` line. `proves:` is read as a reference: the lock records it, the test goes stale when the
  clause changes, and a broken one is a problem. It names a clause or a table row, not a value, a part or a `needs`
  item; only a test may carry it. `expect: {item}` alone compares nothing, so `sor test` cannot run it and `sor check`
  reports it, pointing to `proves:`. Keep every `expect:` a comparison.
- **Which test frees the code of a bug fix.** Any test that proves the item (one of the ways above) and is new,
  changed, or did not pass at the last lock. A bug fix may therefore give the item's own test another `do:` / `expect:`
  pair and a `bug:` line (several are allowed), or add a second test with its own `do:`, `proves:` and `bug:`. A reference
  in `do:` or `each:` proves nothing. For "did not pass at the last lock", which lasts until someone fixes it, only the
  test named after the item, the tests named after nothing and the tests that say `proves:` for it count, so a test of
  another item that mentions it in passing does not keep its code free. The edit guard, `sor status` ("fixing"), a
  scoped `sor lock <item>`, clause coverage and `sor test <item>` all ask the same question.
- **A test written in your own framework.** A test with no `do:`, `expect:` or `measure:` line (its bullet may carry
  `proves:` and `bug:` lines) whose code is marked `// @clause test <part>/<name>` is **external**: `sor test` shows it as
  EXTERNAL and neither runs nor fails it, and `sor lock --run-tests --results F` takes its result from the file F
  (`{"part/test:name": "pass"}`, as `sor test --out` writes it). With `--run-tests`, a result in F for any other test is
  ignored, and said. With no web target nothing runs, there is no EXTERNAL group, and `sor lock --results F` alone takes
  the result of every test that is not `manual:` from F, whether it has steps or not and whether its code is marked or
  not (a result for a `manual:` test is ignored, and a key that is no test refuses the lock); the mark then only ties the
  test's code to its bullet for the edit guard. The folder with that code must be a declared code path: a rule of a target with `{path: test/}` (§10). That rule
  needs a test of its own (it counts for clause coverage), every line in the folder needs a marker, and the folder is
  governed like any code: the edit guard refuses a change to a marked test until its bullet has changed. A stepless test
  without such code stays a failure that says how to mark it. The file F is written by whoever runs the framework: the
  tool reads no jest or pytest output. External
  tests are not run by `sor test`, so they do not count toward its clause coverage, and the tool trusts the framework's
  result, as it does for `--results` alone.
- **A test left to CI.** A test that needs a place (an OS, a GPU, a database replica, an hour) says `runs on: linux, windows+gpu`.
  A comma separates the environments it must pass in; a plus joins the names one machine must provide together; a name is
  lowercase letters, digits, dots, dashes and underscores. Such a test is **deferred**: its lock entry says `deferred`, from the spec
  alone, so the lock holds no result for it and never waits for one (§11); `sor lock` names the tests that just became deferred. `sor test` leaves it out unless the run provides one of its
  environments (`--provides`), says `--all`, or names the test by its own id; `sor test --list` says which, and runs nothing. A CI job
  that ran it writes evidence with `sor evidence` (`--job`, `--provides`, `--results`): one file per job, `{job, provides, results}`,
  with a fingerprint and `pass` or `fail` for each test, so two jobs never write the same file and a team decides whether to commit
  them. The fingerprint hashes the test (its rows and values too), what it refers to, and the text, rows, values and code of every clause it
  proves, the code marked with a row included: a result goes stale when any of them changes, and there is no timestamp. A tool that hashes
  code differently (§11) gives other fingerprints, so the next run of the jobs writes the evidence again. It does not cover code a test only uses as input (`do:` and
  `each:` lines) or code outside the marked regions: a result can stay current while such code changes. `sor verify` is the gate: exit 0 when every environment of every
  deferred test has a current pass, 1 when one is missing, stale or failed (a current failure is not outvoted by another job's pass),
  2 for an evidence file that cannot be read or a bad `runs on:` line. Evidence is as trustworthy as the job that wrote it: the gate
  checks that a result is current and which environments the job said it provides, not that it ran the test. A deferred test proves
  nothing for clause coverage until a run includes it: a project with a coverage budget (`measure: clause-coverage …`) gives that test its
  own `runs on:` and has a job run it with `sor test --all`. A `manual:` test with `runs on:` is a problem; under anything but a test the line is plain text. `runs on:` is for a test that
  needs a place, never for one that fails: that is weakening the test. A failure only CI sees does not free the code of a bug fix (the
  edit guard reads the lock): change the test first, or give it a `bug:` line.
- **A ticket is input, not authority.** Before any edit, ask: is it a bug against a clause? must the clause change?
  must the code change? The cases and what to do in each are in the plugin's `reference/bugs.md`. A ticket that
  contradicts a clause does not rewrite it: ask the owner (an `open:` question on the clause), and do not write back to the
  ticket system unless asked.
- Only probes, generators and metrics the target declares may be used. A typo is an error.
- Tests define no values: limits, budgets and coverage targets are rules; only a `±` tolerance
  may be written inline. A test MAY add or subtract values the clauses define
  (`expect: layout.orbitTop = {bars.top} + {fit.room} ± 0.5`).
- **Clause coverage**: share of Rules and `gives` items with a passing test. **Line coverage**:
  the target's coverage report mapped onto marked code, per clause.
- **Test strength**: the tool changes each value a test refers to and reruns it; a test that
  still passes is reported as weak (it cannot fail).
- Benchmark results never go into `sor-lock.json`. Budgets (values in clauses) are the bar.
- Long tests: if Tests outgrow a screen, move them to `<part>.tests.md` (only a `## Tests` section). The tests there are the part's own: a name used in both files, a rule in the tests file, or a tests file whose part does not exist is a problem in `sor check`, reported in the tests file.

## 9. Targets
A target is a part under `sor/targets/` that says how code is delivered and tested:
- Rules: delivery rules ("one HTML file", "1 px = 1 CSS pixel"), where code goes.
- Approach: how code is built, laid out and run; the test command; the coverage format.
- Contract: `gives` the probes (`read:`, `do:`), generators (`gen:`), metrics (`metrics:`) and
  the setup run before each test (`before each test:`).
- Tests: checks of the target itself (it builds, runs offline).

## 10. Code markers
- Every generated line sits in one region: `@clause <id> [<id> …]` … `@clause end`, written in the
  file's comment syntax. `@clause glue` for wiring. Regions never nest. Unmarked lines fail.
- Where the tool looks for code: the declared code paths, or the whole project when none is declared yet.
  It never enters a folder whose name starts with a dot (`.git`, `.venv`, `.claude`: tools and plugin copies, not
  the project's code), nor `node_modules`, `venv` or `__pycache__`. A code path MAY itself be inside a dot folder.
- Test code: `@clause test camera/limits` … `@clause end`.
- A line marker gives one line to the ids at its end, inside or outside a region:
  `{ name: 'mars', size: 5 },  // @clause bodies/planets/Mars`. Use it where one line serves one
  table row, so a change to that row allows that line and no other.
- `Source: code` parts: markers are optional and MAY sit on functions or whole files
  (`@clause file physics/solver`). Lines without markers are allowed under that part's path.
- A clause can instead point at its code, with no marker in the code: an indented
  `code: src/physics/solver.cpp#World.step` line under the item names a function, class,
  method (`Class.method` or `Class::method`), type or constant; `code: path` alone is the whole
  file. Python is read with Python's parser, other languages by declaration patterns and brace
  matching (C, C++, C#, Java, JS, TS, Go, Rust, Zig, scripts in HTML). The named lines count as
  that item's code in the lock; when they change in a `Source: code` part, `sor status` asks to
  check the clause still holds. An anchor that finds nothing is a problem in `sor check`.
- Lines are numbered as an editor numbers them: a line ends at a line feed, a carriage return or both, and nowhere else (a form feed
  or a Unicode line separator inside a line does not end it).
- Markers plus the lock let any tool go from a line of code to its clause and back.

## 11. sor-lock.json
- One entry per item, row, value and test: the hash of its text, of everything it refers to,
  and of its code regions; for tests, whether they passed when accepted, or `deferred` when the test says `runs on:` (§8): a CI
  job proves it, so no environment and no result of a job is ever in the lock.
- Sorted, one entry per line, no line numbers, no timestamps, no measurements: identical
  input gives identical bytes; a line-based merge keeps different entries apart.
- Hashes do not depend on line endings: spec text is read with universal newlines and code is hashed
  without layout, so an LF checkout and a CRLF checkout of the same files give the same lock.
- The file is written through a temp file and a rename that keeps the permissions the file had, and
  stale temp files (older than 5 minutes, left by a crashed write) are removed. If the file exists and
  is read-only, `sor lock` refuses and changes nothing: some environments keep files read-only until
  they are opened for edit, and replacing the file would bypass that.
- `sor lock` refuses on problems in what it locks, drift, a clause another agent holds, and a test that is neither manual nor deferred without a passing result (the refusal lists the tests and the way out, §15); the points below and §15 give the exact rules. `--allow-incomplete` records a test that did not pass, but does not cover a test of code shared with a changed clause. It does not wait for code: a clause locked before its code exists is reported as `built` once the code arrives.
- `sor lock <ids>` accepts only the named clauses (and parts), and the clauses that share a
  code region with them when their entry would change; every other entry keeps what it had, so
  one agent never accepts another's unfinished work (§16). With no ids it accepts what the agent
  claimed, together with the child parts under a claimed part that have a change of their own (§16); naming a part
  accepts its own items, not the child parts under it. `sor lock --all` accepts everything, and is refused while another
  agent holds a claim.
- The file is written whole through a temp file and a rename: a reader sees the old lock or the
  new one, never half of one.
- **The lock has a format number.** The lock format described here is number 1. Format 1 has no marker in the file: a lock written
  before the number existed is format 1, and a project that stays in format 1 keeps the same bytes. A later format opens the file with
  `"*format": N`, a plain number and not an entry, and no item, row, value, test or glue key can start with `*`. A tool that reads a
  number it does not know stops with exit 2, says to update, and changes nothing. That covers `sor status`, `sor lock` in every form
  (a lock that a newer tool wrote while it was running is not replaced either), `sor changes`, and `sor test` when it runs tests.
  `sor check`, `sor parts`, `sor show` and the other commands that never read the lock go on working. The edit hook refuses edits to
  code, because it cannot tell what drifted, and answers reads without the list of pending changes. A tool older than the number
  cannot be taught: given the marker it stops with a Python error, and its edit hook fails open as for any error of its own. So the
  number protects a lock only from tools that have it; update every copy of the tool (the project's, the plugin's and the extension's).
- Large projects may split it: a folder with a project of its own (§1) holds its own lock.

## 12. Where does it go?

| It is … | Section |
|---|---|
| a goal, rule, number, budget, word, the out-of-scope list | Rules |
| how it is built, why, which child parts, how they work together, what was tried | Approach |
| something others may call or rely on · something it uses · data only it changes | Contract: gives · needs · owns |
| proof, measurement, a fixed bug that must stay fixed, a coverage target | Tests |
| why it exists, who owns it, whether code or spec is the truth | header |

Tie-breaks: a user or a test could notice the change → Rules · only the way it is done changes
→ Approach · another part would break → Contract · it proves or measures → Tests.

## 13. Readability
- Everything above `## Tests` fits one screen (40 lines). Tests MAY run longer; editors fold them.
- At most 7 items per section (a table counts as one). More means: split into child parts. A section counts the
  bullets written in it.
- Tests are exempt from the 7-item cap. One test SHOULD stay within 5 lines; a longer one is split into two.
- One item SHOULD stay within 80 words; `sor check` notes a longer one as `too long`. An item is counted with its indented
  lines; a table, an `open:` line and a `code:` line do not count, and tests are exempt.
- A part SHOULD have at most 12 child parts (the root: 12 top-level parts); `sor check` notes more as `too wide`. More means:
  group related ones under a part of their own, so the tree grows in depth and not in width (`rendering/lighting/shadows`, not
  25 children of `rendering`). A folder that only groups parts is no part and is not counted.
- A value SHOULD be defined once. `sor check` notes a `{name: value}` that another part defines with the same name and the
  same text (case and spacing aside) as `value twice`, at each of the definitions, naming the others: keep one and refer to
  it from the rest (`{part/item.name}`), or, if they are different quantities, rename them so the names say what they are.
  Tests, table cells and `{v: = x}` aliases are not definitions, and the same name with another text is not a copy.
- `sor check` reports a breach of these limits as a note, not a problem (§15): a note
  never changes the exit code, and `sor check --strict` makes notes exit 2.
- No forward surprises: a reader never needs a file below to understand this one.

## 14. Compiler duties (what the AI compiler and the tool MUST do)
- **Review first.** List every problem before building. BLOCKING are only: two rules that
  cannot both hold; a test no build could pass (including one that depends on timing or
  randomness the spec does not control); a word, number or unit the build needs and nobody
  defined; a conflict between parts or with the target. A BLOCKING problem stops the build
  of any part whose clauses have tests. Everything else is a note.
- **Test at the extremes**: smallest and largest values, every test size, fastest speed.
- **Quality every build gets, unless a clause overrides it**: time follows real time, never a
  fixed step per frame; sharp on dense screens; nothing essential cut off at the test sizes;
  controls never cover content at the start; text never overlaps text; random choices made
  once; shortcuts keep working after a click; no errors; no features nobody asked for.
- **Write down every choice** the clauses left open, as assumptions next to the code.
  Promoting an assumption into a clause is how a part gets more exact.
- **Never verify your own build**: someone else runs the tests and decides.
- **Collisions are decided by geometry, not fixed priority** ("the nearest wins").

## 15. What a tool enforces today
`tools/sor.py` (Python 3, no dependencies) reads this format. Run it in a project folder or
with `-C <folder>`:

| Command | Does |
|---|---|
| `sor check [--strict] [PART ...]` | problems: header, names (a name used twice says where the first is), `heading` (a section heading written twice in one part: same text, case and spacing ignored), values, references (§4; one that names nothing says what was found and suggests the nearest valid ids, as in `{core/spawn} names no item, row, value or part; did you mean {core/ecs/spawn}?`), `needs` → `gives` (a `needs` on a part says it is a part and lists the `gives` ids inside it), a `collision` of a part and an item with one id (`"scene/modes" names both a part (scene/modes.md) and an item of scene.md: rename one of them`), orphan tests (named after nothing, with neither `proves:` nor `bug:`), `proves:` lines that name no clause, `expect: {ref}` alone, markers, unmarked lines, `placeholder`, and in a `<part>.tests.md`: a test also named in the part's file (`duplicate`), anything but tests (`misplaced`), no part to belong to (`tests file`) (a `<fill in …>` left in a spec file, for example by `sor new`). Notes, which never change the exit code: a breach of the limits of §13 (items in a section of Rules, Approach or Contract, words in an item (`too long`), lines above `## Tests`, lines in a test, parts directly under one part (`too wide`)), every `open:` question (§3), `loose text` (a line under the title or in a section that belongs to no item: it is not locked, and a change to it goes unnoticed), and `never run` (a test with `do:`, `expect:`, `each:` or `measure:` lines that nothing will run: the project has no web target, the test is not `manual:` and has no `@clause test` code; one note per part); `--strict` makes these exit 2. With parts, `sor check audio` reports only the problems and notes of those parts and of the parts inside them (`audio` covers `audio/mixer`, not `audio-fx`; `ROOT` is the root file alone), and its exit code follows only them; a name that is no part is exit 2 and lists the closest ids. Without parts nothing changes |
| `sor status [--json]` | compares files and code with `sor-lock.json`: **recompile** (new, changed, removed clauses), **review** (a referenced item or value, or shared code, changed), **drift** (code changed, its clause did not), **built**, **info**; and a block `tests (N)` of the tests a lock would refuse for want of a passing result, with the way out (as in the refusal of `sor lock`). `--json` has them as `tests_pending`, a superset of `tests_not_passed` (the tests that had not passed at the last lock); `tests deferred (N)` lists the tests a CI job proves (§8), and `--json` has them as `tests_deferred` |
| `sor test [id …] [--coverage] [--out F] [--provides NAMES] [--all]` | runs the tests in headless Chrome against the web target's probes; reports clause and line coverage. An id is a test, the item it proves, or a part; an id that matches no test is exit 2, not a pass. A test without steps whose code is marked `@clause test` is shown as EXTERNAL: not run, not failed (§8) |
| `sor test --list [id …] [--provides NAMES] [--all] [--json]` | lists the tests a run would run and the ones it would leave to CI (§8): each with its environments, whether your own framework runs it and its fingerprint; runs nothing, so it needs no web target |
| `sor evidence --job NAME --provides NAMES --results F [--out FILE]` | writes what a CI job proved (§8): F is `{test id: pass\|fail}`, as `sor test --out` writes it; only tests that say `runs on:` and name an environment the job provides are kept, the rest are named; default `evidence/NAME.json` |
| `sor verify [FILE or FOLDER …] [--json]` | the gate over the evidence (§8): exit 0 when every environment of every deferred test has a current pass, 1 when one is missing, stale or failed, 2 for a bad evidence file or `runs on:` line |
| `sor lock --rehash` | the one-time rewrite after the rule for hashing code changed (§11): an entry whose code is unchanged under the old rule gets the new hash, and `text`, `refs` and results stay as they are. It takes nothing else and accepts no change |
| `sor test --strength [id …]` | test strength (§8): reruns each passing test with every value it refers to changed; lists weak tests and the value that did not matter, and the passing tests it could not vary (`IDLE`) |
| `sor lock [--run-tests \| --results F] [--confirm test …] [--allow-incomplete]` | writes the lock; refuses on problems, drift, or tests that did not pass. What a scoped lock waits for is in §16. With both `--run-tests` and `--results F`, F gives the results of the EXTERNAL tests only (§8). The refusal for tests without a result says `N test(s) did not pass (F failed, M not run)`, lists the first ten and the way out: with no web target a `manual:` line for a test nobody can run yet, or `--results F` for a test in the project's own framework; with a web target `sor lock --run-tests`, adding `--results F` for a test marked `@clause test <id>`; and `--allow-incomplete` in both |
| `sor lock [<id …> \| --all]` | accepts the named clauses only, none of the child parts under them unless named (§11); with no ids, what you claimed, and the child parts under a claimed part that have a change of their own (new, changed or removed; parts made after the claim too): it prints `locking the parts under them too: …`, and leaves out a child part that another agent's claim overlaps, naming it (`not locking audio/mixer, which is claimed: …`); `ROOT` is not expanded; `--all` the whole project (§16). Refused while someone else claims them. With no ids and every claim of the agent expired, it is refused and says so; when only some expired, it warns (§16) |
| `sor claim <id …> [--as NAME] [--ttl 30m]` | says you are working on these clauses and for how long: `claimed audio until 00:31 (30 min)`; exit 3 and who holds them when someone else is: the refusal names the ids in the way, and says when the others asked for were free but not claimed either, for a claim takes all its ids or none (§16) |
| `sor release [id … \| --all] [--as NAME] [--force]` | gives claims up again. A caller that names itself (`--as NAME` or `SOR_AGENT`) frees only that agent's claims; releasing another agent's claim by id prints `NOT released (held by someone else; --force overrides)` and exits 3. A caller that gives no name (the parent, or the only agent) frees every claim made in its session (§16). `--force` overrides. Claims that had expired are named: `nothing to release: your claims on X expired at 00:31`, or the same as a `note:` beside what was released |
| `sor markers [id \| file:line]` | where an item's code is, or which clauses a line of code serves |
| `sor show <part \| item>` | the clauses with their code underneath, and under an item every test that proves it: one view for people and agents |
| `sor parts [--json] [--tree] [PART …]` | an index of every part (`--tree`: each part indented under its parent, with the number of parts under it; with parts, only those and the parts inside them, as in `sor check`, and a name that is no part is exit 2 with the closest ones): id, title, `Why:`, Owner, Source, bullets per section, what it gives, open questions. Printed, never written into `sor/`, because every `.md` file there is a part. The session-start hook adds a compact version of it |
| `sor needs [part] [--json]` | what a part needs, derived from the `{references}` in its items to items of other parts (words of its parent files, its own child parts and design tokens do not count, so the root needs nothing), each marked `gives` or not. A `needs` bullet (§7) stays allowed and is optional |
| `sor changes [--json]` | the changes pending since the last lock, grouped: **Added**, **Changed**, **Removed**, **Fixes** (new or changed tests with `bug:`), and every item retired with `retired:` |
| `sor new <part> [--why TEXT]` · `sor new --root [--why TEXT]` | writes a skeleton part (the four sections) or the root file (Rules and Approach), with hint comments at the start of a line and `<fill in: …>` placeholders, which `sor check` reports until they are filled in. Never overwrites a file. The edit hook lets one Write fill in a skeleton that is still exactly as written, whatever sentence it was given for `--why` (see the hooks below). Refuses (writing nothing): a `-C` folder that does not exist; an id that is already an item (parts and items share one set of ids, §3; the message says where the item is, `the rule **mixer** in audio.md`, and the two ways out: another part name, or rename that item first); an id whose folder already holds parts; a `--why` with a `Word:` setting inside the sentence (`Owner:`, `Run:`, …), which the reader would take for a setting of the part |
| `sor hook pre-edit \| post-read` | Claude Code hooks, registered in `.claude/settings.json` (below) |

Drift lines name who last changed their lines when the environment can tell (today from `git blame`):
`(changed by NAME in 1a2b3c4 (2026-10-17))`, or `(not committed yet)`; without git nothing is added.
This is the only place the tools ask a version control system anything. They never commit, merge, fetch
or open files for edit, and they do not assume a version control system, workspace layout or build.

`--as NAME` belongs to `claim`, `lock` and `release` only: on any other command the error says so.

Exit codes: 0 clean, 1 work pending, 2 problems or drift (or lock refused), 3 claim refused, 141 the reader closed the output pipe
(`sor status | head`): the program ends quietly, as `ls | head` does. `sor status` also
reports **built**: a clause locked without code that now has code, and **fixing**: code changed
for an item whose test changed first, or did not pass at the last lock (the bug-fix path; "its test" is any test that
proves the item, §8).
Neither is drift. When code shared by several ids changes for one of them, the others are
listed for **review** (`shared`); `sor lock` then needs their own tests to pass again, even
with `--allow-incomplete`. The edit hook and `sor lock` use the same rules as `sor status`.

**Running tests.** `sor test` turns each test into JavaScript, adds it to a copy of the web
target's page (next to the original, removed afterwards) and drives headless Chrome or Edge over
the DevTools protocol (`SOR_CHROME` overrides the path). Every test gets a freshly loaded page,
then the target's `before each test:` actions, so no test sees what another left behind. The page
defines `window.__probe`; each read and action is a member, called with the test's arguments when
it is a function (`body(earth)` → `__probe.body('earth')`). A probe the target does not declare,
or a `{value}` that does not resolve, fails the test before it runs; a declared probe the page
lacks fails with "not built". Built in: `count(x)`, `overlaps(boxes)`, `offset(a, b)`,
`sentences(text)`. `sor lock --run-tests` runs them and locks with the results; `--results F`
takes a JSON file of `{"camera/test:limits": "pass"}` instead.

**Coverage.** `measure: clause-coverage` and `measure: line-coverage` are built in (§8).
*Clause coverage* counts Rules and `gives` items proven by a passing test: the item a test is named
after, and every item an `expect:` or `measure:` line refers to; a rule that is `Refined by`
others is proven when all of them are (§5). A test that measures clause coverage does not count
itself. *Line coverage* is Chrome's block coverage of the page's own script, merged over all test
pages and mapped onto marked regions: `sor test --coverage` lists it per clause, with the clauses no
passing test proves. Other `measure:` metrics (benchmarks) are not run yet.

**Test strength.** `sor test --strength` first runs the tests, then reruns every passing test
once per change of each `{value}` its `do:` and `expect:` lines refer to, each on a fresh page.
Only the literal the runner puts into the test's JavaScript changes, never the clauses or the
page, and nothing is rebuilt. A number is changed 10% up and 10% down (`1.1x` → `1.21` and
`1`; 0 → 1 and -1), a text gets a character added. A test that still passes with every change of
a value is listed as weak, with that value: it cannot fail on it (often a bound far from what the
page does, such as `gap ≥ {bars.top}` with a much larger gap). Exit code 1 when a test is weak.
Values in `measure:` lines, `each:` cases and `before each test:` are not changed. A passing test with nothing to
change (no `{value}` in its `do:` or `expect:` lines, or one that only measures) is listed as `IDLE`, and the summary
says so when nothing at all was changed: strength cannot tell whether such a test, or a `proves:` line, checks anything.
`IDLE` is not a failure.

**Manual checks.** A `manual:` test is never run by the tool, and the builder never verifies its
own build (§14), so only a person can pass one: `sor lock --confirm scene/test:bodies` records
it as checked. The confirmation carries over to later locks until the test or the code of the
item it checks changes; a confirmed check counts for clause coverage.

**Clauses first, for agents.** Three Claude Code hooks make the order part of the tools (all packaged in
the plugin at `plugins/specofrecord/`, DECISIONS.md):
- *Before Edit or Write* on code, the edit is simulated and refused if it would add drift (code
  of a clause that did not change since the lock), unmarked lines, or markers for ids that do not
  exist. Changing the clause first (or, for a bug, adding or changing a test that proves it, with `bug:`) makes the same edit
  pass. `sor-lock.json` and `sor/.sor-claims.json` may not be edited by hand. Spec files are free to
  change, with two exceptions: an existing spec file may not be rewritten with Write (it erases
  what others changed since the agent read it): edit it with Edit, one clause at a time; and where
  `SOR_ENFORCE_CLAIMS=1` is set, a clause another session has claimed may not be edited (§16).
  The refusal to rewrite has one exception: a file that is byte for byte the skeleton `sor new` would write right now
  (for the root or for a part; the sentence given to `--why` is read from its `Why:` line) has nothing in it to erase but
  that line, so one Write may fill it in whole; after any other change to it, it is an existing file like every other.
  A Write that creates a spec file was never refused.
- *After Read* of code, the clauses behind the regions read are added to the agent's context,
  with the clauses that may change now.
- *A hook that cannot run never blocks an edit.* Only a deliberate refusal (a JSON deny) does. Any other failure
  exits 1 with a one-line notice, because Claude Code treats exit code 2 as a refusal and a missing script gives exit
  2. The repository's `.claude/settings.json` therefore looks for the tool at `$CLAUDE_PROJECT_DIR/tools/sor.py`,
  then upward from the session's directory, and the plugin's hooks end in `|| exit 1`.
- *At session start* in a project that has a spec, one short note says so, so an agent knows the
  workflow exists before it edits anything. The note ends with a compact index of the parts (`sor parts`: each
  part's `Why:`, at most 1200 characters; a project with more parts gets the first ones and "and N more"). If the
  index cannot be built, the note comes without it.
- Not covered: code changed through the shell (`sed`, scripts). That still shows as drift in
  `sor status`, and `sor lock` refuses it.

**Code a person changed.** The hooks watch only an agent's own edits. A person who edits code in an editor is not
stopped: the change shows as drift, and `sor lock` refuses it until the clause says the same. The way out is the clause,
not a revert. An agent reads the code with its clause (`sor show`) and changes the clause to say what the code now does.
Status then lists the clause as changed with its code updated, and it locks like any other change. The skill
(`SKILL.md`) has the steps. Drift that an agent causes by its own edit is the other case: it reverts the edit or changes
the clause first.

**What is checked, and how.** The main statements of this format, and what makes sure of them today:

| The format says | Checked by |
|---|---|
| a part has a `Why:` (§2) | problem in `sor check` |
| a name is used once in a part; a section heading is written once; a `{reference}` finds exactly one id (in a table cell too, not in an `open:` question); a value has a space after its colon (§3, §4) | problem in `sor check` |
| `needs` names a `gives` that exists (§7) | problem in `sor check` |
| a test is named after the item it proves, or says `proves:` or carries `bug:` (§8) | problem in `sor check` |
| no `<fill in …>` left in a spec file (`sor new`) | problem in `sor check` (`placeholder`) |
| code sits in a `@clause` region of an id that exists; `code:` finds its code (§10) | problem in `sor check`; the edit hook refuses an edit that adds an unmarked line or a bad marker |
| the limits of §13 | note in `sor check` |
| a `{name: value}` is defined once: the same name with the same text in another part is one fact written twice (§3, §13) | note in `sor check` (`value twice`), at each of the definitions |
| a test with `do:`, `expect:`, `each:` or `measure:` lines that nothing will run: no web target, not `manual:`, no `@clause test` code (§8) | note in `sor check` (`never run`) |
| an `open:` question stays visible until it is answered (§3) | note in `sor check` |
| code changes after the clause it serves (§15) | drift in `sor status`, which `sor lock` refuses; the edit hook refuses an agent's edit, and a person's edit is flagged and not blocked |
| the lock is written only when every test that is not manual or deferred passes (§11) | `sor lock` refuses |
| a `runs on:` line under a test names valid environments, and the test is not manual (§8) | problem in `sor check` (`runs on`) |
| a test that says `runs on:` has a current pass in every environment it names (§8) | `sor verify` exits 1 |
| the lock is in a format this tool reads (§11) | `sor status`, `sor lock`, `sor changes` and `sor test` exit 2 and say to update; the edit hook refuses edits to code |
| a test calls only probes, generators and metrics the target declares, and its `{values}` resolve (§8) | `sor test` fails the test before it runs |
| the lock and claims files are not edited by hand; a spec file is not rewritten with Write, except one that is still the skeleton `sor new` wrote (§11, §15, §16) | the edit hook, in Claude Code only; for other agents, a rule in the skill (`SKILL.md`), which `AGENTS.md` points to |
| nobody edits a clause, or code, that another agent claimed (§16) | `sor claim` and `sor lock` refuse; the edit hook only where `SOR_ENFORCE_CLAIMS=1` |
| four sections in order; names are lowercase words joined by `-`; values carry a unit and are defined outside Tests; no forward surprises (§1, §3, §4, §8, §13) | convention only |
| the compiler's duties, including never verifying its own build; two clauses that contradict each other (§14, §16) | convention only: the compiler's review and the tests find them |

A problem in a file blocks `sor lock` of the clauses in it (`sor lock --all`: of everything); a note never does.

**The plain format** reads alongside the long-hand one:
- The first sentence under the title is the `Why:`. Settings may share a line:
  `Owner: sebastian. Run: open out/index.html`. `Code: <path> (by hand)` is `Source: code at`.
- Bullets right under the title are rules. Headings are read by meaning: Rules, Must,
  Requirements, Behaviour, What → Rules · Notes, How, How it works, Design, Why, Decisions,
  Ideas → Approach · Interface, API → Contract · Checks, Examples, Acceptance, Proof → Tests.
  A heading the table does not know is read as rules.
- `offers`/`provides`/`exports` mean `gives`, `stores` means `owns`, `uses`/`requires`/
  `depends on` mean `needs`. In tests, `given:`/`when:` mean `do:`, `then:`/`should:`/`shows:`
  mean `expect:`, `by eye:`/`by hand:`/`sign-off:` mean `manual:`, `fixes:`/`regression:` mean `bug:`.
- A table may follow its bullet without indentation.
- A bullet nobody named yet is a draft: its key is `~` plus a hash of its words, so it is locked
  and tracked, but nothing can point at it: a marker naming a draft is a problem in `sor check` until tidy names it.
  A draft test is a problem (`unnamed test`) until it is named after the rule it proves or says `proves:` or `bug:`.
  A sentence outside any bullet is no item at all, and neither is a second line under the title (the header reads the
  title, one `Why:` sentence and settings): `sor check` notes it as `loose text`.
- Tidy (done by the AI for now) adds `**names**` in front of bullets that code or tests point at,
  braces around numbers they use, and the precise test lines under the person's own test line.
  It never rewords a sentence.

Choices the tool made where this spec is silent:
- Code is looked for in every `path` value a target's Rules declare, and in `Source: code at`
  folders. Unmarked lines are only allowed in the latter.
- Referring to a whole part (`{targets/web}`) depends on its header and Contract.
- Editing a table row changes the row, not its item; adding or removing a row changes the item.
  A changed, added or removed row lets the code marked with its item change too, so a table
  built as one region follows its rows; line markers (§10) tie each line to its own row.
- An alias value (`{days: = …}`) changes when the value it stands for changes, so `{year.days}`
  is flagged when Earth's row changes.
- A region marked with several ids may change when any one of them changes; the others are
  listed for review and their tests must pass again.
- The root part's lock key is `ROOT`; root items have no prefix (`year`). A lock written before the rename calls it `CLAUSES`: the tool reads that as `ROOT`, so nothing counts as changed, and the next lock writes `ROOT` with every hash as it was.
- The lock hashes code without layout, and the rule follows the type of the file. For every type not named below: no blank lines, no
  comment-only lines (`//`, `/* */`, `<!-- -->`), no indentation, one space for each run of spaces outside quotes.
  - **Python** (`.py`, `.pyi`, `.pyw`): comment-only lines are the `#` lines, and the nesting counts. Every statement carries its depth,
    in levels and not in columns, so changing 2 spaces to 4 is not a change and moving a line into a loop is. Lines that go on inside
    brackets, after a backslash or inside a multi-line string carry no depth (a string that a backslash at the end of a line continues
    is one of them), and a `#` line inside a multi-line string is text. A region is often a piece of a block: a line of the block
    around it that comes after the first line is counted one level below it (`-1:`). A coding cookie (`# -*- coding: latin-1 -*-`) is
    code, because it changes how the file is read.
  - **Shell, Ruby, Perl, R, TOML** (`.sh`, `.bash`, `.zsh`, `.rb`, `.pl`, `.r`, `.toml`): `#` lines are comments (a `#!` line and a
    magic comment such as `# frozen_string_literal: true` are code); indentation does not count. A `#` line inside a here-document or
    a string that goes over several lines is text. A quote the tool takes to be open when it is not only keeps comments as code, so
    it can make a comment edit count as a change but never hide a change to code.
  - **SQL, Lua, Haskell** (`.sql`, `.lua`, `.hs`): `--` lines, one-line `/* */` comments and one-line `{- -}` comments are comments.
    A line that starts with `-->` or `--|` is a Haskell operator, and `{-# … #-}` is a pragma: both are code.
  - A comment after code is part of its line in every type.

  Re-indenting or reformatting is not drift; a changed word, number or string is. Changing this rule changes every locked code hash
  once, and `sor lock --rehash` is that rewrite: it gives the new hash to an entry whose code is unchanged under the old rule, and
  leaves `text`, `refs` and results as they were. `sor status` says when hashes are waiting for it. Until then a change that only the old
  rule ignores, such as a Python line moved into a loop, is not seen. Not covered: YAML and Makefiles (indentation is meaning there too),
  Ruby and Perl block comments (`=begin`, `=pod`) and comments that span several lines in SQL, Lua and Haskell: their lines are code. Tool copies of different ages disagree about Python code: an older tool reads a lock
  that a newer one wrote as drift on every Python region, and refuses to lock, so update every copy of the tool together (the format number above does not help
  here: it protects against formats written from now on).

Not built yet: benchmark metrics in `measure:`, `each: N × x = gen()`, runners for non-web targets (no example here has
one: `sor test` runs nothing there, so a test with steps stays `manual:` or takes its result from `--results F` when the
project's own framework runs it, §8), running that framework from `sor test`, experiments, migrations, split locks, a
merge driver for the lock file, renaming.

## 16. Working in parallel
Several agents, or people and agents, may work on one project. Without a guard, these happen
(each reproduced on the solar-system example, see DECISIONS.md):
- a full-file Write from an earlier read erases another agent's clause change; an Edit is safe
  only because its read-to-write gap is tiny;
- two valid edits in different clauses contradict each other, and `sor check` finds nothing;
- `sor lock` accepted another agent's unbuilt clause change, because it locks the whole project;
- the edit guard keys on clauses, not on who edits: once a clause changed, any agent may edit its code.

What the tool does about it:
- **Claims.** `sor claim <id …> [--as NAME]` says which clauses you work on. A claim holds the
  clauses (a part holds its items, an item its rows, values and own test) and the code regions
  marked with them. Two agents conflict when their claims overlap in either: the same clause, a
  part and its item, or two clauses marked on one region. A clause that shares *another* region
  is not held: claiming the moon does not lock out the light. Claims expire (default 30 minutes, `--ttl` changes it)
  so a crashed agent does not block the project; `sor claim` prints the lifetime (`claimed audio until 00:31 (30 min)`).
  To add a clause, claim the part that will hold it. A claim on a part holds its own items; it does not hold the child
  parts under it, so another agent may claim `audio/mixer` while `audio` is claimed (the plain `sor lock`, below, is what
  covers the child parts). A claim of several ids takes all of them or none.
- **Identity** is found automatically: `--as NAME`, else `SOR_AGENT`, else the Claude Code session
  (the Bash tool exports `CLAUDE_CODE_SESSION_ID`; hooks get the same id as `session_id`: checked equal
  live on 2026-10-18). So an agent never has to say who it is. Each claim also records the `session` it was made
  in. The edit hook compares sessions, never names: a claim made under `--as` still protects its own session's
  edits, a claim by another session blocks them, and a claim by a person at a terminal (no session) blocks every
  agent; an old claim without a `session` field is compared by name. **Subagents share their parent's session id**
  (checked live: the Bash tool and the hook both report the parent's id; the hook also sees a different `agent_id` per
  subagent, the CLI cannot). For the hook the subagents of one session are therefore one agent. At the CLI an agent is
  a session plus a name: a parent that runs subagents in parallel gives each its own name and has it pass `--as <name>`
  on every claim, lock and release (a shell variable does not survive between calls), and does not claim what it
  delegates. Two subagents then conflict at `sor claim`, and so do two chats that both use the same name. The hook does
  not enforce between sibling subagents, so a subagent that skips claiming is not stopped. Claims are advisory: the tool records and shows them (`sor status`, group `claims`, and `claims` in
  `--json`) and `sor lock` respects them, but an agent that never claims is not stopped. The edit hook checks
  them only when `SOR_ENFORCE_CLAIMS=1` is set for it (next points).
- **Releasing follows the name.** `sor release <ids>` and `sor release --all` by a caller that names itself (`--as NAME`
  or `SOR_AGENT`) free only that agent's claims: another agent's claim named by id is `NOT released (held by someone
  else; --force overrides)` and exits 3, and `--all` leaves it alone. A caller that gives no name (the parent, or the
  only agent) frees every claim made in its session under any name, so it can clear what its subagents left behind.
  A subagent that forgets `--as` cannot be told from the parent, and its `release --all` frees its siblings' claims too:
  each subagent passes its own `--as <name>`, and the parent's last `sor release --all` carries no name at all (no `--as`,
  and `SOR_AGENT` unset, for that is a name too).
- **Scoped lock is the default.** `sor lock <ids>` locks those clauses (a part named brings its own items, not the child
  parts under it); a plain `sor lock` locks what you claimed, and is refused when you claimed nothing; `sor lock --all`
  locks the whole project and is refused while another agent holds a claim. A plain `sor lock` also locks, with each
  claimed part, the child parts under it that have a change of their own (new, changed or removed), those made after the
  claim included, and prints `locking the parts under them too: …`. A child part that another agent's claim overlaps is
  left out and named (`not locking audio/mixer, which is claimed: …`); a problem in a child part that is taken in
  refuses the lock like any other in its scope, and `sor lock <ids>` leaves it out; `ROOT` is not expanded, for its
  child parts are the whole project. A claim on a part does not hold its child parts against other agents (above): only
  the plain lock covers them, so that work on a part is not left pending, or locked with `--all`. A clause that shares
  code with the ones locked is locked too when its entry would change, and the lock is refused when that clause has a
  change of its own. A clause the locked ones refer to keeps its old hash in their entries, so they are flagged for
  review once it is locked. Problems in files outside the scope, and drift elsewhere, do not block a scoped lock; nor does a problem of one item's
  own text (`broken`, `needs`, `proves`, `expect`) that lies in an item the lock does not cover, in a file it does cover
  (the lock says how many it left out). A draft test (`unnamed test`), an unfilled `<fill in …>` and a problem that is no
  item's own text (a heading written twice, a name used twice) still block it, and the refusal names the agent that holds the
  item the line lies in. The
  glue of a file that holds nothing but glue (an `__init__.py`) goes with every scoped lock, since no clause could ever
  claim it. Locking a part also retires the entries of items that left it since the last lock (moved to another part,
  where they are new, or deleted): they belong to the nearest part above them that still exists. Several scoped locks at
  once keep each other's entries: the lock is re-read and merged under a short mutex.
- **Edit guard (on where `SOR_ENFORCE_CLAIMS=1` is set for the hook: this repository's settings and the plugin).** The hook refuses an edit to a clause, or to code
  on a region, that another agent holds. It names who, since when and until when at the latest, and
  the agent decides: take another clause, wait and retry (the holder may release sooner), or ask.
  It cannot tell who edits without a `session_id` and then allows. Without the variable it is off, as it
  must be wherever the hook's `session_id` is not the id the CLI finds in `CLAUDE_CODE_SESSION_ID`: if they
  differed, an agent would be refused by its own claim.
- **The claims file** (`sor/.sor-claims.json`, `{"claims": [{agent, asked, keys, regions, session, since, until}]}`) is
  written whole through a temp file and a rename, under a short mutex (`sor/.sor-claims.lock`, an `O_EXCL` file broken
  when older than 10 s); temp files older than 5 minutes are removed. A claim that expired is kept for 2 hours as a
  tombstone (`claims.TOMBSTONE`), only so that its holder can be told (next point); every write of the file prunes the
  older ones, and a tool from before tombstones sees them as expired claims, which they are. The file is deleted when no
  claim and no tombstone is left, so a project where everyone has released has nothing left in it.
- **Expired claims tell their holder.** A claim that expires while its holder works does not stop it, so the holder is
  told at its next lock or release. `sor lock` with no ids, when all its claims expired, is refused with "your claims on
  X, Y expired at 00:31; claims last 30 min by default: claim again, `--ttl 2h` for longer". A no-ids lock that covers
  live claims prints a `warning:` for the expired ones, which are not in that lock. `sor release` says "nothing to
  release: your claims on X expired at 00:31", or adds it as a `note:`. Once the agent claims the same clauses again,
  the tombstone is no news and goes.
- **Exit codes:** a refused claim or release is 3.
- **Not covered:** claims stay inside one workspace (another one, such as a git worktree, a Perforce client or a
  Lore instance, or another machine does not see them: sharing them needs a shared place that differs per
  environment, and none is built); contradictions between clauses (the compiler's review and the tests find those); a Write
  by an agent that does not use the hook; the read-to-write gap of an Edit; a claim that expires
  while its holder is still working (it is not stopped, but the tool tells the holder at its next `sor lock` or
  `sor release`, above: claim again and re-read the clause first; an agent that does neither is not told); two agents that
  both break the same stale mutex file after a crash can both enter the critical section; Windows
  (`os.replace` may fail while a reader has the file open) was not tried.
