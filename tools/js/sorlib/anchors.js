'use strict';
// Symbol anchors (`tools/sorlib/anchors.py`): a clause names the code it is about with an indented line `code: path#name`, and the lines of
// that function, class, method or constant belong to the clause. Every language but Python is read by declaration patterns and brace
// matching, exactly as the Python tool does. Python files are read there with Python's own parser, which JavaScript does not have: here
// they are read by a tokenizer (below) that agrees with `ast` on the first and last line of a def, a class or an assignment, and on the files
// that `ast` refuses because a string or a bracket is left open or the indentation does not fit. It does not check the grammar: a bad operator
// that makes Python refuse the whole file leaves the functions of that file found here.
const { splitLines } = require('./model');
const T = require('./pytext');

const WORD = '\\p{L}\\p{N}_';

function split(target) {
  const i = target.indexOf('#');
  return i < 0 ? [target, ''] : [target.slice(0, i), target.slice(i + 1)];
}

/** (first line, last line), 1-based, of `name` in a file's text; the whole file without a name; null when it is not there. */
function find(text, path, name) {
  const lines = splitLines(text);
  if (!name) return [1, Math.max(1, lines.length)];
  if (path.endsWith('.py')) return pythonSpan(lines, name);
  const names = name.split(/\.|::/);
  if (names.length > 1) {   // C++ writes a method outside its class as Owner::name
    const span = braces(lines, [names.join('::')]);
    if (span) return span;
  }
  return braces(lines, names);
}

// --- Python: the statements of a file, read the way the tokenizer reads them -------------------------------------------------------
// The Python tool asks `ast` for the first line and the last line of a top-level def, class or assignment, and of those inside a class or a
// def. JavaScript has no such parser, so this reads logical lines (strings, brackets, comments and continuation lines as Python's tokenizer
// takes them) and the blocks that indentation makes of them. It answers `null` for a file Python would not parse because of a string or a
// bracket left open or an indentation that does not fit, as `ast.parse` raises SyntaxError there.

const PY_NAME = `[\\p{L}\\p{N}_]`;
const COMPOUND = /^(?:async[ \t]+def|def|class|if|elif|else|for|while|try|except|finally|with|match|case)(?![\p{L}\p{N}_])/u;
// `match` and `case` are names in a program that does not use the statement: `match = re.compile(x)`, `case: int = 3`, `match.group()`
const SOFT_NAME = /^(?:match|case)[ \t]*(?:=(?!=)|:|[.,;)\]]|$)/u;
const isCompound = (s) => COMPOUND.test(s) && !SOFT_NAME.test(s);

/** The width of a line's indentation as the tokenizer counts it: a tab goes to the next multiple of 8, a form feed starts again. */
function indentWidth(line) {
  let n = 0;
  for (const c of line) {
    if (c === ' ') n += 1;
    else if (c === '\t') n = (Math.floor(n / 8) + 1) * 8;
    else if (c === '\f') n = 0;
    else break;
  }
  return n;
}

/** [{first, last, indent, code}] for the logical lines of a Python source (`code`: the statement with the inside of strings and the comments
 *  blanked), or null when a string, a bracket or a backslash is left open, or a bracket is closed that was not opened. */
function logicalLines(lines) {
  const out = [];
  let cur = null;
  let depth = 0;
  let triple = null;   // the three quote characters of a string that goes on to the next line
  let single = null;   // the quote of a single-line string that a backslash at the end of the line carries on
  let joined = false;  // the line before ended with a backslash outside a string
  for (let n = 0; n < lines.length; n++) {
    const line = lines[n];
    if (triple === null && single === null && depth === 0 && !joined) {
      const s = T.lstrip(line);
      if (!s || s[0] === '#') continue;   // a blank line or a comment is no statement
      cur = { first: n + 1, last: n + 1, indent: indentWidth(line), code: '' };
    }
    cur.last = n + 1;
    cur.code += ' ';   // a physical line break is a space inside a statement
    let i = 0;
    let carried = false;
    joined = false;
    while (i < line.length) {
      const c = line[i];
      if (triple !== null || single !== null) {
        const end = triple !== null ? triple : single;
        if (c === '\\') {
          i += 2;
          cur.code += ' ';
          if (i > line.length) carried = true;   // the backslash was the last character: the string goes on in the next line
          continue;
        }
        if (line.startsWith(end, i)) {
          cur.code += end;
          i += end.length;
          triple = null;
          single = null;
        } else {
          cur.code += ' ';
          i += 1;
        }
        continue;
      }
      if (c === '#') break;
      if (c === '"' || c === "'") {
        if (line.startsWith(c.repeat(3), i)) {
          triple = c.repeat(3);
          cur.code += triple;
          i += 3;
        } else {
          single = c;
          cur.code += c;
          i += 1;
        }
        continue;
      }
      if (c === '\\' && i === line.length - 1) {
        joined = true;
        i += 1;
        continue;
      }
      if ('([{'.includes(c)) depth += 1;
      else if (')]}'.includes(c)) {
        depth -= 1;
        if (depth < 0) return null;
      }
      cur.code += c;
      i += 1;
    }
    if (single !== null && !carried) return null;   // a string of one line is closed in its line, or the line ends with a backslash
    if (triple === null && single === null && depth === 0 && !joined) out.push(cur);
  }
  return triple === null && single === null && depth === 0 && !joined ? out : null;
}

/** The number of the line in `ll` that a block opened by line `k` ends with, or k when it has no block. */
function blockEndIndex(ll, k, hi) {
  let j = k + 1;
  while (j < hi && ll[j].indent > ll[k].indent) j += 1;
  return j - 1;
}

/** The text of a statement up to its first top-level colon is a compound statement's header: whether the colon ends the statement (a block follows). */
function opensBlock(code) {
  const s = code.trim();
  if (!isCompound(s)) return false;
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if ('([{'.includes(c)) depth += 1;
    else if (')]}'.includes(c)) depth -= 1;
    else if (c === ':' && depth === 0 && s[i + 1] !== '=') return T.strip(s.slice(i + 1)) === '';   // `:=` is no colon
  }
  return false;
}

/** Whether the indentation of the logical lines fits together: a block after a colon, and every dedent back to a level that was open. */
function indentsFit(ll) {
  const stack = [0];
  let opened = false;
  for (const l of ll) {
    const top = stack[stack.length - 1];
    if (opened) {
      if (l.indent <= top) return false;
      stack.push(l.indent);
    } else if (l.indent > top) {
      return false;
    } else {
      while (l.indent < stack[stack.length - 1]) stack.pop();
      if (l.indent !== stack[stack.length - 1]) return false;
    }
    opened = opensBlock(l.code);
  }
  return !opened;
}

/** The statements of a line, split at the semicolons outside brackets. */
function simpleStatements(code) {
  const out = [];
  let depth = 0;
  let from = 0;
  for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if ('([{'.includes(c)) depth += 1;
    else if (')]}'.includes(c)) depth -= 1;
    else if (c === ';' && depth === 0) {
      out.push(code.slice(from, i));
      from = i + 1;
    }
  }
  out.push(code.slice(from));
  return out.map((x) => T.strip(x)).filter((x) => x);
}

const OPERATOR = /(?:<<|>>|\*\*|\/\/|[-+*\/%&|^@])=|[<>!=:]=|=/y;
const AUGMENTED = /^(?:<<|>>|\*\*|\/\/|[-+*\/%&|^@])=$/;

/** Whether a statement is an assignment, or an annotation with or without a value, to the name `part` (a plain name, maybe in parentheses). */
function assignsTo(code, part) {
  const isPart = (text) => {
    let t = T.strip(text);
    while (t.startsWith('(') && t.endsWith(')')) t = T.strip(t.slice(1, -1));
    return t === part && new RegExp(`^${PY_NAME}+$`, 'u').test(t) && !/^[0-9]/.test(t);
  };
  if (isCompound(T.strip(code))) return false;   // a compound statement with its body on the same line: the statements after the colon are the body's
  for (const s of simpleStatements(code)) {
    let depth = 0;
    let colon = -1;
    const equals = [];
    let augmented = false;
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if ('([{'.includes(c)) depth += 1;
      else if (')]}'.includes(c)) depth -= 1;
      else if (depth === 0 && c === ':' && colon < 0 && equals.length === 0 && s[i + 1] !== '=') colon = i;
      else if (depth === 0 && '=<>!:+-*/%&|^@'.includes(c)) {
        OPERATOR.lastIndex = i;
        const m = OPERATOR.exec(s);
        if (m === null) continue;
        if (m[0] === '=') equals.push(i);
        else if (AUGMENTED.test(m[0]) && equals.length === 0) augmented = true;   // x += 1 assigns, but it is not an Assign
        i += m[0].length - 1;
      }
    }
    if (augmented) continue;
    if (colon >= 0) {
      if (isPart(s.slice(0, colon))) return true;
      continue;
    }
    // a = b = value: every piece before the last equals sign is a target
    let from = 0;
    for (const e of equals) {
      if (isPart(s.slice(from, e))) return true;
      from = e + 1;
    }
  }
  return false;
}

function pythonSpan(lines, name) {
  const ll = logicalLines(lines);
  if (ll === null || !indentsFit(ll)) return null;
  let lo = 0;
  let hi = ll.length;
  const parts = name.split('.');
  for (let k = 0; k < parts.length; k++) {
    const part = parts[k];
    const def = new RegExp(`^(?:async[${T.SPACE}]+def|def|class)[${T.SPACE}]+${T.escapeRegExp(part)}(?![${WORD}])`, 'u');
    const level = lo < hi ? ll[lo].indent : -1;
    let found = -1;
    for (let i = lo; i < hi; i++) {
      if (ll[i].indent !== level) continue;
      if (def.test(ll[i].code.trim()) || assignsTo(ll[i].code, part)) found = i;   // the last one counts, as a later def of the name replaces the first
    }
    if (found < 0) return null;
    const end = blockEndIndex(ll, found, hi);
    if (k === parts.length - 1) {
      let first = found;
      while (first > lo && ll[first - 1].indent === ll[found].indent && ll[first - 1].code.trim().startsWith('@')) first -= 1;
      return [ll[first].first, ll[end].last];
    }
    lo = found + 1;
    hi = end + 1;
  }
  return null;
}

const KEYWORDS = `(?:export[${T.SPACE}]+)?(?:default[${T.SPACE}]+)?(?:pub(?:\\([^)]*\\))?[${T.SPACE}]+)?(?:async[${T.SPACE}]+)?(?:static[${T.SPACE}]+)?`;

/** What follows a name in a pattern that ends it with \b. */
function boundary(name) {
  return /[\p{L}\p{N}_]$/u.test(name) ? T.WORD_END : `(?=[${WORD}])`;
}

function declPatterns(name) {
  const n = T.escapeRegExp(name);
  const b = boundary(name);
  const S = T.SPACE;
  const flags = 'su';
  return [
    new RegExp(`${KEYWORDS}(?:function[${S}]*\\*?|class|struct|interface|enum|union|trait|impl|type|fn|func(?:[${S}]*\\([^)]*\\))?|def|namespace|module|record)[${S}]+${n}${b}`, flags),
    new RegExp(`${KEYWORDS}(?:const|let|var|val)[${S}]+${n}${b}`, flags),
    new RegExp(`^[${S}]*(?:[${WORD}$<>\\[\\],:*&~]+[${S}]+)+(?:[${WORD}$<>]+::)*${n}[${S}]*\\([^;]*$`, flags),   // C, C++, Java, C#
    new RegExp(`^[${S}]*${KEYWORDS}${n}[${S}]*\\([^;]*\\)[${S}]*\\{?[${S}]*$`, flags),      // object or class method
    new RegExp(`^[${S}]*${n}[${S}]*:[${S}]*(?:async[${S}]+)?function${T.WORD_END}`, flags),
  ];
}

function braces(lines, names, lo = 0, hi = null) {
  hi = hi === null ? lines.length : hi;
  const patterns = declPatterns(names[0]);
  for (let i = lo; i < hi; i++) {
    if (patterns.some((p) => p.test(lines[i]))) {
      const end = braceEnd(lines, i, hi);
      if (names.length === 1) return [i + 1, end + 1];
      const inner = braces(lines, names.slice(1), i + 1, end);
      if (inner) return inner;
    }
  }
  return null;
}

/** Last line of the declaration starting at `start`: through its matching `}`, or through the `;` that ends it when it opens no block. */
function braceEnd(lines, start, hi) {
  let depth = 0;
  let opened = false;
  let quote = null;
  let blockComment = false;
  for (let i = start; i < hi; i++) {
    const line = lines[i];
    let j = 0;
    while (j < line.length) {
      const c = line[j];
      const two = line.slice(j, j + 2);
      if (blockComment) {
        if (two === '*/') {
          blockComment = false;
          j += 1;
        }
      } else if (quote) {
        if (c === '\\') j += 1;
        else if (c === quote) quote = null;
      } else if (two === '//') {
        break;
      } else if (two === '/*') {
        blockComment = true;
        j += 1;
      } else if ('"\'`'.includes(c)) {
        quote = c;
      } else if (c === '{') {
        depth += 1;
        opened = true;
      } else if (c === '}') {
        depth -= 1;
        if (opened && depth === 0) return i;
      } else if (c === ';' && !opened && depth === 0) {
        return i;
      }
      j += 1;
    }
    if (quote === '"' || quote === "'") quote = null;   // strings do not run past the end of a line
    if (!opened && i - start >= 3) return start;   // no block opened within a few lines: a one-line declaration
  }
  return opened ? hi - 1 : start;
}

module.exports = { split, find };
