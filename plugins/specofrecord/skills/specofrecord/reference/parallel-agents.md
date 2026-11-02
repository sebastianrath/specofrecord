# Working beside other agents

## Contents
- What a claim is
- Who you are
- Subagents
- Two agents on one clause, one language each
- When a claim of yours was freed
- When a claim refuses you
- Locking while others work
- Merging a worktree branch

Use this when more than one agent, or a person and an agent, work in the same project at once, or when you start
subagents. The everyday rules (claim before you edit, what to do on REFUSED, lock only your own clauses, release when you
stop) are in `SKILL.md`, under "Claims" and "Locking".

## What a claim is
A claim says which clauses you work on. The tool records it, `sor status` shows it in the `claims` group, and `sor lock`
respects it. It is advice: an agent that never claims is not stopped.

Every working folder of the project sees your claims: the agents in your folder, in other git worktrees of the repository, and in clones or
Perforce workspaces whose users set the same `SOR_CLAIMS_DIR`. So you do not have to put agents in one folder to keep them apart, and you may give each its own
worktree. A claim holds a clause and the code marked with it. It does not hold glue (`@clause glue`), files the edit guard does not govern
or build output: agents in one folder share all three, and agents in worktrees each have their own and meet at the merge.

A claim is held while its holder works. It does not run out under you: after 30 minutes without activity (`Claims: idle` in the root file changes that) the holder is
*quiet*, and what happens to the claim is decided when another agent asks for the clause, by what you left behind:
- you left nothing, or your session ended and what you left is in the folder the asker works in: the claim is freed, and you are told when you come back;
- you left unfinished work in another worktree: the claim is *parked* with it; another agent may continue it (`sor claim --take-over`), and it frees itself after the parked window (24 hours by default,
  `Claims: parked 12h`);
- you finished and locked work in your worktree that is not merged yet: the claim *waits for the merge*, with no limit, and is freed when the work reaches the asker's copy or you release it; whoever merges may say
  `sor queued <your name> --by <their name>`, which only changes the notice (queued, or nobody has said they will merge it). So an agent in a worktree does not release what it locked: it keeps the claims until the merge
  ("Merging a worktree branch", below), and releases only what it claimed and did not lock.
A long build that runs in the background does not make you quiet: the claim stays while it runs.

## Who you are
The tool knows who you are from your Claude Code session, so you do not have to say. Pass `--as <name>` (or set
`SOR_AGENT`) only to act under another name. `--as` belongs to `sor claim`, `sor lock` and `sor release` only: any other
command refuses it. An agent that is not Claude Code has no session: it chooses one name and passes `--as <name>` on every
claim, lock and release. Another name is another agent.

## Subagents
Subagents share your session, but Claude Code tells the hooks which subagent acts, and a subagent names itself. When you run subagents in parallel:
- Each passes its own name with `--as <name>` on every claim, lock and release. The hook refuses a claim, lock or release from a subagent without one, and refuses a name that a sibling already uses.
  A shell variable would not survive between calls. The name binds the subagent: the edit guard attributes its edits to the name, so it is refused a clause a sibling or its parent holds.
- Do not claim what you delegate, because your claim would block your subagent's.
- A subagent releases with its own name (`sor release --all --as <name>`; one in its own worktree keeps its claims on locked, unmerged work, as above): that frees only its claims, and another agent's
  claim named by id is left alone ("NOT released (held by someone else)", exit 3). Nobody runs `sor release --force`: the hook refuses it.
  `sor release <id>` gives up that id only: the other ids you claimed in the same call stay held (`still holding: …`), and an id under a part you claimed is "NOT released" until you release the part.
- A finished subagent's claims are not kept alive by you working on: only its own activity renews them, and it is gone once it stopped.
- Your own final `sor release --all` has no `--as`, and `SOR_AGENT` is not set in your environment (it is a name too, and
  your subagents share that environment). A caller that gives no name frees every claim of the session, so it also clears
  what a subagent that crashed left behind. It frees the claims that subagents keep on locked work in their worktrees as well, so run it
  only after those branches are merged, or release by id.
- Claim items, not whole parts, when others work in the same part: a claim on a part holds all its own items, so another
  agent's claim on an item inside it is refused until you release, and your claim on the part is refused while someone
  holds one of its items (child parts are separate). Claim the part only to add an item to it.
- A `sor lock` of your own items is not held up by a broken reference (or a bad `needs`, `proves` or `expect`) in another
  agent's item, even in the same file: the lock says how many problems it left out, and `sor check` still lists them. An
  unnamed test, an unfilled `<fill in …>`, a heading written twice and `sor lock --all` still wait, and the refusal names
  who holds the item the line is in.
- Run `sor check <your parts>` instead of a plain `sor check`: only the problems and notes of those parts and of the parts
  inside them are shown, and the exit code follows only them, so another agent's unfinished part does not fail yours.
  `audio` covers `audio/mixer`, not `audio-fx`; `ROOT` is the root file alone.

## Two agents on one clause, one language each
In a project that says its targets (`Targets: py, ts` in the root file) a clause has code in more than one language, and an id may carry the
language: `greet/hello@py`. Use it when another agent rebuilds the other language of the clause at the same time.
- `sor claim greet/hello@py` holds the Python side only: its lock line, the lines of its test and of its table rows, and the code in the Python files. Another agent may
  claim `greet/hello@ts` at once. Nobody can change the clause's text while either of you holds a language of it, because your code is built for
  that text. To change the clause, claim the whole clause (`sor claim greet/hello`), which holds every language and waits for them.
- The order for a clause that changes: the agent that changes the text claims the whole clause, rebuilds the language it works on, and locks the
  clause (`sor lock greet/hello`), which is refused while another language would stay behind. Only when the user has said that a language is rebuilt by
  someone else, it adds `--allow-behind ts` (the hook asks the user first) and gives the result of the Python test only (`--results` with
  `greet/test:hello@py`). The clause is locked then, `ts` is listed as behind, and the TypeScript test waits for its own result.
- The other agent claims `greet/hello@ts`, changes the TypeScript code, runs the tests, and locks it with `sor lock greet/hello@ts`. That lock writes the
  TypeScript line, the line of the clause's test in TypeScript and the glue of the TypeScript files, and nothing else, so it cannot undo what the first
  agent locked. It is refused while the clause has an unlocked change ("lock the clause first"), for code that did not change (use `--already-fits ts`
  only after you checked that it fits the changed clause as it is), and while the test in that language has no passing result (`--results` with
  `greet/test:hello@ts`).
- A language that is `behind` the clause, or has no code for it (`Targets:`), gets its code first. `--already-fits T` is only for code of T that you read against the changed
  clause, and `--allow-behind T` only if the user says so; the hook asks the user before either runs.
- Two clauses that share one code region in a language are locked together: `sor lock greet/hello@py greet/bye@py`.
- A lock of one language tells you which other languages of the clause are still behind or without code. When you release a language that has code
  that is not locked, `sor release` says so.

## When a claim of yours was freed
A claim whose holder fell quiet and left nothing is freed by the next agent that asks for the clause, and another agent may hold it since. A claim that someone took over is no longer yours either.
The tool tells you when you come back to `sor lock` or `sor release`:
- `sor lock` with no ids, when all your claims were freed, is refused with "your claims on X, Y expired at 00:31 (or: taken over by NAME at 00:31); claim
  again (a holder is quiet after 30 min idle by default; `--ttl 2h` for a longer window)".
- A `sor lock` that still covers live claims prints a `warning:` for the freed ones, which are not in that lock; a `sor lock` that names clauses you lost is refused until you claim them again.
- `sor release` says "nothing to release: your claims on X expired at ...", or adds the same as a `note:`.

Then claim again and re-read the clause before you go on, because someone may have changed it meanwhile. The tool keeps this news for a few hours only, and only `sor lock`
and `sor release` say it: an agent that does neither is not told.

## When a claim refuses you
`sor claim` prints REFUSED and exits with 3. The refusal says who holds the clause and why it stands. A claim takes
all its ids or none: the REFUSED line names only the ids in the way, and a line below it says which of the others were free
but were not claimed either, so claim those on their own. Do not edit that clause or its code, and do not look for a way
around it (never `sor release --force`: the hook refuses it). Then decide by what the refusal says:
- *held*: its holder is at work. Take another clause, wait a little and try again, or ask the user.
- *parked*: its holder is gone and left unfinished work in another folder (the refusal names it and the branch). `sor claim <ids> --take-over` continues that work, with nobody asked: do it in the folder
  named, which the claim now records; the changes there are the previous agent's unfinished work, not a person's change to keep. From a session isolated in a worktree the main checkout cannot be edited:
  hand the work to a session that can, or take another clause. A parked claim frees itself after the parked window.
- *waiting for the merge*: its holder finished and locked work that is not in your copy yet. Take another clause, or update your copy once the work is merged (the claim is freed when it arrives).
  The notice says whether someone has queued it.

Tell the user which clause blocked you and who holds it.

## Locking while others work
Lock only your own clauses, as in "Locking" in `SKILL.md`. A plain `sor lock` locks what you claimed and also the child
parts under a claimed part that have a change of their own (new, changed or removed), those you made after the claim
included: it says "locking the parts under them too". A child part that another agent has claimed is left out and named
("not locking audio/mixer, which is claimed: ..."): leave it to them. `ROOT` is not expanded, so claiming the root does
not lock the whole project. A problem in a child part that is taken in (a `<fill in: ...>` left in it, say) refuses that
lock like any other problem in its scope; `sor lock <ids>` locks exactly what you name and leaves the child part out.

A claim on a part does not hold its child parts against other agents: someone may claim `audio/mixer` while you hold
`audio`. So claim the child parts you will change as well when that matters. Never lock the whole project (`--all`) while
others hold claims: the tool refuses it, because it would also accept their unfinished work.

## Merging a worktree branch
For whoever merges a branch that another agent finished in its own worktree (an orchestrator, a merge queue, a person). That agent locked its work
and kept its claims, as "When a claim of yours was freed" and `SKILL.md` ("Claims") say.
1. If the merge will not happen at once, say so: `sor queued <holder> --by <your name>`. It changes the notice and nothing else.
2. Merge the branch. Set the lock merge up once per clone: the line `sor/sor-lock.json merge=sor-lock` in `.gitattributes`, and `git config merge.sor-lock.driver "sor merge-lock %O %A %B"`. The `.gitattributes` line is committed, the `git config` entry is per clone: a clone without it merges as git alone does. The driver merges the lock by entry and names the entries that
   both sides changed, which step 3 locks again; it exits 1 then, so git lists the file as conflicted: lock them, then `git add` the file. Without it git often reports a conflict in `sor/sor-lock.json` although no entry changed on both sides (a new entry next to a changed one is enough). Do not edit a conflicted lock by hand: restore one
   side's file (`git checkout --ours sor/sor-lock.json`, or `git checkout --theirs sor/sor-lock.json`) and `git add` it. That drops the other side's entries, which is why step 3 follows.
   Perforce: its own resolve reports the same adjacency case as a conflict. Set `P4MERGE` to a script that is called as `script BASE THEIRS YOURS RESULT`, copies YOURS over RESULT, and runs `sor merge-lock BASE RESULT THEIRS`; answer `m` at the
   resolve prompt (tried with p4d 2025.2). Perforce ignores the tool's exit code, so the entries it leaves out are named only on the tool's own output: run `sor status` after the resolve and lock what it lists as new.
3. Run `sor status`, then `sor lock <ids>` for the clauses whose entries came from the side whose file you did not keep (when unsure, for every clause `sor status` lists), so the lock is made against the merged code. Your lock respects other agents' claims: a clause one of them holds is left out and named.
4. Release the claims of the branch's agent once it has finished and its work is in your copy. The tool frees them by itself when the work has reached your copy ("its work has reached this copy"), but after a merge `sor claims` can
   still list them as *waiting for the merge* (seen after a merge with no lock conflict at all). Then release them under the holder's name: `sor release --as <holder> <ids>`.
   That is acting under another agent's name, so do it only for a holder that has finished and whose branch is merged, never for one at work, and never with `--force`. Do it from the parent session: the hook refuses a
   subagent that passes a name a sibling uses, and SPEC §16 defines no other way to release another agent's claim.
5. A lock refused for items you did not touch: `sor status` lists them as recompile, review or drift, and `sor claims` says which claims hold them and which clauses share their code region (nobody else can claim
   those meanwhile). Lock together the ones that share a region with your ids, release the claims of finished holders (step 4), and run `sor lock` again. Items of an agent still at work stay pending: leave them to it
   and tell the user.
