# Proposal: more than one code target

Status: Phases 0, 1, 2 and the first slice of 3 are built and merged. Stage 1 of the rest (the note respects `Targets:`, `sor status` prints it) and stage 2 (a lock asks for code in every language that applies) are built, and so are the hook that asks before `--allow-behind` (stage 3) the pending line of the session-start note (stage 4a) and the claim lifetime (stage 4b). Per-target results and claims are open. The decisions for the owner were made on 2026-10-21 (see the end), and nothing else is built. Written the same day after reading the tool and checking the points marked "shown" in a temporary project.

## The goal
One spec, code in more than one place: `src_py/` and `src_ts/`, or `src/py/` and `src/ts/`. Tests, environments and the evidence gate have to work with that. A first use is the tool itself, in Python and in TypeScript, so a VS Code user needs no Python.

## What the tool does today
- **A target is a description, not an owner of code.** `sor/targets/<name>.md` says how code is delivered and tested. The tool takes every `path` value of every target, plus every `Source: code at`, as the code folders (`code_roots`). A region found in a file does not know which target it belongs to.
- **One code hash per clause.** `code_hashes()` joins the normalized code of every region of a clause, in every file, into a single hash. Code in two languages would share one hash, and `sor status` could not say which side moved.
- **Tests run in a web target only.** Anything else is an external test: code marked `@clause test`, one `--results` file, one result per test in the lock.
- **Claims hold a clause's regions in every file**, so two agents cannot work on the same clause, one per language.
- **The lock has no format version.** `markers --json` has one.

## Two bugs that existed, shown, and fixed by Phase 0 (branch `sor-normalize`)
Both are in how code is normalized for the hash (`normalized()` in `tools/sorlib/markers.py`). It strips comment-only lines that start with `//`, `/*` or `<!--`, and it strips all indentation.
1. **A Python indentation change is not seen.** Moving `return t` into a `for` loop changes what a function returns, and `sor status` says "clauses, code and lock agree".
2. **A Python `#` comment edit is drift.** Editing only a comment inside a region gives drift and exit 2.

Phase 0 makes normalization follow the file type. The cure was not to add `#` to the comment pattern for everyone, because that would hide `#define` and `#include` changes in C. Normalization has to follow the file type, not the target. A game-engine style target already mixes C++ and Objective-C++, and a web target mixes HTML, JS and CSS.

Changing the rule changes every locked code hash once. SPEC §11 already describes that case, and the migration is a relock.

## Also shown
A changed clause whose code is "not updated yet" is accepted by `sor lock`, and `sor status` then says everything agrees. So the lock does not require code to be rebuilt today. With more than one language that leaves one behind without a word (shown below, under "A target that is behind"). A project with one target keeps today's rule.

## Design
1. **Targets own folders.** A file belongs to the target whose `path` is the longest prefix of its project-relative path. No new marker syntax.
   - Two targets claiming the same folder, or one folder holding code of two targets, is a `sor check` problem. The tool does not guess.
   - A `Source: code at` area outside every target root needs an owner, or it is a problem.
   - Target names must not collide with reserved key prefixes (`glue`, `test`) or with environment names.
2. **Which clauses apply to which target (decided).** A `Targets: py, ts` setting. The root file holds the default and a part may override it, so adding a second target does not turn every clause into "ts not built" in one step. `sor status` summarizes ("N clauses have no ts code") and does not list thousands of lines.
3. **Compatibility.** A project with one code target behaves as today, with the same lock bytes.
4. **Lock.** With two or more targets, separate lines: the clause's text and refs entry stays single, and each target gets its own code-only entry (`clause@py`, as `glue:<file>` is a prefixed key). Reasons:
   - SPEC §11 and §16 want line-level merges, and work on two targets is naturally parallel, one agent per language.
   - `status` can reuse its per-key logic for new, changed, drift and built.
   - Each per-target line also records `built`, the text hash of the clause that target's code was accepted against. That is what makes a target "behind" (next section).
5. **Normalization by file type** (a table by extension: comment styles, and whether indentation is significant). Python and YAML keep indentation, and Python strips `#` comment lines.
6. **Tests.** A test applies to its clause's targets. Test code lives per target, results are per (test, target), and `--results` takes `id@py` keys or one file per target. Running each target's own framework from `sor test` is still "not built yet", so every target hands in external results.
7. **Environments and targets are separate.** A target is what was built, an environment is where a job ran it. A result key becomes (test, target).
   - **The evidence fingerprint becomes per target.** Today it hashes the code of every region of the clauses it proves, so a TypeScript edit would make Python evidence stale.
   - `runs on:` stays about environments. A target name used as an environment name is a problem, or `runs on: py` would defer a test that should run locally.
8. **Claims and `sor lock` get a target scope**, so a Python agent and a TypeScript agent can work on one clause.
9. **Index and extension.** Regions get a `targetName` field in `markers --json` (built in Phase 2; `target` is taken by the anchor text). The lens can show one title per target. Coverage becomes per target.

## A target that is behind, and code a person changed
Shown in a temporary project: one clause with code in `src_py/` and in `src_ts/`, and a person changing the Python by hand.
- `sor status` reported drift on the clause and listed both files.
- The clause was brought in line with the Python, as the workflow says to. `sor status` then said "changed, code updated" with both files listed, and `sor lock` said clauses, code and lock agree, while the TypeScript still said the old greeting.
- The single code hash cannot tell a language that was rebuilt from one that was forgotten. Per-target lines can, if they record what they were built for.

The rule, decided on 2026-10-21:
- A target is **behind** for a clause when the target applies to it (`Targets:`), it has a line for the clause, and that line's `built` is not the clause's current text hash. A clause with no code at all for a target is not behind. It is counted in the "no code for target" report of Phase 2, so adding a second target does not make every clause behind at once.
- `sor status` lists what is behind in a group of its own, naming the clause and the target, and the exit code is 1 as for any pending change.
- A lock accepts a target's code with the clause when that code changed since the last lock: it was rebuilt, or a person changed it and the clause was brought in line with it. Code that did not change stays behind.
- **`sor lock` refuses while a target is behind for a clause it locks,** and names the target. A flag (called `--allow-behind <target>` here) accepts the clause anyway. The target stays listed as behind until its code changes, so the flag hides nothing. It means "I rebuild it later". A clause that does not concern a language is the job of `Targets:`.
- A project with one target has no per-target lines and behaves as today.

A person changes the Python by hand, in order:
1. `sor status` reports drift on `greeting@py` only.
2. The clause is brought in line with the Python (`reference/code-a-person-changed.md`). `greeting@ts` is now behind.
3. The TypeScript is rebuilt from the clause, and the lock accepts both: the Python because the person's code is the reference, the TypeScript because its code changed.

A person changes the spec instead: every target that applies is behind until it is rebuilt.

Open: a language whose code is already right for the new wording, because the change was to a sentence that does not concern it. The tool cannot tell it from a language that was forgotten, and a changed code hash is its only proof. Options are a confirmation that only a person may give (as `--confirm` is for a `manual:` test), or touching the code. Not decided.

## Layouts: what works today, and what usually sits around a source folder
Shown in a temporary project with two targets, `src_py/` and `src_ts/`:
- **The layout itself works.** `sor check`, `sor lock` and `sor status` accept one clause with code in both folders. `#` and `//` markers are both read. `src/py/` and `src/ts/` behave the same, since a path is only a folder prefix.
- **What fails is whatever else lives inside the folder.** With explicit code folders the tool scans every text file under them, and every line must sit in a region.
  - `package.json` in `src_ts/` or `pyproject.toml` in `src_py/` is reported as "code outside any @clause region".
  - Compiler output inside the folder (`tsc` keeps comments) is read as more regions, and its code joins the clause's one code hash.
  - Test files inside the folder are unmarked lines unless they carry `@clause test` or sit in a `Source: code` area.
- **So a target's `path` has to be the source folder, not the package folder.** Config files, lock files and build output stay outside it: `packages/py/src/` and `packages/ts/src/`, not `packages/py/`.

How projects like this are usually built, from what I found. Treat the examples as patterns, not rules:
- One folder per language, or `packages/<language>/`, each with its own package manager, plus a root that orchestrates. [coinbase/x402](https://deepwiki.com/coinbase/x402/11-development) keeps TypeScript, Python and Go side by side, and [google/A2UI](https://deepwiki.com/google/A2UI/10.3-monorepo-structure-and-package-management) uses npm workspaces for TypeScript and uv for Python. A [scaffold template](https://tomevault.io/tome/carlosmarte/skills) puts the ports in `packages/ts` and `packages/py`, governed by one `SPEC.md` and a shared parity fixture. That last source is a third-party page, not an established convention.
- A language-neutral set of test cases that every implementation runs: the [JSON Schema Test Suite](https://www.mintlify.com/json-schema-org/json-schema-spec/resources/test-suite) and the [protobuf conformance suite](https://buf.build/blog/protobuf-conformance), where a runner takes a request and returns a response so any language can plug in. This is the model for hash parity between a Python and a TypeScript `sor`: test vectors in the spec, run by both.

## Version skew comes first
Phase 0 already shows it, in one direction: a tool that follows the file type reads a lock written under the old rule correctly, but an older tool reads a lock written by the newer one as drift on every Python region and refuses to lock. Update every copy of the tool together until the lock has a format version.

Tool copies of different ages meet in practice: a project keeps its own copy and the VS Code extension prefers it to its bundled one. An old tool reading per-target lock lines would report them as removed or as drift, with no complaint. So the lock needs a format version first, and an old reader must refuse with a message that says to update the tool.

Phase 1 built that (`DECISIONS.md`, "The lock has a format number"). Format 1 has no marker, and a later format opens the file with `"*format": N`. A tool from Phase 1 on refuses a number it does not know, with exit 2 and a message to update. A tool older than Phase 1 cannot be taught: given the marker it stops with a Python error, and its edit hook fails open. So every copy of the tool has to be updated before Phase 3 writes a lock in a later format.

## Order of work
- **Phase 0, a bug fix of its own (built and merged):** normalization by file type.
- **Phase 1 (built and merged):** a lock format version, and refusal by an older reader.
- **Phase 2, nothing changes in the lock (built):** map regions to targets in the index, `sor check` problems for overlapping roots and reserved names, and a "no code for target" report.
- **Phase 3, first slice (built):** per-target lock lines with `built`, the behind report and the refusing lock, `--allow-behind`, `Targets:` with a root default (`DECISIONS.md`, "Code per target in the lock").
- **Phase 3, open:** per-target test results (`--results id@py`) and per-target claims and locks, so that one agent can work on one language of a clause. The second needs a lock of one language to accept the clause's text, and that is not decided.
- **Phase 4:** per-target evidence and fingerprints.

## For the Python and TypeScript tool
The risk is that the two copies disagree on a hash. So the hashing and normalization rules should be clauses with tables of test vectors (input, expected hash), and both implementations should run against the same rows. The rows are built (`vectors/hashing.json`, `DECISIONS.md`); a first slice of the second copy is built, in JavaScript and not TypeScript (`tools/js`, `DECISIONS.md`): the hashing, marker and lock text rules, run against the same rows and compared with the Python tool by a test. It is written by hand, since the tool has no spec of its own to build it from.

## Decisions (made on 2026-10-22)
1. **A clause that applies to a language but has no code there refuses at lock,** unless `--allow-behind` allows it. Only clauses being locked now are
   concerned, so adding a second language does not flood the locked ones.
2. **A claim ends when its session ends, or after an idle time.** A `SessionEnd` hook releases it, and every `sor` call or edit by the holder renews it.
   The fallback is a project setting and may be "never".
3. **A new session is told about changes an earlier session left pending,** in the session-start note.
4. **Test results are per target** where the test has test code, and each stage gets one commit.
5. **The tool offers mechanisms and never decides by who calls it.** Whether one agent or several work on a clause is the developer's instruction to the agents.

Still open, asked of the owner: whether a one-language lock may ever rewrite the clause's text line (recommended: no), whether `--already-fits <language>` is
added to `sor lock` and recorded on the language's line in lock format 3, which further guards `--allow-behind` gets, and whether `Targets:` may be written
on a single clause.

## Decisions (made on 2026-10-21)
1. **Lock shape:** separate lines per (clause, target), each with `built`. Not a dict inside one entry.
2. **Applicability:** a default in the root file, with part overrides.
3. **Phase 0 now,** on its own, ahead of everything else. Done: merged, with the fixes from its reviews.
4. **A lock refuses while a target is behind,** with a flag to allow it. Status reports it either way.

Still open: how a language confirms that its code already fits a changed clause (above), and the name of the flag.
