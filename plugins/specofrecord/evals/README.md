# Behavior evals for the skill

These cases run a model against the plugin and grade its answer. They call the model, so they cost money and are run by hand, not with the unit tests,
from the root of this repository:

    claude plugin eval plugins/specofrecord --runs 6 --ablation none --no-publish --trust-plugin

The results go to `evals/results/` here (git and the plugin zip leave it out).

- `claims-across-folders`: the agent already has the skill loaded and cannot open the reference files. Asked whether another agent can pick up other work
  at the same time, it must say that claims are seen from every working folder of the project (one folder, git worktrees, clones or workspaces that share a `SOR_CLAIMS_DIR`), so
  the other agent may work in the same folder or in a worktree of its own, and must not say that a worktree defeats the claims.
  Two graders: `criteria` (a model judges the answer) and `across-folders` (the answer says claims are seen across working folders). The first passes on text that
  never says who sees a claim, so the second is the one that fails when `SKILL.md` stops saying it. `test_sor_docs.py` checks the sentence is there.
