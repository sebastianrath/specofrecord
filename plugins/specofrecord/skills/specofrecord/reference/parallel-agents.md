# Working beside other agents

Use this when more than one agent, or a person and an agent, work in the same project at once, or when you start
subagents. The everyday rules (claim before you edit, what to do on REFUSED, lock only your own clauses, release when you
stop) are in `SKILL.md`, under "Claims" and "Locking".

## What a claim is
A claim says which clauses you work on. The tool records it, `sor status` shows it in the `claims` group, and `sor lock`
respects it. It is advice: an agent that never claims is not stopped. Claims end after 30 minutes without activity (`--ttl`, or
`Claims:` in the root file, changes it) and when their session ends, so an agent that crashed does not block the project for good.

## Who you are
The tool knows who you are from your Claude Code session, so you do not have to say. Pass `--as <name>` (or set
`SOR_AGENT`) only to act under another name. `--as` belongs to `sor claim`, `sor lock` and `sor release` only: any other
command refuses it. An agent that is not Claude Code has no session: it chooses one name and passes `--as <name>` on every
claim, lock and release. Another name is another agent.

## Subagents
Subagents share your session, so the tool cannot tell them apart from you by itself. When you run subagents in parallel:
- Give each its own name and have it pass `--as <name>` on every claim, lock and release. A shell variable would not
  survive between calls.
- Do not claim what you delegate, because your claim would block your subagent's.
- A subagent releases with its own name (`sor release --all --as <name>`): that frees only its claims, and another agent's
  claim named by id is left alone ("NOT released (held by someone else; --force overrides)", exit 3). A subagent that
  forgets `--as` looks like the parent: its `sor release --all` frees every claim made in the session, its siblings' too.
- Your own final `sor release --all` has no `--as`, and `SOR_AGENT` is not set in your environment (it is a name too, and
  your subagents share that environment). A caller that gives no name frees every claim of the session, so it also clears
  what a subagent that crashed left behind.
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
- `sor claim greet/hello@py` holds the Python side only: its lock line, the line of its test, and the code in the Python files. Another agent may
  claim `greet/hello@ts` at once. Nobody can change the clause's text while either of you holds a language of it, because your code is built for
  that text. To change the clause, claim the whole clause (`sor claim greet/hello`), which holds every language and waits for them.
- The order for a clause that changes: the agent that changes the text claims the whole clause, rebuilds the language it works on, and locks the
  clause (`sor lock greet/hello`), which is refused while another language would stay behind. Only when the user has said that a language is rebuilt by
  someone else, it adds `--allow-behind ts` (the hook asks the user first). The clause is locked then, and `ts` is listed as behind.
- The other agent claims `greet/hello@ts`, changes the TypeScript code, runs the tests, and locks it with `sor lock greet/hello@ts`. That lock writes the
  TypeScript line, the line of the clause's test in TypeScript and the glue of the TypeScript files, and nothing else, so it cannot undo what the first
  agent locked. It is refused while the clause has an unlocked change ("lock the clause first"), for code that did not change (use `--already-fits ts`
  only after you checked that it fits the changed clause as it is), and while the test in that language has no passing result (`--results` with
  `greet/test:hello@ts`).
- Two clauses that share one code region in a language are locked together: `sor lock greet/hello@py greet/bye@py`.
- A lock of one language tells you which other languages of the clause are still behind or without code. When you release a language that has code
  that is not locked, `sor release` says so.

## When your claim runs out
A claim that expired protects nothing, and another agent may have claimed the clause since. The tool tells you when you
come back to `sor lock` or `sor release`:
- `sor lock` with no ids, when all your claims expired, is refused with "your claims on X, Y expired at 00:31; claims
  end after 30 min idle by default: claim again, `--ttl 2h` for a longer window".
- A `sor lock` with no ids that still covers live claims prints a `warning:` for the expired ones, which are not in that lock.
- `sor release` says "nothing to release: your claims on X expired at ...", or adds the same as a `note:`.

Then claim again (`sor claim <ids> --ttl 2h` for a long task) and re-read the clause before you go on, because someone may
have changed it meanwhile. The tool keeps this news for a few hours only, and only `sor lock` and `sor release` say it: an
agent that does neither is not told.

## When a claim refuses you
`sor claim` prints REFUSED and exits with 3. The refusal says who holds the clause and until when at the latest. A claim takes
all its ids or none: the REFUSED line names only the ids in the way, and a line below it says which of the others were free
but were not claimed either, so claim those on their own. Do not edit that clause or its code, and do not look for a way
around it. Then decide:
- take another clause, or
- wait a little and try again (the holder may release sooner), or
- ask the user.

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
