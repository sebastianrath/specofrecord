# Putting existing code under a spec
"I'm about to change X, put it under Spec of Record" in a project that already has code means the asked area only,
never the whole project. The rest stays as it is, and the edit guard does not govern it.
1. Read the code of that area (a feature or a folder) and leave it alone: do not rewrite, move or tidy it.
2. If `sor/SPECOFRECORD.md` does not exist, write it: why the project exists, one `out-of-scope` rule saying that only
   the asked areas are specified, and a `parts` item. Then one part file per asked area, headed `Source: code at <folder>/`,
   so the existing code stays the truth for how it works inside.
3. Write the clauses for what the code does today, in plain words, with its numbers in braces; never what it should
   do. Point each rule at its function with a line `code: <path>#<name>` under it. Say anything you could not tell from
   the code as `open: <question>`.
4. Write a test for each rule that you checked by reading or running the code. `manual:` with a reason when there is no
   test runner. Never write a test for behaviour you did not check.
5. `sor check` until 0 problems, claim the parts, `sor lock`, release. That records today's state. Only then make the
   user's change, as in the next section: clause first, then the code. Code changed alone shows up in `sor status` as
   "check the clause still holds".
6. Tell the user which areas are now specified, which are not, and the open questions.
