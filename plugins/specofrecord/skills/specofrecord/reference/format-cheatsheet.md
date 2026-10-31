# Spec of Record: the format cheat sheet

Copied from SPEC.md of Spec of Record by Sebastian Rath (sebastianrath.io), licensed CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). The full format is in SPEC.md of the project.


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
Targets: py, ts                                    optional, the targets clauses apply to; a part may override

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
`## Tests` (every line of a table counts), 5 lines per test, 80 words per item (a table's words do not count), 12 child parts
per part. More items than that: make the part a folder of child parts; more child parts than that: group them under parts of their own.

