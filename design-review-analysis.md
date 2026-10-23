# Sor Design Review, analysed finding by finding

Source is the conversation "Sor Design Review" (reviewers tested commit `dfbb011`). Every open item was re-checked
against HEAD (`62017a2`) where a check was cheap. Items I re-ran are marked "reproduced". Items taken from the
reviewers without a re-run are marked "reviewers' result". "Unchanged" means no commit since `dfbb011` touched that
code, not that I re-ran it. The advisor checked the verdicts in five calls, one per theme, and the last call also read
this file. Findings are numbered F1 to F36, and some were merged or split along the way.

## How to read the tables

Every verdict depends on who is assumed to be the adversary.

- **(a)** An honest builder agent that makes mistakes. This is the model the tool documents (`SPEC.md:279`, `DECISIONS.md:488` say the lock trusts the caller).
- **(b)** A builder agent that lies on purpose. Outside the documented model, so a failure here is "by design plus a documentation overclaim" unless the threat model is widened.
- **(c)** An untrusted repository, meaning a cloned repo, a pulled branch or a hostile spec. The plugin and the extension have to assume this one.

Verdict words are design failure, implementation bug, gap, by design, doc overclaim, and fixed.
The last column says whether I wrote the code in question during this stretch of work.

## Facts the verdicts lean on

- A hook that exits with anything but 0 or 2 is a "non-blocking error" (Claude Code hooks reference). The user sees a `<hook name> hook error` notice with the first line of stderr. The docs do not say the model receives it.
- A timeout on `PreToolUse` does not block either.
- The hooks page lists `"onFailure": "block"` (v2.1.295 and later), which makes a failed hook act like exit 2. I read only the first third of that page.
- `sor/.sor-claims.json` and the mutex files are git-ignored in this repository (`.gitignore` lines 15 to 18). Nothing in `SPEC.md`, the skill or its reference files tells a user project to do the same.

## Theme 1, trust and verification

| ID | Finding | Verdict | Threat model | Status at HEAD | Fix layer | Mine |
|---|---|---|---|---|---|---|
| F1 | A hand-typed `--results` file locks. "agree" and "pass" only mean the caller said so, and the lock line records no source. | By design plus doc overclaim. `README.md:3` says the spec "always stays in sync with the code" and `SKILL.md:128` calls `sor test` "the independent check". Both promise more than the tool checks, since `SPEC.md:279` and `DECISIONS.md:488` say the lock trusts the caller. | (b) | Unchanged | Reword both lines. A `by` label on the lock line is optional. | no |
| F2 | A stale results file locks after an honest edit. Reuse the old `results.json` and it passes. CI evidence is tied to a test fingerprint and `--results` is not. | Design inconsistency plus a real bug. | (a) | Unchanged | Tie `--results` to the fingerprint, or run through `run:`. The earlier session weighed both and listed the downsides. | no |
| F3 | The exit code of a `--targets` run is only a note (`targetrun.py:235`). | Implementation gap, low. Tests the run did not report become `skipped`, which limits the damage. A test already reported as pass stays pass. | (a) | Unchanged | One line. | yes |
| F4 | 999 of 1,234 engine tests are `manual:`, and an unconfirmed manual test is invisible to `sor status`. A failing test given a `manual:` line locks. The tool's own refusal text points an honest agent at `manual:` and `--allow-incomplete`. | Design failure. The escape hatch has no accounting and "agree" hides the debt. | (a) | Unchanged | Put counts next to "agree" in `sor status`. Reword the refusal text. Do not block. | no |
| F5 | One agent writes the clause, the test, the code, the results and the lock, while the docs call `sor test` "the independent check" and `Owner:` is never read. | Merged into F1, F2 and F4. It is their umbrella plus a doc contradiction. | n/a | n/a | n/a | no |
| F6 | Which flags are for people only. | Split. Only `--confirm` is for people only, and that rests on prose with no hook, so it is low and needs (b). `--allow-incomplete`, `--results F` and `--targets` are agent flags, and the skill tells agents to use the first two. They weaken what a lock proves, and that part belongs to F2 and F4. | (b) for `--confirm`, (a) for the rest | Ran `hook.pre_bash` on `sor lock --confirm t1`, `--allow-incomplete` and `--results r.json`. It makes no decision for any of them, which is expected for the agent flags and is the gap for `--confirm`. Only `--allow-behind` and `--already-fits` ask. | An ask hook for `--confirm`. | no |
| F7 | A hostile spec declares `{run: …}`. A plain `sor test` ends with the line `sor test --targets py runs it` (`targetrun.py:44`, printed at `cli.py:833`). The agent follows the hint. `allowed-tools: Bash(sor *)` (`SKILL.md:4`) is approved in advance, so nobody is asked. The skills page says the grant holds only during the turn that invokes the skill and clears on the next user message, which narrows this but does not remove it. | High design failure. sor runs repo-defined commands under a blanket approval, which walks around the approval Claude Code would otherwise ask for. | (c) | The hook half is reproduced at HEAD, `pre_bash` returns no decision for `sor test --targets py`. The approval half is read from `SKILL.md:4` and was not run. That pattern matches the `sor` command on the PATH, not `python3 tools/sor.py`. | An ask hook on `--targets`, or leave `--targets` out of the approval. | yes, I built `--targets` and the hint |

## Theme 2, edit guard and hooks

| ID | Finding | Verdict | Threat model | Status at HEAD | Fix layer | Mine |
|---|---|---|---|---|---|---|
| F8 | The guard has two failure policies. An unreadable lock format denies the edit (`hook.py:212`). Every other load failure exits 1 and the edit goes through (`hook.py:570`). A stray `sor/CLAUSES.md`, one non-UTF-8 byte or a `[…]` in the project path therefore switch the guard off, while an unknown format stops it. A missing or empty lock also allows every edit (`hook.py:214`). | Design failure (inconsistent failure policy). | (a) for a merge-conflicted `sor-lock.json`, which parallel branches produce normally. (c) for a planted `CLAUSES.md`. The deleted lock is mostly (b), and `git checkout` or `git rm` of the lock is the (a) route. | Reproduced. With conflict markers in `sor-lock.json` the hook raises `JSONDecodeError`, exits 1, and the same edit that is denied with a good lock goes through. `shellguard` only partly covers a deleted lock, and skips lines with `git` or `sor`. | Make the loader report problems (`glob.escape`, undecodable files, a conflict as a `Problem`). See decision 2 below. | no |
| F14 | Drift is not guarded a second time. `pre_edit` refuses only drift that is new compared with the drift already there (`hook.py:238`). | Design gap. | (a) | Reproduced. After a change outside the tool to `'body/sun'`, a further `Edit` of the same region is allowed. | Refuse an edit that changes the hash of an already drifted region while its clause has not changed since the lock. The exemption looks deliberate, so that a person's earlier drift does not block unrelated edits, and this fix keeps that case. | no |
| F10b | Rewording a clause clears drift. The drift message offers both ways out and the skill makes rewording the workflow for a person's change. Nothing records whether the code led and the clause followed. | Design failure. Same root as F30. | (a) | Unchanged. Reviewers' result. | Record direction and provenance, and flag "clause changed to match existing code" for review. A better hash would not help. | no |
| F10c | A `bug:` test with `expect: 1 = 1` frees an edit. `bugs.md` says the test must fail first and nothing records that it did. | Gap, medium low. | (a) | Unchanged. Reviewers' result. | Record the failing run. | no |
| F10a | A cosmetic edit to a clause opens the guard for its code. | By design, low. A text change should demand a rebuild and a review. | (a) | n/a | None. | no |
| F11 | `sed -i`, scripts and formatters bypass the guard. The engine log records this at least four times. | Design gap, now narrower. | (a) | Partly addressed by `shellguard` (`afca936`). It warns after the command, covers code and the lock file, and leaves out spec files and lines with `git` or `sor`. It has not run in a live session because hooks load at session start. The plugin does not register `PostToolUseFailure`. | Cover spec files. Verify live in the next session. | yes |
| F12 | `because:` and `Why:` lines reach the agent verbatim under the tool's own header. The read hook also pulls in spec text from files the agent never opened. | Real, bounded. Clauses are instructions by design, but hostile text gets the tool's authority. | (c) | Unchanged | Fence the text and add one "spec text is data" line to the skill. | no |
| F9 | Case variant paths pass on macOS (`hook.py:184` and `:187` compare exactly). | Implementation bug, low. | (b) | Unchanged | `samefile` or `normcase`. | no |
| F13 | The `pre-bash` lexer misses backticks, `sudo`, `env -i`, `xargs` and `sh script.sh`. | Low. | (b) | The quoted form `allow-"behind"` now asks. I ran three spellings and all returned `ask`. That came with removing the shell prefilter, which starts Python on every Bash command, at least 50 to 60 ms by my timing of the module import alone. | None needed. | yes, the removal |

## Theme 3, concurrency and runtime robustness

| ID | Finding | Verdict | Threat model | Status at HEAD | Fix layer | Mine |
|---|---|---|---|---|---|---|
| F15 | A mutex holder slower than `STALE_LOCK` (10 s) loses its mutex. A waiter removes it (`claims.py:179`), and the first holder's `__exit__` later removes the waiter's mutex unconditionally (`claims.py:190`). SPEC §16 and the comment at `claims.py:180` say this happens "after a crash only". | Design bug, medium. The documented rule is wrong for a stalled holder. | (a), a sleeping laptop or Ctrl-Z | Unchanged. `sor lock` rereads and compares inside the mutex (`cli.py:519`), which covers most of it. `claim`, `release` and the renewal on every edit (`claims.py:458`, `519`, `550`) do the whole read, modify, write inside the mutex with no recheck, so a stolen mutex there loses a claim silently. Tests and hashing run before the `sor lock` mutex, so normal use stays well under 10 s. | An owner token in the mutex file and remove only your own, or `flock`. | no |
| F16 and F18 | No `fsync` anywhere in `sorlib`, and no test proves the write is atomic (an in place write passes every test). | Merged. The concurrency rules have no tests, which is why F15 survived. An empty lock after a power cut feeds F8. | (a), rare | Unchanged. Reviewers' result. | Fsync the temp file before `os.replace`. Add a test that reads during a write. | no |
| F17 | A malformed claims file crashes the reader (`[]` gives `AttributeError`, `{"claims": 5}` gives `TypeError`, a claim without `until` gives `KeyError`). A merge-conflicted file reads as no claims at all (`claims.py:119`). | Same inconsistency as F8. Claim enforcement turns off silently for that edit. Medium low. | (a). User projects are not told to ignore the claims file. | Reproduced | Validate the shape on read and report it. Tell projects to git ignore the claims and mutex files. | no |
| F19 | Claims use wall clock `until`. | By design. A deadline that must outlive the process has to be wall clock. Only the local wait deadline in `__enter__` should be monotonic. | (a), rare | Unchanged | Trivial. | no |
| F20 | Scanner robustness. A FIFO in the repo hangs `open()`. The marker regex is quadratic. Dot folders, files over 2 MB (`MAX_BYTES` in `scan`) and non-UTF-8 files are skipped without a word. | The hang and the regex are the F8 class under (c), because a `PreToolUse` timeout does not block. The silent skips are the design failure, since code the scanner skips sits outside the guard with no note. This also covers the Latin-1 file in F8. | (c) for the hang and the regex. (a) for the skips. | Unchanged. Reviewers' result. | Report skipped files as problems. Bound the time and size. | no |
| F21 | Path checks for spec folder aliases and symlinked output folders exist only in `sor check`. `names_of` (`targetrun.py:29`) validates names and `run:` but not paths. | Implementation gap, low. Under (c) it adds nothing because `{run:}` already runs code (F7). | (a) | Fixed in `sor check` after the reviewed commit. Open at run time. | Validate in `names_of`. | yes |

## Theme 4, extension and code structure

| ID | Finding | Verdict | Threat model | Status at HEAD | Fix layer | Mine |
|---|---|---|---|---|---|---|
| F22 | The extension runs `git blame` in the workspace (`tools/js/sorlib/views.js:139`), so repo config such as `core.fsmonitor` can run commands. | Low. `package.json` declares no `capabilities`, and the VS Code Workspace Trust guide says an extension without the declaration is disabled in Restricted Mode. So the missing declaration is the safe default and is not a finding. The exposure exists only after the user trusts the folder. | (c), after trust | I fetched the trust guide. I did not check how VS Code's own Git integration behaves, so I am not claiming it has the same exposure. | Switch repo defined commands off for that call, for example `-c core.fsmonitor=false`. | yes, the JS port |
| F23 | The hover sets `md.isTrusted = true` (`extension.js:675`). `f.id` and the blame name `w.finding.by` go in through `appendMarkdown` unescaped (`extension.js:682` to `:684`), which makes a `[x](command:…)` link real. Clause text goes through `appendCodeblock`. | Medium low. A hostile clause id, git author name or a clause text containing a closing code fence can put a clickable command link in a hover that may run any command. | (c), after trust, and it needs a click | Unchanged. The code fence break out is from my memory of the VS Code API and was not run. | Escape the text, and use `isTrusted = { enabledCommands: [...] }` with only the extension's own command. | partly, the hover predates me and the blame text comes through my port |
| F24 | Library code exits with `SystemExit` (`model.py:455`, `:457`, `testrun.py:574`, `:654`, `:789`). The hooks catch `(Exception, SystemExit)` because of it. `targetrun` imports the Chrome runner `testrun` (`targetrun.py:18`). | Structure debt, not a product design failure. Every caller has to know to catch `SystemExit`. I did not check import cycles or module size. | n/a | Confirmed for these two points only. | Raise a tool error class instead. | `targetrun` import yes |
| F25 and F32 | Two implementations (Python and JS) must agree on hashing, markers, lock text and status. Reviewers found divergences in exit codes and error wording, and a mutation that swaps UTF-16 and code point columns survived the tests. | By design cost, mitigated by the vectors and the cross check. The surviving mutation is a test gap. | (a) | Reviewers' result. I fixed match/case and absolute anchors after the reviewed commit. The column mutation was not rerun. | Add the missing test. | yes |
| F26 | `.DS_Store` can make `sync-tools --check` fail locally. | Low tooling bug. | (a) | `sh plugins/sync-tools.sh --check` passes now and no `.DS_Store` is present. | Exclude it in the script. | no |
| F27 | Target line coverage counts test regions. `line_coverage` (`targetrun.py:143`) filters regions by target file only. Test code is marked `@clause test` (`markers.py:723`), so the lines of a target's own tests count as covered code. | Metric gap, low medium. The freshness stamp of the results file is also not pinned by a test. | (a) | Read, not run | Skip `r.kind == 'test'` in the loop. | yes |

## Theme 5, format and scale

| ID | Finding | Verdict | Threat model | Status at HEAD | Fix layer | Mine |
|---|---|---|---|---|---|---|
| F28 | The 7 item cap shapes content. 215 of 274 sections in the engine project sit at exactly 7. | Tradeoff. Only a note, never an error. | (a) | Reviewers' result, the engine project was not reopened. | Report the distribution. | no |
| F29 | Ids are paths, so a part cannot be renamed. A `sed` experiment showed the cost across ids, references and lock keys. | Design limitation, medium. | (a) | Unchanged | A `sor rename` command. | no |
| F30 | Spec as source versus audited traceability. The tool says clauses lead, but in the engine log code led and clauses followed. Contradictions between clauses are "convention only" and unbuilt state has no home. | Design failure at the root of F10b. The tool can check that text and code agree. It cannot check which came first. | (a) | Unchanged | Record direction, or say plainly in the README that it audits traceability and does not make the clause the source. | no |
| F31 | `open:` questions are not enforced. | Low medium. The skill's rule "do not choose an answer" is prose only. | (a) | Unchanged | Make `sor lock` list the open questions under the claimed ids. | no |
| F33 | The runner is web only and a custom DSL is not argued against Gherkin. `DECISIONS.md:631` lists `each: N ×` generators and benchmark metrics as not built. | Documented gap, low to medium. I did not check whether the cheat sheet still teaches them. | (a) | `--targets` runs any command, which narrows the gap. The price is the F7 surface, so both belong in the same sentence. | n/a | partly |
| F34 | The hash is half pinned. No Unicode normalization exists in `tools/sorlib` or `tools/js/sorlib`, so the hash covers the bytes as written and the vectors have `é` but no NFC and NFD pair. The hash rule version is not recorded in the lock either. `old_rule_keys` (`lock.py:199`) recomputes the one known legacy rule. The hash is 12 hex digits. | Low medium. Inferred, not recorded, and it handles exactly one past change. | (a). A deliberate collision needs (b). | Confirmed by grep | Add an NFC and NFD vector, state the rule in SPEC §11, and record a rule version at the next rule change. | no |
| F35 | Documents contradict the tool. `comparisons/` does not exist, yet `DECISIONS.md:382` and `:437` point at it. `tools/test_sor_docs.py` passes (25 tests), so it does not check paths in `DECISIONS.md`. | Docs gap, low. Most "not built" lines in `DECISIONS.md` are legitimate alternatives. I could not confirm the "10 minutes" claim (the cheat sheet is 790 words). | n/a | Confirmed | Check paths in the docs test. | no |
| F36 | The per language target feature has no user. `Project.targeted()` is `False` for both `examples/solar-system` and `editors/vscode`, and `SPEC.md` names `Targets: py, ts` (§9) as the line that switches it on. Both projects do have target parts (`web`, `vscode`), but that is the older idea of where code goes. | Design risk. It is a lot of surface (per language lock lines, `behind`, `--allow-behind`, `--already-fits`, `--targets`) and part of the guard's complexity (`hook.py:228`) and of F7. I built it without a project that needed it. | (a) and (c) | Confirmed with the tool | Keep it and mark it experimental, or trim it. A call for the user. | yes |

## Top five design failures under (a) or (c)

1. **F7.** A `Bash(sor *)` approval in advance (read from `SKILL.md:4`) plus a spec that declares `{run: …}` plus a hint that names `--targets` means an untrusted repo can run code with no prompt. The hook half is reproduced at HEAD, the approval half is read, not run.
2. **F8 with F17 and F20.** The guard has one failure policy for everything except a lock format error, and the docs do not say the model receives a hook error. A merge-conflicted lock, a malformed claims file and a planted FIFO all let the edit through. Reproduced for the conflicted lock. For the claims file I reproduced the crash, and that it lets the edit through is inferred from `run()`. Not run for the FIFO.
3. **F10b with F30 and F14.** Nothing records the direction of a change, so rewording a clause to match the code clears drift, and an edit to a region that already drifted is not stopped a second time (F14, reproduced). The claim that the clause is the source of truth is not something the tool can check.
4. **F4 with F1 and F2.** "agree" hides how little was checked. Unconfirmed manual tests are uncounted, a stale results file locks, and the refusal text sends honest agents to `manual:` and `--allow-incomplete`.
5. **F11.** Script edits bypass the guard. The new warning is mine, covers no spec files and has not run live.

Just below the line is F15, the claims mutex, which is medium and wrongly documented.

## Two decisions for the user

1. **Widen the threat model to (b)?** If yes, F1, F6, F9 and F13 become real design failures, `--results` needs a provenance label and the hook has to ask about the human only flags. If no, the README and the skill should say so plainly (`README.md:3`, `SKILL.md:128`).
2. **Should `pre-edit` fail closed when a project with a lock cannot load?** It can be done with `"onFailure": "block"` on the `pre-edit` hook only, or in code. The cost is that every hook bug, and the wrapper's own "tools/sor.py not found" exit 1, becomes a hard stop on every edit.

## What I did not check

- Import cycles and module size (F24).
- The engine project numbers (999 of 1,234 manual tests, 59 of 72 manual rows runnable, 215 of 274 sections at 7). They come from the other session's transcript.
- VS Code behaviour of `appendCodeblock` (F23), and VS Code's Git integration (F22).
- The `shellguard` hooks in a live session, the GitHub CI jobs, and Windows.
- The reviewers tested `dfbb011`. Since then `127ad4a`, `18764de`, `afca936` and `62017a2` fixed the timeout kill, the `./sor/` aliases in `sor check`, `run:` splitting, web failure standing, lcov digits, JS match/case and absolute anchors, the extension fix, and part of the script edits.

## After the change on `sor-lock-provenance` (not committed)

A first answer to F1, F4, F6 and F7 is on the branch `sor-lock-provenance`, made from `main` and left uncommitted in this worktree.

| Finding | What changed | What is still open |
|---|---|---|
| F7 and F6 | The Bash hook now asks the user before `sor lock` with `--allow-behind`, `--already-fits`, `--allow-incomplete`, `--confirm` or `--results`, and before `sor lock` or `sor test` with `--targets`. The `--results` of `sor evidence` does not ask. | The permissions page says a `PreToolUse` hook runs before the permission prompt and can force a prompt, but neither it nor the hooks page names the case of a matching allow rule or a skill's `allowed-tools`, and I did not test it live. If an allow rule wins, F7 needs `SKILL.md:4` narrowed instead. |
| F1 | The lock records `via` on a pass or a fail, `run` when sor evaluated the test itself in a web run, `command` when a command the spec declares wrote the result (`--targets`), and `file` when the result came from `--results F`. A lock made before the labels has none, and no unlabeled pass is counted as run. | `README.md:3` and `SKILL.md:128` still say "always stays in sync" and "the independent check". Rewording them is a separate change. |
| F4 | `sor status` prints `tests locked: …` with the passed count, where the results came from, and the manual tests that nobody has checked. | `status --json` does not have it, and the refusal text still points an honest agent at `manual:` and `--allow-incomplete`. |
