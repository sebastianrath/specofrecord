'use strict';
// What changed since the last lock (`tools/py/sorlib/lock.py`, the reading half): the entries the files would produce now, the lock as it is, and
// the findings that compare them. Nothing here writes a file, accepts a change or runs a test.
const fs = require('fs');
const path = require('path');
const lock = require('./lock');
const { Item, Row, LEGACY_FILE_NAME, testKeyword } = require('./model');
const T = require('./pytext');

const SETTLED = ['pass', 'manual', 'checked', 'deferred'];
const isObject = (e) => e !== null && typeof e === 'object' && !Array.isArray(e);
const hasKeys = (e) => isObject(e) && Object.keys(e).length > 0;
const has = (o, k) => isObject(o) && Object.prototype.hasOwnProperty.call(o, k);
const get = (o, k) => (has(o, k) ? o[k] : undefined);
const keys = (o) => (isObject(o) ? Object.keys(o) : []);

/** Whether two plain objects (a clause's references) hold the same keys and values. */
function same(a, b) {
  const ka = keys(a);
  const kb = keys(b);
  return ka.length === kb.length && ka.every((k) => has(b, k) && a[k] === b[k]);
}

class LockFormatError extends Error {}

function existingPath(project) {
  for (const p of [project.lockPath, project.legacyLockPath]) {
    try {
      if (fs.statSync(p).isFile()) return p;
    } catch (e) {
      // not there
    }
  }
  return null;
}

/** The lock as the tool works with it: [] of entries by key, with the lines of each language folded into their clause. */
function read(project) {
  const file = existingPath(project);
  if (!file) return {};
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (isObject(data) && has(data, lock.FORMAT_KEY)) {
    const number = data[lock.FORMAT_KEY];
    delete data[lock.FORMAT_KEY];
    const rel = path.relative(project.root, file).split(path.sep).join('/');
    if (typeof number !== 'number' || !Number.isInteger(number) || number < 1) {
      throw new LockFormatError(`${rel} has ${lock.FORMAT_KEY} ${JSON.stringify(number)}, which is not a lock format number (a whole number from 1 up). The file may be damaged. Nothing was changed.`);
    }
    if (number > lock.FORMAT) {
      throw new LockFormatError(`${rel} is in lock format ${number}, and this sor reads format ${lock.FORMAT} at most. Update sor, every copy of it (the project's tools, the plugin and the editor extension), and try again. Nothing was changed.`);
    }
  }
  // A lock written before the root was called ROOT keeps it under CLAUSES.
  if (has(data, LEGACY_FILE_NAME) && !has(data, project.rootKey)) {
    T.put(data, project.rootKey, data[LEGACY_FILE_NAME]);
    delete data[LEGACY_FILE_NAME];
  }
  return lock.fold(data);
}

function isManual(test) {
  return test.lines.some(([, t]) => (testKeyword(t) || [''])[0] === 'manual');
}

/** The lock entries the files would produce right now. */
function snapshot(project, scan) {
  const entries = {};
  const text = {};
  const put = (key, kind, t) => {
    T.put(entries, key, { kind, text: t });
    T.put(text, key, t);
  };
  for (const p of project.parts.values()) {
    put(p.key, 'part', lock.h(p.face()));
    for (const it of p.items.values()) {
      put(it.id, it.isTest ? 'test' : 'item', lock.h(it.text()));
      for (const r of it.rows.values()) put(r.id, 'row', lock.h(r.text));
    }
  }
  const values = new Map();
  const ownerRefs = new Map();
  const refKey = (id, ref) => `${id}\u0000${ref}`;
  for (const it of project.allItems()) {
    for (const [, ref] of it.refs) {
      const hits = project.resolve(it.part.id, ref);
      if (hits.length === 1) {
        ownerRefs.set(refKey(it.id, ref), hits[0]);
        for (const r of it.rows.values()) ownerRefs.set(refKey(r.id, ref), hits[0]);
      }
    }
    for (const [name, val] of it.values) values.set(`${it.id}.${name}`, [it, name, val]);
    for (const r of it.rows.values()) for (const [name, val] of r.values) values.set(`${r.id}.${name}`, [r, name, val]);
  }
  const valueText = (key, guard) => {
    if (values.has(key)) {
      const [owner, , val] = values.get(key);
      return valueHash(owner, val, guard);
    }
    return has(text, key) ? text[key] : '';
  };
  const valueHash = (owner, val, guard) => {
    if (val.startsWith('=')) {   // an alias: it changes when the value it stands for changes
      const target = ownerRefs.get(refKey(owner.id, T.strip(val.slice(1))));
      if (target && !guard.has(target)) return lock.h(`${val}\u0000${valueText(target, new Set([...guard, target]))}`);
    }
    return lock.h(val);
  };
  for (const key of values.keys()) put(key, 'value', valueText(key, new Set([key])));
  for (const it of project.allItems()) {
    const targets = project.resolvedRefs(it);
    if (targets.size) {
      const refs = {};
      for (const t of T.sorted([...targets])) T.put(refs, t, has(text, t) ? text[t] : '');
      entries[it.id].refs = refs;
    }
  }
  const perTarget = project.targeted() ? scan.targetCodeHashes() : new Map();
  for (const [key, c] of scan.codeHashes()) {
    if (!has(entries, key)) T.put(entries, key, { kind: 'glue' });
    const entry = entries[key];
    if (perTarget.has(key) && ['item', 'row', 'part', 'test'].includes(entry.kind)) {
      entry.targets = {};
      for (const [t, code] of perTarget.get(key)) T.put(entry.targets, t, { code });
      entry.code = lock.digest(entry.targets);
    } else {
      entry.code = c;
    }
  }
  return entries;
}

/** `now` with each clause's code in the shape the lock keeps it (one joined hash, or one hash per target), so a clause is compared with itself. */
function conform(now, locked, scan) {
  let perTarget = null;
  for (const key of Object.keys(now)) {
    const a = now[key];
    const b = get(locked, key);
    if (!b || !['item', 'row', 'part', 'test'].includes(a.kind)) continue;
    if (hasKeys(b.targets) && !hasKeys(a.targets)) {
      perTarget = perTarget === null ? scan.targetCodeHashes() : perTarget;
      if (perTarget.has(key)) {
        a.targets = {};
        for (const [t, code] of perTarget.get(key)) T.put(a.targets, t, { code });
        a.code = lock.digest(a.targets);
      }
    } else if (hasKeys(a.targets) && !hasKeys(b.targets)) {
      delete a.targets;
      a.code = scan.codeHashes().get(key);   // the same regions as the per-target hashes, so the key is there
    }
  }
  return now;
}

/** The targets whose code is not the same in these two entries of a clause (both per target), sorted. */
function movedTargets(a, b) {
  const ta = isObject(a.targets) ? a.targets : {};
  const tb = isObject(b.targets) ? b.targets : {};
  const all = new Set([...Object.keys(ta), ...Object.keys(tb)]);
  return T.sorted([...all].filter((t) => get(get(ta, t), 'code') !== get(get(tb, t), 'code')));
}

/** What a language's `built` is compared with for one clause: its text hash, and for an item with a table also the text hash of its rows without code of their own. */
function basisOf(project, entries, key) {
  const item = project.items.get(key);
  const rows = item instanceof Item
    ? T.sorted([...item.rows.values()].filter((r) => has(entries, r.id) && !hasKeys(entries[r.id].targets)).map((r) => r.id)) : [];
  const text = has(entries, key) ? entries[key].text : undefined;
  return rows.length ? lock.h([text || ''].concat(rows.map((r) => entries[r].text || '')).join('\n')) : text;
}

function bases(project, entries) {
  const out = new Map();
  for (const key of Object.keys(entries)) if (hasKeys(entries[key].targets)) out.set(key, basisOf(project, entries, key));
  return out;
}

function ownerParts(project) {
  const owners = new Map();
  for (const p of project.parts.values()) {
    owners.set(p.key, p);
    for (const it of p.items.values()) {
      owners.set(it.id, p);
      for (const r of it.rows.values()) owners.set(r.id, p);
    }
  }
  return owners;
}

/** The targets of a locked clause that apply to it and whose code was accepted for an older text of the clause than the locked one. */
function laggingTargets(project, key, entry, owners, basis) {
  const applicable = project.targetsOfPart(owners.get(key));
  const want = basis.has(key) ? basis.get(key) : entry.text;
  return T.sorted(keys(entry.targets).filter((t) => applicable.includes(t) && get(entry.targets[t], 'built') !== want));
}

/** The targets that apply to a locked clause and have no line in the lock: it was locked without code in them. */
function unbuiltTargets(project, key, entry, owners) {
  const applicable = project.targetsOfPart(owners.get(key));
  return T.sorted(applicable.filter((t) => !has(isObject(entry.targets) ? entry.targets : {}, t)));
}

/** {lock key: the hash it would have now} for entries whose code hash was made with the rule every file followed before the file type. */
function oldRuleKeys(locked, scan) {
  const out = new Map();
  if (!Object.keys(locked).length || !scan.hasOwnRules()) return out;
  const now = scan.codeHashes();
  const differ = Object.keys(locked).filter((k) => {
    const e = locked[k];
    return e.code && !hasKeys(e.targets) && now.has(k) && now.get(k) !== e.code;
  });
  if (!differ.length) return out;
  const legacy = scan.codeHashes(true);
  for (const k of differ) if (legacy.get(k) === locked[k].code) out.set(k, now.get(k));
  return out;
}

function upgrade(locked, scan) {
  const stale = oldRuleKeys(locked, scan);
  if (!stale.size) return locked;
  const out = Object.assign({}, locked);
  for (const [k, hash] of stale) out[k] = Object.assign({}, locked[k], { code: hash });
  return out;
}

class Finding {
  constructor(status, key, detail = '', where = '') {
    this.status = status;
    this.key = key;
    this.detail = detail;
    this.where = where;
  }

  /** The finding as the JSON has it: its fields that are not empty, in the order they are set. */
  asDict() {
    const out = {};
    for (const k of ['status', 'key', 'detail', 'where', 'by']) if (this[k]) out[k] = this[k];
    return out;
  }
}

const ownTest = (key) => {
  const i = key.lastIndexOf('/');
  return i < 0 ? `test:${key}` : `${key.slice(0, i)}/test:${key.slice(i + 1)}`;
};

/** [findings, not_passed]: the files compared with the lock. */
function status(project, scan, locked) {
  locked = upgrade(locked, scan);
  const now = conform(snapshot(project, scan), locked, scan);
  const lockBasis = bases(project, locked);
  const hand = new Set([...project.parts.values()].filter((p) => p.sourceCode).map((p) => p.key));
  const ownerPart = ownerParts(project);

  const where = (key) => scan.regionsFor(key).map((r) => r.where).join(', ');
  const whereIn = (key, targets) => {
    if (!targets.length) return where(key);
    return scan.regionsFor(key).filter((r) => targets.includes(project.targetOf(r.file) || '*')).map((r) => r.where).join(', ');
  };
  const codeNote = (key, a, b) => {
    if (!has(b, 'code') && !has(a, 'code')) return '';
    if (hasKeys(a.targets) && hasKeys(b.targets)) {
      const moved = movedTargets(a, b);
      const unmoved = T.sorted(Object.keys(a.targets).filter((t) => !moved.includes(t)));
      if (moved.length && unmoved.length) return `code updated in ${moved.join(', ')} · not yet in ${unmoved.join(', ')}`;
      return moved.length ? 'code updated' : `code not updated yet in ${unmoved.join(', ')}`;
    }
    return get(a, 'code') !== get(b, 'code') ? 'code updated' : 'code not updated yet';
  };
  const allKeys = T.sorted([...new Set([...Object.keys(now), ...Object.keys(locked)])]);
  const changedValues = (key) => {
    const out = [];
    for (const k of allKeys) {
      if (k.startsWith(`${key}.`) && !k.slice(key.length + 1).includes('/')) {
        if (get(get(now, k), 'text') !== get(get(locked, k), 'text')) out.push(k.slice(key.length + 1));
      }
    }
    return out;
  };

  const findings = [];
  for (const key of allKeys) {
    const a = get(now, key);
    const b = get(locked, key);
    const kind = (a || b).kind;
    if (kind === 'value') continue;   // reported with the item or row that holds it
    if (b === undefined) {
      findings.push(new Finding('new', key, '', where(key)));
      continue;
    }
    if (a === undefined) {
      findings.push(new Finding('removed', key, b.code ? 'delete its code' : ''));
      continue;
    }
    if (a.text !== b.text) {
      const vals = changedValues(key);
      const detail = [vals.length ? `values: ${vals.join(', ')}` : '', codeNote(key, a, b)].filter((x) => x).join(' · ');
      findings.push(new Finding('changed', key, detail, where(key)));
    } else if (!same(a.refs, b.refs)) {
      const ra = isObject(a.refs) ? a.refs : {};
      const rb = isObject(b.refs) ? b.refs : {};
      const moved = T.sorted([...new Set([...Object.keys(ra), ...Object.keys(rb)])]).filter((t) => get(ra, t) !== get(rb, t));
      const note = codeNote(key, a, b);
      findings.push(new Finding('stale', key, `refers to ${moved.join(', ')} (changed)${note ? ` · ${note}` : ''}`, where(key)));
    } else if (get(a, 'code') !== get(b, 'code')) {
      const moved = hasKeys(a.targets) && hasKeys(b.targets) ? movedTargets(a, b) : [];
      const late = moved.length ? laggingTargets(project, key, b, ownerPart, lockBasis) : [];
      const first = unbuiltTargets(project, key, b, ownerPart).filter((t) => moved.includes(t));   // a language the clause was locked without
      if (!has(b, 'code')) {
        findings.push(new Finding('built', key, 'first code for a locked clause', where(key)));
      } else if (moved.length && moved.every((t) => late.includes(t) || first.includes(t))) {   // the code of the targets that are behind is being rebuilt: not drift
        findings.push(new Finding('behind', key, moved.join(', ') + (late.length ? ' (being rebuilt)' : ' (first code)'), whereIn(key, moved)));
      } else if (kind === 'glue') {
        findings.push(new Finding('glue', key, '', where(key)));
      } else if (ownerPart.get(key) && hand.has(ownerPart.get(key).key)) {
        const anchored = scan.regionsFor(key).filter((r) => r.kind === 'anchor').map((r) => r.target);
        findings.push(new Finding('code-changed', key, anchored.length ? `its code changed (${anchored.join(', ')}): check the clause still holds` : 'hand-written code', where(key)));
      } else if (project.testsOf(key, true).some((t) => ['fail', 'none'].includes(get(get(locked, t), 'result')))) {
        // its own test, or a bug test that proves it, did not pass at the last lock: the code is being fixed against it
        findings.push(new Finding('fixing', key, 'its test did not pass at the last lock', where(key)));
      } else {
        findings.push(new Finding('drift', key, moved.join(', '), whereIn(key, moved) || where(key) || 'code removed'));
      }
    }
  }
  // a locked clause whose text has not changed, but whose code in a target was accepted for an older text
  const seen = new Set(findings.map((f) => f.key));
  for (const key of T.sorted(Object.keys(locked))) {
    const b = locked[key];
    const a = get(now, key);
    if (a === undefined || seen.has(key) || !hasKeys(b.targets) || a.text !== b.text) continue;
    const late = laggingTargets(project, key, b, ownerPart, lockBasis).filter((t) => has(a.targets, t));
    if (late.length) findings.push(new Finding('behind', key, late.join(', '), whereIn(key, late)));
  }
  // A table's code is usually marked with the item, not each row: a changed, added or removed row is a change to that code.
  const rowsChanged = new Map();
  for (const f of findings) {
    const entry = get(now, f.key) || get(locked, f.key) || {};
    if (['new', 'changed', 'removed', 'built'].includes(f.status) && entry.kind === 'row') {
      const i = f.key.lastIndexOf('/');
      const item = f.key.slice(0, i);
      if (!rowsChanged.has(item)) rowsChanged.set(item, []);
      rowsChanged.get(item).push(f.key.slice(i + 1));
      if (!f.where && where(item)) {
        const a = get(now, item) || {};
        const b = get(locked, item) || {};
        const note = get(a, 'code') !== get(b, 'code') ? 'code updated' : 'code not updated yet';
        f.detail = [f.detail, `${note} (in ${item})`].filter((x) => x).join(' · ');
        f.where = where(item);
      }
    }
  }
  for (const f of findings) {
    if (f.status === 'drift' && rowsChanged.has(f.key)) {
      f.status = 'changed';
      f.detail = `rows changed: ${rowsChanged.get(f.key).join(', ')} · code updated`;
    }
  }
  // A test that changed first allows its item's code to change: the bug-fix path.
  const testsChanged = new Set(findings.filter((f) => ['new', 'changed'].includes(f.status)).map((f) => f.key));
  for (const f of findings) {
    if (f.status === 'drift' && project.testsOf(f.key).some((t) => testsChanged.has(t))) {
      f.status = 'fixing';
      f.detail = 'its test changed first';
    }
  }
  // A region marked with several ids may change for any of them. The other ids are not drift, but they are not free either.
  const explained = new Set(findings.filter((f) => ['new', 'changed', 'stale', 'built', 'fixing', 'behind'].includes(f.status)).map((f) => f.key));
  for (const f of findings) {
    if (f.status !== 'drift') continue;
    const shared = T.sorted([...new Set(scan.regionsFor(f.key).flatMap((r) => r.keys))].filter((k) => explained.has(k)));
    if (shared.length) {
      const test = ownTest(f.key);
      const need = has(now, test) ? `its test ${test} must pass again` : 'review it: it has no test';
      f.status = 'shared';
      f.detail = `code changed with ${shared.join(', ')}; ${need}`;
    }
  }
  const notPassed = T.sorted(Object.keys(now).filter((k) => now[k].kind === 'test' && has(locked, k) && !SETTLED.includes(locked[k].result)));
  return [findings, notPassed];
}

/** Keys of the tests a lock would refuse for want of a passing result. */
function pendingTests(project, findings, notPassed) {
  const wanted = new Set(notPassed);
  const parts = new Map([...project.parts.values()].map((p) => [p.key, p]));
  for (const f of findings) {
    if (!['new', 'changed', 'stale', 'built', 'shared', 'fixing'].includes(f.status)) continue;
    let o = project.items.get(f.key);
    if (o instanceof Row) o = project.items.get(f.key.slice(0, f.key.lastIndexOf('/')));
    if (o instanceof Item) {
      if (o.isTest) wanted.add(o.id);
      else for (const t of project.testsOf(o.id)) wanted.add(t);
    } else if (parts.has(f.key)) {
      for (const i of parts.get(f.key).items.values()) if (i.isTest) wanted.add(i.id);
    }
  }
  return T.sorted([...wanted].filter((k) => {
    const it = project.items.get(k);
    return it instanceof Item && it.isTest && !isManual(it) && !it.runsOn().length;
  }));
}

/** Keys of the tests left to CI: the ones that say `runs on:`. */
function deferredTests(project) {
  return T.sorted([...project.allItems()].filter((i) => i.isTest && i.runsOn().length && !isManual(i)).map((i) => i.id));
}

/** The claims in force: [{agent, asked, since, until}]. */
function activeClaims(project, now = Date.now() / 1000) {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(path.join(project.specDir, '.sor-claims.json'), 'utf8')).claims || [];
  } catch (e) {
    return [];
  }
  return data.filter((c) => c.until > now).map((c) => ({ agent: c.agent, asked: c.asked, since: c.since, until: c.until }));
}

module.exports = { read, status, pendingTests, deferredTests, activeClaims, Finding, LockFormatError };
