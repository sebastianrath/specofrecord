# Todos
Why: keep a todo list from the command line.
Owner: the cli team

## Rules
- **limits** — a title has 1 to {max: 200 characters}.
- **sun** — size {size: 28}, color {color: #FFC93C}.
- **list-time** — listing {todos: 10000} todos takes at most {budget: 50 ms}.
## Approach
- **storage** — one JSON file in the home folder.
  because: no server needed, and `people` can read it.
  limit: {list-time.budget}
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
- **positions** — after one year, Earth is back.
  do: slider(100) · remember body(earth) · step(1)
  expect: body(earth).x changed by 0 ± 1
  expect: startAngles unchanged
- **delete-last** — deleting the last todo works.
  bug: #12
  proves: {limits}

# Plain
Watch the planets go round.
Owner: sebastian. Run: open out/index.html

- **zoom** — Zoom stays between {min: 0.3x} and {max: 6x}.
  code: out/index.html#zoomAt
- offers **table** — every body.
- uses {clock/time} — time passed.

## Rules
- calm and roomy
## How it works
- a base scale fits it all
## Checks
- **zoom** — zoom in forever, stops at 6x
  given: zoomSteps(200)
  then: zoom = {zoom.max}
  by eye: looks calm
  fixes: #9
