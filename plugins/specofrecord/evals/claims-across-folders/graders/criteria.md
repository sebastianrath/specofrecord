---
type: llm
weight: 1
---

Pass only if the answer tells the user that another agent can work on a different part at the same time, in the same folder or in a git worktree of its own, and that Spec of Record claims coordinate them either way (each agent claims its own parts; a claim on something another agent holds is refused, and the claims are seen from every working folder of the project).

Fail if the answer says that an agent in another worktree, clone or folder would not see the claims, or that the agents would conflict unless they share one folder, or that a separate worktree defeats the claims. Advice to keep build output apart (a separate build folder), or that a clone needs `SOR_CLAIMS_DIR` to share the claims, is fine and is not a fail.
