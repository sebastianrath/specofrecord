'use strict';
// The text rules of the Python tool that JavaScript has in another form. A lock written by one tool has to read as unchanged by the
// other (SPEC §11), so every place where the two differ is settled here once, and the other modules call these and nothing else:
// - what whitespace is: Python's `str.strip()`, not `trim()` and not `\s` (they differ at U+001C to U+001F, U+0085 and U+FEFF),
// - what a word character is: Unicode letters and digits and `_`, which is Python's `\w` and `\b` (JavaScript's are ASCII only),
// - what `.` matches: everything but a line feed, so the regular expressions carry the `s` flag (U+2028 and U+2029 are text),
// - the order of strings: by code point, where JavaScript's own sort goes by UTF-16 unit and puts U+10000 below U+FFFF.

// str.isspace(): the Unicode White_Space characters, and U+001C to U+001F. Not U+FEFF.
const SPACE = '\\t\\n\\v\\f\\r\\u001c-\\u001f \\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const SPACE_CHAR = new RegExp(`^[${SPACE}]$`);
const SPACE_RUN = new RegExp(`[${SPACE}]+`);
const WORD_CHAR = /^[\p{L}\p{N}_]$/u;
// What follows a word that ends in a word character, for `\b`.
const WORD_END = '(?![\\p{L}\\p{N}_])';

function isSpace(ch) {
  return SPACE_CHAR.test(ch);
}

function lstrip(s) {
  let i = 0;
  while (i < s.length && isSpace(s[i])) i++;
  return s.slice(i);
}

function rstrip(s) {
  let j = s.length;
  while (j > 0 && isSpace(s[j - 1])) j--;
  return s.slice(0, j);
}

function strip(s) {
  return lstrip(rstrip(s));
}

/** str.split(): the words between runs of whitespace, none of them empty. */
function words(s) {
  return s.split(SPACE_RUN).filter((w) => w !== '');
}

/** The code point that ends just before index k, as a string. */
function charBefore(s, k) {
  const low = s.charCodeAt(k - 1);
  if (low >= 0xdc00 && low <= 0xdfff && k >= 2) {
    const high = s.charCodeAt(k - 2);
    if (high >= 0xd800 && high <= 0xdbff) return s.slice(k - 2, k);
  }
  return s[k - 1];
}

/** str.isalnum() or '_' for one character: whether it belongs to a word. */
function isWordChar(ch) {
  return WORD_CHAR.test(ch);
}

/** len(s.expandtabs(8)): the length of leading whitespace with each tab taken to the next multiple of 8. */
function expandedLength(ws) {
  let col = 0;
  let length = 0;
  for (const ch of ws) {
    if (ch === '\t') {
      const step = 8 - (col % 8);
      col += step;
      length += step;
    } else {
      length += 1;
      col = ch === '\n' || ch === '\r' ? 0 : col + 1;
    }
  }
  return length;
}

/** os.path.commonprefix: the characters all the strings start with. */
function commonPrefix(strings) {
  if (!strings.length) return '';
  let prefix = strings[0];
  for (const s of strings) {
    while (!s.startsWith(prefix)) prefix = prefix.slice(0, -1);
  }
  return prefix;
}

/** Python's order of strings, by code point (a < b: -1). */
function compare(a, b) {
  if (a === b) return 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const x = a.charCodeAt(i);
    const y = b.charCodeAt(i);
    if (x === y) continue;
    const astralX = x >= 0xd800 && x <= 0xdfff;
    const astralY = y >= 0xd800 && y <= 0xdfff;
    if (astralX !== astralY) return astralX ? 1 : -1;   // a code point from U+10000 up is above every one of the first plane
    return x < y ? -1 : 1;
  }
  return a.length < b.length ? -1 : 1;
}

function sorted(strings) {
  return strings.slice().sort(compare);
}

/** re.escape for a regular expression that is built with the `u` flag. */
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
}

/** re.search(pattern, s, pos): the first match at or after i, or null. The pattern has the `g` flag. */
function searchFrom(re, s, i) {
  re.lastIndex = i;
  return re.exec(s);
}

/** pattern.match(s, pos): the match that starts at i, or null. The pattern has the `y` flag. */
function matchAt(re, s, i) {
  re.lastIndex = i;
  return re.exec(s);
}

/** obj[key] when the object has it itself (a key such as `__proto__` or `constructor` is a name like any other here). */
function own(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj, key) ? obj[key] : undefined;
}

/** obj[key] = value, also for a key such as `__proto__`. */
function put(obj, key, value) {
  Object.defineProperty(obj, key, { value, enumerable: true, writable: true, configurable: true });
}

module.exports = {
  SPACE, WORD_END, isSpace, strip, lstrip, rstrip, words, charBefore, isWordChar, expandedLength, commonPrefix, compare, sorted,
  escapeRegExp, searchFrom, matchAt, own, put,
};
