# Tests that CI proves

Some tests need a place: an operating system, a GPU, a database replica, an hour nobody wants to wait. The spec says so with
one line, and the lock stops waiting for them. A CI job proves them instead.

## The line
```
- **payment** - totals match the replica.
  expect: total = {order.total}
  runs on: linux+db, windows
```
`runs on:` names the environments the test must pass in. A comma separates environments. A plus joins the names one machine must
provide together, so `linux+db` is one machine with both. A name is lowercase letters, digits, dots, dashes and underscores.
`sor check` reports a bad line under a test and a `runs on:` line on a `manual:` test. Under anything but a test the line is plain text.

## What you do
- Write `runs on:` only when the person says where the test can run. Never to get past a test that fails: moving a failing test
  to `runs on:` is weakening it.
- `sor lock` records the test as `deferred`, does not wait for it, and names the tests that just became deferred. Say in your
  report which tests are left to CI.
- `sor test` leaves deferred tests out. `sor test --list` shows what a run would run and what it leaves to CI. `--provides linux`
  also runs the tests whose environment this machine provides, `--all` runs every one, and naming a test by its own id runs it.
- A person owns the CI setup. Never write or edit an evidence file so that `sor verify` passes: a job writes them.

## What a CI job does
1. It runs the tests it provides: `sor test --provides linux,db --out results.json` for a web project, or its own framework for
   tests written there (`sor test --list --json` names them, with their environments).
2. `sor evidence --job linux-db --provides linux,db --results results.json` writes one file for the job. Only tests that say
   `runs on:` and name an environment the job provides are kept; the rest are named in the output. One file per job, so two jobs
   never write the same file. `--commit SHA` and `--run ID` add the commit and the CI run the job saw; `sor verify` names them next to
   the job. A file written without them is the same as before, and one written with them is evidence format 2: an older `sor` refuses it.
3. A last job runs `sor verify` over all the evidence files, downloaded CI artifacts or the committed evidence folder. A folder
   is searched all the way down, so each artifact can stay in its own subfolder. Exit 0:
   every environment of every deferred test has a current pass. Exit 1: one is missing, stale or failed. Exit 2: an evidence file
   or a `runs on:` line is wrong.

## Good to know
- A result counts only for the fingerprint it was made for: the test (its rows and values too), what it refers to, and the text, rows,
  values and code of every clause it proves, the code marked with a row included. Change any of them and the result is stale. There
  are no timestamps. It does not cover code a test only uses as input, or code outside the marked regions. After a tool upgrade that
  changes how code is hashed, the old evidence reads as stale until the jobs run again.
- The lock never holds a result of a job, so it has the same bytes whatever ran where. Committing the evidence or keeping it as CI
  artifacts is the team's choice.
- A deferred test does not count for clause coverage until a run includes it. A project with a coverage budget gives that
  test its own `runs on:` and has a job run it with `sor test --all`.
- A failure that only CI sees does not free the code of a bug fix: change the test first, or give it a `bug:` line.
