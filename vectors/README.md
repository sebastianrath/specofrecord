# Hashing vectors

`hashing.json` holds rows of input and expected output for the rules that decide whether a lock written by one implementation of the
tool is read as unchanged by another (SPEC section 11): which style a file gets, how lines are split, how a marker is found in a line (SPEC section 10), how code is normalized, how the
regions of a clause are joined and hashed, how a text is hashed, how the code of a clause per target is digested and folded out of the
lock file's lines, and how the lock file is written.

An implementation passes when it gives the expected output for every row. The Python tool runs them in `tools/py/test_sor_vectors.py` and its JavaScript copy in `tools/js/test/vectors.js`
(`tools/py/test_sor_js.py` runs that one too); a port to another language loads the same file.

- `make_hashing.py` writes the file (`python3 vectors/make_hashing.py`, and `--check` to see whether it is up to date); a test fails when the
  two differ. The expected texts in it were written by hand, and every hash was computed with SHA-256 alone, never with the tool. The rows
  that list the table of types (an extension and its style or starters) come from the tool's own table: they stop the table changing
  without the file changing, and cannot prove it right.
- The expected texts were written by hand, and every hash was computed with SHA-256 alone, never with the tool. Three rows carry the
  hashes the tool pinned before the rule followed the file type.
- A row has a unique `name`, so a failure names the row. `style_of` has a row for every extension and name in the tool's table, and a
  test fails when the table gains one without a row, so a port cannot map a type differently.
- The Python rows include f-strings with fields that reuse their quote or span lines (Python 3.12 and later): a port reads them whatever
  Python it runs on.
- A rule that changes means the rows change in the same commit, and `format` in the file counts the changes that are not
  additions. Adding rows does not change it. Format 2 is the table of types with a safe default, and keeps indentation and tracks multi-line
  strings where the type needs it. Format 3 is a lock line that carries every field it has, which is also what makes a lock format 3.
- A row pins a rule and not what one tool happens to do. Several rows are there for the places where another language does the same thing
  differently: what whitespace is (`str.strip()`), what a word character is, what a dot matches (a line separator is text), and the order of
  strings (by code point). They were found by breaking the JavaScript copy on purpose and seeing what the rows let through.
- Not covered: the evidence fingerprint, which needs a parsed project, and the status of a clause.

## Adding a row
Give it a new unique `name`, the input, and the expected output written by hand from the rule. A `hash` is SHA-256 of the expected
text, UTF-8, the first 12 hex digits. Run `python3 -m unittest discover -s tools/py -p test_sor_vectors.py`: when a hash is wrong, the failure prints the value
the text really has, and when the output is wrong, it prints both texts. If your hand-written text and the tool disagree, find out which
one follows the rule before changing either.
