// @clause glue
/*
 * Spec of Record for VS Code (rebuild from the clauses in editors/vscode/clauses).
 *
 * Notes and assumptions of the builder (more in BUILD-NOTES.md):
 * - Everything comes from `sor markers --json` and `sor status --json`; this file parses no clauses.
 * - A "marker line on its own" is a line of an index region (kind code/glue) at its start or end
 *   whose text is only an @clause comment. Line-end markers (kind "line") are never hidden.
 * - Item lens flags and hover use the words "to review" / "to recompile"; marker lenses show the raw
 *   status word (stale, changed, ...) as the lens clause says.
 * - Gutter mark lines in state.marks are 1-based; fold ranges in state.folds are 0-based.
 * - Part headings without code get a lens titled "no code" that does nothing when clicked.
 * - When hiding is off the extension returns no folding ranges at all (also no indentation fallback).
 */
'use strict';
const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const cp = require('child_process');
// @clause end

// @clause marker-lines/which
const MARKER_RE = /^\s*(?:([^\w\s])\1*|\/\*+|<!--+|\(\*+|[Rr][Ee][Mm])\s*@clause\b/;
// @clause end
// @clause lenses/clause-lens lenses/jump
/** Where a region is, as the lens and the list of regions say it: `out/index.html:26-28`. */
const rangeOf = (r) => `${r.file}:${r.start === r.end ? r.start : r.start + '-' + r.end}`;
/** The targets (languages) the regions are in, as `py, ts`, when they are in more than one; '' for code in one target or in none. */
function targetsOf(regs) {
  const names = [...new Set(regs.map((r) => r.targetName).filter(Boolean))].sort();
  return names.length > 1 ? names.join(', ') : '';
}
/** The title of a clause lens: the place of its one region, or how many regions it has and, when they differ, which targets they are in. */
function codeTitle(regs) {
  if (!regs.length) return 'no code';
  if (regs.length === 1) return rangeOf(regs[0]);
  const targets = targetsOf(regs);
  return `${regs.length} code regions` + (targets ? ` (${targets})` : '');
}
/** One entry of the list of regions a click asks about: its place, and its ids, with its target in front when the regions are in several. */
function pickOf(r, several) {
  return { label: rangeOf(r), description: [several && r.targetName, ...(r.ids || [])].filter(Boolean).join(' '), region: r };
}
// @clause end
// @clause marker-lines/fallback-folds
const SERVER_LANGS = new Set(['html', 'javascript', 'typescript', 'javascriptreact', 'typescriptreact', 'css', 'scss', 'less', 'json', 'jsonc', 'xml', 'markdown']);
// @clause end
// @clause state/states state/worst-wins lenses/flags
const RANK = { drift: 3, review: 2, recompile: 1 };
const WORD = { drift: 'drift', review: 'to review', recompile: 'to recompile' };
const FLAG = { drift: '● drift', review: '● to review', recompile: '● to recompile' };
// @clause end

// @clause targets/vscode/paths-case
const norm = (p) => path.normalize(p).toLowerCase();
// @clause end
// @clause glue
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// @clause end

// @clause state/words
function classOf(status) {
  if (status === 'drift') return 'drift';
  if (status === 'stale' || status === 'shared') return 'review';
  if (status === 'new' || status === 'changed' || status === 'removed' || status === 'behind') return 'recompile';
  return null;
}
// @clause end

// @clause project/tool-path project/node
/** The command that runs the tool: the JavaScript tool inside the extension (tools/sor.js, next to src/) on the editor's own Node. Nothing of the project is looked at. */
function toolCommand(root, args, node = process.execPath, dir = __dirname) {
  return { file: node, args: [path.join(dir, '..', 'tools', 'sor.js'), '-C', root, ...args], env: { ELECTRON_RUN_AS_NODE: '1' } };
}
// @clause end

// @clause glue
function activate(context) {
  const out = vscode.window.createOutputChannel('Spec of Record');
  const state = {
    projects: [],
    marks: new Map(),        // file key -> { drift: [line], review: [line], recompile: [line] } (1-based)
    markerLines: new Map(),  // file key -> { lines: [hidden marker lines, 1-based] }
    folds: new Map(),        // file key -> { fold: [{start, end}], skipped: [marker line, 0-based], ... }
  };
  const lensEmitter = new vscode.EventEmitter();
  const foldEmitter = new vscode.EventEmitter();
  const refreshEmitter = new vscode.EventEmitter();
  const hideOn = () => vscode.workspace.getConfiguration('sor').get('hideMarkerLines') !== false;
  let generation = 0;
// @clause end

  // @clause project project/wake
  // ---------------------------------------------------------------- project / tool
  /** Runs `sor -C root ...args` and returns its JSON. Exit codes 1 and 2 still count. */
  function runSor(project, args) {
    return new Promise((resolve, reject) => {
      const run = toolCommand(project.root, args);
      cp.execFile(run.file, run.args, {
        maxBuffer: 256 * 1024 * 1024, windowsHide: true, encoding: 'utf8', env: { ...process.env, ...run.env },
      }, (err, stdout, stderr) => {
        const text = (stdout || '').trim();
        if (text) {
          try { resolve(JSON.parse(text)); return; } catch (e) { /* fall through */ }
        }
        const tail = [(err && err.message) || '', stderr || '', text].join('\n').split(/\r?\n/).filter(Boolean).slice(-8);
        reject(new Error(tail.join('\n') || 'no JSON from the sor tool'));
      });
    });
  }

  async function discover() {
    const found = await Promise.all(['**/sor/SPECOFRECORD.md', '**/sor/CLAUSES.md']   // the root file, and its older name
      .map((g) => vscode.workspace.findFiles(g, '**/node_modules/**', 20)));
    const files = found.flat();
    const roots = new Set();
    for (const f of files) {
      if (f.scheme !== 'file') continue;
      roots.add(path.dirname(path.dirname(f.fsPath)));
    }
    return [...roots].sort();
  }

  function buildDerived(project) {
    const worst = new Map();
    const findings = (project.status && project.status.findings) || [];
    for (const f of findings) {
      const c = classOf(f.status);
      if (!c) continue;
      const cur = worst.get(f.key);
      if (!cur || RANK[c] > RANK[cur.cls]) worst.set(f.key, { cls: c, status: f.status, finding: f });
    }
    project.worst = worst;
    project.itemsById = new Map();
    for (const it of (project.index && project.index.items) || []) project.itemsById.set(it.id, it);
  }

  let queue = Promise.resolve();
  function refresh() {
    const p = queue.then(doRefresh, doRefresh);
    queue = p.catch(() => {});
    return p;
  }
  let timer;
  function scheduleRefresh() {
    clearTimeout(timer);
    timer = setTimeout(() => { refresh(); }, 400);
  }

  async function doRefresh() {
    let roots = [];
    try { roots = await discover(); } catch (e) { out.appendLine('discover failed: ' + e.message); }
    const old = new Map(state.projects.map((p) => [p.root, p]));
    const next = [];
    await Promise.all(roots.map(async (root) => {
      const project = old.get(root) || { root, specDir: path.join(root, 'sor'), index: null, status: null };
      try {
        const [index, status] = await Promise.all([runSor(project, ['markers', '--json']), runSor(project, ['status', '--json'])]);
        project.index = index;
        project.status = status;
        if (index.specDir) project.specDir = index.specDir;
      } catch (e) {
        out.appendLine(`[${root}] refresh failed:\n${e.message}`);
      }
      buildDerived(project);
      next.push(project);
    }));
    next.sort((a, b) => a.root.localeCompare(b.root));
    state.projects = next;
    generation++;
    computeMarks();
    refreshAll();
    refreshEmitter.fire();
    lensEmitter.fire();
    foldEmitter.fire();
    updateStatusBar();
  }

  function projectOf(fsPath) {
    const k = norm(fsPath);
    let best = null;
    for (const p of state.projects) {
      const r = norm(p.root);
      if (k === r || k.startsWith(r.endsWith(path.sep) ? r : r + path.sep)) {
        if (!best || r.length > norm(best.root).length) best = p;
      }
    }
    return best;
  }
  const isSpecDoc = (project, fsPath) => {
    const d = norm(project.specDir);
    return norm(fsPath).startsWith(d + path.sep) && /\.md$/i.test(fsPath);
  };
  const docProject = (doc) => (doc.uri.scheme === 'file' ? projectOf(doc.uri.fsPath) : null);
  const regionsOfFile = (project, fsPath) => {
    if (!project.index) return [];
    const k = norm(fsPath);
    return project.index.regions.filter((r) => norm(r.path) === k);
  };
  // @clause end

  // @clause state state/status-bar
  // ---------------------------------------------------------------- state: marks and status bar
  function computeMarks() {
    const files = new Map();   // key -> Map(line -> cls)
    const put = (file, line, cls) => {
      const k = norm(file);
      let m = files.get(k);
      if (!m) files.set(k, (m = new Map()));
      const cur = m.get(line);
      if (!cur || RANK[cls] > RANK[cur]) m.set(line, cls);
    };
    const best = (project, keys) => {
      let c = null;
      for (const key of keys) {
        const w = project.worst.get(key);
        if (w && (!c || RANK[w.cls] > RANK[c])) c = w.cls;
      }
      return c;
    };
    for (const project of state.projects) {
      if (!project.index) continue;
      for (const r of project.index.regions) {
        if (!files.has(norm(r.path))) files.set(norm(r.path), new Map());
        const c = best(project, r.keys);
        if (c) for (let l = r.start; l <= r.end; l++) put(r.path, l, c);
      }
      for (const f of (project.status && project.status.findings) || []) {
        const c = classOf(f.status);
        const m = c && f.where && /^(.*):(\d+)(?:-(\d+))?$/.exec(f.where);
        if (m) {
          const a = +m[2];
          const b = m[3] ? +m[3] : a;
          for (let l = a; l <= b; l++) put(path.join(project.root, m[1]), l, c);
        }
      }
      for (const it of project.index.items) {
        if (!files.has(norm(it.path))) files.set(norm(it.path), new Map());
        const c = best(project, [it.id]);
        if (c) for (let l = it.line; l <= (it.endLine || it.line); l++) put(it.path, l, c);
      }
    }
    state.marks.clear();
    for (const [k, m] of files) {
      const o = { drift: [], review: [], recompile: [] };
      for (const [l, c] of [...m].sort((a, b) => a[0] - b[0])) o[c].push(l);
      state.marks.set(k, o);
    }
  }

  const decoTypes = {};
  for (const c of ['drift', 'review', 'recompile']) {
    decoTypes[c] = vscode.window.createTextEditorDecorationType({
      gutterIconPath: vscode.Uri.file(context.asAbsolutePath(path.join('media', c + '.svg'))),
      gutterIconSize: 'contain',
    });
  }
  const hideType = vscode.window.createTextEditorDecorationType({ opacity: '0' });

  function applyMarks(editor) {
    const doc = editor.document;
    const m = doc.uri.scheme === 'file' ? state.marks.get(norm(doc.uri.fsPath)) : null;
    for (const c of ['drift', 'review', 'recompile']) {
      const ranges = m && docProject(doc) ? m[c].filter((l) => l <= doc.lineCount).map((l) => new vscode.Range(l - 1, 0, l - 1, 0)) : [];
      editor.setDecorations(decoTypes[c], ranges);
    }
  }

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  status.command = 'sor.refresh';
  status.name = 'Spec of Record';
  function updateStatusBar() {
    if (!state.projects.length) { status.hide(); return; }
    const n = { drift: 0, review: 0, recompile: 0 };
    for (const p of state.projects) {
      for (const f of (p.status && p.status.findings) || []) {
        const c = classOf(f.status);
        if (c) n[c]++;
      }
    }
    status.text = `${n.drift} drift · ${n.review} review · ${n.recompile} recompile`;
    state.statusBarText = status.text;   // a status bar item cannot be read back, so tests read it here (state/status-bar)
    status.tooltip = 'Spec of Record: click to refresh';
    status.show();
  }
  // @clause end

  // @clause marker-lines marker-lines/which marker-lines/setting
  // ---------------------------------------------------------------- marker lines: hiding and folding
  /** 0-based indexes of the marker lines of a document (own-line @clause comments at region ends). */
  function markerIdx(doc) {
    const project = docProject(doc);
    if (!project) return [];
    const set = new Set();
    for (const r of regionsOfFile(project, doc.uri.fsPath)) {
      if (r.kind === 'line') continue;
      for (const l of [r.start - 1, r.end - 1]) {
        if (l >= 0 && l < doc.lineCount && MARKER_RE.test(doc.lineAt(l).text)) set.add(l);
      }
    }
    return [...set].sort((a, b) => a - b);
  }

  function selectedLines(doc) {
    const s = new Set();
    for (const ed of vscode.window.visibleTextEditors) {
      if (ed.document !== doc) continue;
      for (const sel of ed.selections) for (let l = sel.start.line; l <= sel.end.line; l++) s.add(l);
    }
    return s;
  }

  function updateMarkerLines(doc) {
    if (doc.uri.scheme !== 'file') return;
    const key = norm(doc.uri.fsPath);
    const idx = markerIdx(doc);
    if (!idx.length) { state.markerLines.delete(key); applyHide(doc, []); return; }
    if (!hideOn()) { state.markerLines.set(key, { lines: [] }); applyHide(doc, []); return; }
    const sel = selectedLines(doc);
    const exempt = new Set();
    for (const m of idx) if (sel.has(m)) exempt.add(m);
    const lines = idx.filter((m) => !exempt.has(m)).map((m) => m + 1);
    state.markerLines.set(key, { lines });
    applyHide(doc, lines);
  }

  function applyHide(doc, lines) {
    for (const ed of vscode.window.visibleTextEditors) {
      if (ed.document !== doc) continue;
      ed.setDecorations(hideType, lines.map((l) => new vscode.Range(l - 1, 0, l - 1, 0)));
    }
  }
  // @clause end

  // @clause marker-lines marker-lines/fold marker-lines/blank-rows marker-lines/own-regions marker-lines/fallback-folds
  /** Indentation folds, used only when no other folding provider gave anything. */
  function indentFolds(doc) {
    const n = doc.lineCount;
    const ind = [];
    for (let i = 0; i < n; i++) {
      const t = doc.lineAt(i).text;
      ind.push(/^\s*$/.test(t) ? -1 : t.replace(/\t/g, '    ').search(/\S/));
    }
    const res = [];
    const stack = [];
    for (let i = 0; i <= n; i++) {
      const cur = i < n ? ind[i] : 0;
      if (cur === -1) continue;
      while (stack.length && stack[stack.length - 1].indent >= cur) {
        const s = stack.pop();
        let end = i - 1;
        while (end > s.start && ind[end] === -1) end--;
        if (end > s.start) res.push({ start: s.start, end });
      }
      if (i < n) stack.push({ start: i, indent: cur });
    }
    return res.sort((a, b) => a.start - b.start || b.end - a.end);
  }

  const computing = new Set();
  const planning = new Map();

  async function computePlan(doc, project) {
    const key = norm(doc.uri.fsPath);
    const version = doc.version;
    const idx = markerIdx(doc);
    const plan = { version, key: idx.join(','), fold: [], skipped: [], indent: null };
    if (idx.length) {
      let others = [];
      computing.add(key);
      try {
        // the built-in language servers may still be starting: ask again a few times for their languages
        const tries = SERVER_LANGS.has(doc.languageId) ? 6 : 1;
        for (let t = 0; t < tries && !others.length; t++) {
          if (t) await sleep(400);
          others = (await vscode.commands.executeCommand('vscode.executeFoldingRangeProvider', doc.uri)) || [];
        }
      } catch (e) { others = []; } finally { computing.delete(key); }
      let own = null;
      if (!others.length) {
        own = indentFolds(doc);
        others = own.map((r) => ({ start: r.start, end: r.end }));
        plan.indent = own;
      }
      if (others.some((o) => o.kind === vscode.FoldingRangeKind.Region)) {
        plan.skipped = idx.slice();
      } else {
        const runs = [];
        for (const m of idx) {
          const last = runs[runs.length - 1];
          if (last && last[last.length - 1] === m - 1) last.push(m); else runs.push([m]);
        }
        for (const run of runs) {
          const a = run[0] - 1;
          const b = run[run.length - 1];
          const bad = a < 0 || others.some((o) => o.start === a || o.end === a
            || (o.start < a && o.end >= a && o.end < b) || (o.start > a && o.start <= b && o.end > b));
          if (bad) plan.skipped.push(...run); else plan.fold.push({ start: a, end: b });
        }
      }
    }
    if (doc.version !== version) return plan;
    state.folds.set(key, plan);
    return plan;
  }

  async function getPlan(doc) {
    const project = docProject(doc);
    if (!project || !project.index || !hideOn()) return null;
    const key = norm(doc.uri.fsPath);
    const have = state.folds.get(key);
    if (have && have.version === doc.version && have.key === markerIdx(doc).join(',')) return have;
    if (planning.has(key)) return planning.get(key);
    const p = computePlan(doc, project).then((plan) => {
      foldEmitter.fire();
      updateMarkerLines(doc);
      lensEmitter.fire();
      return plan;
    }).finally(() => planning.delete(key));
    planning.set(key, p);
    return p;
  }

  const foldProvider = {
    onDidChangeFoldingRanges: foldEmitter.event,
    async provideFoldingRanges(doc) {
      const key = norm(doc.uri.fsPath);
      if (computing.has(key) || !hideOn()) return [];
      const plan = await getPlan(doc);
      if (!plan) return [];
      const r = plan.fold.map((f) => new vscode.FoldingRange(f.start, f.end, vscode.FoldingRangeKind.Region));
      if (plan.indent) for (const f of plan.indent) r.push(new vscode.FoldingRange(f.start, f.end));
      return r;
    },
  };
  // @clause end

  // @clause marker-lines marker-lines/cursor-opens marker-lines/cursor-kept marker-lines/toggle-off marker-lines/setting
  const opened = new Map();   // file key -> Set of fold start lines opened by the cursor
  let epoch = 0;              // bumped when hiding changes, so late timers do nothing
  async function reconcile(editor, lines) {
    if (!hideOn() || editor !== vscode.window.activeTextEditor) return;
    const doc = editor.document;
    const key = norm(doc.uri.fsPath);
    const plan = state.folds.get(key);
    if (!plan) return;
    let set = opened.get(key);
    if (!set) opened.set(key, (set = new Set()));
    const sel = lines || new Set();
    if (!lines) for (const s of editor.selections) for (let l = s.start.line; l <= s.end.line; l++) sel.add(l);
    for (const f of plan.fold) {
      let touched = false;
      for (let l = f.start; l <= f.end; l++) if (sel.has(l)) { touched = true; break; }
      if (touched && !set.has(f.start)) {
        set.add(f.start);
        await vscode.commands.executeCommand('editor.unfold', { levels: 1, direction: 'down', selectionLines: [f.start] });
      } else if (!touched && set.has(f.start)) {
        set.delete(f.start);
        await vscode.commands.executeCommand('editor.fold', { levels: 1, direction: 'down', selectionLines: [f.start] });
      }
    }
  }

  async function applyFolds(editor, myEpoch) {
    if (!hideOn() || myEpoch !== epoch || editor !== vscode.window.activeTextEditor) return;
    const plan = await getPlan(editor.document);
    if (!plan || !plan.fold.length || !hideOn() || myEpoch !== epoch || editor !== vscode.window.activeTextEditor) return;
    const vis = new Set();
    for (const r of editor.visibleRanges) for (let l = r.start.line; l <= r.end.line; l++) vis.add(l);
    const touchedNow = new Set();
    for (const s of editor.selections) for (let l = s.start.line; l <= s.end.line; l++) touchedNow.add(l);
    // nothing to do when every fold in view is already closed (or open because the cursor is there)
    const open = plan.fold.some((f) => vis.has(f.start) && vis.has(f.end) && ![...touchedNow].some((l) => l >= f.start && l <= f.end));
    if (!open) return;
    // folding hides lines, and VS Code then moves a cursor out of them: remember where it was
    const saved = editor.selections.slice();
    const lines = new Set();
    for (const s of saved) for (let l = s.start.line; l <= s.end.line; l++) lines.add(l);
    await vscode.commands.executeCommand('editor.foldAllMarkerRegions');
    opened.delete(norm(editor.document.uri.fsPath));
    await reconcile(editor, lines);
    // put a cursor back only if folding pushed it from a folded line onto that fold's first line;
    // a cursor someone placed meanwhile stays where it is
    const now = editor.selections;
    const pushed = now.length === saved.length && now.some((s, i) => !s.isEqual(saved[i])
      && plan.fold.some((f) => s.active.line === f.start && saved[i].active.line > f.start && saved[i].active.line <= f.end));
    if (pushed) editor.selections = saved;
  }

  function scheduleApply(editor) {
    if (!editor) return;
    const myEpoch = epoch;
    for (const ms of [150, 600, 1100, 1700, 2500]) setTimeout(() => { applyFolds(editor, myEpoch).catch(() => {}); }, ms);
  }

  function refreshAll() {
    for (const doc of vscode.workspace.textDocuments) updateMarkerLines(doc);
    for (const ed of vscode.window.visibleTextEditors) applyMarks(ed);
    const ed = vscode.window.activeTextEditor;
    if (ed && hideOn()) {
      getPlan(ed.document).then(() => scheduleApply(ed)).catch(() => {});
    }
  }

  async function onHideChanged() {
    epoch++;
    if (!hideOn()) {
      if (vscode.window.activeTextEditor) {
        try { await vscode.commands.executeCommand('editor.unfoldAllMarkerRegions'); } catch (e) { /* ignore */ }
      }
      state.folds.clear();
      opened.clear();
      setTimeout(() => { if (!hideOn() && vscode.window.activeTextEditor) vscode.commands.executeCommand('editor.unfoldAllMarkerRegions').then(undefined, () => {}); }, 500);
    }
    for (const doc of vscode.workspace.textDocuments) updateMarkerLines(doc);
    foldEmitter.fire();
    lensEmitter.fire();
    if (hideOn()) {
      const ed = vscode.window.activeTextEditor;
      if (ed) { await getPlan(ed.document); scheduleApply(ed); }
    }
  }
  // @clause end

  // @clause lenses lenses/cursor-only lenses/marker-lens lenses/show-all
  // ---------------------------------------------------------------- lenses
  const wordOf = (project, id) => {
    const w = project.worst.get(id);
    return w ? w.status : 'in sync';
  };

  function regionsFor(project, ids) {
    const seen = new Set();
    const res = [];
    for (const id of ids) {
      const it = project.itemsById.get(id);
      for (const i of (it && it.regions) || []) {
        if (!seen.has(i)) { seen.add(i); res.push(project.index.regions[i]); }
      }
    }
    return res;
  }

  function locOf(project, id) {
    const it = project.itemsById.get(id);
    return it ? { path: it.path, line: it.line, col: it.col || 0 } : null;
  }

  /** The 1-based line of the cursor in an editor showing doc, or null when none shows it. */
  function cursorLine(doc) {
    const ed = vscode.window.activeTextEditor && vscode.window.activeTextEditor.document === doc
      ? vscode.window.activeTextEditor : vscode.window.visibleTextEditors.find((e) => e.document === doc);
    return ed ? ed.selection.active.line + 1 : null;
  }
  /** The smallest block that contains a line: [first, last] pairs with their payload. */
  const innermost = (blocks, line) => blocks.filter(([a, b]) => line >= a && line <= b)
    .sort((x, y) => (x[1] - x[0]) - (y[1] - y[0]))[0];
  function cursorBlock(project, doc) {
    const line = cursorLine(doc);
    if (line === null || !project.index) return null;
    if (isSpecDoc(project, doc.uri.fsPath)) {
      const k = norm(doc.uri.fsPath);
      const items = project.index.items.filter((it) => norm(it.path) === k)
        .map((it) => [it.line, it.kind === 'part' ? it.line : (it.endLine || it.line), it]);
      const hit = innermost(items, line);
      return hit ? { item: hit[2] } : null;
    }
    // in code, every region around the cursor counts: a function's anchor and the block marking it
    const regions = regionsOfFile(project, doc.uri.fsPath).filter((r) => r.ids.length && line >= r.start && line <= r.end);
    return regions.length ? { regions } : null;
  }
  const lensBlockOf = new Map();   // file key -> the block whose lenses are shown
  function lensCursorMoved(editor) {
    const doc = editor.document;
    const project = docProject(doc);
    if (!project) return;
    const b = cursorBlock(project, doc);
    const key = b ? (b.item ? 'i:' + b.item.id : 'r:' + b.regions.map((r) => r.start).join(',')) : '';
    if (lensBlockOf.get(norm(doc.uri.fsPath)) !== key) { lensBlockOf.set(norm(doc.uri.fsPath), key); lensEmitter.fire(); }
  }
  // @clause end

  // @clause lenses lenses/clause-lens lenses/flags lenses/marker-lens lenses/show-all lenses/line-marker lenses/folded
  const lensProvider = {
    onDidChangeCodeLenses: lensEmitter.event,
    async provideCodeLenses(doc) {
      const project = docProject(doc);
      if (!project || !project.index) return [];
      const lenses = [];
      const at = (line) => new vscode.Range(line, 0, line, 0);
      const block = cursorBlock(project, doc);   // only the block with the cursor gets lenses
      if (!block) return [];
      if (isSpecDoc(project, doc.uri.fsPath)) {
        const k = norm(doc.uri.fsPath);
        for (const it of project.index.items) {
          if (norm(it.path) !== k || it !== block.item) continue;
          const regs = it.regions.map((i) => project.index.regions[i]);
          if (!regs.length && it.kind !== 'part') continue;
          let title = codeTitle(regs);
          const w = project.worst.get(it.id);
          if (w) title += ' ' + FLAG[w.cls];
          lenses.push(new vscode.CodeLens(at(Math.max(0, it.line - 1)), { title, command: 'sor.showCode', arguments: [regs] }));
        }
        return lenses;
      }
      const plan = await getPlan(doc);
      for (const r of regionsOfFile(project, doc.uri.fsPath)) {
        if (!r.ids.length || !block.regions || !block.regions.includes(r)) continue;
        let line = r.start - 1;
        if (r.kind !== 'line' && plan) {
          const f = plan.fold.find((x) => line > x.start && line <= x.end);
          if (f) line = Math.min(f.end + 1, doc.lineCount - 1);
        }
        for (const id of r.ids) {
          lenses.push(new vscode.CodeLens(at(line), {
            title: `${id} · ${wordOf(project, id)}`, command: 'sor.openClause', arguments: [locOf(project, id)],
          }));
        }
        if (r.ids.length > 1) {
          lenses.push(new vscode.CodeLens(at(line), { title: 'Show all code', command: 'sor.showCode', arguments: [regionsFor(project, r.ids)] }));
        }
      }
      return lenses;
    },
  };
  // @clause end

  // @clause lenses lenses/jump
  async function openAt(file, line, col) {
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(file));
    const ed = await vscode.window.showTextDocument(doc);
    const pos = new vscode.Position(Math.max(0, line), col || 0);
    ed.selection = new vscode.Selection(pos, pos);
    ed.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
    return ed;
  }

  async function showCode(regions) {
    if (!Array.isArray(regions) || !regions.length) return;
    let r = regions[0];
    if (regions.length > 1) {
      const several = targetsOf(regions);   // name the target of each region only when they are in more than one
      const pick = await vscode.window.showQuickPick(regions.map((x) => pickOf(x, several)), { placeHolder: 'Which code region?' });
      if (!pick) return;
      r = pick.region;
    }
    await openAt(r.path, r.start - 1, 0);
  }
  // @clause end

  // @clause state references/unresolved state/blame
  // ---------------------------------------------------------------- hover
  const hoverProvider = {
    async provideHover(doc, pos) {
      const project = docProject(doc);
      if (!project || !project.index) return null;
      if (isSpecDoc(project, doc.uri.fsPath)) {
        const ref = refAt(project, doc, pos);
        if (ref && !ref.to) return new vscode.Hover(new vscode.MarkdownString(`\`{${ref.text}}\` names no item or value`));
        return null;
      }
      const line = pos.line + 1;
      const regs = regionsOfFile(project, doc.uri.fsPath).filter((r) => r.ids.length && r.kind !== 'glue' && line >= r.start && line <= r.end);
      if (!regs.length) return null;
      let res;
      try {
        const rel = path.relative(project.root, doc.uri.fsPath).split(path.sep).join('/');
        res = await runSor(project, ['markers', '--json', `${rel}:${line}`]);
      } catch (e) {
        out.appendLine('hover failed: ' + e.message);
        return null;
      }
      const seen = new Set();
      const md = new vscode.MarkdownString();
      md.isTrusted = true;
      for (const r of res.regions || []) {
        for (const f of r.clauses || []) {
          if (seen.has(f.id)) continue;
          seen.add(f.id);
          const w = project.worst.get(f.id);
          const loc = f.where ? { path: f.where.path, line: f.where.line, col: f.where.col || 0 } : locOf(project, f.id);
          const link = loc ? `[${f.id}](command:sor.openClause?${encodeURIComponent(JSON.stringify([loc]))})` : f.id;
          const by = w && w.finding && w.finding.by ? ` · ${w.finding.by}` : '';
          md.appendMarkdown(`**${link}** · ${w ? WORD[w.cls] : 'in sync'}${by}\n\n`);
          const text = String(f.text || '').split(/\r?\n/).slice(0, 6).join('\n');
          md.appendCodeblock(text, 'markdown');
        }
      }
      return seen.size ? new vscode.Hover(md) : null;
    },
  };
  // @clause end

  // @clause references
  // ---------------------------------------------------------------- references
  function refAt(project, doc, pos) {
    if (!project.index) return null;
    const k = norm(doc.uri.fsPath);
    return project.index.refs.find((r) => norm(r.path) === k && r.line === pos.line + 1
      && pos.character >= r.col - 1 && pos.character <= r.end) || null;
  }

  const definitionProvider = {
    provideDefinition(doc, pos) {
      const project = docProject(doc);
      if (!project || !isSpecDoc(project, doc.uri.fsPath)) return undefined;
      const ref = refAt(project, doc, pos);
      if (!ref || !ref.to) return undefined;
      return new vscode.Location(vscode.Uri.file(ref.to.path), new vscode.Position(Math.max(0, ref.to.line - 1), ref.to.col || 0));
    },
  };
  // @clause end

  // @clause preview preview/zero-size preview/code-box preview/cursor-place preview/code-open preview/toggle preview/marks-hidden preview/values preview/code-lines preview/tables
  /** Live preview of spec files: formatting marks hidden, their text styled. Bold marks never come
   *  back (like Slack); the marks of code, values, references and headings come back only while a
   *  selection is inside that element (like Obsidian). Like the colors it reads only the text. */
  const previewOn = () => vscode.workspace.getConfiguration('sor').get('livePreview') !== false;
  state.preview = new Map();   // file key -> { hide, bold, code, heading, link, faint: [[line, from, to]] } (0-based)
  const deco = (o) => vscode.window.createTextEditorDecorationType(o);
  const pv = {
    // shrunk to nothing, not taken out of the line (`display: none`): the editor then still measures every character, and a
    // selection after hidden marks keeps its place; taken out, a selected word is drawn nowhere (preview/zero-size)
    hide: deco({ textDecoration: 'none; font-size: 0;' }),
    bold: deco({ fontWeight: 'bold' }),
    // inline code in a small framed box, as Slack draws it
    // The box is CSS on the text itself (through textDecoration, as for `hide`), not backgroundColor/border: those
    // are painted in a layer of their own at the columns the text had before the backticks were hidden, which put
    // the box one character to the right of its text. The tint comes from the editor's text color, so it shows on any
    // theme (the theme's own code background is nearly transparent). light/dark variants do not take this CSS.
    code: deco({
      color: new vscode.ThemeColor('textPreformat.foreground'),
      textDecoration: 'none; background-color: color-mix(in srgb, var(--vscode-editor-foreground) 14%, transparent);'
        + ' border: 1px solid color-mix(in srgb, var(--vscode-editor-foreground) 26%, transparent); border-radius: 4px;',
    }),
    // An empty pair of ticks with the cursor between: each tick is shrunk to nothing, like every hidden mark, and drawn as one half of a
    // small box (a fixed-size block, because text of no size gives a box neither width nor height). The cursor sits between the
    // two ticks, so it sits in the middle of the box (preview/code-open).
    pairL: deco({ textDecoration: 'none; font-size: 0; display: inline-block; box-sizing: border-box; width: 6px; vertical-align: text-bottom;'
      + ' height: calc(var(--vscode-editor-font-size, 14px) * 1.15); background-color: color-mix(in srgb, var(--vscode-editor-foreground) 14%, transparent);'
      + ' border: 1px solid color-mix(in srgb, var(--vscode-editor-foreground) 26%, transparent); border-right: 0; border-radius: 4px 0 0 4px;' }),
    pairR: deco({ textDecoration: 'none; font-size: 0; display: inline-block; box-sizing: border-box; width: 6px; vertical-align: text-bottom;'
      + ' height: calc(var(--vscode-editor-font-size, 14px) * 1.15); background-color: color-mix(in srgb, var(--vscode-editor-foreground) 14%, transparent);'
      + ' border: 1px solid color-mix(in srgb, var(--vscode-editor-foreground) 26%, transparent); border-left: 0; border-radius: 0 4px 4px 0;' }),
    block: deco({ isWholeLine: true, light: { backgroundColor: 'rgba(0, 0, 0, 0.05)' }, dark: { backgroundColor: 'rgba(255, 255, 255, 0.08)' } }),
    heading: deco({ fontWeight: 'bold', textDecoration: 'none; font-size: 1.15em;' }),
    link: deco({ color: new vscode.ThemeColor('textLink.foreground') }),
    faint: deco({ opacity: '0.45' }),
    // text the editor cannot count as characters: it then measures the line, hidden marks and all
    anchor: deco({ after: { contentText: '\u200b' } }),
  };
  // @clause end

  // @clause preview preview/reveal preview/element-reveal preview/code-box preview/cursor-place preview/code-closes preview/code-open preview/toggle preview/marks-hidden preview/values preview/code-lines preview/tables
  function previewRanges(doc) {
    const out = Object.fromEntries(Object.keys(pv).map((k) => [k, []]));
    let fence = false;   // inside a ``` block: shaded as one block, its text left as written
    const sel = [];
    for (const ed of vscode.window.visibleTextEditors) if (ed.document === doc) sel.push(...ed.selections);
    // a selection is inside an element when it touches it, edges included
    const inside = (l, a, b) => sel.some((x) => !(x.end.line < l || (x.end.line === l && x.end.character < a)
      || x.start.line > l || (x.start.line === l && x.start.character > b)));
    // ...but inline code opens only for a cursor or selection strictly inside it: right after the closing tick it is closed (preview/code-closes)
    const within = (l, a, b) => sel.some((x) => {
      if (x.start.line > l || x.end.line < l) return false;
      const s = x.start.line < l ? 0 : x.start.character, e = x.end.line > l ? Infinity : x.end.character;
      return e > a && s < b;
    });
    for (let l = 0; l < doc.lineCount; l++) {
      const t = doc.lineAt(l).text;
      if (/^\s*```/.test(t) || fence) {
        out.block.push([l, 0, Math.max(1, t.length)]);
        if (/^\s*```/.test(t)) { out.faint.push([l, 0, t.length]); fence = !fence; }
        continue;
      }
      const add = (k, a, b) => { if (b > a) out[k].push([l, a, b]); };
      const h = /^(#{1,6}\s+)(.*\S)\s*$/.exec(t);
      if (h) { if (!inside(l, 0, t.length)) add('hide', 0, h[1].length); add('heading', h[1].length, t.length); continue; }
      if (/^\s*\|[\s:|-]+\|\s*$/.test(t)) { add('faint', 0, t.length); continue; }
      const c = /^(\s+)(code:)(\s*)(\S+)\s*$/.exec(t);
      if (c) {
        add('faint', c[1].length, c[1].length + 5);
        add('link', c[1].length + 5 + c[3].length, c[1].length + 5 + c[3].length + c[4].length);
        continue;
      }
      const taken = [];   // inline code first: braces inside backticks are plain text
      const free = (a, b) => !taken.some(([x, y]) => a < y && b > x);
      for (const m of t.matchAll(/`([^`\n]*)`/g)) {
        const a = m.index, b = m.index + m[0].length;
        if (b - a > 2) { add('hide', a, a + 1); add('code', a + 1, b - 1); add('hide', b - 1, b); }   // the ticks are hidden wherever the cursor is (preview/code-closes)
        else if (within(l, a, b)) { add('pairL', a, a + 1); add('pairR', a + 1, b); }   // an empty pair with the cursor between: a small box, the ticks invisible (preview/code-open)
        taken.push([a, b]);   // an empty pair stays as typed once the cursor leaves
      }
      // a backtick still waiting for its partner: the rest of the line is already code while you type (like Slack)
      const lone = [...t.matchAll(/`/g)].map((m) => m.index).filter((i) => free(i, i + 1)).pop();
      if (lone !== undefined && lone + 1 < t.length) { add('code', lone + 1, t.length); taken.push([lone, t.length]); }
      for (const m of t.matchAll(/\*\*([^*\n]+?)\*\*/g)) {
        if (!free(m.index, m.index + m[0].length)) continue;
        add('hide', m.index, m.index + 2); add('bold', m.index + 2, m.index + m[0].length - 2);
        add('hide', m.index + m[0].length - 2, m.index + m[0].length);
      }
      for (const m of t.matchAll(/\{([A-Za-z][\w-]*:\s*)([^{}]+)\}/g)) {   // {name: value}
        if (!free(m.index, m.index + m[0].length)) continue;
        taken.push([m.index, m.index + m[0].length]);
        if (inside(l, m.index, m.index + m[0].length)) continue;   // the value being edited stays raw
        add('hide', m.index, m.index + 1); add('faint', m.index + 1, m.index + 1 + m[1].length);
        add('hide', m.index + m[0].length - 1, m.index + m[0].length);
      }
      for (const m of t.matchAll(/\{([^{}:\s][^{}:]*)\}/g)) {   // {reference}
        if (!free(m.index, m.index + m[0].length) || inside(l, m.index, m.index + m[0].length)) continue;
        add('hide', m.index, m.index + 1); add('link', m.index + 1, m.index + m[0].length - 1);
        add('hide', m.index + m[0].length - 1, m.index + m[0].length);
      }
      if (/^\s*\|/.test(t)) for (const m of t.matchAll(/\|/g)) add('faint', m.index, m.index + 1);
    }
    for (const l of new Set(out.hide.map((h) => h[0]))) out.anchor.push([l, doc.lineAt(l).text.length, doc.lineAt(l).text.length]);
    return out;
  }

  function applyPreview(editor) {
    const doc = editor.document;
    const project = docProject(doc);
    const on = previewOn() && project && isSpecDoc(project, doc.uri.fsPath);
    const r = on ? previewRanges(doc) : Object.fromEntries(Object.keys(pv).map((k) => [k, []]));
    if (on) state.preview.set(norm(doc.uri.fsPath), r); else state.preview.delete(norm(doc.uri.fsPath));
    for (const k of Object.keys(pv)) editor.setDecorations(pv[k], r[k].map(([l, a, b]) => new vscode.Range(l, a, l, b)));
  }
  const refreshPreview = () => { for (const ed of vscode.window.visibleTextEditors) applyPreview(ed); };
  // @clause end

  // @clause references/complete references/complete-words
  /** Typing `{` in a spec file offers the project's parts, items and rows, written by their full id. */
  const WORDS_MAX = 160;
  function wordsOf(project, doc, it, whys) {
    if (it.kind === 'part') return whys.get(it.id) || '';
    if (!it.line || !it.path || it.line < 1) return '';
    let lines;
    try {
      const own = norm(doc.uri.fsPath) === norm(it.path);   // paths are compared without case (targets/vscode/paths-case)
      lines = (own ? doc.getText() : fs.readFileSync(it.path, 'utf8')).split(/\r?\n/);
    } catch (e) { return ''; }
    const text = lines.slice(it.line - 1, (it.endLine || it.line)).join(' ')
      .replace(/^\s*(-|\|)\s*/, '').replace(/\*\*([^*]+)\*\*\s*(—|-)?\s*/, '').replace(/\s+/g, ' ').trim();
    return text.length > WORDS_MAX ? text.slice(0, WORDS_MAX - 1) + '…' : text;
  }

  const completionProvider = {
    async provideCompletionItems(doc, pos) {
      const project = docProject(doc);
      if (!project || !project.index || !isSpecDoc(project, doc.uri.fsPath)) return undefined;
      const before = doc.lineAt(pos.line).text.slice(0, pos.character);
      const open = before.lastIndexOf('{');
      if (open < 0 || before.indexOf('}', open) >= 0) return undefined;
      const typed = before.slice(open + 1);
      if (/[:\s]/.test(typed) || (before.slice(0, open).split('`').length - 1) % 2) return undefined;
      let whys = new Map();
      try {
        for (const p of await runSor(project, ['parts', '--json'])) whys.set(p.id, p.why || '');
      } catch (e) { /* the words of parts are left out */ }
      const after = doc.lineAt(pos.line).text[pos.character] === '}' ? 1 : 0;
      const range = new vscode.Range(pos.line, open + 1, pos.line, pos.character + after);
      return project.index.items
        .filter((it) => it.id !== 'ROOT' && it.id !== 'CLAUSES' && it.kind !== 'test')
        .map((it) => {
          const c = new vscode.CompletionItem(it.id, vscode.CompletionItemKind.Reference);
          const words = wordsOf(project, doc, it, whys);
          c.detail = it.kind === 'part' ? 'part' : `${it.kind}${it.section ? ' · ' + it.section : ''}`;
          c.documentation = words;
          c.filterText = it.id;
          c.insertText = it.id + '}';
          c.range = range;
          return c;
        });
    },
  };
  // @clause end

  // @clause references/code-jump
  /** Go to Definition on a `code: path#name` line jumps to the region the index made for it. */
  const codeJumpProvider = {
    provideDefinition(doc, pos) {
      const project = docProject(doc);
      if (!project || !project.index || !isSpecDoc(project, doc.uri.fsPath)) return undefined;
      const m = /^\s+code:\s*(\S+)\s*$/.exec(doc.lineAt(pos.line).text);
      if (!m) return undefined;
      const line = pos.line + 1;
      const item = project.index.items.find((it) => norm(it.path) === norm(doc.uri.fsPath)
        && line >= it.line && line <= (it.endLine || it.line));
      const r = project.index.regions.find((x) => x.kind === 'anchor' && x.target === m[1]
        && (!item || x.keys.includes(item.id)));
      if (!r) return undefined;
      return new vscode.Location(vscode.Uri.file(r.path), new vscode.Position(r.start - 1, 0));
    },
  };
  // @clause end

  // @clause glue
  // ---------------------------------------------------------------- wiring
  const sel = { scheme: 'file' };
  // A second copy of this extension (an older version still installed) already owns the command ids.
  // Registering them again throws, and the rest of this list, the live preview with it, would never be wired.
  const reg = (id, fn) => {
    try { return vscode.commands.registerCommand(id, fn); }
    catch (e) { out.appendLine(`command ${id} skipped: ${e.message}. Is another copy of this extension installed?`); return { dispose() {} }; }
  };
  context.subscriptions.push(
    out, status, lensEmitter, foldEmitter, refreshEmitter, hideType, ...Object.values(decoTypes),
    vscode.languages.registerCodeLensProvider(sel, lensProvider),
    vscode.languages.registerHoverProvider(sel, hoverProvider),
    vscode.languages.registerDefinitionProvider(sel, definitionProvider),
    vscode.languages.registerDefinitionProvider(sel, codeJumpProvider),
    vscode.languages.registerCompletionItemProvider(sel, completionProvider, '{'),
    vscode.languages.registerFoldingRangeProvider(sel, foldProvider),
    reg('sor.refresh', () => refresh()),
    reg('sor.showCode', (regions) => showCode(regions)),
    reg('sor.openClause', (loc) => (loc ? openAt(loc.path, loc.line - 1, loc.col) : undefined)),
    reg('sor.toggleMarkerLines', () => vscode.workspace.getConfiguration('sor')
      .update('hideMarkerLines', !hideOn(), vscode.ConfigurationTarget.Global)),
    vscode.workspace.onDidChangeConfiguration((e) => { if (e.affectsConfiguration('sor.hideMarkerLines')) onHideChanged(); }),
    vscode.workspace.onDidSaveTextDocument(scheduleRefresh),
    vscode.workspace.onDidChangeWorkspaceFolders(scheduleRefresh),
    vscode.workspace.onDidOpenTextDocument((d) => updateMarkerLines(d)),
    vscode.window.onDidChangeVisibleTextEditors((eds) => { for (const e of eds) { applyMarks(e); updateMarkerLines(e.document); } }),
    vscode.window.onDidChangeActiveTextEditor((ed) => {
      if (!ed) return;
      applyMarks(ed);
      updateMarkerLines(ed.document);
      if (hideOn()) getPlan(ed.document).then(() => scheduleApply(ed)).catch(() => {});
    }),
    vscode.window.onDidChangeTextEditorSelection((e) => {
      updateMarkerLines(e.textEditor.document);
      reconcile(e.textEditor).catch(() => {});
      applyPreview(e.textEditor);
      lensCursorMoved(e.textEditor);
    }),
    ...Object.values(pv),
    reg('sor.toggleLivePreview', () => vscode.workspace.getConfiguration('sor')
      .update('livePreview', !previewOn(), vscode.ConfigurationTarget.Global)),
    vscode.workspace.onDidChangeConfiguration((e) => { if (e.affectsConfiguration('sor.livePreview')) refreshPreview(); }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      for (const ed of vscode.window.visibleTextEditors) if (ed.document === e.document) applyPreview(ed);
    }),
    vscode.window.onDidChangeVisibleTextEditors(() => refreshPreview()),
    refreshEmitter.event(() => refreshPreview()),
  );
  // @clause end
  // @clause project/refresh
  const watcher = vscode.workspace.createFileSystemWatcher('**/*');
  const onFile = (uri) => { if (!/__pycache__/.test(uri.fsPath)) scheduleRefresh(); };
  watcher.onDidCreate(onFile);
  watcher.onDidChange(onFile);
  watcher.onDidDelete(onFile);
  context.subscriptions.push(watcher);
  // @clause end

  // @clause highlight/counterpart highlight/all-ids highlight/only-visible highlight/marker-lines highlight/clears highlight/theme highlight/from-lens highlight/test-view
  // ---------------------------------------------------------------- highlight: the counterpart of the cursor's block
  // Theme colours only, none fixed, and a mark on the scrollbar for a counterpart that is out of view (highlight/theme).
  const litType = vscode.window.createTextEditorDecorationType({
    isWholeLine: true,
    backgroundColor: new vscode.ThemeColor('editor.selectionHighlightBackground'),
    overviewRulerColor: new vscode.ThemeColor('editorOverviewRuler.selectionHighlightForeground'),
    overviewRulerLane: vscode.OverviewRulerLane.Center,
  });
  state.counterpart = new Map();   // file key -> [first, last] pairs (1-based) lit there now; VS Code cannot read a decoration back

  /** The lines the block under the cursor lights up in other files: [{ path, first, last }], 1-based. It asks the lens's own question. */
  function counterpartOf(project, doc) {
    const block = cursorBlock(project, doc);
    if (!block) return [];
    const lit = [];
    if (block.item) {
      for (const r of regionsFor(project, [block.item.id])) {
        if (!r.ids.length) continue;
        // a region that has marker lines (code, test) is painted between them, not on them (highlight/marker-lines)
        const marked = r.kind === 'code' || r.kind === 'test';
        const first = marked ? r.start + 1 : r.start, last = marked ? r.end - 1 : r.end;
        if (last >= first) lit.push({ path: r.path, first, last });
      }
    } else {
      for (const r of block.regions) {   // every clause the region is marked for (highlight/all-ids)
        for (const id of r.ids) {
          const it = project.itemsById.get(id);
          if (it) lit.push({ path: it.path, first: it.line, last: it.kind === 'part' ? it.line : (it.endLine || it.line) });
        }
      }
    }
    return lit;
  }

  const litSeen = new WeakMap();   // editor -> the lines drawn in it last time, so the same block is not drawn twice
  // The editor whose cursor moved last leads (an editor that was made active counts as a cursor that moved). A window without
  // focus does not switch `activeTextEditor`, but the cursor event still names the editor the person is in.
  let leading = null;
  const leader = () => (leading && vscode.window.visibleTextEditors.includes(leading) ? leading : vscode.window.activeTextEditor);
  function updateCounterpart() {
    const active = leader();
    const doc = active && active.document;
    let lit = [];
    // unsaved changes on either side: the index lines are off, so nothing is lit (highlight/clears)
    if (doc && doc.uri.scheme === 'file' && !doc.isDirty) {
      const project = docProject(doc);
      if (project && project.index) lit = counterpartOf(project, doc);
    }
    for (const ed of vscode.window.visibleTextEditors) {   // only editors that already show the file (highlight/only-visible)
      const d = ed.document;
      const key = norm(d.uri.fsPath);
      const pairs = d === doc || d.isDirty || d.uri.scheme !== 'file' ? []
        : lit.filter((l) => norm(l.path) === key && l.first <= d.lineCount).map((l) => [l.first, Math.min(l.last, d.lineCount)]);
      const sig = JSON.stringify(pairs);
      if (litSeen.get(ed) === sig) continue;
      litSeen.set(ed, sig);
      ed.setDecorations(litType, pairs.map(([a, b]) => new vscode.Range(a - 1, 0, b - 1, 0)));
    }
    // what tests read is what was drawn, not what was meant to be drawn
    state.counterpart.clear();
    for (const ed of vscode.window.visibleTextEditors) {
      const drawn = JSON.parse(litSeen.get(ed) || '[]');
      if (drawn.length) state.counterpart.set(norm(ed.document.uri.fsPath), drawn);
    }
  }
  context.subscriptions.push(
    litType,
    vscode.window.onDidChangeTextEditorSelection((e) => { leading = e.textEditor; updateCounterpart(); }),
    vscode.window.onDidChangeActiveTextEditor((ed) => { if (ed) leading = ed; updateCounterpart(); }),
    vscode.window.onDidChangeVisibleTextEditors(() => updateCounterpart()),
    vscode.workspace.onDidChangeTextDocument((e) => { if (e.document.uri.scheme === 'file') updateCounterpart(); }),
    refreshEmitter.event(() => updateCounterpart()),
  );
  // @clause end

  // @clause targets/vscode/api
  const ready = refresh();
  const api = { state, refresh, onDidRefresh: refreshEmitter.event };
  return ready.then(() => api, () => api);
  // @clause end
// @clause glue
}

function deactivate() {}

module.exports = { activate, deactivate };
// @clause end
