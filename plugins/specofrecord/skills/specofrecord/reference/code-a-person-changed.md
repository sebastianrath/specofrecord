# Code a person changed ("keep my change")
A person edits the code themselves, because they know better. The edit guard watches only your own edits, so theirs
goes through and shows up as **drift** in `sor status`. Its lines say who changed them and when, where git can tell.
`sor lock` refuses until the clause says the same, and the way out is the clause, not a revert.

Whose drift it is:
- Drift that was already there when you started is the person's. Keep their code and follow the steps below.
- Drift that appears after your own edit is yours: revert the edit, or change the clause, then redo the edit.

Keep their code and bring the spec in line:
1. `sor show <id>` for each drifted clause, with the version control system's diff of those lines, if there is one, when it helps to see what changed.
2. Claim the clauses (see "Claims" in the skill).
3. Edit each clause so it says what the code now does: the value, the table row or the item, in the person's words
   where you can. Leave the code alone.
4. Change the clause's test to match when the behaviour changed. Never weaken a test.
5. `sor status` now lists those clauses as changed, with their code updated. Run `sor test` and lock them (see
   "Locking" in the skill), then `sor release --all`.
6. Tell the person in plain words what you wrote into the spec, so they can read it. If the change contradicts another
   clause, or looks like a slip and not a decision, say so and leave that clause unlocked.
