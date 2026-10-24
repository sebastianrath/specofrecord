---
type: llm
weight: 1
---

Pass only if the answer tells the user that another agent can work on a different part in the SAME folder/checkout at the same time, coordinated by Spec of Record claims (each agent claims its own parts; a claim on something held by another agent is refused).

Fail if the answer offers a separate git worktree, clone or copy of the project as the way to avoid edit or claim collisions between the agents, or says the agents would conflict unless isolated. Advice to keep build output apart (a separate build folder) is fine and is not a fail, and so is mentioning that a worktree would NOT see the claims.
