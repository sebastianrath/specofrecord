'use strict';
// Every region under the project's code roots, checked against the project's ids (`Scan` of `tools/py/sorlib/markers.py`): which files are
// code, the regions of each, the keys of a region (items, rows, parts, tests and glue) and the hashes of the code of each key, in all and
// per target. What is wrong with the markers (the problems of the scan) is not here.
const fs = require('fs');
const path = require('path');
const anchors = require('./anchors');
const markers = require('./markers');
const { hasSpec, splitLines } = require('./model');
const T = require('./pytext');

const SKIP_DIRS = new Set(['node_modules', '__pycache__', 'venv']);   // and every folder whose name starts with a dot
const MAX_BYTES = 2000000;
const DECODER = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });

/** The files under a code root, in the order the Python tool walks them: folders and files by name, hidden and skipped folders left out. */
function* filesUnder(project, root) {
  const start = path.join(project.root, root);
  let st = null;
  try {
    st = fs.statSync(start);
  } catch (e) {
    return;
  }
  if (st.isFile()) {
    yield start;
    return;
  }
  function* walk(dir) {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (e) {
      return;
    }
    const dirs = [];
    const files = [];
    for (const e of entries) {
      let isDir = e.isDirectory();
      if (e.isSymbolicLink()) {
        try {
          isDir = fs.statSync(path.join(dir, e.name)).isDirectory();
        } catch (err) {
          isDir = false;
        }
      }
      (isDir ? dirs : files).push([e.name, e.isSymbolicLink()]);
    }
    for (const f of T.sorted(files.map(([name]) => name))) yield path.join(dir, f);
    // os.walk visits a folder's files before the folders under it; a link to a folder is listed but not entered
    const keep = T.sorted(dirs.filter(([name]) => !SKIP_DIRS.has(name) && !name.startsWith('.')
      && path.resolve(path.join(dir, name)) !== project.specDir && !hasSpec(path.join(dir, name))).map(([name]) => name));
    for (const name of keep) {
      if (dirs.find(([n]) => n === name)[1]) continue;
      yield* walk(path.join(dir, name));
    }
  }
  yield* walk(start);
}

class Scan {
  constructor(project) {
    this.project = project;
    this.regions = [];
    this._hashes = new Map();
    this._hand = project.handWritten();
    this._explicit = !(project.codeRoots().length === 1 && project.codeRoots()[0] === '.');
    const seen = new Set();
    for (const root of project.codeRoots()) {
      for (const file of filesUnder(project, root)) {
        const rel = this.rel(file);
        if (seen.has(rel)) continue;
        seen.add(rel);
        let size;
        try {
          size = fs.statSync(file).size;
        } catch (e) {
          continue;
        }
        if (size > MAX_BYTES) continue;
        let text;
        try {
          text = DECODER.decode(fs.readFileSync(file));
        } catch (e) {
          continue;   // not text, or not readable
        }
        this._add(rel, text);
      }
    }
    this._anchor();
  }

  /** Regions for `code: path#name` lines: the named symbol's lines belong to the item. */
  _anchor() {
    for (const item of this.project.allItems()) {
      for (const [, target] of item.anchors) {
        const [file, name] = anchors.split(target);
        let rel = file.replace(/\\/g, '/');
        if (rel.startsWith('./')) rel = rel.slice(2);
        let text;
        try {
          text = DECODER.decode(fs.readFileSync(path.resolve(this.project.root, rel)));   // an absolute path stays itself, as in os.path.join
        } catch (e) {
          continue;
        }
        const span = anchors.find(text, rel, name);
        if (span === null) continue;
        const r = new markers.Region(rel, span[0], 'anchor', [item.id]);
        r.end = span[1];
        r.lines = splitLines(text).slice(span[0] - 1, span[1]).map(T.rstrip);
        r.keys = [item.id];
        r.target = target;
        this.regions.push(r);
      }
    }
  }

  rel(file) {
    return path.relative(this.project.root, path.resolve(file)).split(path.sep).join('/');
  }

  /** Whether a file at this project-relative path is code the tool looks at. */
  covers(rel) {
    if (rel.startsWith('../') || rel === this.project.specName || rel.startsWith(`${this.project.specName}/`)) return false;
    return this.project.codeRoots().some((r) => r === '.' || rel === r || rel.startsWith(`${r}/`));
  }

  _add(rel, text) {
    if (!this._explicit && !text.includes('@clause')) return;
    const { regions } = markers.scanText(rel, text, this.project.commentStarters(rel));
    for (const r of regions) this._keys(r);
    this.regions.push(...regions);
  }

  _keys(r) {
    const p = this.project;
    if (r.kind === 'glue') {
      r.keys = [`glue:${r.file}`];
      return;
    }
    for (const ident of r.ids) {
      const name = ident.slice(ident.lastIndexOf('/') + 1);
      if ((name.startsWith('test:') ? name.slice(5) : name).startsWith('~')) continue;
      if (r.kind === 'test') {
        const i = ident.lastIndexOf('/');
        const part = i < 0 ? '' : ident.slice(0, i);
        const tail = ident.slice(i + 1);
        const key = tail.startsWith('test:') ? ident : (part ? `${part}/test:${tail}` : `test:${tail}`);
        const item = p.items.get(key);
        if (item !== undefined && item.isTest) r.keys.push(key);
        continue;
      }
      const found = p.find(ident);
      if (found === null) continue;
      if (found[0] === 'item' && found[1].isTest) continue;
      r.keys.push(found[0] === 'part' ? found[1].key : found[1].id);
    }
  }

  regionsFor(key) {
    return this.regions.filter((r) => r.keys.includes(key));
  }

  /** Whether any file with code in it is of a type that is normalized in its own way (not as C-family). */
  hasOwnRules() {
    return this.regions.some((r) => markers.styleOf(r.file) !== 'c');
  }

  _byFileAndLine() {
    return this.regions.slice().sort((a, b) => T.compare(a.file, b.file) || a.start - b.start);
  }

  /** lock key -> hash of all code marked with it, in file and line order; `legacy`: with the rule every file followed before the file type. */
  codeHashes(legacy = false) {
    if (!this._hashes.has(legacy)) {
      const byKey = new Map();
      for (const r of this._byFileAndLine()) {
        for (const k of r.keys) {
          if (!byKey.has(k)) byKey.set(k, []);
          byKey.get(k).push(r);
        }
      }
      this._hashes.set(legacy, new Map([...byKey].map(([k, rs]) => [k, markers.codeHash(rs, legacy)])));
    }
    return this._hashes.get(legacy);   // worked out once; the callers only read it
  }

  /** key -> Map(target -> hash) of the code marked with it, one hash for the regions in each target's paths. Code in no target's path is under `*`. */
  targetCodeHashes() {
    if (!this._hashes.has('targets')) {
      const byKey = new Map();
      for (const r of this._byFileAndLine()) {
        const target = this.project.targetOf(r.file) || '*';
        for (const k of r.keys) {
          if (!byKey.has(k)) byKey.set(k, new Map());
          if (!byKey.get(k).has(target)) byKey.get(k).set(target, []);
          byKey.get(k).get(target).push(r);
        }
      }
      this._hashes.set('targets', new Map([...byKey].map(([k, byTarget]) => [k, new Map([...byTarget].map(([t, rs]) => [t, markers.codeHash(rs)]))])));
    }
    return this._hashes.get('targets');
  }

  /** The regions around file:line. */
  at(file, line) {
    const f = file.replace(/\\/g, '/');
    return this.regions.filter((r) => r.file === f && r.contains(line));
  }
}

module.exports = { Scan, filesUnder, SKIP_DIRS, MAX_BYTES };
