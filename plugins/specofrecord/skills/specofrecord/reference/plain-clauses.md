# Clauses written in plain sentences (tidy)
Clauses may be written in plain sentences: bullets under the title, Tests and Notes, no names. Before building, tidy
them:
- Add a `**name** - ` in front of each bullet that code or a test points at. `sor check` says `unnamed test` for a test
  bullet without one: name it after the rule it proves, or add `proves: {rule}`.
- Wrap a number a test uses in braces (`{max: 6x}`).
- Write the precise `do:` / `expect:` lines under the person's own test line, where the web target's probes can say it
  (see "A loose test").
- Never reword their sentences and never add a test they didn't write; propose those instead.
- `code: path#name` under a rule points at the function that implements it.

## A loose test
A loose test ("test that the moon circles around") is a bullet in Tests, named after its rule (or add `proves: {rule}`).
`do:` / `expect:` lines are run by `sor test` against the web target's probes. When the probes can say what the test
checks, write those lines under the bullet. When they cannot, or the project has no web target, give the bullet no such
lines and write the test in the project's framework under `// @clause test <part>/<name>`, in a folder a target declares
(`{path: test/}`). `sor test` then shows it as EXTERNAL. Lock with `sor lock --results F`, where F holds its result (with
a web target, add `--run-tests`).

## Loose text
`sor check` notes `loose text` for a sentence that belongs to no bullet: it is not locked, and a change to it goes
unnoticed. Make it a bullet (`- **name** - ...`), or indent it under the item it continues; in the header, join it to the
`Why:` line. Do that only in a part you are writing or changing in this task, and mention older ones at most once.
