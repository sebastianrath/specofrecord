# A bug report ("this is broken", a ticket)
A bug report, from a person or a ticket system, is input. The spec decides what is right, and the ticket never
changes a clause by itself. Before any edit, answer three questions:
1. Is it a bug against a clause? Find the clause (`sor show <part>`, `sor markers <file:line>`) and read what it says.
2. Must the clause change?
3. Must the code change?

| What you find | What to do | Owner's OK first? |
|---|---|---|
| Clause right, code wrong or incomplete | Give the clause a test that fails (below). Fix the code. Run the tests (`sor test`, or your own framework's), lock. | no |
| Clause wrong and code wrong | Change the clause, then the code, then a test that carries the ticket in `bug:`. | yes: behaviour changes |
| Clause right but missing something, code too | A spec gap, not a regression. Add a new clause (it shows as Added), build it, test it. `bug:` on the test is optional. | yes |
| Code right, clause only worded badly | Fix the wording and lock. The code is not touched. Tell the person it was wording only. | no |
| Code does what a flawed clause says | A requirements change, the same path as "clause wrong and code wrong". | yes |
| Works as the clause says (a feature request, a misunderstanding) | Change nothing. Quote the clause in your answer. | n/a |
| The clause is ambiguous | Add an `open:` question to the clause for the owner (it stays out of the lock text). Change nothing else. | the owner answers |
| Cannot be reproduced | No failing test can be written. Change nothing, and say what you tried. | n/a |
| Known, fix postponed | `bug: #id open` on the test, then lock with `--allow-incomplete`. | no |
| Bug in wiring or unmarked code | Add a clause for it, or fix the `@clause glue` region with a clause change. | yes if behaviour changes |
| Bug crosses a shared or contract item | Several parts and claims: claim them all, change them together, lock them together. | yes |
| The test itself is wrong | Fix the test. Never weaken it to make it pass. | no |

**The test that frees the code.** The edit guard refuses code whose clause did not change. For a bug it accepts a new or
changed test that proves the clause. Two ways, the first one when the scenario is small:
1. Add the scenario to the clause's own test: another `do:` / `expect:` pair (a test may repeat them) and a `bug:` line
   with the ticket (a test may carry several).
   ```
   - **space** — click Pause, press space → running again (bug #3); Space twice in a row too
     do: press(Space) · press(Space)
     expect: paused is false
     do: use(pause) · press(Space)
     expect: paused is false
     bug: #3
     bug: PROJ-123
   ```
2. A second test, when the scenario needs a setup of its own or the first test is already long. Names are unique, so it
   cannot be named after the clause: it says what it proves with `proves: {clause}`. This works for every clause, with or
   without values.
   ```
   - **space-twice** — Space twice in a row → running again
     proves: {space}
     do: press(Space) · press(Space)
     expect: paused is false
     bug: PROJ-123
   ```
   Keep `expect:` a comparison: `expect: {space}` alone is not a line `sor test` can run, and `sor check` reports it.
   A reference in `do:` proves nothing.

Write the test first and run it: it must fail on the buggy code. Fix the code, run it again, then lock the clause (claim it first)
with `sor lock --run-tests`, or, with no web target, with `sor lock --results F` from your own framework's run. The test keeps its `bug:` line for good: it is what the next person sees under
Fixes in `sor changes`, and it is never deleted silently.

**What goes where.**
- The ticket id or a few words: on the test, in `bug:`. Nowhere else.
- Not on the clause: it says how things work now, and its text is part of the lock, so a ticket id there forces a recompile
  and goes stale. A reason that belongs on a clause goes in `because:` in words.
- Not in code comments. The chain marker → clause → test → ticket is enough.
- The history is the project's version control.

**A wrong or stale ticket.** Checking the ticket against the spec before acting is your job; judging the ticket system is
not. If the ticket contradicts a clause, do not rewrite the clause and do not change the code: tell the person which clause
disagrees, add an `open:` question to it, and let the owner decide. Never write back to the ticket system (comment,
close, reassign) unless the person asked for it.
