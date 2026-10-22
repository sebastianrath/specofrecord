# The reading half of `sor` in JavaScript

A copy of what `tools/sorlib` does when it reads a project, for an editor that has no Python. The VS Code extension ships it and always runs
it (`editors/vscode/tools`, made from this folder by `plugins/sync-tools.sh`). It reads the spec folder and the code, works out what changed
since the last lock, and prints it as JSON. It writes nothing.

    node tools/js/sor.js -C <project> markers --json              every item, row, value, reference and code region
    node tools/js/sor.js -C <project> markers --json FILE:LINE    the regions around a line, with the clauses they serve
    node tools/js/sor.js -C <project> markers --json ID           where the code of a clause (and of its test) is
    node tools/js/sor.js -C <project> status --json               what changed since the last lock
    node tools/js/sor.js -C <project> parts --json                the parts, the root first

Each answer is the one `python3 tools/sor.py` gives for the same command, field for field and position for position (columns are counted in
code points, as the Python tool counts them). Three things differ on purpose:

- `status --json` has no `problems`. Finding them is `sor check`, which is not in this copy, and the extension never read them.
- It never touches a claim. The Python tool marks the claims of the Claude Code session that runs it as alive; this one only reads them.
- An anchor `code: path#name` in a `.py` file is found by a tokenizer (strings, brackets, comments, continuation lines and the blocks that
  indentation makes), not by Python's parser. They agree on the first and last line of a def, a class or an assignment, on every name in the
  standard library, and on a file with a string or bracket left open or an indentation that does not fit (no anchor). The tokenizer does not
  check the grammar: a file that Python refuses as a whole for a bad operator still has its functions found here. A `match` statement is read
  although Python 3.9 refuses it, and `match` and `case` are names where they are used as names.
- An anchor path that is absolute is read where it is, as in the Python tool.

Everything else (`check`, `lock`, `claim`, `test`, `verify`, the edit guard) is the Python tool's.

It is plain JavaScript (CommonJS) with no dependencies, for Node 16 or later, the Node of VS Code 1.80; a CI job runs it and its tests on Node 16
(`.github/workflows/vscode.yml`). A lock in a format newer than 3 is
refused with the Python tool's message, and the exit code is 2.

## What is in here

- `sor.js` is the command line. `sorlib/index.js` lists the modules.
- `sorlib/model.js` reads the spec folder (`tools/sorlib/model.py`), `sorlib/scan.js` and `sorlib/anchors.js` find the code regions
  (`markers.py` `Scan`, `anchors.py`), `sorlib/status.js` compares the two with the lock (`lock.py`), and `sorlib/views.js` shapes the
  answers (`index.py`, `views.py`, `blame.py`).
- `sorlib/markers.js` and `sorlib/lock.js` are the rules that decide whether a lock written by one tool reads as unchanged by the other
  (SPEC §10 and §11): the style of a file type, the splitting of lines, the normalization of code, `@clause` markers, the hash of a clause's
  code, the digest of its code per target, and the text of the lock file.
- `sorlib/pytext.js` has the text rules of Python that JavaScript has in another form (what whitespace is, what a word character is, what a
  dot matches, the order of strings). The other files use it and nothing else for these.

## Tests

    node tools/js/test/vectors.js     run every row of vectors/hashing.json

`tools/test_sor_js.py` runs that in the normal test run, and also checks the JavaScript against the Python tool, which is the reference:

- the code of this repository through every style, plain and with characters put in at random places, and markers and lock texts;
- a project in many states (a clause reworded, code edited in one language, a region shared by two clauses, a language left behind, a
  lock from a newer sor, a damaged lock, ...): the three JSON answers must be equal, and the states must include every kind of finding.

`SOR_COMPARE_JS=1 python3 -m unittest discover -s tools -p 'test_*.py'` does the second kind for every state the whole test suite makes: before and
after each command a test runs, the project goes through both tools. It takes about twelve minutes, and it is how this copy meets states
nobody thought of. Run it after a change to how the Python tool reads a project, and read what differs.

Both are skipped, with a message, when `node` is not installed; nothing in the Python tool needs it.

## Keeping the two in step

- A change to how `tools/sorlib` reads a project or to what the three commands print goes into `tools/js/sorlib/` in the same change, and
  `sh plugins/sync-tools.sh` copies the result into the extension.
- A change to the hashing, marker or lock text rules also goes into `vectors/hashing.json` through `python3 vectors/make_hashing.py`.
- This copy is written by hand. The tool has no Spec of Record project of its own, so nothing builds it from clauses.
