# Proposal: the merger's side of Spec of Record

Status: written, not built. Evidence: one long orchestration of about 25 branches that agents built in their own worktrees, merged by one orchestrator, in a project with about 4,500 lock entries. The read of the code is marked "read", a check I ran is marked "shown". Nothing here was reproduced in a temporary project yet.

## The goal
An agent that works in a worktree locks its work and keeps its claims until the merge ("When a claim of yours was freed", `reference/parallel-agents.md`). Whoever merges then has to finish the locks and free the claims. Today that takes many manual steps, and one of them looks like a bug.

## Built with this proposal (branch `skill-improvements`)
- The `--as` hint of `sor lock` no longer names a subagent's claims (shown by a test): subagents share the parent's session id, and following the hint would lock a live agent's unfinished work.
- The skill and `reference/parallel-agents.md` agree on release: an agent in its own worktree keeps the claims on work it locked; whoever merges releases them. A section "Merging a worktree branch" says how.
- `sor check` notes a code region that serves more clauses than SPEC §13 allows (`wide region`). The number is a first guess for the maintainer to confirm. Run on the project that showed the problem, it names 79 regions (the two that blocked correct one-line changes serve 22 and 8 clauses; the next widest serve 21 and 19), and 3 regions in `editors/vscode`, none in `examples/solar-system`. All of them are plain `@clause` regions, which is the kind the note counts.

## 1. Claims that stay after the merge (a symptom seen, a cause not yet known)
Observed more than once: after a branch was merged, `sor claims` kept saying "waiting for the merge … has not reached this copy" until the merger released the ids by name (`sor release --as <holder> <ids>`).

`decide()` in `claims.py` calls a holder's work arrived when "it locked work, left nothing unfinished, and every entry it changed differs from the grant in this copy too" (`arrived`, about line 978). It compares **lock entries** with the claim's base, and `all(...)` means that one entry left at the base keeps the claim waiting.

### Cause (replayed from git history of the one merge checked, not yet reproduced in a temporary project)
The claim records were gone (released claims are dropped), so I rebuilt the arrival test from git: the lock at the merge base (the grant's base), at the branch tip (what the holder locked) and in the merging copy, after the merge and after every later commit.
- The holder had locked 20 entries since the grant.
- Git reported a textual conflict in `sor/sor-lock.json` for that merge, although no entry had changed on both sides. The cause is plain: this side had inserted a new glue entry right in front of an entry the branch had changed, and the blank-line separator of lock format 4 does not keep two hunks apart, because all blank lines are equal and git aligns them freely.
- The merge script then took main's side of the file, as SPEC §11 tells the merger to. That dropped all 21 entries the branch had locked. The merged lock was identical to main's before the merge.
- So all 20 of the holder's entries were still at the grant's base in the merging copy, and they stayed there for every later commit until the claims were released by name. `arrived` needs every one to differ, so the claim never arrived. The re-lock of those entries was held up by the claim itself, because the holder's own claim kept its code regions: a circle.
- H2 (one entry at the base is enough) is also true of the code, but it was not needed: here every entry was at the base.

Reproduced: `test_sor_lockmerge.py` builds a git repo in a temporary folder where one side inserts a lock entry next to an entry the other side changed. Git alone reports a conflict. Built: `sor merge-lock` (below), which merges that case cleanly.

Still open: a claim that is stranded although the lock merged cleanly. With the lock merged by entry, the holder's entries reach the merging copy, so the first check should be that `sor claims` then frees the claim by itself (a worktree test with claim and lock). If it does not, option A below is needed.

### What not to build
Do not decide arrival by git ancestry of the commit that was HEAD when the agent locked. An agent often locks before it commits, on top of the tip it was cut from. That commit is already an ancestor of the merging copy, so the claim would be freed at once, with the work unmerged. SoR also says it "knows nothing of git" (SPEC §16, Queued).

### Options
- **A. Compare the code, not the lock** (if H1 or H2 is confirmed). At lock time the claim records the code hash of each key it locked (next to `locked_keys`). `decide()` calls the work arrived when this copy's code for those keys has the same hashes. That is independent of whether the merger finished the lock, and it is the thing the claim protects. Needs a claim format addition and SPEC §16 text.
- **B. A merger release.** `sor release --merged <holder>`, which frees a holder's ids only when A's comparison says the work is here, and refuses otherwise, with the hook asking nobody. It replaces acting under the holder's name, which the skill now allows for a finished and merged holder as the only way.
- **C. Both.** A makes the free automatic; B is the explicit step when it cannot be.

Recommended: the key-level lock merge of section 2 first, because it removes the cause seen here. Then A, if a claim can still be stranded after a lock that merges cleanly, and B only if A leaves cases.

## 2. A merge driver for the lock file: worth building (this reverses my first view)
SPEC §15 lists it as not built. My first analysis looked only at entries both sides had changed differently, found few, and concluded that a driver would not help. That was the wrong question. Measured on the last 60 merges of the project (git's own merge-tree against the same merges):
- 41 merges had no textual conflict in the lock file, and none of them had an entry changed on both sides.
- 19 merges had a textual conflict. In 11 of them no entry was changed differently on both sides: git conflicted because a new entry sat next to a changed one. A merge by key would have merged these cleanly.
- In the other 8, 1 to 6 entries really differed (entries that several clauses share through a code region, and glue). The right value depends on the merged code, so those still need a re-lock, but only those.

Restoring one side of a file that conflicts only by adjacency is not harmless: it drops the other side's locked entries (section 1). A merge by entry keeps them and leaves only the real conflicts. That is the fix to build first. It also needs no change to the claim format.

Built (SPEC §11, `sor merge-lock`, a git merge driver). Run on the 19 merges of the engine project that git reported as lock conflicts: 11 merge with nothing left out, the others leave out 1 to 6 entries, and restoring main's side in those 19 merges would have dropped 3,545 entries the branches had locked. The entries it leaves out are listed as new by `sor status` and need `sor lock`.

## 3. Rules that nothing proves (not built)
A rule with no code and no test can go stale without any flag. Example: "Until the owner decides otherwise: consoles, … The editor is out of scope." stayed in a root file for the whole life of the project while the editor grew into the largest part. `sor status` compares text with code and cannot know.

Proposal: a note (not a problem), `unproven`, for a rule or approach item with no test, no code and no `needs`/`gives` pointing at it, whose text names a part that has changed in the lock since the rule was last locked. The check is a word match against part names; it will have false positives, which is why it is a note. A `sor check --unproven` list for the iteration close is enough to start with.

## Not changed on purpose
- No "attested no-behaviour-change" path for the edit guard. The guard pushed agents into cosmetic clause edits to unlock correct code (observed: cross-references added to four clauses; a clause reworded to move one constant out of a shared region). That is a symptom of wide regions, which the new note addresses. A bare attestation would be the escape hatch the design review (F4, F10b, F30) already criticises. If a move path is added, it should ask the user in the hook like `--already-fits`.
- No shorter skill. The body is 2,200 words and routes to eight reference files; nothing seen was caused by its length.
