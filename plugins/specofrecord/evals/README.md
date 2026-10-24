# Behavior evals for the skill

These cases run a model against the plugin and grade its answer. They call the model, so they cost money and are run by hand, not with the unit tests,
from the root of this repository:

    claude plugin eval plugins/specofrecord --runs 6 --ablation none --no-publish --trust-plugin

The results go to `evals/results/` here (git and the plugin zip leave it out).

- `worktree-vs-claims`: the agent already has the skill loaded and cannot open the reference files. Asked whether another agent can pick up other work
  at the same time, it must say that agents sharing a folder coordinate through claims, and not send the other agent to a separate worktree or clone.
  Two graders: `criteria` (a model judges the answer) and `same-folder` (the answer says the agents share a folder). The first passes on text that
  never says who sees a claim, so `same-folder` is the one that fails when `SKILL.md` stops saying it. `test_sor_docs.py` checks the sentence is there.
