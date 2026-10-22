'use strict';
// Reads a spec folder (sor/) into parts, items, table rows and values (SPEC §1-3), and resolves {references} by looking outward from where
// they are written (SPEC §4): `tools/sorlib/model.py` in JavaScript, for the questions an editor asks. What `sor check` says about a spec (the
// problems of the parts, items and references) is not here, and neither is the "did you mean" of a broken reference.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const T = require('./pytext');

const SP = T.SPACE;
const WORD = '\\p{L}\\p{N}_';   // Python's \w
const re = (src, flags = 'su') => new RegExp(src, flags);

const ITEM = re('^- (?:(gives|owns|offers|provides|exports|stores) )?\\*\\*([^*]+)\\*\\*');
const NEEDS = re(`^- (?:needs|uses|requires|depends on)${T.WORD_END}`);
const CONTRACT_WORD = new Map([['offers', 'gives'], ['provides', 'gives'], ['exports', 'gives'], ['stores', 'owns']]);
const VDEF = () => re(`\\{([A-Za-z][${WORD}-]*):[${SP}]*([^{}]+)\\}`, 'gsu');
const REF = () => re(`\\{([^{}:${SP}][^{}:]*)\\}`, 'gsu');
const BAD_VDEF = () => re(`\\{[^{}${SP}]+:[^${SP}][^{}]*\\}`, 'gsu');
const CODE = /`[^`]*`/g;
const HEADER_KEYS = 'Why|Owner|Source|Run|Code|Design|Targets|Claims';
const SETTING = re(`(?:^|\\.[${SP}]+|[${SP}]+·[${SP}]+)(${HEADER_KEYS}):[${SP}]*`);
const SETTING_AT_START = re(`^(?:^|\\.[${SP}]+|[${SP}]+·[${SP}]+)(${HEADER_KEYS}):[${SP}]*`);
const SECTION = re(`^## (.+?)[${SP}]*$`);
const SECTIONS = ['Rules', 'Approach', 'Contract', 'Tests'];
const SECTION_WORDS = new Map([
  ['Rules', ['rules', 'must', 'requirements', 'behaviour', 'behavior', 'what']],
  ['Approach', ['approach', 'notes', 'how', 'how it works', 'design', 'why', 'decisions', 'ideas']],
  ['Contract', ['contract', 'interface', 'api']],
  ['Tests', ['tests', 'checks', 'examples', 'acceptance', 'proof']],
]);
const ANCHOR = re(`^[${SP}]+code:[${SP}]*([^${SP}]+)[${SP}]*$`);
const OPEN = re(`^[${SP}]+open:[${SP}]*(.*?)[${SP}]*$`, 'siu');
const TEST_WORDS = new Map([
  ['each', 'each'], ['do', 'do'], ['given', 'do'], ['when', 'do'], ['expect', 'expect'], ['then', 'expect'], ['should', 'expect'],
  ['shows', 'expect'], ['measure', 'measure'], ['manual', 'manual'], ['by eye', 'manual'], ['by hand', 'manual'], ['sign-off', 'manual'],
  ['bug', 'bug'], ['fixes', 'bug'], ['regression', 'bug'], ['proves', 'proves'], ['runs on', 'runs_on'],
]);
const TEST_LINE = re(`^[${SP}]+(${[...TEST_WORDS.keys()].sort((a, b) => b.length - a.length).map(T.escapeRegExp).join('|')}):[${SP}]*(.*)$`, 'siu');
const ENV_NAME = /^[a-z0-9][a-z0-9._-]*$/;
const LINE_BREAK = /\r\n|\r|\n/;
const STARTER = re(`^[^${WORD}${SP}@{}'"\`]{1,3}$`);
const FILLER = re(`^[-*_=${SP}]+$`);
const SPEC_DIR = 'sor';
const LOCK_FILE = 'sor-lock.json';
const LEGACY_LOCK_FILE = 'clauses-lock.json';
const ROOT = 'ROOT';
const PART_FILE_NAME = 'SPECOFRECORD';
const LEGACY_FILE_NAME = 'CLAUSES';
const ROOT_ALIASES = new Set([ROOT, PART_FILE_NAME, LEGACY_FILE_NAME]);
const SKIP_HIDDEN = (name) => name.startsWith('.');

/** All matches of a global regular expression in a text. */
const all = (rx, text) => Array.from(text.matchAll(rx));

/** The lines of a text, numbered the way an editor numbers them: a line ends at LF, CRLF or CR and nowhere else. */
function splitLines(text) {
  const lines = text.split(LINE_BREAK);
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines;
}

/** s.rpartition(sep): [before, sep, after]; ['', '', s] when sep is not in s. */
function rpartition(s, sep) {
  const i = s.lastIndexOf(sep);
  return i < 0 ? ['', '', s] : [s.slice(0, i), sep, s.slice(i + sep.length)];
}

/** s.partition(sep): [before, sep, after]; [s, '', ''] when sep is not in s. */
function partition(s, sep) {
  const i = s.indexOf(sep);
  return i < 0 ? [s, '', ''] : [s.slice(0, i), sep, s.slice(i + sep.length)];
}

const dirname = (p) => {
  const i = p.lastIndexOf('/');
  return i < 0 ? '' : p.slice(0, i);
};

function within(rel, p) {
  return p === '.' || p === '' || rel === p || rel.startsWith(`${p}/`);
}

/** ([starters], [what is not one]) of a `{comment: %, !}` value. */
function startersIn(text) {
  const found = T.strip(text).split(re(`[,${SP}]+`)).filter((t) => t);
  return [found.filter((t) => STARTER.test(t)), found.filter((t) => !STARTER.test(t))];
}

function sectionOf(heading) {
  const h = T.strip(heading).toLowerCase();
  for (const [canonical, words] of SECTION_WORDS) if (words.includes(h)) return canonical;
  return 'Rules';
}

/** The name of a bullet nobody named yet: stable while its words stay the same. */
function unnamed(text) {
  return `~${crypto.createHash('sha1').update(T.words(text).join(' '), 'utf8').digest('hex').slice(0, 6)}`;
}

function testKeyword(line) {
  const m = TEST_LINE.exec(line);
  return m ? [TEST_WORDS.get(m[1].toLowerCase()), T.strip(m[2])] : null;
}

/** [[environment names...]] for the words after `runs on:`; an environment is the names joined by `+`, in the order they were written. */
function parseRunsOn(text) {
  if (!T.strip(text)) return [[], 'name the environments'];
  const out = [];
  for (const entry of text.split(',')) {
    const names = entry.split('+').map((n) => T.strip(n).toLowerCase());
    const bad = names.filter((n) => !ENV_NAME.test(n));
    if (bad.length) return [[], `"${bad[0]}" is not an environment name`];
    const env = Array.from(new Set(names));
    const key = (e) => JSON.stringify([...new Set(e)].sort());
    if (!out.some((e) => key(e) === key(env))) out.push(env);
  }
  return [out, null];
}

const join = (pid, name) => (pid ? `${pid}/${name}` : name);

function isRow(t) {
  const s = T.strip(t);
  return s.startsWith('|') && !re(`^\\|[${SP}:|-]+\\|$`).test(s) && s !== '';
}

class Row {
  constructor(item, name, text, values) {
    this.id = `${item.id}/${name}`;
    this.name = name;
    this.text = text;
    this.values = values;
  }
}

class Item {
  constructor(part, name, section, kind, lineno) {
    this.part = part;
    this.name = name;
    this.section = section;
    this.kind = kind;
    this.id = join(part.id, name);
    this.file = part.rel;
    this.lineno = lineno;
    this.lines = [];        // [lineno, text] of the bullet and its continuation lines
    this.bullets = new Map(SECTIONS.map((s) => [s, 0]));
    this.values = new Map();
    this.rows = new Map();
    this.refs = [];         // [lineno, reference text]
    this.anchors = [];      // [lineno, 'path#name']
    this.opens = [];        // [lineno, question]
    this.openLines = new Set();
    this.draft = false;
  }

  get isTest() {
    return this.kind === 'test';
  }

  /** The item a test proves (its name without `test:`). */
  get targetName() {
    return this.isTest ? this.name.slice(5) : this.name;
  }

  /** [[keyword, text]] of the keyword lines under the bullet; a line that wraps belongs to the keyword above it. */
  steps() {
    const out = [];
    for (const [n, t] of this.lines.slice(1)) {
      if (this.openLines.has(n)) continue;
      const kw = testKeyword(t);
      if (kw) out.push(kw);
      else if (out.length && T.strip(t)) {
        const [k, v] = out[out.length - 1];
        out[out.length - 1] = [k, `${v} ${T.strip(t)}`];
      }
    }
    return out;
  }

  /** The environments a test must pass in, one list of names for each ([] for a test that runs anywhere). */
  runsOn() {
    if (!this.isTest) return [];
    const key = (e) => JSON.stringify([...new Set(e)].sort());
    const out = [];
    for (const [k, v] of this.steps()) {
      if (k === 'runs_on') for (const e of parseRunsOn(v)[0]) if (!out.some((x) => key(x) === key(e))) out.push(e);
    }
    return out;
  }

  /** The item's own text: table rows are items of their own, so only their names count here. `open:` lines are left out. */
  text() {
    let lines = this.lines;
    if (this.openLines.size) {
      lines = lines.filter(([n]) => !this.openLines.has(n));
      while (lines.length && !T.strip(lines[lines.length - 1][1])) lines.pop();
    }
    const out = lines.filter(([, t]) => !isRow(t)).map(([, t]) => t);
    if (this.rows.size) out.push(`rows: ${[...this.rows.keys()].join(', ')}`);
    return out.join('\n');
  }

  finish() {
    while (this.lines.length && !T.strip(this.lines[this.lines.length - 1][1])) this.lines.pop();
    let header = null;
    let asking = null;   // the indent of the `open:` line whose question is still wrapping onto deeper lines
    for (let i = 0; i < this.lines.length; i++) {
      const [n, t] = this.lines[i];
      const clean = t.replace(CODE, '');
      const s = T.strip(t);
      if (s.startsWith('|')) {
        asking = null;
        if (re(`^\\|[${SP}:|-]+\\|$`).test(s)) continue;
        for (const m of all(REF(), clean)) this.refs.push([n, T.strip(m[1])]);   // a cell refers like any other text
        for (const m of all(VDEF(), clean)) if (T.strip(m[2]).startsWith('=')) this.refs.push([n, T.strip(T.strip(m[2]).slice(1))]);
        const cells = T.strip(s.replace(/^\|+|\|+$/g, '')).split('|').map((c) => T.strip(c));
        if (header === null) {
          header = cells.map((c) => c.toLowerCase());
          this.lines[i] = [n, `  ${s}`];   // the header is item text
        } else {
          const vals = new Map();
          for (let k = 1; k < Math.min(header.length, cells.length); k++) vals.set(header[k], cells[k]);
          this.rows.set(cells[0], new Row(this, cells[0], s, vals));
        }
        continue;
      }
      const asked = this.isTest ? null : OPEN.exec(t);
      if (asked) {
        this.opens.push([n, asked[1]]);
        this.openLines.add(n);
        asking = t.length - T.lstrip(t).length;
        continue;
      }
      if (asking !== null && s && t.length - T.lstrip(t).length > asking) {
        const [n0, question] = this.opens[this.opens.length - 1];   // a wrapped question: deeper-indented lines right after it
        this.opens[this.opens.length - 1] = [n0, T.strip(`${question} ${s}`)];
        this.openLines.add(n);
        continue;
      }
      asking = null;
      const anchor = ANCHOR.exec(t);
      if (anchor && !this.isTest) {
        this.anchors.push([n, anchor[1]]);
        continue;
      }
      for (const m of all(VDEF(), clean)) {
        this.values.set(m[1], T.strip(m[2]));
        if (T.strip(m[2]).startsWith('=')) this.refs.push([n, T.strip(T.strip(m[2]).slice(1))]);
      }
      for (const m of all(REF(), clean)) this.refs.push([n, T.strip(m[1])]);
    }
  }
}

class Part {
  constructor(pid, filePath, rel, rootKey = ROOT) {
    this.id = pid;
    this.path = filePath;
    this.rel = rel;
    this.key = pid || rootKey;
    this.title = '';
    this.header = new Map();
    this.items = new Map();
    this.headings = new Map();
    this.nlines = 0;
  }

  /** The folder or file a part's hand-written code lives in (`Source: code at <path>`, or `Code: <path> (by hand)`), or null. */
  get sourceCode() {
    let m = re(`^code at[${SP}]+([^${SP}]+)`).exec(this.header.get('Source') || '');
    if (!m) m = re(`^([^${SP}]+)[${SP}]*\\(by hand\\)`).exec(this.header.get('Code') || '');
    return m ? m[1].replace(/\/+$/, '') : null;
  }

  /** What other parts see when they refer to the whole part: its header and Contract. */
  face() {
    const out = [this.title];
    for (const k of T.sorted([...this.header.keys()])) out.push(`${k}: ${this.header.get(k)}`);
    for (const i of this.items.values()) if (i.section === 'Contract') out.push(i.text());
    return out.join('\n');
  }
}

function partFiles(folder) {
  return [PART_FILE_NAME, LEGACY_FILE_NAME].map((n) => path.join(folder, `${n}.md`)).filter((f) => isFile(f));
}

function isFile(f) {
  try {
    return fs.statSync(f).isFile();
  } catch (e) {
    return false;
  }
}

function isDir(f) {
  try {
    return fs.statSync(f).isDirectory();
  } catch (e) {
    return false;
  }
}

const hasSpec = (projectRoot) => partFiles(path.join(projectRoot, SPEC_DIR)).length > 0;

/** The id of the part a file holds: its path under the spec folder without .md, or the folder for a folder's own file. */
function partId(root, f) {
  const rel = path.relative(root, f).slice(0, -3).split(path.sep).join('/');
  const base = rel.slice(rel.lastIndexOf('/') + 1);
  const folder = dirname(rel);
  return (base === PART_FILE_NAME || base === LEGACY_FILE_NAME) ? folder : rel;
}

/** Which of two files claiming one part counts: `<id>.md` first, then a folder's own file, then the older CLAUSES.md. */
function fileRank(p, specDir) {
  const base = path.basename(p);
  if (base === `${LEGACY_FILE_NAME}.md`) return 2;
  if (base === `${PART_FILE_NAME}.md`) return path.resolve(path.dirname(p)) === path.resolve(specDir) ? 0 : 1;
  return 0;
}

/** The files under a folder that glob('**\/*.md', recursive) finds: no hidden file or folder, in the order of their paths as strings. */
function mdFiles(folder) {
  const out = [];
  const walk = (dir) => {
    let names;
    try {
      names = fs.readdirSync(dir);
    } catch (e) {
      return;
    }
    for (const name of names) {
      if (SKIP_HIDDEN(name)) continue;
      const full = path.join(dir, name);
      if (isDir(full)) walk(full);
      else if (name.endsWith('.md')) out.push(full);
    }
  };
  walk(folder);
  return T.sorted(out);
}

function parsePart(root, file) {
  const rel = path.relative(root, file).split(path.sep).join('/');
  const part = new Part(partId(root, file), file, rel, ROOT);
  let section = null;
  let cur = null;
  const lines = splitLines(fs.readFileSync(file, 'utf8'));
  part.nlines = lines.length;
  let fenced = false;
  let commented = false;   // inside a ``` block or an HTML comment: text there is not loose
  for (let n = 1; n <= lines.length; n++) {
    const line = T.rstrip(lines[n - 1]);
    let marked = fenced || commented;
    if (T.strip(line).startsWith('```')) {
      fenced = !fenced;
      marked = true;
    } else if (commented) {
      commented = !line.includes('-->');
    } else if (T.strip(line).startsWith('<!--')) {
      commented = !line.includes('-->');
      marked = true;
    }
    const h = SECTION.exec(line);
    if (h) {
      section = sectionOf(h[1]);
      cur = null;
      if (!part.headings.has(section)) part.headings.set(section, n);
      continue;
    }
    if (section === null && !line.startsWith('- ')) {
      if (line.startsWith('# ') && !part.title) {
        part.title = T.strip(line.slice(2));
      } else if (SETTING.test(line) && SETTING_AT_START.test(line)) {
        const pieces = line.split(SETTING);
        for (let i = 1; i + 1 < pieces.length; i += 2) part.header.set(pieces[i], T.strip(pieces[i + 1]));
      } else if (T.strip(line) && part.title && !part.header.has('Why')) {
        part.header.set('Why', T.strip(line));
      } else if (T.strip(line).startsWith('|') && cur !== null) {
        cur.lines.push([n, line]);
      }
      continue;
    }
    if (section === null) section = 'Rules';   // bullets right under the title are rules
    if (line.startsWith('- ')) {
      const m = ITEM.exec(line);
      if (m) {
        let name = T.strip(m[2]);
        const word = CONTRACT_WORD.get(m[1]) || m[1];
        const kind = section === 'Tests' ? 'test' : (word || section.toLowerCase());
        if (section === 'Tests') name = `test:${name}`;
        if (!part.items.has(name)) part.items.set(name, new Item(part, name, section, kind, n));
        cur = part.items.get(name);
      } else if (NEEDS.test(line) && section === 'Contract') {
        if (!part.items.has('needs')) part.items.set('needs', new Item(part, 'needs', section, 'needs', n));
        cur = part.items.get('needs');
      } else {
        // not named yet: a draft until tidy names it; its key follows its words
        let name = unnamed(line.slice(2));
        if (section === 'Tests') name = `test:${name}`;
        const kind = section === 'Tests' ? 'test' : section.toLowerCase();
        if (!part.items.has(name)) part.items.set(name, new Item(part, name, section, kind, n));
        cur = part.items.get(name);
        cur.draft = true;
      }
      cur.lines.push([n, line]);
      cur.bullets.set(section, cur.bullets.get(section) + 1);
    } else if (cur !== null && (line === '' || ' \t|'.includes(line[0]))) {
      cur.lines.push([n, line]);
    } else if (line) {
      cur = null;
    }
  }
  for (const item of part.items.values()) item.finish();
  return part;
}

class Project {
  /** root: a project folder (holding sor/) or the spec folder itself. */
  constructor(root) {
    root = path.resolve(root);
    if (hasSpec(root)) root = path.join(root, SPEC_DIR);   // a project folder; otherwise the folder is the spec folder itself
    const found = partFiles(root);
    if (!found.length) throw new Error(`no ${SPEC_DIR}/${PART_FILE_NAME}.md under ${root}`);
    if (found.length > 1) {
      throw new Error(`both ${SPEC_DIR}/${PART_FILE_NAME}.md and ${SPEC_DIR}/${LEGACY_FILE_NAME}.md exist under ${root}`);
    }
    this.specDir = root;
    this.specName = SPEC_DIR;
    this.rootKey = ROOT;
    this.lockFile = LOCK_FILE;
    this.root = path.dirname(root);
    this._proved = null;
    this._cache = new Map();
    const files = mdFiles(root).filter((f) => !f.endsWith('.tests.md'));
    const byId = new Map();
    for (const f of files) {
      const p = parsePart(root, f);
      if (!byId.has(p.id)) byId.set(p.id, []);
      byId.get(p.id).push([fileRank(f, root), p]);
    }
    this.parts = new Map();
    for (const [pid, claimants] of byId) {
      claimants.sort((a, b) => a[0] - b[0]);   // a stable sort: the first of equal rank counts
      this.parts.set(pid, claimants[0][1]);
    }
    for (const f of mdFiles(root).filter((x) => x.endsWith('.tests.md'))) this._mergeTests(root, f);
    this._design();
    this.items = new Map();   // every item and row by id
    for (const p of this.parts.values()) {
      for (const it of p.items.values()) {
        this.items.set(it.id, it);
        for (const r of it.rows.values()) this.items.set(r.id, r);
      }
    }
  }

  /** `Design: design/tokens.json` under the root title: the exported design becomes the part `design`. */
  _design() {
    const rootPart = this.parts.get('');
    const m = /(\S+\.json)/u.exec(rootPart ? (rootPart.header.get('Design') || '') : '');
    if (!m) return;
    const rel = m[1];
    const file = path.join(this.root, rel);
    const part = new Part('design', file, rel);
    part.title = 'Design';
    part.header.set('Why', 'colors and pictures exported from the design file');
    this.parts.set('design', part);
    let data;
    try {
      data = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch (e) {
      return;
    }
    const item = (name) => {
      const it = new Item(part, name, 'Contract', 'design', 0);   // not a promise: it is not counted as a rule
      it.lines = [[0, `- **${name}** — from ${rel}`]];
      part.items.set(name, it);
      return it;
    };
    const isObject = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
    for (const group of Object.keys(data)) {
      const tokens = data[group];
      if (group.startsWith('$') || !isObject(tokens)) continue;
      const it = item(group);
      for (const name of Object.keys(tokens)) {
        const tok = tokens[name];
        if (isObject(tok) && Object.prototype.hasOwnProperty.call(tok, '$value')) {
          const value = String(tok.$value);
          it.rows.set(name, new Row(it, name, `| ${name} | ${value} |`, new Map([['value', value]])));
        }
      }
    }
    const assets = path.join(path.dirname(file), 'assets');
    if (isDir(assets)) {
      const it = item('assets');
      for (const f of T.sorted(fs.readdirSync(assets).filter((x) => x.endsWith('.svg') && !SKIP_HIDDEN(x)).map((x) => path.join(assets, x)))) {
        const name = path.basename(f, '.svg');
        const digest = crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex').slice(0, 12);
        const fileRel = path.relative(this.root, f).split(path.sep).join('/');
        it.rows.set(name, new Row(it, name, `| ${name} | ${fileRel} | ${digest} |`, new Map([['file', fileRel]])));
      }
    }
  }

  /** `<part>.tests.md` holds more tests of the part. What cannot be merged is left out here (`sor check` reports it). */
  _mergeTests(root, f) {
    const extra = parsePart(root, f);
    const pid = partId(root, `${f.slice(0, -9)}.md`);
    const home = this.parts.get(pid);
    if (home === undefined) return;
    for (const [k, it] of extra.items) {
      if (!it.isTest || home.items.has(k)) continue;
      it.part = home;
      it.id = join(pid, it.name);
      home.items.set(k, it);
    }
  }

  get lockPath() {
    return path.join(this.specDir, this.lockFile);
  }

  get legacyLockPath() {
    return path.join(this.specDir, LEGACY_LOCK_FILE);
  }

  * allItems() {
    for (const p of this.parts.values()) yield* p.items.values();
  }

  /** An id as written in a marker or on the command line → [kind, object] or null. */
  find(ident) {
    if (this.parts.has(ident)) return ['part', this.parts.get(ident)];
    if (ROOT_ALIASES.has(ident)) return ['part', this.parts.get('')];
    if (this.items.has(ident)) {
      const o = this.items.get(ident);
      return [o instanceof Row ? 'row' : 'item', o];
    }
    return null;
  }

  /** rest is `name`, `name.value`, `name/Row` or `name/Row.value` inside part pid. */
  _inPart(pid, rest) {
    const [pth, , val] = partition(rest, '.');
    const segs = pth.split('/');
    const item = this.parts.get(pid).items.get(segs[0]);
    if (item === undefined) return null;
    if (segs.length > 2) return null;
    if (segs.length === 2) {
      const row = item.rows.get(segs[1]);
      if (row === undefined || (val && !row.values.has(val))) return null;
      return val ? `${row.id}.${val}` : row.id;
    }
    if (val && !item.values.has(val)) return null;
    return val ? `${item.id}.${val}` : item.id;
  }

  /** All ids `ref`, written in part `pid`, can mean. Exactly one is a valid reference. */
  resolve(pid, ref) {
    const key = `${pid}\u0000${ref}`;
    if (this._cache.has(key)) return this._cache.get(key);
    const levels = [];
    let p = pid;
    for (;;) {
      levels.push(p);
      if (p === '') break;
      p = dirname(p);
    }
    const [pth, , val] = partition(ref, '.');
    const segs = pth.split('/');
    const hits = [];
    for (const level of levels) {
      if (this.parts.has(level)) {
        const hit = this._inPart(level, ref);
        if (hit) hits.push(hit);
      }
      for (let k = segs.length; k > 0; k--) {
        const sub = (level ? [level] : []).concat(segs.slice(0, k)).join('/');
        if (this.parts.has(sub) && sub !== level) {
          const rest = segs.slice(k).join('/');
          let hit;
          if (rest) hit = this._inPart(sub, rest + (val ? `.${val}` : ''));
          else if (val) hit = null;   // a part has no values of its own
          else hit = sub;
          if (hit) hits.push(hit);
          break;
        }
      }
    }
    const out = T.sorted(Array.from(new Set(hits)));
    this._cache.set(key, out);
    return out;
  }

  /** The Set of target ids of an item's references that resolve to exactly one id. */
  resolvedRefs(item) {
    const out = new Set();
    for (const [, ref] of item.refs) {
      const hits = this.resolve(item.part.id, ref);
      if (hits.length === 1) out.add(hits[0]);
    }
    return out;
  }

  /** [[item id, how]]: what a test proves (SPEC §8). `how` is 'name', 'refers' or 'says'. */
  proofLinks(test) {
    const out = [];
    const target = test.part.items.get(test.targetName);
    if (target !== undefined && !target.isTest) out.push([target.id, 'name']);
    let word = null;
    const words = new Map();
    for (const [n, t] of test.lines.slice(1)) {
      const kw = testKeyword(t);
      if (kw) word = kw[0];
      words.set(n, word);   // a wrapped line belongs to the keyword above it
    }
    for (const [n, ref] of test.refs) {
      const w = words.get(n);
      if (!['expect', 'measure', 'proves'].includes(w)) continue;
      const hits = this.resolve(test.part.id, ref);
      if (hits.length !== 1) continue;
      let owner = hits[0];
      if (!this.items.has(owner) && owner.includes('.')) owner = owner.slice(0, owner.lastIndexOf('.'));
      if (this.items.get(owner) instanceof Row) owner = owner.slice(0, owner.lastIndexOf('/'));
      const o = this.items.get(owner);
      if (o instanceof Item && !o.isTest) out.push([owner, w === 'proves' ? 'says' : 'refers']);
    }
    return out;
  }

  proves(test) {
    return new Set(this.proofLinks(test).map(([i]) => i));
  }

  /** Ids of the tests that prove an item: the test named after it, then every other that proves it. */
  testsOf(itemId, regressionsOnly = false) {
    if (this._proved === null) {
      this._proved = new Map();
      this._namedAfterNothing = new Set();
      this._declared = new Map();
      for (const t of this.allItems()) {
        if (!t.isTest) continue;
        if (t.part.items.get(t.targetName) === undefined) this._namedAfterNothing.add(t.id);
        for (const [i, how] of this.proofLinks(t)) {
          if (!this._proved.has(i)) this._proved.set(i, []);
          if (!this._proved.get(i).includes(t.id)) this._proved.get(i).push(t.id);
          if (how === 'says') {
            if (!this._declared.has(i)) this._declared.set(i, new Set());
            this._declared.get(i).add(t.id);
          }
        }
      }
    }
    const [head, , tail] = rpartition(itemId, '/');
    const own = join(head, `test:${tail}`);
    let others = (this._proved.get(itemId) || []).filter((t) => t !== own);
    if (regressionsOnly) others = others.filter((t) => this._namedAfterNothing.has(t) || (this._declared.get(itemId) || new Set()).has(t));
    return [own].concat(others);
  }

  /** Where code lives: every `path` value a target declares, and every `Source: code at`. */
  codeRoots() {
    const roots = [];
    for (const p of this.parts.values()) {
      if (p.id.startsWith('targets/')) {
        for (const it of p.items.values()) if (it.section === 'Rules' && it.values.has('path')) roots.push(it.values.get('path'));
      }
      if (p.sourceCode) roots.push(p.sourceCode);
    }
    const out = T.sorted(Array.from(new Set(roots.map((r) => r.replace(/\/+$/, '')))));
    return out.length ? out : ['.'];
  }

  /** [[target name, path, the part that says so]] for every `path` a target declares, in part order. */
  targetPaths() {
    if (!this._targetPaths) {
      this._targetPaths = [];
      for (const p of this.parts.values()) {
        if (!p.id.startsWith('targets/')) continue;
        for (const it of p.items.values()) {
          if (it.section === 'Rules' && it.values.has('path')) this._targetPaths.push([p.id.split('/')[1], it.values.get('path').replace(/\/+$/, ''), p]);
        }
      }
    }
    return this._targetPaths;
  }

  /** The comment starters that the target of this file declares for its markers. */
  commentStarters(rel) {
    const target = this.targetOf(rel);
    if (target === null) return [];
    if (!this._starters) {
      this._starters = new Map();
      for (const p of this.parts.values()) {
        if (!p.id.startsWith('targets/')) continue;
        for (const it of p.items.values()) {
          if (it.section === 'Rules' && it.values.has('comment')) {
            const name = p.id.split('/')[1];
            if (!this._starters.has(name)) this._starters.set(name, []);
            this._starters.get(name).push(...startersIn(it.values.get('comment'))[0]);
          }
        }
      }
    }
    return this._starters.get(target) || [];
  }

  targetNames() {
    return T.sorted(Array.from(new Set(this.targetPaths().map(([name]) => name))));
  }

  rootPart() {
    return this.parts.get('');
  }

  /** Whether the project says which targets its clauses apply to: its root file has a `Targets:` line (SPEC §9). */
  targeted() {
    const root = this.rootPart();
    return Boolean(root && T.strip(root.header.get('Targets') || ''));
  }

  /** The targets the clauses of a part apply to: the nearest `Targets:` of the part or the parts around it, up to the root file's. */
  targetsOfPart(part) {
    if (!this.targeted()) return [];
    const names = (text) => text.split(',').map((n) => T.strip(n)).filter((n) => n);
    let pid = part ? part.id : '';
    while (pid) {
      const p = this.parts.get(pid);
      const text = p ? T.strip(p.header.get('Targets') || '') : '';
      if (text) return names(text);
      pid = rpartition(pid, '/')[0];
    }
    return names(this.rootPart().header.get('Targets'));
  }

  /** The id of the part a lock key belongs to: the part itself, or the nearest part above an item, row or value. */
  ownerPartId(key) {
    let pid = this.parts.has(key) ? key : rpartition(key, '/')[0];
    while (pid && !this.parts.has(pid)) pid = rpartition(pid, '/')[0];
    return pid;
  }

  /** The targets the clause behind a lock key applies to. All the targets when the root file says nothing. */
  targetsApplyingTo(key) {
    if (!this.targeted()) return this.targetNames();
    return this.targetsOfPart(this.parts.get(this.ownerPartId(key)));
  }

  /** The target a file belongs to: the one whose path is the longest prefix of this project-relative path, or null. */
  targetOf(rel) {
    let best = -1;
    let names = [];
    for (const [name, pth] of this.targetPaths()) {
      if (!within(rel, pth)) continue;
      const size = (pth === '.' || pth === '') ? 0 : pth.length;
      if (size > best) {
        best = size;
        names = [name];
      } else if (size === best && !names.includes(name)) names.push(name);
    }
    return names.length === 1 ? names[0] : null;
  }

  /** Folders whose code is written by people: unmarked lines are allowed there. */
  handWritten() {
    const out = new Map();
    for (const p of this.parts.values()) if (p.sourceCode) out.set(p.sourceCode, p);
    return out;
  }
}

module.exports = {
  splitLines, rpartition, partition, dirname, within, startersIn, sectionOf, unnamed, testKeyword, parseRunsOn, join, isRow, Row, Item, Part,
  Project, parsePart, partId, partFiles, hasSpec, mdFiles, isFile, isDir, ROOT_ALIASES, SPEC_DIR, LOCK_FILE, LEGACY_LOCK_FILE, ROOT,
  PART_FILE_NAME, LEGACY_FILE_NAME, SECTIONS, VDEF, REF, CODE,
};
