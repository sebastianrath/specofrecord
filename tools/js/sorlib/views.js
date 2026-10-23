'use strict';
// The machine-readable views of a project (`tools/py/sorlib/index.py`, `views.part_info`, `blame.py`): what an editor reads to show clauses, code and
// what changed. Positions are counted in code points, as in the Python tool's JSON, not in UTF-16 units.
const { spawnSync } = require('child_process');
const path = require('path');
const model = require('./model');
const T = require('./pytext');

const VERSION = 2;   // of the index JSON; the editor extension reads it

/** The number of code points in a text (a position in the Python tool's JSON). */
const points = (s) => Array.from(s).length;
const column = (s, i) => points(s.slice(0, i));

function regionDict(project, r) {
  const d = { file: r.file, path: path.resolve(project.root, r.file), start: r.start, end: r.end, kind: r.kind, keys: r.keys, ids: r.ids };
  d.targetName = project.targetOf(r.file);   // the target the file belongs to, or null (`target` below is something else)
  if (r.kind === 'anchor') d.target = r.target;   // the `code: path#name` text the region came from
  return d;
}

/** The same expression, answering with the position of each group too. */
const withIndices = (rx) => new RegExp(rx.source, `${rx.flags}d`);
// Built once. matchAll works on a copy of a global expression, so sharing these between lines and calls is safe (exec and test would not be).
const VALUE_DEFINITION = withIndices(model.VDEF());
const REFERENCE = model.REF();

/** The text with each `code span` blanked out, keeping every other character where it was. */
const mask = (text) => text.replace(model.CODE, (m) => ' '.repeat(points(m)));

const whereOf = (part, line, col = 0, end = null) => ({ file: part.rel, path: part.path, line, col, end });

function locate(project, target, valuePos) {
  if (valuePos.has(target)) return valuePos.get(target);
  let found = project.find(target);
  if (found === null && target.includes('.')) found = project.find(target.slice(0, target.lastIndexOf('.')));
  if (found === null) return null;
  const [kind, o] = found;
  if (kind === 'part') return whereOf(o, 1);
  if (kind === 'row') {
    const item = project.items.get(o.id.slice(0, o.id.lastIndexOf('/')));
    for (const [n, t] of item.lines) if (T.strip(t) === o.text) return whereOf(item.part, n);
    return whereOf(item.part, item.lineno);
  }
  return whereOf(o.part, o.lineno);
}

/** Items, rows, values, references and code regions of the whole project. */
function fullIndex(project, scan) {
  const regions = scan.regions.map((r) => regionDict(project, r));
  const byKey = new Map();   // key -> the numbers of the regions it serves
  scan.regions.forEach((r, i) => new Set(r.keys).forEach((k) => { if (!byKey.has(k)) byKey.set(k, []); byKey.get(k).push(i); }));
  const inRegions = (key) => byKey.get(key) || [];
  const items = [];
  const valuePos = new Map();
  const refs = [];
  for (const part of project.parts.values()) {
    items.push(Object.assign({ id: part.key, kind: 'part', name: part.title }, whereOf(part, 1), { regions: inRegions(part.key) }));
    for (const it of part.items.values()) {
      for (const [n, text] of it.lines) {
        const masked = mask(text);
        for (const m of masked.matchAll(VALUE_DEFINITION)) {
          const start2 = m.indices[2][0];
          valuePos.set(`${it.id}.${m[1]}`, whereOf(part, n, column(masked, m.index), column(masked, m.index + m[0].length)));
          const val = m[2];
          if (T.strip(val).startsWith('=')) {
            const ref = T.strip(T.strip(val).slice(1));
            const at = Math.max(masked.indexOf(ref, start2), start2);
            refs.push([it, n, column(masked, at), column(masked, at + ref.length), ref]);
          }
        }
        for (const m of masked.matchAll(REFERENCE)) {
          const start = m.index + 1;   // the group starts right after the opening brace
          refs.push([it, n, column(masked, start), column(masked, start + m[1].length), T.strip(m[1])]);
        }
      }
      items.push(Object.assign({ id: it.id, kind: it.kind, section: it.section, name: it.name }, whereOf(part, it.lineno, 0, null),
        { endLine: it.lines.length ? it.lines[it.lines.length - 1][0] : it.lineno, regions: inRegions(it.id) }));
      for (const row of it.rows.values()) {
        const hit = it.lines.find(([, t]) => T.strip(t) === row.text);
        const line = hit ? hit[0] : it.lineno;
        items.push(Object.assign({ id: row.id, kind: 'row', name: row.name }, whereOf(part, line), { endLine: line, regions: inRegions(row.id) }));
      }
    }
  }
  const outRefs = refs.map(([it, n, col, end, text]) => {
    const hits = project.resolve(it.part.id, text);
    const target = hits.length === 1 ? hits[0] : null;
    return Object.assign(whereOf(it.part, n, col, end), { text, from: it.id, target, to: target && locate(project, target, valuePos) });
  });
  return { version: VERSION, root: project.root, specDir: project.specDir, regions, items, refs: outRefs };
}

function atLine(project, scan, file, line, describe) {
  const out = scan.at(file, line).map((r) => Object.assign(regionDict(project, r), {
    clauses: r.keys.map((k) => ({ id: k, text: describe(project, k), where: locate(project, k, new Map()) })),
  }));
  return { version: VERSION, file, line, regions: out };
}

function forId(project, scan, key, rows, found) {
  return { version: VERSION, id: key, exists: found !== null, regions: rows.map((r) => regionDict(project, r)) };
}

/** An id in words: a part with its why, a row with its text, an item with its lines. */
function describe(project, key) {
  const found = project.find(key);
  if (found === null) return key;
  const [kind, o] = found;
  if (kind === 'part') return `${o.key}  (${o.rel}) — ${o.header.get('Why') || ''}`;
  if (kind === 'row') return `${o.id}  ${o.text}`;
  return o.lines.map(([, t]) => t).join('\n    ');
}

/** {id, title, why, owner, source, rel, bullets, gives, open} of a part, as `sor parts --json` has it. */
function partInfo(part) {
  const source = part.header.get('Source') || (part.sourceCode ? `code at ${part.sourceCode}` : null);
  const bullets = {};
  for (const s of model.SECTIONS) T.put(bullets, s.toLowerCase(), 0);
  for (const item of part.items.values()) for (const [s, n] of item.bullets) bullets[s.toLowerCase()] += n;
  return {
    id: part.key, title: part.title, why: part.header.get('Why') || '', owner: part.header.has('Owner') ? part.header.get('Owner') : null,
    source, rel: part.rel, bullets,
    gives: [...part.items.values()].filter((i) => i.kind === 'gives').map((i) => i.name),
    open: [...part.items.values()].reduce((n, i) => n + i.opens.length, 0),
  };
}

/** Part ids: the root first, then by id. */
function inOrder(project) {
  return (project.parts.has('') ? [''] : []).concat(T.sorted([...project.parts.keys()].filter((p) => p !== '')));
}

// --- blame: who last changed drifted code, and when, if git can tell ------------------------------------------------------

const UNCOMMITTED = '0'.repeat(40);

function blameLines(root, file, a, b) {
  const out = spawnSync('git', ['blame', '--porcelain', '-L', `${a},${b}`, '--', file], { cwd: root, timeout: 20000, maxBuffer: 64 * 1024 * 1024 });
  if (out.error || out.status !== 0) return [];
  const commits = new Map();
  let cur = null;
  for (const line of out.stdout.toString('utf8').split('\n')) {
    const head = /^([0-9a-f]{40}) \d+ \d+/.exec(line);
    if (head) {
      if (!commits.has(head[1])) commits.set(head[1], {});
      cur = commits.get(head[1]);
    } else if (cur !== null && line.includes(' ')) {
      const i = line.indexOf(' ');
      const k = line.slice(0, i);
      if (['author', 'author-time', 'summary'].includes(k)) cur[k] = line.slice(i + 1);
    }
  }
  return [...commits].map(([sha, info]) => Object.assign({ sha }, info));
}

/** 'changed by NAME in 1a2b3c4 (2026-10-17)', 'not committed yet', or '' for a `where` like 'out/index.html:12-30, out/index.html:40-41'. */
function blame(root, where) {
  const found = [];
  for (const part of where.split(',').map((w) => T.strip(w)).filter((w) => w)) {
    const m = /^(.*):(\d+)(?:-(\d+))?$/u.exec(part);
    if (m) found.push(...blameLines(root, m[1], m[2], m[3] || m[2]));
  }
  if (!found.length) return '';
  if (found.some((c) => c.sha === UNCOMMITTED)) return 'not committed yet';
  let last = found[0];
  for (const c of found) if (parseInt(c['author-time'] || 0, 10) > parseInt(last['author-time'] || 0, 10)) last = c;
  const d = new Date(parseInt(last['author-time'] || 0, 10) * 1000);
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return `changed by ${last.author || '?'} in ${last.sha.slice(0, 7)} (${day})`;
}

/** Adds `by` to the drift findings: the last change to their lines. At most `most` of them are asked. */
function annotate(project, findings, statuses = ['drift', 'code-changed'], most = 20) {
  let done = 0;
  for (const f of findings) {
    if (statuses.includes(f.status) && f.where && done < most) {
      const by = blame(project.root, f.where);
      if (by) f.by = by;
      done += 1;
    }
  }
}

module.exports = { VERSION, regionDict, fullIndex, atLine, forId, describe, partInfo, inOrder, blame, annotate, column, points };
