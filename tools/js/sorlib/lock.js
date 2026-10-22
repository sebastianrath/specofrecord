'use strict';
// The lock file as the Python tool writes it (SPEC §11): hashes of text, the digest of a clause's code per target, the lines
// `clause@target` folded into and out of their clause, and the text of the file. Nothing here reads or writes a file.
const crypto = require('crypto');
const { compare, sorted, own, put } = require('./pytext');

const FORMAT = 3;               // the newest lock format this tool reads and writes
const LINE_FIELDS = ['code', 'built'];   // what a format 2 line holds; a line with more is format 3
const LINE_KIND = 'code';       // the kind of a per-target line in the file
const FORMAT_KEY = '*format';   // the marker of a format above 1

class LockWriteError extends Error {}

/** Python's ValueError: a caller asked for something the lock cannot be. */
class ValueError extends Error {}

/** SHA-256 of the UTF-8 text, the first 12 hex digits. */
function h(s) {
  return crypto.createHash('sha256').update(s, 'utf8').digest('hex').slice(0, 12);
}

const isObject = (e) => e !== null && typeof e === 'object' && !Array.isArray(e);
const hasKeys = (e) => isObject(e) && Object.keys(e).length > 0;

/**
 * The result of a test that keeps one per language (a line with `result`): `fail` if one failed, `pass` if all passed, else `none`. It is worked
 * out when the lock is read and not written, so every reader of a test's `result` goes on reading one.
 */
function derivedResult(targets) {
  const results = Object.keys(targets).filter((t) => Object.prototype.hasOwnProperty.call(targets[t], 'result')).map((t) => targets[t].result);
  if (results.includes('fail')) return 'fail';
  return results.length && results.every((r) => r === 'pass') ? 'pass' : 'none';
}

const hasResults = (targets) => Object.keys(targets).some((t) => Object.prototype.hasOwnProperty.call(targets[t], 'result'));

/** The `code` of a clause that has its code per target: a hash of the targets' hashes, in the order of their names. */
function digest(targets) {
  return h(sorted(Object.keys(targets)).map((t) => `${t}:${targets[t].code}`).join('\n'));
}

/**
 * The lock as the tool works with it: each per-target line `K@t` of the file (kind `code`) goes into the entry of its clause as
 * `targets[t]` = {code, built}, and the clause's `code` becomes the digest of its targets'. A line whose clause is not in the file
 * has nothing to belong to and is dropped. `data` is changed and returned.
 */
function fold(data) {
  const out = {};
  const lines = [];
  for (const k of Object.keys(data)) {
    const e = data[k];
    if (isObject(e) && e.kind === LINE_KIND) lines.push(e);
    else put(out, k, e);
  }
  for (const e of lines) {
    const parent = typeof e.of === 'string' ? own(out, e.of) : undefined;
    if (isObject(parent) && typeof e.target === 'string') {
      if (!isObject(parent.targets)) parent.targets = {};
      const line = {};
      for (const x of Object.keys(e)) if (x !== 'kind' && x !== 'of' && x !== 'target') put(line, x, e[x]);
      put(parent.targets, e.target, line);
    }
  }
  for (const k of Object.keys(out)) {
    if (isObject(out[k]) && hasKeys(out[k].targets)) {
      out[k].code = digest(out[k].targets);
      if (out[k].kind === 'test' && hasResults(out[k].targets)) out[k].result = derivedResult(out[k].targets);
    }
  }
  return out;
}

/**
 * The entries as the file holds them: a clause that has code per target loses its `code` and `targets`, and each target gets a line
 * `K@t` of its own. Refuses an id that is already a key.
 */
function unfold(entries) {
  const out = {};
  for (const k of Object.keys(entries)) {
    const e = entries[k];
    if (!hasKeys(isObject(e) ? e.targets : undefined)) {
      put(out, k, e);
      continue;
    }
    const rest = {};
    const derived = hasResults(e.targets);   // the result of a test with a result on each line is worked out when the lock is read
    for (const x of Object.keys(e)) if (x !== 'targets' && x !== 'code' && !(derived && x === 'result')) put(rest, x, e[x]);
    put(out, k, rest);
    for (const t of Object.keys(e.targets)) {
      if (Object.prototype.hasOwnProperty.call(entries, `${k}@${t}`)) {
        throw new LockWriteError(`${k}@${t} is a clause of its own and also the lock line for the code of ${k} in ${t}: rename one of them`);
      }
      put(out, `${k}@${t}`, Object.assign({ kind: LINE_KIND, of: k, target: t }, e.targets[t]));
    }
  }
  return out;
}

/** json.dumps(value, sort_keys=True, separators=(', ', ': '), ensure_ascii=False) */
function dumps(value) {
  if (value === null) return 'null';
  if (Array.isArray(value)) return `[${value.map(dumps).join(', ')}]`;
  if (typeof value === 'object') {
    return `{${sorted(Object.keys(value)).map((k) => `${JSON.stringify(k)}: ${dumps(value[k])}`).join(', ')}}`;
  }
  return JSON.stringify(value);
}

/**
 * The text of a lock file: a format above 1 opens with its marker, then one entry per line, sorted by code point. The format follows
 * the entries: 3 when a line of a language holds more than `code` and `built`, 2 when a clause has code per target, else 1. A caller
 * cannot name a lower one than the entries need. `newest` is the newest format this tool writes; the tests move it to try a later one.
 */
function render(entries, fmt, newest = FORMAT) {
  let needed = 1;
  for (const k of Object.keys(entries)) {
    const e = entries[k];
    if (isObject(e) && hasKeys(e.targets)) {
      const more = Object.keys(e.targets).some((t) => Object.keys(e.targets[t]).some((x) => !LINE_FIELDS.includes(x)));
      needed = Math.max(needed, more ? 3 : 2);
    }
  }
  const format = fmt === null || fmt === undefined ? needed : fmt;
  if (format > newest) throw new ValueError(`lock format ${format} is newer than this tool (${newest})`);
  if (format < needed) throw new ValueError(`these entries need lock format ${needed}, not ${format}`);
  const unfolded = unfold(entries);
  const lines = Object.keys(unfolded).sort(compare).map((k) => `${JSON.stringify(k)}: ${dumps(unfolded[k])}`);
  if (format > 1) lines.unshift(`${JSON.stringify(FORMAT_KEY)}: ${format}`);
  return `{\n${lines.join(',\n')}\n}\n`;
}

module.exports = { FORMAT, LINE_KIND, FORMAT_KEY, LockWriteError, ValueError, h, digest, fold, unfold, render, dumps };
