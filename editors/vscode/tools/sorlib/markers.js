'use strict';
// How the Python tool reads `@clause` markers (SPEC §10) and normalizes code before it hashes it (SPEC §11), line for line, so that
// the two tools give one hash for one piece of code. `vectors/hashing.json` is what says they do. Only the rules are here: finding
// files, projects and checking ids against the spec are not.
const crypto = require('crypto');
const { splitLines } = require('./model');
const T = require('./pytext');

// ---- markers ------------------------------------------------------------------------------------------------------------------

// A marker is `@clause` after a comment starter. A starter is a run (`;; @clause`, `/// @clause`), so the marker is the whole line and
// not "code, then a line marker". Every file has these; a type adds its own (LANGUAGES) and a target may declare more.
const BASE_STARTERS = ['//+', '#+', '/\\*+', '<!--', '-{2,}', ';+'];
const EXTRA_STARTERS = new Map([
  ['%', '%+'], ['!', '!+'], ["'", "'+"], ['(*', '\\(\\*+'],
  ['rem', `^[${T.SPACE}]*(?:[rR][eE][mM]${T.WORD_END}|::)`],
]);
const MARKER_CLOSERS = new RegExp(`(\\*/|-->|\\*\\))[${T.SPACE}]*$`);   // a comment that closes on the line is not an id
const MARKERS = new Map();

/** The regular expression that finds a marker in a line, for the extra starters of a file. Group 1 is what follows `@clause`. */
function markerRegex(extras = []) {
  const key = Array.from(new Set(extras));
  const id = key.join('\u0000');
  if (!MARKERS.has(id)) {
    const alts = BASE_STARTERS.concat(key.map((s) => {
      if (EXTRA_STARTERS.has(s)) return EXTRA_STARTERS.get(s);
      const last = Array.from(s).pop();
      return `${T.escapeRegExp(s)}${T.escapeRegExp(last)}*`;
    }));
    MARKERS.set(id, new RegExp(`(?:${alts.join('|')})[${T.SPACE}]*@clause${T.WORD_END}(.*)$`, 'su'));
  }
  return MARKERS.get(id);
}

/** [the code before the marker, the words after `@clause`] of a line, from the match of `markerRegex`. */
function splitMarker(m, line) {
  return [T.rstrip(line.slice(0, m.index)), T.words(m[1].replace(MARKER_CLOSERS, ''))];
}

/**
 * {code, words} of a line of the file at this path that holds a marker, else null. `starters`: what the file's target declares besides
 * the starters of its type.
 */
function parseMarker(rel, line, starters = []) {
  const m = markerRegex(startersOf(rel).concat(starters)).exec(line);
  if (m === null) return null;
  const [code, words] = splitMarker(m, line);
  return { code, words };
}

class Region {
  constructor(file, start, kind, ids) {
    this.file = file;
    this.start = start;
    this.kind = kind;
    this.ids = ids;
    this.end = null;
    this.lines = [];
    this.keys = [];   // lock keys after checking: item, row and part ids, test ids, or glue:<file>
    this.cache = new Map();
  }

  get where() {
    return this.end ? `${this.file}:${this.start}-${this.end}` : `${this.file}:${this.start}`;
  }

  contains(n) {
    return this.start <= n && n <= (this.end || this.start);
  }

  /** This region's code as the lock sees it under a style, worked out once. The lines do not change once the scan is made. */
  normalized(style) {
    if (!this.cache.has(style)) this.cache.set(style, normalized(this.lines, style));
    return this.cache.get(style);
  }
}

const problem = (kind, where, text) => ({ kind, where, text });

/** {regions, problems, unmarked} of one file's text: the regions, what is wrong with its markers, and the numbers of code lines outside any region. */
function scanText(rel, text, starters = []) {
  const regions = [];
  const problems = [];
  let unmarked = [];
  let cur = null;
  let whole = null;
  const lines = splitLines(text);
  const mark = markerRegex(startersOf(rel).concat(starters));
  lines.forEach((line, index) => {
    const n = index + 1;
    const m = mark.exec(line);
    if (!m) {
      if (cur !== null) cur.lines.push(T.rstrip(line));
      else if (T.strip(line)) unmarked.push(n);
      return;
    }
    const [code, words] = splitMarker(m, line);
    const head = words.length ? words[0] : '';
    if (code) {
      // a line marker: this one line belongs to the ids at its end (a table row, say), not to the region around it
      const r = new Region(rel, n, 'line', words);
      r.end = n;
      r.lines = [code];
      if (!words.length || ['end', 'glue', 'test', 'file'].includes(head)) {
        problems.push(problem('marker', `${rel}:${n}`, 'a line marker names the ids its line serves'));
      }
      regions.push(r);
      return;
    }
    if (head === 'end') {
      if (cur === null) {
        problems.push(problem('marker', `${rel}:${n}`, '@clause end without an open region'));
      } else {
        cur.end = n;
        regions.push(cur);
        cur = null;
      }
      return;
    }
    if (cur !== null) {
      problems.push(problem('marker', `${rel}:${n}`, `regions never nest: the region at line ${cur.start} is still open`));
      cur.end = n - 1;
      regions.push(cur);
      cur = null;
    }
    if (head === 'file') {
      whole = new Region(rel, n, 'file', words.slice(1));
      return;
    }
    if (head === 'glue') cur = new Region(rel, n, 'glue', []);
    else if (head === 'test') cur = new Region(rel, n, 'test', words.slice(1));
    else cur = new Region(rel, n, 'code', words);
    if (cur.kind !== 'glue' && !cur.ids.length) problems.push(problem('marker', `${rel}:${n}`, '@clause needs at least one id'));
  });
  if (cur !== null) {
    problems.push(problem('marker', `${rel}:${cur.start}`, 'region is never closed with @clause end'));
    cur.end = lines.length;
    regions.push(cur);
  }
  if (whole !== null) {
    whole.end = lines.length;
    whole.lines = lines.filter((l) => !mark.test(l)).map(T.rstrip);
    regions.push(whole);
    unmarked = [];
  }
  return { regions, problems, unmarked };
}

// ---- the style of a file --------------------------------------------------------------------------------------------------------

const QUOTED = /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/s;
const COMMENT_LINE = /^(\/\/.*|\/\*.*\*\/|<!--.*-->)$/s;
const HASH_COMMENT = /^#(?!!).*$/s;   // a `#!` line names the interpreter: that is code
// `--` ends in a symbol character only in Haskell, where `-->` is an operator and a line that starts with one continues an expression.
// `{-#` is a pragma, and a block comment that closes and then goes on with code is code.
const DASH_COMMENT = /^(--+(?![!#$%&*+./<=>?@\\^|~:]).*|\/\*(?:(?!\*\/).)*\*\/|\{-(?!#)(?:(?!-\}).)*-\})$/s;
// A comment that changes what the interpreter does is code: a Python coding cookie changes how the file is read, and so does Ruby's
// `# frozen_string_literal: true`.
const MAGIC = /^#.*(?:coding[:=]|frozen_string_literal:|shareable_constant_value:)/s;

// How a file's code is normalized follows its type. A style is written `family[-keep][+kinds]`. One row per kind of file: its
// extensions, its style, and the comment starters (besides the ones every file has) that a marker may be written after. This is the
// table of tools/sorlib/markers.py; the vectors have a row for every type in it, in both directions.
const LANGUAGES = [
  ['py pyi pyw pyx pxd pxi bzl bazel star sky', 'python', ''],
  ['sh bash zsh ksh fish rb rake gemspec pl pm r toml ex exs jl ps1 psm1 tf tfvars cmake nix tcl cr awk', 'hash', ''],
  ['sql lua vhd vhdl ada adb ads', 'dash', ''],
  ['hs elm purs idr', 'dash-keep', ''],
  ['nim nims coffee', 'hash-keep', ''],
  ['js jsx mjs cjs ts tsx mts cts', 'c+tick', ''],
  ['go', 'c+rawtick', ''],
  ['java kt kts swift cs', 'c+triple', ''],
  ['dart groovy gradle', 'c+triple+triple1', ''],
  ['scala sc', 'c-keep+triple', ''],
  ['fs fsx fsi', 'c-keep', '(*'],
  ['sass styl', 'c-keep', ''],
  ['c h cc cpp cxx c++ h++ hh hpp hxx cppm ixx inl ipp tpp ino mm rs php zig sol proto thrift prisma dts dtsi d v sv svh '
   + 'glsl vert frag comp geom tesc tese mesh task rgen rchit rmiss rahit rint rcall hlsl hlsli wgsl slang metal cu cuh cl '
   + 'html htm xhtml css scss less vue svelte astro erb cshtml razor jsp asp aspx hbs mustache twig ejs liquid mdx '
   + 'xml svg xsd xsl xslt xaml plist csproj fsproj vbproj props targets resx wsdl rss storyboard xib '
   + 'json jsonc json5', 'c', ''],
  ['graphql gql', 'hash', ''],
  ['m', 'c', '%'],                       // Objective-C, or MATLAB
  ['pas pp', 'c', '(*'],
  ['erl hrl tex sty', 'safe', '%'],
  ['f f90 f95 f03 f08 for ftn', 'safe', '!'],
  ['vb vbs bas', 'safe', "'"],
  ['bat cmd', 'safe', 'rem'],
  ['ml mli mll mly', 'safe', '(*'],
];
// Files known by their name, not their extension.
const LANGUAGES_BY_NAME = new Map([['dockerfile', 'hash'], ['containerfile', 'hash'], ['rakefile', 'hash'], ['gemfile', 'hash'],
  ['vagrantfile', 'hash'], ['cmakelists.txt', 'hash']]);
// ... and by the name exactly as written: a script called `build` is a shell script, `BUILD` is Bazel's.
const LANGUAGES_BY_EXACT_NAME = new Map([['BUILD', 'python'], ['WORKSPACE', 'python']]);
const DEFAULT_STYLE = 'safe';
const STYLES = new Map();
for (const [exts, style, starters] of LANGUAGES) for (const ext of T.words(exts)) STYLES.set(ext, [style, starters]);
const FAMILIES = ['c', 'hash', 'dash', 'python', 'safe'];
const KINDS = ['tick', 'rawtick', 'triple', 'triple1'];

/** [style, extra marker starters] of the file at this project-relative path (its parts are separated by `/`). */
function language(rel) {
  const exact = rel.slice(rel.lastIndexOf('/') + 1);
  const name = exact.toLowerCase();
  if (LANGUAGES_BY_EXACT_NAME.has(exact)) return [LANGUAGES_BY_EXACT_NAME.get(exact), ''];
  if (LANGUAGES_BY_NAME.has(name)) return [LANGUAGES_BY_NAME.get(name), ''];
  const dot = name.lastIndexOf('.');
  if (dot < 0) return [DEFAULT_STYLE, ''];
  return STYLES.get(name.slice(dot + 1)) || [DEFAULT_STYLE, ''];
}

/** The comment starters, besides the ones every file has, that a marker may follow in the file at this path (its type's). */
function startersOf(rel) {
  return T.words(language(rel)[1]);
}

/** The normalization style of the file at this project-relative path; `safe` for a type not listed. */
function styleOf(rel) {
  return language(rel)[0];
}

// ---- normalizing code -------------------------------------------------------------------------------------------------------------

/** One space for every run of spaces outside quotes; what is inside quotes stays as written. */
function collapse(t) {
  return t.split(QUOTED).map((part, i) => (i % 2 ? part : part.replace(/[ \t]+/g, ' '))).join('');
}

/**
 * How indentation reads in a hash: the number of spaces (`3`), or, when it holds a tab or another whitespace character, the
 * indentation itself with each of those written as `\u` and its code point in four hex digits at least (`  \u0009`), so that a tab
 * is never the same as eight spaces.
 */
function lead(rest) {
  if (/^ *$/.test(rest)) return String(rest.length);
  return Array.from(rest).map((c) => (c === ' ' ? c : `\\u${c.codePointAt(0).toString(16).padStart(4, '0')}`)).join('');
}

/**
 * The texts of the kept lines [[line, text]], each led by its indentation when indentation counts (`3:foo`): the indentation as
 * written, less the characters all the kept lines start with, so that moving the whole piece of code is not a change.
 */
function indented(kept, keep) {
  if (!keep) return kept.map(([, text]) => text);
  const leads = kept.map(([line]) => line.slice(0, line.length - T.lstrip(line).length));
  const base = T.commonPrefix(leads).length;
  return kept.map(([, text], i) => `${lead(leads[i].slice(base))}:${text}`);
}

/**
 * Code as the lock sees it: no blank lines, no comment-only lines, no indentation, and one space for every run of spaces outside
 * quotes. Text inside quotes and everything else stays exactly as written, so re-indenting and re-spacing is not a change but a new
 * word is. `style` says which lines are comments, whether indentation counts, and which multi-line strings there are.
 */
function normalized(lines, style = 'c') {
  const [base, ...kinds] = style.split('+');
  const family = base.endsWith('-keep') ? base.slice(0, -5) : base;
  if (!FAMILIES.includes(family) || kinds.some((k) => !KINDS.includes(k)) || (kinds.length && family !== 'c')) {
    throw new RangeError(`unknown normalization style '${style}'`);   // a typo must not switch a protection off in silence
  }
  if (family === 'python') return pythonNormalized(lines);
  const keep = family === 'safe' || base.endsWith('-keep');
  if (family === 'hash') return hashNormalized(lines, keep);
  const comment = family === 'c' ? COMMENT_LINE : family === 'dash' ? DASH_COMMENT : null;
  const inside = kinds.length ? insideStrings(lines, kinds) : null;
  const kept = [];
  lines.forEach((line, i) => {
    const t = T.strip(line);
    if (!t || (comment !== null && comment.test(t) && !(inside && inside[i]))) return;
    kept.push([line, keep ? t : collapse(t)]);
  });
  return indented(kept, keep).join('\n');
}

const LEX = /\/\/|\/\*|`|"""|'''|"|'/g;
const CLOSERS = new Map();

/**
 * The index just after the next `quote` at or after i, where a backslash makes the next character no closer (unless `escapes` is
 * false); -1 when the line has none.
 */
function afterCloser(line, i, quote, escapes = true) {
  if (!escapes) {
    const j = line.indexOf(quote, i);
    return j < 0 ? -1 : j + quote.length;
  }
  if (!CLOSERS.has(quote)) CLOSERS.set(quote, new RegExp(`\\\\|${T.escapeRegExp(quote)}`, 'g'));
  for (;;) {
    const m = T.searchFrom(CLOSERS.get(quote), line, i);
    if (m === null) return -1;
    if (m[0] !== '\\') return m.index + m[0].length;
    i = m.index + 2;
  }
}

/**
 * For each line, whether it starts inside a multi-line string (so it is text, and a line that looks like a comment is not one).
 * `kinds`: tick, rawtick, triple, triple1. Comments are skipped, `//` to the end of the line and `/* *\/` over lines, before a quote
 * is looked for, and a quote that closes on its line is a string of one line. Wrongly inside keeps comment lines, which only gives a
 * false alarm. Wrongly outside hides a change, and the tracker catches the one case it can see: a region that ends inside a string or
 * a comment has lost its place, so none of its lines is dropped.
 */
function insideStrings(lines, kinds) {
  const opens = new Map([['`', kinds.includes('tick') || kinds.includes('rawtick')], ['"""', kinds.includes('triple')],
    ["'''", kinds.includes('triple1')]]);
  const escapes = !kinds.includes('rawtick');
  const out = [];
  let state = null;   // null, 'block' (inside a block comment), or the closer of the multi-line string that is open
  for (const line of lines) {
    out.push(state !== null && state !== 'block');
    let i = 0;
    const n = line.length;
    while (i < n) {
      if (state === 'block') {
        const j = line.indexOf('*/', i);
        if (j < 0) break;
        state = null;
        i = j + 2;
      } else if (state !== null) {
        const j = afterCloser(line, i, state, escapes || state !== '`');
        if (j < 0) break;
        state = null;
        i = j;
      } else {
        const m = T.searchFrom(LEX, line, i);
        if (m === null) break;
        let tok = m[0];
        i = m.index + tok.length;
        if (tok === '//') break;
        if (tok === '/*') {
          const j = line.indexOf('*/', i);
          if (j < 0) {
            state = 'block';
            break;
          }
          i = j + 2;
          continue;
        }
        if ((tok === '"""' || tok === "'''") && !opens.get(tok)) {
          tok = tok[0];   // an empty string, then whatever follows
          i = m.index + 1;
        }
        const j = afterCloser(line, i, tok, escapes || tok !== '`');
        if (opens.get(tok)) {
          if (j < 0) {
            state = tok;
            break;
          }
          i = j;
        } else if ((tok === '"' || tok === "'") && j >= 0) {
          i = j;   // a string of one line (an unclosed quote is an apostrophe)
        }
      }
    }
  }
  // A region does not end inside a string or a comment, so the tracker lost its place (a lone backtick in JSX text, say). Every line
  // is then kept as text, which can only give a false alarm; reading on would trust a parity that is wrong.
  return state !== null ? lines.map(() => true) : out;
}

/** Whether a stripped line of a `#` language is a comment of its own (a magic comment is not). */
function isComment(t) {
  return HASH_COMMENT.test(t) && !MAGIC.test(t);
}

/**
 * Python code without layout but with its nesting: comment-only lines and blank lines are gone, spaces are collapsed, and every line
 * that starts a statement carries its depth (`2:return x`), counted in levels, not in columns, so changing 2 spaces to 4 everywhere is
 * not a change and moving a line into a loop is. Lines that continue a statement (inside brackets, after a backslash, inside a
 * multi-line string) carry no depth. A `#` line inside a multi-line string is text, not a comment.
 */
function pythonNormalized(lines) {
  const out = [];
  const levels = new Levels();
  let stack = [];
  let depth = 0;
  let continued = false;
  for (const line of lines) {
    const t = T.strip(line);
    if (stack.length) {
      if (t) out.push(collapse(t));
    } else if (t && !isComment(t)) {
      let text = collapse(t);
      if (depth === 0 && !continued) {
        const width = T.expandedLength(line.slice(0, line.length - T.lstrip(line).length));
        text = `${levels.of(width)}:${text}`;
      }
      out.push(text);
    }
    [stack, depth, continued] = pythonState(line, stack, depth);
  }
  return out.join('\n');
}

/**
 * The depth of the statements of a piece of code, counted from the first one. A piece of code is often not a whole file: it may start
 * inside a method and go on with a line of the class around it, so the depth can go below the first line's (-1).
 */
class Levels {
  constructor() {
    this.stack = [];   // the columns of the open levels, increasing
    this.below = 0;    // how many levels under the first line's there have been
  }

  /**
   * The level of a statement that starts at this column: deeper than the line before opens a level, shallower closes levels down to
   * the column it matches, and shallower than every open level is a new level below them all.
   */
  of(width) {
    const stack = this.stack;
    if (!stack.length || width > stack[stack.length - 1]) {
      stack.push(width);
    } else {
      while (stack.length > 1 && width < stack[stack.length - 1]) stack.pop();
      if (width > stack[stack.length - 1]) {    // a dedent that matches no level there was: a new one
        stack.push(width);
      } else if (width < stack[stack.length - 1]) {   // shallower than all of them: the piece began inside a block
        stack.length = 0;
        stack.push(width);
        this.below += 1;
      }
    }
    return stack.length - 1 - this.below;
  }
}

const PY_OPEN = /['"#()[\]{}]/g;
const PY_FIELD = /['"#()[\]{}:]/g;   // what matters inside the code of an f-string's replacement field
const PY_SPEC = /[{}]/g;             // and inside its format spec
const PY_CLOSE = new Map(['"', "'", '"""', "'''"].map((q) => [q, new RegExp(`\\\\|${q}`, 'g')]));
const PY_LITERAL = new Map();        // quote -> what matters in the text of an f-string

function literal(quote) {
  if (!PY_LITERAL.has(quote)) PY_LITERAL.set(quote, new RegExp(`\\\\|\\{\\{|\\}\\}|\\{|\\}|${quote}`, 'g'));
  return PY_LITERAL.get(quote);
}

/**
 * [frame, length of the opening quotes] of the string whose quote is at line[j]. A frame is ['s', quote] for a string and
 * ['f', quote, raw] for an f-string or a template string (`t"..."`, Python 3.14), which have code in them the same way. The prefix is
 * read back from the quote, and the end of a name such as `if` in `if"x"` or `not` in `not"x"` is not a prefix.
 */
function openString(line, j) {
  const q = line[j];
  const quote = line.startsWith(q.repeat(3), j) ? q.repeat(3) : q;
  let k = j;
  while (k > 0 && j - k < 2 && 'rRbBuUfFtT'.includes(line[k - 1])) k--;
  let prefix = line.slice(k, j).toLowerCase();
  if (k > 0 && T.isWordChar(T.charBefore(line, k))) prefix = '';
  if (prefix.includes('f') || prefix.includes('t')) return [['f', quote, prefix.includes('r')], quote.length];
  return [['s', quote], quote.length];
}

/**
 * [what is open, bracket depth, whether the statement goes on] after one line of Python. What is open is a list of frames, the
 * innermost last: ['s', quote] a string, ['f', quote, raw] the text of an f-string, ['e', n] the code of one of its replacement fields
 * with n brackets open in it, ['m'] its format spec. Since Python 3.12 the code of a field may use the quote of the f-string around it
 * and span lines, so the end of an f-string is found by reading the fields, not by the next quote. A one-quote string or f-string text
 * ends with its line unless a backslash goes on.
 */
function pythonState(line, open, depthBefore) {
  let depth = depthBefore;
  let i = 0;
  const n = line.length;
  let codeEnd = n;
  const stack = open.slice();
  while (i < n) {
    const top = stack.length ? stack[stack.length - 1] : null;
    if (top === null) {                         // code
      const m = T.searchFrom(PY_OPEN, line, i);
      if (m === null) break;
      const c = m[0];
      i = m.index + 1;
      if (c === '#') {
        codeEnd = m.index;
        break;
      }
      if (c === "'" || c === '"') {
        const [frame, size] = openString(line, m.index);
        stack.push(frame);
        i = m.index + size;
      } else {
        depth = Math.max(depth + ('([{'.includes(c) ? 1 : 0) - (')]}'.includes(c) ? 1 : 0), 0);
      }
    } else if (top[0] === 's') {                // a string
      const m = T.searchFrom(PY_CLOSE.get(top[1]), line, i);
      if (m === null) {
        i = n;
      } else if (m[0] === '\\') {
        i = m.index + 2;                        // the escaped character; past the end when the backslash ends the line
      } else {
        i = m.index + m[0].length;
        stack.pop();
      }
    } else if (top[0] === 'f') {                // the text of an f-string
      const m = T.searchFrom(literal(top[1]), line, i);
      if (m === null) {
        i = n;
        continue;
      }
      const g = m[0];
      i = m.index + g.length;
      if (g === '\\') {
        const next = line.slice(i, i + 1);
        if (!next) {
          i += 1;                               // a backslash at the end of the line goes on
        } else if (top[2]) {                    // raw: a backslash only keeps a quote or a backslash from meaning anything
          if (next === '\\' || next === top[1][0]) i += 1;
        } else if (next === 'N' && line.startsWith('{', i + 1)) {   // \N{NAME}
          const close = line.indexOf('}', i + 2);
          i = close < 0 ? n : close + 1;
        } else if (!'{}'.includes(next)) {
          i += 1;
        }
      } else if (g === '{') {
        stack.push(['e', 0]);
      } else if (g === top[1]) {
        stack.pop();
      }
    } else if (top[0] === 'e') {                // the code of a replacement field
      const m = T.searchFrom(PY_FIELD, line, i);
      if (m === null) break;
      const c = m[0];
      const j = m.index;
      i = j + 1;
      if (c === '#') break;                     // a comment, to the end of the line
      if (c === "'" || c === '"') {
        const [frame, size] = openString(line, j);
        stack.push(frame);
        i = j + size;
      } else if ('([{'.includes(c)) {
        stack[stack.length - 1] = ['e', top[1] + 1];
      } else if (')]'.includes(c)) {
        stack[stack.length - 1] = ['e', Math.max(top[1] - 1, 0)];
      } else if (c === '}') {
        if (top[1] > 0) stack[stack.length - 1] = ['e', top[1] - 1];
        else stack.pop();
      } else if (top[1] === 0) {                // a colon outside brackets: the format spec begins
        stack[stack.length - 1] = ['m'];
      }
    } else {                                    // the format spec of a field
      const m = T.searchFrom(PY_SPEC, line, i);
      if (m === null) break;
      i = m.index + 1;
      if (m[0] === '{') stack.push(['e', 0]);
      else stack.pop();
    }
  }
  const last = stack.length ? stack[stack.length - 1] : null;
  if (last !== null && (last[0] === 's' || last[0] === 'f') && last[1].length === 1 && i <= n) stack.pop();   // a one-quote string ends with its line
  return [stack, depth, stack.length === 0 && T.rstrip(line.slice(0, codeEnd)).endsWith('\\')];
}

const HEREDOC = /<<[-~]?[ \t]*(?:"([^"]+)"|'([^']+)'|\\?([A-Za-z_][A-Za-z0-9_]*))/y;

/**
 * Code of a `#` language (shell, Ruby, Perl, R, TOML) without layout: comment-only lines and blank lines are gone and spaces are
 * collapsed. A `#` line inside a string or a here-document is text, not a comment, so what is open at the end of a line is tracked.
 * `keep`: indentation counts, and spaces are not collapsed.
 */
function hashNormalized(lines, keep = false) {
  const kept = [];
  let open = null;
  for (const line of lines) {
    const t = T.strip(line);
    if (open === null && (!t || isComment(t))) continue;
    if (t) kept.push([line, keep ? t : collapse(t)]);
    open = hashState(line, open);
  }
  return indented(kept, keep).join('\n');
}

/**
 * What a line of a `#` language leaves open: null, the quote of a string that goes on (`"`, `'`, a backtick, or three of them), or
 * {words} for the here-documents the line started, each ended by a line that is its word. A quote is taken as opened wherever one is
 * found, so a doubtful line leaves a string open and keeps the comments after it: that can only make a comment edit count as a
 * change, never hide a change to code.
 */
function hashState(line, open) {
  if (open !== null && typeof open === 'object') {
    const words = T.strip(line) === open.words[0] ? open.words.slice(1) : open.words;
    return words.length ? { words } : null;
  }
  let i = 0;
  const n = line.length;
  const words = [];
  while (i < n) {
    if (open) {
      if (line[i] === '\\') i += 2;
      else if (line.startsWith(open, i)) {
        i += open.length;
        open = null;
      } else i += 1;
    } else if (line[i] === '#' && (i === 0 || ' \t;&|('.includes(line[i - 1]))) {
      break;
    } else if ("'\"`".includes(line[i])) {
      open = line.startsWith(line[i].repeat(3), i) ? line[i].repeat(3) : line[i];
      i += open.length;
    } else if (line.startsWith('<<<', i)) {
      i += 3;
    } else if (line.startsWith('<<', i)) {
      const m = T.matchAt(HEREDOC, line, i);
      if (m) words.push(m[1] || m[2] || m[3]);
      i = m ? m.index + m[0].length : i + 2;
    } else {
      i += 1;
    }
  }
  return open || !words.length ? open : { words };
}

/**
 * The hash of the code of these regions: in file and line order, each region normalized by the rule of its file (`legacy`: the
 * C-family rule for all), joined by a line that holds a NUL, then SHA-256, the first 12 hex digits.
 */
function codeHash(regions, legacy = false) {
  const ordered = regions.slice().sort((a, b) => T.compare(a.file, b.file) || a.start - b.start);
  const parts = ordered.map((r) => r.normalized(legacy ? 'c' : styleOf(r.file)));
  return crypto.createHash('sha256').update(parts.join('\n\u0000\n'), 'utf8').digest('hex').slice(0, 12);
}

module.exports = {
  LANGUAGES, LANGUAGES_BY_NAME, LANGUAGES_BY_EXACT_NAME, STYLES, Region, markerRegex, parseMarker, scanText, styleOf, startersOf,
  normalized, codeHash,
};
