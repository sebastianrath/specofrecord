# The hashing rules in JavaScript

A copy of the rules in `tools/sorlib` that decide whether a lock written by one tool reads as unchanged by the other (SPEC §10 and §11),
for an editor that has no Python: the style of a file type, the splitting of lines, the normalization of code, `@clause` markers, the hash
of a clause's code, the digest of its code per target, and the text of the lock file. It has no project reader and no command line, and the
extension and the plugin do not ship it yet.

It is plain JavaScript (CommonJS) with no dependencies, for Node 16 or later, the Node of VS Code 1.80.

    node tools/js/test/vectors.js     run every row of vectors/hashing.json

`tools/test_sor_js.py` runs that in the normal test run, and also puts the code of this repository through both tools and compares the
answers. It is skipped, with a message, when `node` is not installed.

- `sorlib/pytext.js` has the text rules of Python that JavaScript has in another form (what whitespace is, what a word character is, what a
  dot matches, the order of strings). The other files use it and nothing else for these.
- `sorlib/markers.js`, `sorlib/lock.js` and `sorlib/model.js` follow `tools/sorlib/markers.py`, `lock.py` and `model.py`.
- A change to those rules in the Python goes in here in the same change, and into `vectors/hashing.json` through `vectors/make_hashing.py`.
- This copy is written by hand. The tool has no Spec of Record project of its own yet, so nothing builds it from clauses.
