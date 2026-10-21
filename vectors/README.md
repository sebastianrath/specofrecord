# Hashing vectors

`hashing.json` holds rows of input and expected output for the rules that decide whether a lock written by one implementation of the
tool is read as unchanged by another (SPEC section 11): which style a file gets, how lines are split, how code is normalized, how the
regions of a clause are joined and hashed, how a text is hashed, how the code of a clause per target is digested and folded out of the
lock file's lines, and how the lock file is written.

An implementation passes when it gives the expected output for every row. The Python tool runs them in `tools/test_sor_vectors.py`;
a port (for example a TypeScript one, so that an editor needs no Python) loads the same file.

- The expected texts were written by hand, and every hash was computed with SHA-256 alone, never with the tool. Three rows carry the
  hashes the tool pinned before the rule followed the file type.
- A row has a unique `name`, so a failure names the row.
- The Python rows include f-strings with fields that reuse their quote or span lines (Python 3.12 and later): a port reads them whatever
  Python it runs on.
- A rule that changes means the rows change in the same commit, and `format` in the file counts the changes that are not
  additions. Adding rows does not change it.
- Not covered: the evidence fingerprint, which needs a parsed project, and the status of a clause.

## Adding a row
Give it a new unique `name`, the input, and the expected output written by hand from the rule. A `hash` is SHA-256 of the expected
text, UTF-8, the first 12 hex digits. Run `python3 -m unittest tools.test_sor_vectors`: when a hash is wrong, the failure prints the value
the text really has, and when the output is wrong, it prints both texts. If your hand-written text and the tool disagree, find out which
one follows the rule before changing either.
