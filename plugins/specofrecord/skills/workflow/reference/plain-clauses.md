# Clauses written in plain sentences (tidy)
Clauses may be written in plain sentences: bullets under the title, Tests and Notes, no names. Before building, tidy
them:
- Add a `**name** - ` in front of each bullet that code or a test points at.
- Wrap a number a test uses in braces (`{max: 6x}`).
- Write the precise `do:` / `expect:` lines under the person's own test line.
- Never reword their sentences and never add a test they didn't write; propose those instead.
- `code: path#name` under a rule points at the function that implements it.

## A loose test
A loose test ("test that the moon circles around") is a bullet in Tests, named after its rule (or add `proves: {rule}`).
With no `do:` / `expect:` lines, write it in the project's framework under `// @clause test <part>/<name>`, in a folder a
target declares (`{path: test/}`). `sor test` then shows it as EXTERNAL. Lock with `sor lock --results F`, where F holds
its result (with a web target, add `--run-tests`).
