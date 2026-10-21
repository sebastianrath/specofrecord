# Proposal: more than one code target

Status: draft for discussion, nothing built. Written 2026-10-21 after reading the tool and checking the points marked "shown" in a temporary project.

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
A changed clause whose code is "not updated yet" is accepted by `sor lock`, and `sor status` then says everything agrees. So the lock does not require code to be rebuilt today. A rule like "a clause is built only when every target has code" would be new behaviour. This proposal does not add it: each target follows whatever the single-target rules are.

## Design
1. **Targets own folders.** A file belongs to the target whose `path` is the longest prefix of its project-relative path. No new marker syntax.
   - Two targets claiming the same folder, or one folder holding code of two targets, is a `sor check` problem. The tool does not guess.
   - A `Source: code at` area outside every target root needs an owner, or it is a problem.
   - Target names must not collide with reserved key prefixes (`glue`, `test`) or with environment names.
2. **Which clauses apply to which target.** A `Targets: py, ts` setting. The root file holds the default and a part may override it, so adding a second target does not turn every clause into "ts not built" in one step. `sor status` summarizes ("N clauses have no ts code") and does not list thousands of lines.
3. **Compatibility.** A project with one code target behaves as today, with the same lock bytes.
4. **Lock.** With two or more targets, separate lines: the clause's text and refs entry stays single, and each target gets its own code-only entry (`clause@py`, as `glue:<file>` is a prefixed key). Reasons:
   - SPEC §11 and §16 want line-level merges, and work on two targets is naturally parallel, one agent per language.
   - `status` can reuse its per-key logic for new, changed, drift and built.
5. **Normalization by file type** (a table by extension: comment styles, and whether indentation is significant). Python and YAML keep indentation, and Python strips `#` comment lines.
6. **Tests.** A test applies to its clause's targets. Test code lives per target, results are per (test, target), and `--results` takes `id@py` keys or one file per target. Running each target's own framework from `sor test` is still "not built yet", so every target hands in external results.
7. **Environments and targets are separate.** A target is what was built, an environment is where a job ran it. A result key becomes (test, target).
   - **The evidence fingerprint becomes per target.** Today it hashes the code of every region of the clauses it proves, so a TypeScript edit would make Python evidence stale.
   - `runs on:` stays about environments. A target name used as an environment name is a problem, or `runs on: py` would defer a test that should run locally.
8. **Claims and `sor lock` get a target scope**, so a Python agent and a TypeScript agent can work on one clause.
9. **Index and extension.** Regions get a `target` field in `markers --json`. The lens can show one title per target. Coverage becomes per target.

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

## Order of work
- **Phase 0, a bug fix of its own:** normalization by file type.
- **Phase 1:** a lock format version, and refusal by an older reader.
- **Phase 2, nothing changes in the lock:** map regions to targets in the index, `sor check` problems for overlapping roots and reserved names, and a "no code for target" report.
- **Phase 3:** per-target lock lines, per-target results and claims, `Targets:` with a root default.
- **Phase 4:** per-target evidence and fingerprints.

## For the Python and TypeScript tool
The risk is that the two copies disagree on a hash. So the hashing and normalization rules should be clauses with tables of test vectors (input, expected hash), and both implementations should run against the same rows. Not part of this proposal to build.

## Decisions for the owner
1. **Lock shape:** separate lines per (clause, target), or a dict inside one entry. Recommended: separate lines.
2. **Applicability:** a default in the root file with part overrides, or "all targets" everywhere. Recommended: the root default.
3. **Phase 0 now,** on its own, ahead of everything else. Recommended: yes, because it fixes projects that are single-target today.
