const vscode = require('vscode');
const assert = require('assert');
const path = require('path');
const fs = require('fs');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Waits for a state instead of a fixed time: on a busy machine the editor and the extension take longer than any sleep chosen for an idle one.
const until = async (fn, ms = 8000) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(150); } return !!(await fn()); };
const ok = (name) => console.log('  ok  ' + name);

exports.run = async function run() {
  const ext = vscode.extensions.getExtension('sebastianrath.sor-vscode');
  const api = await ext.activate();
  const project = api.state.projects[0];
  assert(project, 'a project is found');
  const file = (...p) => vscode.Uri.file(path.join(project.root, ...p));
  // lenses show only for the block with the cursor: put it there first
  const lensesAt = async (doc, line) => {
    const e = await vscode.window.showTextDocument(doc, { preview: false });
    e.selection = new vscode.Selection(line, 0, line, 0);
    await sleep(250);
    return vscode.commands.executeCommand('vscode.executeCodeLensProvider', doc.uri);
  };

  // 1. CodeLens on a clause
  const bodies = await vscode.workspace.openTextDocument(file('sor', 'bodies.md'));
  assert.strictEqual(bodies.languageId, 'sor-markdown', 'sor/*.md gets the sor-markdown language (syntax colours)');
  const bLine = (re) => [...Array(bodies.lineCount).keys()].find((n) => re.test(bodies.lineAt(n).text));
  const lenses = await lensesAt(bodies, bLine(/\*\*sun\*\*/));
  const sun = lenses.find((l) => bodies.lineAt(l.range.start.line).text.includes('**sun**'));
  assert(sun, 'lens on **sun**');
  assert(/out\/index\.html:\d+-\d+/.test(sun.command.title), sun.command.title);
  assert(lenses.every((l) => l.range.start.line === sun.range.start.line), 'only the sun item has lenses: ' + lenses.length);
  const marsLenses = await lensesAt(bodies, bLine(/^\s*\| Mars\b/));
  const mars = marsLenses.find((l) => /^\s*\| Mars\b/.test(bodies.lineAt(l.range.start.line).text));
  assert(mars && /out\/index\.html:\d+/.test(mars.command.title), 'lens on the Mars row');
  assert(!marsLenses.some((l) => bodies.lineAt(l.range.start.line).text.includes('**sun**')), 'the sun lens is gone once the cursor left it');
  ok('lenses only in the cursor block: sun, then Mars');
  await vscode.commands.executeCommand(sun.command.command, ...sun.command.arguments);
  const ed = vscode.window.activeTextEditor;
  assert(ed.document.fileName.endsWith('index.html') && ed.selection.start.line + 1 === sun.command.arguments[0][0].start, 'jumped to the sun region');
  ok('codelens: ' + sun.command.title);

  // 1b. CodeLens on @clause marker lines in code
  const code = await vscode.workspace.openTextDocument(file('out', 'index.html'));
  const lineOf = (re) => code.getText().split(/\r?\n/).findIndex((l) => re.test(l));
  const cl = await lensesAt(code, lineOf(/@clause bodies\/sun( |$)/) + 1);
  const at = (n) => cl.filter((l) => l.range.start.line === n).map((l) => l.command.title);
  const sunMarker = lineOf(/@clause bodies\/sun( |$)/);
  const sunPlan = api.state.folds.get(path.normalize(code.uri.fsPath).toLowerCase());
  const sunFolded = sunPlan && sunPlan.fold.some((f) => f.end === sunMarker);
  const sunLens = at(sunFolded ? sunMarker + 1 : sunMarker);
  assert(sunLens.some((t) => t.includes('bodies/sun · ')), JSON.stringify(sunLens));
  assert(!at(lineOf(/@clause end/)).length, '@clause end has no lens');
  const glueLenses = await lensesAt(code, lineOf(/@clause glue/) + 1);
  const glueLens = glueLenses.filter((l) => l.command && l.command.title === 'glue');
  assert(glueLens.length === 1 && !glueLens[0].command.command, 'a glue region has one plain "glue" lens: ' + JSON.stringify(glueLenses.map((l) => l.command)));
  const marsMarker = lineOf(/bodies\/planets\/Mars/);
  const marsLens = (await lensesAt(code, marsMarker)).filter((l) => l.range.start.line === marsMarker).map((l) => l.command.title);
  assert(marsLens.some((t) => t.includes('bodies/planets/Mars')), 'line marker lens: ' + marsLens);
  const multiLine = lineOf(/\/\/ @clause [\w\/-]+ [\w\/-]+/);
  const multiLenses = await lensesAt(code, multiLine + 1);
  await sleep(2700);   // the fold timers run for 2.5 s after a file is shown: the cursor must stay put
  assert(vscode.window.activeTextEditor.selection.active.line === multiLine + 1, 'the cursor stays where it was put (bug: it jumped back)');
  ok('cursor kept while folds are applied');
  const multi = multiLenses.find((l) => l.command.title.includes('Show all code'));
  assert(multi, 'a "Show all code" lens on a multi-id region: ' + JSON.stringify(multiLenses.map((l) => l.command.title)));
  const jump = cl.find((l) => l.command.title.includes('bodies/sun · '));
  await vscode.commands.executeCommand(jump.command.command, ...jump.command.arguments);
  const here = vscode.window.activeTextEditor;
  assert(here.document.fileName.endsWith('bodies.md') && here.document.lineAt(here.selection.start.line).text.includes('**sun**'), 'jumped to **sun**');
  ok('marker lenses: ' + sunLens.join(' / ') + ' | ' + marsLens.join(', ') + ' | ' + multi.command.title);

  // 1c. marker lines: hidden by default, shown under the cursor, toggled by the command
  const cfg = vscode.workspace.getConfiguration('sor');
  assert(cfg.inspect('hideMarkerLines').defaultValue === true, 'sor.hideMarkerLines defaults to true');
  const codeEd = await vscode.window.showTextDocument(code);
  const key = path.normalize(code.uri.fsPath).toLowerCase();
  const markerLines = code.getText().split(/\r?\n/).map((t, i) => [t, i + 1])
    .filter(([t]) => /^\s*(\/\/|<!--)\s*@clause\b/.test(t)).map(([, i]) => i);
  const setHide = async (v) => {
    await cfg.update('hideMarkerLines', v, vscode.ConfigurationTarget.Global);
    await vscode.commands.executeCommand('sor.refresh');
    await sleep(300);
    return api.state.markerLines.get(key);
  };
  const outsideSelection = (l) => l - 1 < codeEd.selection.start.line || l - 1 > codeEd.selection.end.line;
  let m = await setHide(true);
  assert.deepStrictEqual(m.lines, markerLines.filter(outsideSelection), 'hidden: exactly the marker lines');
  assert(m.lines.every((l) => /@clause/.test(code.lineAt(l - 1).text)), 'only marker lines');
  codeEd.selection = new vscode.Selection(markerLines[1] - 1, 3, markerLines[1] - 1, 3);
  await sleep(300);
  m = api.state.markerLines.get(key);
  assert(!m.lines.includes(markerLines[1]), 'the line under the cursor is shown');
  assert(m.lines.length === markerLines.length - 1, 'other marker lines still hidden');
  await vscode.commands.executeCommand('sor.toggleMarkerLines');   // true -> false
  await until(() => (api.state.markerLines.get(key) || { lines: [0] }).lines.length === 0);
  m = api.state.markerLines.get(key);
  assert(vscode.workspace.getConfiguration('sor').get('hideMarkerLines') === false && m.lines.length === 0, 'toggle shows them');
  ok(`marker lines: ${markerLines.length} marker lines; hidden/cursor/toggle`);

  // 1d. folding: the marker lines leave the view, so the line numbers skip
  await vscode.commands.executeCommand('sor.refresh');
  await setHide(true);
  await vscode.window.showTextDocument(code);
  await sleep(1500);   // the fold is applied once VS Code has our ranges
  const plan = api.state.folds.get(key);
  assert(plan && plan.fold.length > 10, 'a fold plan with many ranges');
  const provided = await vscode.commands.executeCommand('vscode.executeFoldingRangeProvider', code.uri);
  for (const f of plan.fold) {
    assert(provided.some((p) => p.start === f.start && p.end === f.end), `provider gives ${f.start}-${f.end}`);
  }
  const visibleSet = () => new Set(codeEd2().visibleRanges.flatMap((r) => Array.from({ length: r.end.line - r.start.line + 1 }, (_, i) => r.start.line + i)));
  const codeEd2 = () => vscode.window.activeTextEditor;
  const reveal = async (line) => { codeEd2().revealRange(new vscode.Range(line, 0, line + 5, 0), vscode.TextEditorRevealType.AtTop); await sleep(500); };
  codeEd2().selection = new vscode.Selection(0, 0, 0, 0);
  const viewLine = lineOf(/@clause bodies\/sun( |$)/) - 2;   // where the example has several regions
  await reveal(viewLine);
  let vis = visibleSet();
  const inView = plan.fold.filter((f) => vis.has(f.start) || vis.has(f.end));
  assert(inView.length >= 3, 'folds in the viewport: ' + inView.length);
  for (const f of inView) {
    const hint = vscode.window.state.focused ? '' : ' (the test window has no focus: a locked screen, or another app in front. Folding cannot be checked without a focused window)';
    assert(vis.has(f.start) && !vis.has(f.end), `marker line ${f.end + 1} is folded away, line ${f.start + 1} stays${hint}`);
  }
  const hiddenInView = inView.reduce((n, f) => n + (f.end - f.start), 0);
  ok(`folded: ${plan.fold.length} folds, ${plan.skipped.length} marker lines not foldable (${plan.skipped.map((l) => l + 1).join(',')}); ${hiddenInView} lines gone from the viewport`);
  // those that could not fold keep the blank-row hiding
  const deco = api.state.markerLines.get(key).lines;
  assert(plan.skipped.every((l) => deco.includes(l + 1) || l === 0), 'skipped marker lines are still hidden by decoration');
  // the lens of a folded marker sits on the first line after it, and is in view
  const sunFold = plan.fold.find((f) => f.end === lineOf(/@clause bodies\/sun( |$)/));
  codeEd2().selection = new vscode.Selection(sunFold.end + 1, 0, sunFold.end + 1, 0);
  await sleep(300);
  const lens2 = await vscode.commands.executeCommand('vscode.executeCodeLensProvider', code.uri);
  const sunLens2 = lens2.find((l) => l.command.title.includes('bodies/sun · '));
  assert(sunFold && sunLens2.range.start.line === sunFold.end + 1, 'lens moved below the folded marker');
  assert(vis.has(sunLens2.range.start.line) || !vis.has(sunFold.end), 'the lens line is visible');
  // a user fold is left alone by hiding / showing
  const own = provided.find((p) => p.kind === undefined && p.start >= viewLine && p.end <= viewLine + 100 && p.end - p.start >= 3
    && !plan.fold.some((f) => f.start === p.start));
  await vscode.commands.executeCommand('editor.fold', { levels: 1, direction: 'down', selectionLines: [own.start] });
  await sleep(300);
  // the cursor on the line above a folded marker opens it
  codeEd2().selection = new vscode.Selection(sunFold.start, 0, sunFold.start, 0);
  await reveal(viewLine); await sleep(500);
  vis = visibleSet();
  assert(vis.has(sunFold.end), 'cursor touching a fold shows its marker line');
  codeEd2().selection = new vscode.Selection(0, 0, 0, 0);
  await sleep(700);
  vis = visibleSet();
  assert(!vis.has(sunFold.end), 'it folds again when the cursor leaves');
  await cfg.update('hideMarkerLines', false, vscode.ConfigurationTarget.Global);
  await until(async () => { await reveal(viewLine); vis = visibleSet(); return inView.every((f) => vis.has(f.end)); });
  vis = visibleSet();
  assert(inView.every((f) => vis.has(f.end)), 'with hiding off every marker line is back');
  await cfg.update('hideMarkerLines', true, vscode.ConfigurationTarget.Global);
  await until(async () => { await reveal(viewLine); vis = visibleSet(); return inView.every((f) => !vis.has(f.end)) && !vis.has(own.start + 1) && vis.has(own.start); });
  vis = visibleSet();
  assert(inView.every((f) => !vis.has(f.end)) && !vis.has(own.start + 1) && vis.has(own.start), 'folded again; the user\'s own fold stayed closed');
  ok('fold: cursor opens it, toggle off/on, own fold untouched, lens below the marker');
  await cfg.update('hideMarkerLines', undefined, vscode.ConfigurationTarget.Global);

  // 2. hover on a code line
  const html = await vscode.workspace.openTextDocument(file('out', 'index.html'));
  const marsLine = html.getText().split('\n').findIndex((l) => l.includes('bodies/planets/Mars'));
  const hovers = await vscode.commands.executeCommand('vscode.executeHoverProvider', html.uri, new vscode.Position(marsLine, 4));
  const text = hovers.flatMap((h) => h.contents.map((c) => c.value)).join('\n');
  assert(text.includes('bodies/planets/Mars') && text.includes('Mars'), text);
  ok('hover: ' + text.split('\n').slice(0, 3).join(' / ').slice(0, 120));
  const moonLine = html.getText().split('\n').findIndex((l) => l.includes('moon') && l.includes('size'));
  const h2 = await vscode.commands.executeCommand('vscode.executeHoverProvider', html.uri, new vscode.Position(moonLine, 4));
  const t2 = h2.flatMap((h) => h.contents.map((c) => c.value)).join('\n');
  console.log('  hover on a changed line:\n' + t2.split('\n').map((l) => '      ' + l).join('\n'));

  // 3. gutter marks (what the decorations were given)
  await vscode.window.showTextDocument(html);
  await sleep(500);
  api.state.marks.get(path.normalize(html.uri.fsPath).toLowerCase());
  await vscode.commands.executeCommand('sor.refresh');
  await vscode.window.showTextDocument(html);
  await sleep(300);
  const marks = api.state.marks.get(path.normalize(html.uri.fsPath).toLowerCase());
  console.log('  gutter marks in index.html: ' + JSON.stringify(marks));
  const expect = process.env.SOR_EXPECT_MARKS;
  if (expect) for (const g of expect.split(',')) assert(marks[g].length, 'marks for ' + g);
  if (process.env.SOR_EXPECT_REVIEW) {   // review marks sit on the clauses (they have no code here)
    const sceneDoc = await vscode.workspace.openTextDocument(file('sor', 'scene.md'));
    await vscode.window.showTextDocument(sceneDoc);
    await sleep(300);
    const m = api.state.marks.get(path.normalize(sceneDoc.uri.fsPath).toLowerCase());
    console.log('  gutter marks in scene.md: ' + JSON.stringify(m));
    assert(m.review.length, 'review mark on scene.md');
  }
  ok('gutter');

  // 4. {references}
  const refs = project.index.refs.filter((r) => r.to && r.path.endsWith('bodies.md'));
  const clausesMd = await vscode.workspace.openTextDocument(file('sor', 'SPECOFRECORD.md'));
  const r = project.index.refs.find((x) => x.target && x.path.endsWith('SPECOFRECORD.md'));
  const defs = await vscode.commands.executeCommand('vscode.executeDefinitionProvider', clausesMd.uri, new vscode.Position(r.line - 1, r.col + 1));
  assert(defs.length === 1, 'one definition');
  const loc = defs[0];
  const uri = loc.targetUri || loc.uri;
  assert(uri.fsPath.toLowerCase() === path.normalize(r.to.path).toLowerCase(), uri.fsPath);
  ok(`reference {${r.text}} -> ${path.basename(uri.fsPath)}:${(loc.targetRange || loc.range).start.line + 1}`);
  const withVal = project.index.refs.find((x) => x.target && x.target.includes('.'));
  if (withVal) {
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(withVal.path));
    const d = await vscode.commands.executeCommand('vscode.executeDefinitionProvider', doc.uri, new vscode.Position(withVal.line - 1, withVal.col + 1));
    assert(d.length === 1, 'value reference resolves');
    ok(`value reference {${withVal.text}} -> line ${(d[0].targetRange || d[0].range).start.line + 1}`);
  }
  void refs;

  // 5. code: lines jump to their code
  const bodiesDoc = await vscode.workspace.openTextDocument(file('sor', 'bodies.md'));
  const codeLineNo = [...Array(bodiesDoc.lineCount).keys()].find((n) => /^\s+code:\s*out\/index\.html#positions\s*$/.test(bodiesDoc.lineAt(n).text));
  assert(codeLineNo !== undefined, 'bodies.md has a code: out/index.html#positions line');
  const codeDefs = await vscode.commands.executeCommand('vscode.executeDefinitionProvider', bodiesDoc.uri, new vscode.Position(codeLineNo, 10));
  assert(codeDefs.length === 1, 'one place for the code: line, got ' + codeDefs.length);
  const codeUri = codeDefs[0].targetUri || codeDefs[0].uri;
  const codeTarget = await vscode.workspace.openTextDocument(codeUri);
  const codeLanded = codeTarget.lineAt((codeDefs[0].targetRange || codeDefs[0].range).start.line).text;
  assert(codeUri.fsPath.endsWith('index.html') && /function positions\b/.test(codeLanded), 'lands on positions: ' + codeLanded.trim());
  ok(`code: out/index.html#positions -> ${codeLanded.trim()}`);

  // 6. live preview of spec files
  const pvDoc = await vscode.workspace.openTextDocument(file('sor', 'bodies.md'));
  let pvEd = await vscode.window.showTextDocument(pvDoc);
  const pvKey = path.normalize(pvDoc.uri.fsPath).toLowerCase();
  const sunNo = [...Array(pvDoc.lineCount).keys()].find((n) => pvDoc.lineAt(n).text.includes('**sun**'));
  const sunText = pvDoc.lineAt(sunNo).text;
  const hasRange = (ranges, line, a, b) => ranges.some(([l, x, y]) => l === line && x === a && y === b);
  const moveTo = async (line) => { pvEd.selection = new vscode.Selection(line, 0, line, 0); await sleep(300); return api.state.preview.get(pvKey); };
  const before = pvDoc.getText();
  let pvState = await moveTo(0);
  const sunAt = sunText.indexOf('**sun**');
  assert(pvState && hasRange(pvState.hide, sunNo, sunAt, sunAt + 2) && hasRange(pvState.hide, sunNo, sunAt + 5, sunAt + 7) && hasRange(pvState.bold, sunNo, sunAt + 2, sunAt + 5),
    'the ** around sun are hidden and sun is bold');
  const valAt = sunText.indexOf('{size: 28}');
  assert(hasRange(pvState.hide, sunNo, valAt, valAt + 1) && hasRange(pvState.faint, sunNo, valAt + 1, valAt + 7) && hasRange(pvState.hide, sunNo, valAt + 9, valAt + 10),
    '{size: 28}: braces hidden, name faint');
  const tick = [...Array(pvDoc.lineCount).keys()].find((n) => /`[^`]+`/.test(pvDoc.lineAt(n).text));
  if (tick !== undefined) {
    const tickAt = pvDoc.lineAt(tick).text.indexOf('`');
    assert(hasRange(pvState.hide, tick, tickAt, tickAt + 1) && pvState.code.some(([l, x]) => l === tick && x === tickAt + 1), 'backticks hidden, inline code styled');
  }
  // the ticks of inline code hide as soon as the code is closed (preview/code-closes)
  const scratch = path.join(project.root, 'sor', 'scratch-ticks.md');
  fs.writeFileSync(scratch, '# Scratch\nWhy: s.\n\n## Rules\nabc `test` ok\na `` b\nx `hello(test)` y\n');
  await sleep(800);
  const sd = await vscode.workspace.openTextDocument(scratch);
  const sed = await vscode.window.showTextDocument(sd);
  const skey = path.normalize(sd.uri.fsPath).toLowerCase();
  const ln = sd.lineAt(4).text, ta = ln.indexOf('`'), tb = ln.lastIndexOf('`');
  sed.selection = new vscode.Selection(4, tb + 1, 4, tb + 1);   // right after the closing tick
  await sleep(400);
  let ts = api.state.preview.get(skey);
  assert(hasRange(ts.hide, 4, ta, ta + 1) && hasRange(ts.hide, 4, tb, tb + 1), 'with the cursor right after the closing tick both ticks are hidden');
  sed.selection = new vscode.Selection(4, ta + 2, 4, ta + 2);   // between the ticks
  await sleep(400);
  ts = api.state.preview.get(skey);
  assert(hasRange(ts.hide, 4, ta, ta + 1) && hasRange(ts.hide, 4, tb, tb + 1), 'with the cursor inside the code the ticks stay hidden');
  assert(hasRange(ts.code, 4, ta + 1, tb), 'the box frames the word');
  // one box for `hello(test)`: the top and bottom lines run along all of it, the left and right lines are on its ends only (preview/code-box)
  const hl = sd.lineAt(6).text, ha = hl.indexOf('`'), hb = hl.lastIndexOf('`');
  assert(hasRange(ts.code, 6, ha + 1, hb) && hasRange(ts.codeL, 6, ha + 1, ha + 2) && hasRange(ts.codeR, 6, hb - 1, hb)
    && ts.codeL.filter(([l]) => l === 6).length === 1 && ts.codeR.filter(([l]) => l === 6).length === 1, 'hello(test) is one box, not one per piece');
  // what VS Code leaves after typing one tick: a pair with the cursor between (preview/code-open)
  const pl = sd.lineAt(5).text, pa = pl.indexOf('`');
  sed.selection = new vscode.Selection(5, pa + 1, 5, pa + 1);
  await sleep(400);
  ts = api.state.preview.get(skey);
  assert(hasRange(ts.pairL, 5, pa, pa + 1) && hasRange(ts.pairR, 5, pa + 1, pa + 2) && !ts.hide.some(([l]) => l === 5), 'an empty pair with the cursor between is already a (small) box: one half each side of the cursor');
  sed.selection = new vscode.Selection(5, 0, 5, 0);
  await sleep(400);
  ts = api.state.preview.get(skey);
  assert(!ts.pairL.some(([l]) => l === 5) && !ts.pairR.some(([l]) => l === 5) && !ts.code.some(([l]) => l === 5) && !ts.hide.some(([l]) => l === 5), 'moving away leaves the empty pair as plain ticks');
  await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
  fs.unlinkSync(scratch);
  pvEd = await vscode.window.showTextDocument(pvDoc);
  pvState = await moveTo(sunNo);   // cursor at the start of the sun line: bold marks stay hidden (Slack)
  assert(hasRange(pvState.hide, sunNo, sunAt, sunAt + 2) && hasRange(pvState.hide, sunNo, sunAt + 5, sunAt + 7),
    'the ** around sun stay hidden with the cursor on that line');
  pvEd.selection = new vscode.Selection(sunNo, valAt + 3, sunNo, valAt + 3);   // inside {size: 28}
  await sleep(300);
  pvState = api.state.preview.get(pvKey);
  assert(!hasRange(pvState.hide, sunNo, valAt, valAt + 1) && hasRange(pvState.hide, sunNo, sunAt, sunAt + 2),
    'inside {size: 28} its braces show, the rest of the line stays formatted');
  await vscode.workspace.getConfiguration('sor').update('livePreview', false, vscode.ConfigurationTarget.Global);
  await sleep(400);
  assert(!api.state.preview.get(pvKey), 'live preview off: nothing hidden');
  await vscode.workspace.getConfiguration('sor').update('livePreview', true, vscode.ConfigurationTarget.Global);
  pvState = await moveTo(0);
  assert(pvState && pvState.hide.length > 0 && pvDoc.getText() === before, 'live preview on again, file unchanged');
  ok(`live preview: ${pvState.hide.length} marks hidden, ${pvState.bold.length} bold, bold stays hidden, value revealed under the cursor, toggle off/on`);
  // 6. completion of {references}: typing { offers the project's items; the chosen one resolves
  const cDoc = await vscode.workspace.openTextDocument(file('sor', 'bodies.md'));
  const cEd = await vscode.window.showTextDocument(cDoc, { preview: false });
  const endOfDoc = cDoc.lineAt(cDoc.lineCount - 1).range.end;
  await cEd.edit((b) => b.insert(endOfDoc, '\nSee {'));   // in memory only; reverted below, never saved
  const cPos = new vscode.Position(cDoc.lineCount - 1, 5);
  const offered = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider', cDoc.uri, cPos, '{');
  const ids = project.index ? api.state.projects[0].index.items.map((i) => i.id) : [];
  const labels = offered.items.map((i) => (typeof i.label === 'string' ? i.label : i.label.label));
  assert(labels.includes('bodies') && labels.includes('bodies/planets/Mars'), 'part and row offered: ' + labels.slice(0, 5));
  assert(!labels.includes('ROOT') && !labels.includes('CLAUSES') && !labels.some((l) => /(^|\/)test:/.test(l)), 'neither the root part nor a test is offered');
  assert(labels.every((l) => ids.includes(l)), 'every offered id is an id of the index');
  const partItem = offered.items.find((i) => i.label === 'bodies');
  assert(partItem.documentation && String(partItem.documentation.value || partItem.documentation).length > 5, 'a part comes with its Why');
  const sunItem = offered.items.find((i) => i.label === 'bodies/sun');
  assert(sunItem && /sun/i.test(String(sunItem.documentation.value || sunItem.documentation)), 'a clause comes with its words');
  assert(sunItem.insertText === 'bodies/sun}', 'picking writes the id and closes the brace: ' + sunItem.insertText);
  await vscode.commands.executeCommand('undo');
  const none = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider', cDoc.uri, new vscode.Position(0, 0), '{');
  assert(!none.items.some((i) => i.label === 'bodies/sun'), 'no offer where no { was typed');
  ok(`completion: ${labels.length} choices after {, with their words`);

  // 7. highlight: the counterpart of the cursor's block, lit in the other visible editor
  await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  const hl_index = api.state.projects[0].index;
  const hl_regionOf = (id, kind) => hl_index.regions.find((r) => r.ids.includes(id) && (!kind || r.kind === kind));
  const hl_specDoc = await vscode.workspace.openTextDocument(file('sor', 'bodies.md'));
  const hl_codeDoc = await vscode.workspace.openTextDocument(file('out', 'index.html'));
  const hl_specKey = path.normalize(hl_specDoc.uri.fsPath).toLowerCase();
  const hl_codeKey = path.normalize(hl_codeDoc.uri.fsPath).toLowerCase();
  const hl_lit = (key) => api.state.counterpart.get(key) || [];
  const hl_sunI = hl_index.items.find((i) => i.id === 'bodies/sun');
  const hl_sunR = hl_regionOf('bodies/sun', 'code');
  assert(hl_sunI && hl_sunR, 'the sun item has a code region');
  // only-visible: with the code file not open, nothing is lit, and no editor is opened for it
  const hl_specEd = await vscode.window.showTextDocument(hl_specDoc, { viewColumn: vscode.ViewColumn.One, preview: false });
  hl_specEd.selection = new vscode.Selection(hl_sunI.line - 1, 0, hl_sunI.line - 1, 0);
  await sleep(500);
  assert(api.state.counterpart.size === 0, 'nothing is lit while the code file is not shown: ' + [...api.state.counterpart.keys()]);
  assert(vscode.window.visibleTextEditors.length === 1, 'no editor was opened for the counterpart');
  ok('highlight: with the counterpart file closed nothing is lit and nothing is opened');
  // counterpart: spec -> code, painted between the marker lines
  const hl_codeEd = await vscode.window.showTextDocument(hl_codeDoc, { viewColumn: vscode.ViewColumn.Two, preview: false, preserveFocus: true });
  await sleep(300);
  const hl_rangeBefore = hl_codeEd.visibleRanges.map((r) => [r.start.line, r.end.line]);
  (await vscode.window.showTextDocument(hl_specDoc, { viewColumn: vscode.ViewColumn.One, preview: false })).selection = new vscode.Selection(hl_sunI.line - 1, 0, hl_sunI.line - 1, 0);
  assert(await until(() => hl_lit(hl_codeKey).length > 0), 'the sun region is lit in the code editor');
  const hl_pair = hl_lit(hl_codeKey)[0];
  assert(hl_pair[0] === hl_sunR.start + 1 && hl_pair[1] === hl_sunR.end - 1, `lit ${hl_pair} is the region ${hl_sunR.start}-${hl_sunR.end} without its two marker lines`);
  assert(/@clause/.test(hl_codeDoc.lineAt(hl_sunR.start - 1).text) && /@clause end/.test(hl_codeDoc.lineAt(hl_sunR.end - 1).text) && !/@clause/.test(hl_codeDoc.lineAt(hl_pair[0] - 1).text),
    'the lines above and below the lit block are the marker lines');
  assert(JSON.stringify(hl_codeEd.visibleRanges.map((r) => [r.start.line, r.end.line])) === JSON.stringify(hl_rangeBefore), 'the code editor was not scrolled');
  assert(!hl_lit(hl_specKey).length, 'the editor with the cursor is not lit');
  ok(`highlight: the sun item lights ${hl_pair[0]}-${hl_pair[1]} in the code editor, between its marker lines, without scrolling it`);
  // counterpart: code -> spec, and clears when the cursor leaves the block
  (await vscode.window.showTextDocument(hl_codeDoc, { viewColumn: vscode.ViewColumn.Two, preview: false })).selection = new vscode.Selection(hl_pair[0] - 1, 0, hl_pair[0] - 1, 0);
  assert(await until(() => hl_lit(hl_specKey).length > 0 && !hl_lit(hl_codeKey).length), 'the clause is lit in the spec editor');
  const hl_specPair = hl_lit(hl_specKey)[0];
  assert(hl_specPair[0] === hl_sunI.line && hl_specPair[1] === (hl_sunI.endLine || hl_sunI.line), `the sun item ${hl_sunI.line}-${hl_sunI.endLine} is lit: ${hl_specPair}`);
  (await vscode.window.showTextDocument(hl_codeDoc, { viewColumn: vscode.ViewColumn.Two, preview: false })).selection = new vscode.Selection(0, 0, 0, 0);   // line 1 of the page is glue: no clause
  assert(await until(() => hl_lit(hl_specKey).length === 0), 'the highlight is gone once the cursor leaves the block');
  ok('highlight: code lights its clause in the spec editor, and it clears when the cursor leaves');
  // regions without marker lines of their own are lit whole: a table row's line marker, and a `code:` anchor
  const hl_marsI = hl_index.items.find((i) => i.id === 'bodies/planets/Mars');
  const hl_marsR = hl_index.regions.find((r) => r.kind === 'line' && r.ids.includes('bodies/planets/Mars'));
  const hl_motionR = hl_index.regions.find((r) => r.kind === 'anchor' && r.ids.includes('bodies/motion'));
  assert(hl_marsI && hl_marsR && hl_motionR, 'the Mars row has a line marker and bodies/motion has an anchor');
  const hl_specEd2 = await vscode.window.showTextDocument(hl_specDoc, { viewColumn: vscode.ViewColumn.One, preview: false });
  hl_specEd2.selection = new vscode.Selection(hl_marsI.line - 1, 0, hl_marsI.line - 1, 0);
  assert(await until(() => hl_lit(hl_codeKey).length > 0 && hl_lit(hl_codeKey)[0][0] === hl_marsR.start), 'the Mars row lights its line');
  assert(JSON.stringify(hl_lit(hl_codeKey)) === JSON.stringify([[hl_marsR.start, hl_marsR.end]]), 'a line marker is lit as it is, not trimmed: ' + JSON.stringify(hl_lit(hl_codeKey)));
  const hl_motionI = hl_index.items.find((i) => i.id === 'bodies/motion');
  hl_specEd2.selection = new vscode.Selection(hl_motionI.line - 1, 0, hl_motionI.line - 1, 0);
  assert(await until(() => hl_lit(hl_codeKey).some((p) => p[0] === hl_motionR.start && p[1] === hl_motionR.end)), 'the whole function of a code: anchor is lit: ' + JSON.stringify(hl_lit(hl_codeKey)));
  ok(`highlight: a table row lights its marker line (${hl_marsR.start}) and a code: anchor its whole function (${hl_motionR.start}-${hl_motionR.end}), untrimmed`);
  // all-ids: a region marked for several clauses lights each of them (they live in two spec files)
  const hl_shared = hl_index.regions.find((r) => r.kind === 'code' && r.ids.length >= 4 && r.ids.includes('clock/start') && r.ids.includes('screen/hud/space'));
  assert(hl_shared, 'a region marked for clock/start and screen/hud/space exists');
  const hl_clockDoc = await vscode.workspace.openTextDocument(file('sor', 'clock.md'));
  const hl_hudDoc = await vscode.workspace.openTextDocument(file('sor', 'screen', 'hud.md'));
  await vscode.window.showTextDocument(hl_clockDoc, { viewColumn: vscode.ViewColumn.Three, preview: false, preserveFocus: true });
  await vscode.window.showTextDocument(hl_hudDoc, { viewColumn: vscode.ViewColumn.Four, preview: false, preserveFocus: true });
  (await vscode.window.showTextDocument(hl_codeDoc, { viewColumn: vscode.ViewColumn.Two, preview: false })).selection = new vscode.Selection(hl_shared.start, 0, hl_shared.start, 0);
  const hl_clockKey = path.normalize(hl_clockDoc.uri.fsPath).toLowerCase();
  const hl_hudKey = path.normalize(hl_hudDoc.uri.fsPath).toLowerCase();
  const hl_want = hl_shared.ids.length;
  assert(await until(() => hl_lit(hl_clockKey).length + hl_lit(hl_hudKey).length + hl_lit(hl_specKey).length === hl_want),
    `all ${hl_want} clauses of the region are lit: ${hl_lit(hl_clockKey).length}+${hl_lit(hl_hudKey).length}+${hl_lit(hl_specKey).length}`);
  assert(hl_lit(hl_clockKey).length >= 3 && hl_lit(hl_hudKey).length >= 1, 'clock.md and hud.md each light their clauses');
  const hl_speedI = hl_index.items.find((i) => i.id === 'clock/speed');
  assert(hl_speedI.endLine > hl_speedI.line, 'clock/speed is a clause of several lines');
  assert(hl_lit(hl_clockKey).some((p) => p[0] === hl_speedI.line && p[1] === hl_speedI.endLine), 'a clause of several lines is lit whole: ' + JSON.stringify(hl_lit(hl_clockKey)));
  ok(`highlight: a region marked for ${hl_want} clauses lights all of them, in the two spec files that hold them`);
  // clears: an unsaved change on either side, and the counterpart closing
  const hl_edSpec = await vscode.window.showTextDocument(hl_hudDoc, { viewColumn: vscode.ViewColumn.Four, preview: false });
  const hl_spaceI = hl_index.items.find((i) => i.id === 'screen/hud/space');
  hl_edSpec.selection = new vscode.Selection(hl_spaceI.line - 1, 0, hl_spaceI.line - 1, 0);
  assert(await until(() => hl_lit(hl_codeKey).length > 0), 'the clause lights its code again');
  await hl_edSpec.edit((b) => b.insert(new vscode.Position(hl_spaceI.line - 1, 0), ' '));   // in memory only; reverted below
  assert(await until(() => hl_lit(hl_codeKey).length === 0), 'unsaved changes in the spec: nothing is lit');
  await vscode.commands.executeCommand('workbench.action.files.revert');
  assert(!hl_hudDoc.isDirty, 'the change is reverted, the file was never saved');
  assert(await until(() => hl_lit(hl_codeKey).length > 0), 'saved state again: lit again');
  await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  (await vscode.window.showTextDocument(hl_hudDoc, { viewColumn: vscode.ViewColumn.One, preview: false })).selection = new vscode.Selection(hl_spaceI.line - 1, 0, hl_spaceI.line - 1, 0);
  await sleep(400);
  assert(api.state.counterpart.size === 0, 'the code editor is closed: nothing to light');
  ok('highlight: unsaved changes and a closed counterpart both clear it');

  // 8. refresh: a burst of changes gives one refresh (project/refresh)
  const rfCount = { n: 0 };
  const rfSub = api.onDidRefresh(() => { rfCount.n++; });
  const settle = async (quiet = 2500) => {   // waits until no refresh has fired for a while: a running one would split a burst
    let last = rfCount.n, since = Date.now();
    while (Date.now() - since < quiet) { await sleep(200); if (rfCount.n !== last) { last = rfCount.n; since = Date.now(); } }
    return rfCount.n;
  };
  await settle();
  const rfA = file('scratch-refresh-a.tmp').fsPath, rfB = file('scratch-refresh-b.tmp').fsPath;
  const rf0 = rfCount.n;
  fs.writeFileSync(rfA, 'a'); fs.writeFileSync(rfB, 'b');
  assert(await until(() => rfCount.n > rf0, 10000), 'creating files gives a refresh');
  await settle();
  assert(rfCount.n === rf0 + 1, `two files created together give one refresh, got ${rfCount.n - rf0}`);
  const rf1 = rfCount.n;
  fs.unlinkSync(rfA); fs.unlinkSync(rfB);
  assert(await until(() => rfCount.n > rf1, 10000), 'deleting files gives a refresh');
  await settle();
  assert(rfCount.n === rf1 + 1, `two files deleted together give one refresh, got ${rfCount.n - rf1}`);
  rfSub.dispose();
  ok('refresh: two files created together give one refresh, deleting them one more');

  // 9. status bar: the numbers of the tool's status (state/status-bar)
  const countsOf = () => {
    const n = { drift: 0, review: 0, recompile: 0 };
    const cls = { drift: 'drift', stale: 'review', shared: 'review', new: 'recompile', changed: 'recompile', removed: 'recompile' };
    for (const p of api.state.projects) for (const f of (p.status && p.status.findings) || []) if (cls[f.status]) n[cls[f.status]]++;
    return `${n.drift} drift · ${n.review} review · ${n.recompile} recompile`;
  };
  const sbZero = '0 drift · 0 review · 0 recompile';
  assert(api.state.statusBarText === sbZero, 'a clean project reads zeros: ' + api.state.statusBarText);
  // a changed value that tests refer to: one clause to recompile, and the tests that refer to it to review
  const sbFile = file('sor', 'screen', 'scene.md').fsPath;
  const sbOriginal = fs.readFileSync(sbFile);
  fs.writeFileSync(sbFile, fs.readFileSync(sbFile, 'utf8').replace('Orbits: thin faint {width: 1px}', 'Orbits: thin faint {width: 2px}'));
  try {
    assert(await until(() => api.state.statusBarText !== sbZero, 15000), 'the status bar changes when a clause changes on disk');
    await settle();
    assert(api.state.statusBarText === countsOf() && /^0 drift · [1-9]\d* review · [1-9]\d* recompile$/.test(api.state.statusBarText),
      `the status bar shows the numbers of the tool's status: "${api.state.statusBarText}" against "${countsOf()}"`);
    // while that clause is changed on disk: its code line says to recompile (state/states), and the marks are there (state/gutter)
    const stRegion = api.state.projects[0].index.regions.find((r) => r.kind === 'code' && r.ids.includes('screen/scene/orbits'));
    const stHtml = await vscode.workspace.openTextDocument(file('out', 'index.html'));
    const stHovers = await vscode.commands.executeCommand('vscode.executeHoverProvider', stHtml.uri, new vscode.Position(stRegion.start, 4));
    const stText = stHovers.flatMap((h) => h.contents.map((c) => c.value)).join('\n');
    assert(/screen\/scene\/orbits/.test(stText) && /to recompile/.test(stText), "the changed clause's code line says to recompile: " + stText.slice(0, 220));
    const stMarks = api.state.marks.get(path.normalize(stHtml.uri.fsPath).toLowerCase());
    assert(stMarks && stMarks.recompile.length > 0 && stMarks.drift.length === 0, 'the code file has a recompile mark and no drift mark: ' + JSON.stringify(stMarks));
    const stScene = api.state.marks.get(path.normalize(file('sor', 'screen', 'scene.md').fsPath).toLowerCase());
    assert(stScene && stScene.review.length > 0, 'a clause item that needs review has a review mark in scene.md: ' + JSON.stringify(stScene));
    // hovering that marked line of the spec says what the mark means (state/gutter); a line without a mark says nothing
    const mkDoc = await vscode.workspace.openTextDocument(file('sor', 'screen', 'scene.md'));
    const mkHover = async (line) => (await vscode.commands.executeCommand('vscode.executeHoverProvider', mkDoc.uri, new vscode.Position(line - 1, 2)))
      .flatMap((h) => h.contents.map((c) => c.value)).join('\n');
    const mkText = await mkHover(stScene.review[0]);
    assert(/to review/.test(mkText) && /changed: check that it still holds/.test(mkText) && /\*\*[^*]+\*\*/.test(mkText), 'the review mark of scene.md explains itself on hover: ' + mkText);
    const mkMarked = new Set([...stScene.review, ...stScene.recompile, ...stScene.drift]);
    const mkFree = [...Array(mkDoc.lineCount).keys()].map((n) => n + 1).find((n) => !mkMarked.has(n));
    assert(mkFree === undefined || (await mkHover(mkFree)) === '', 'a line of scene.md without a mark has no mark hover');
  } finally {
    fs.writeFileSync(sbFile, sbOriginal);
  }
  assert(await until(() => api.state.statusBarText === sbZero, 15000), 'zeros again once the file is restored');
  await settle();
  ok(`status bar: "${sbZero}", and the tool's numbers while a clause is changed on disk; hover says to recompile, recompile and review marks are there`);

  // 10. marker lines: which lines are hidden (marker-lines/which)
  const mlDoc = await vscode.workspace.openTextDocument(file('out', 'index.html'));
  const mlEd = await vscode.window.showTextDocument(mlDoc, { preview: false });
  mlEd.selection = new vscode.Selection(49, 0, 49, 0);   // a marker the cursor is on is shown, and a file opens with the cursor on line 1
  const mlKey = path.normalize(mlDoc.uri.fsPath).toLowerCase();
  const mlIndex = api.state.projects[0].index;
  const mlSun = mlIndex.regions.find((r) => r.kind === 'code' && r.ids.includes('bodies/sun'));
  const mlMars = mlIndex.regions.find((r) => r.kind === 'line' && r.ids.includes('bodies/planets/Mars'));
  const mlNow = () => (api.state.markerLines.get(mlKey) || {}).lines || [];
  // the file opened with the cursor on line 1, which showed that marker for a moment: wait for the cursor to have moved away
  assert(await until(() => mlNow().includes(mlSun.start) && mlNow().includes(1)), 'the marker lines of the code file are hidden, the one at the top too: ' + mlNow().slice(0, 6));
  const mlLines = api.state.markerLines.get(mlKey).lines;
  assert(mlLines.includes(mlSun.start) && mlLines.includes(mlSun.end), `the opening and the @clause end line of a region are hidden: ${mlSun.start}, ${mlSun.end} in ${mlLines.slice(0, 8)}`);
  assert(mlLines.includes(1), 'the marker at the top of the file is hidden');
  assert(!mlLines.includes(mlMars.start), `the marker at the end of the Mars code line (${mlMars.start}) is not hidden`);
  ok(`marker lines: region ends and the file-top marker are hidden (${mlLines.length} lines), the Mars line marker (${mlMars.start}) is not`);

  // 11. references: a place only where the index has it (references/tool-resolves)
  const trUri = file('sor', 'scratch-refs.md');
  fs.writeFileSync(trUri.fsPath, '# Scratch\nWhy: s.\n\n## Rules\n- **a** — real {bodies/sun} and in code `{bodies/sun}` here.\n');
  try {
    await api.refresh();
    const trDoc = await vscode.workspace.openTextDocument(trUri);
    const trLine = trDoc.lineAt(4).text;
    const realAt = trLine.indexOf('{bodies/sun}') + 2, tickAt = trLine.lastIndexOf('{bodies/sun}') + 2;
    const where = (col) => vscode.commands.executeCommand('vscode.executeDefinitionProvider', trDoc.uri, new vscode.Position(4, col));
    const realDefs = await where(realAt);
    assert(realDefs.length === 1 && (realDefs[0].targetUri || realDefs[0].uri).fsPath.endsWith('bodies.md'), 'the reference the index has gives bodies.md: ' + realDefs.length);
    assert((await where(tickAt)).length === 0, 'the same text inside backticks, which the tool does not index, gives no place');
  } finally {
    fs.unlinkSync(trUri.fsPath);
    await api.refresh();
  }
  ok('references: the indexed reference jumps to bodies.md, the one in backticks gives nothing');

  // 12. colors: nothing is edited (colors/text-unchanged)
  const tuFile = file('sor', 'bodies.md').fsPath;
  const tuBytes = fs.readFileSync(tuFile);
  const tuDoc = await vscode.workspace.openTextDocument(tuFile);
  const tuEd = await vscode.window.showTextDocument(tuDoc, { preview: false });
  assert(tuDoc.languageId === 'sor-markdown' && vscode.workspace.getConfiguration('sor').get('livePreview') !== false, 'colors and the live preview are on');
  for (let l = 0; l < tuDoc.lineCount; l += 2) { tuEd.selection = new vscode.Selection(l, 0, l, 0); await sleep(25); }
  await sleep(600);
  assert(!tuDoc.isDirty && tuDoc.getText() === tuBytes.toString('utf8'), 'the document was not edited');
  assert(Buffer.compare(fs.readFileSync(tuFile), tuBytes) === 0, 'the file on disk is the same bytes');
  ok(`colors: ${tuDoc.lineCount} lines walked with colors and preview on, the document is not edited and the file is the same bytes`);

  // 13. node: a refresh starts only the editor's own Node, running the bundled tool (project/node). child_process is one module for the extension and
  // this test, and the extension calls cp.execFile when it needs it, so wrapping it shows every program a refresh starts, whatever the PATH holds.
  {
    const cp = require('child_process');
    const started = [];
    const execFile = cp.execFile;
    cp.execFile = function (file, args, ...rest) { started.push([file, ...(Array.isArray(args) ? args : [])]); return execFile.call(this, file, args, ...rest); };
    try {
      await api.refresh();
    } finally {
      cp.execFile = execFile;
    }
    assert(started.length >= 2 * api.state.projects.length, 'a refresh asks the tool for the index and the status of each project: ' + started.length + ' calls');
    const toolJs = path.join(ext.extensionPath, 'tools', 'sor.js');
    const odd = started.filter((c) => c[0] !== process.execPath || c[1] !== toolJs);
    assert(!odd.length, 'a refresh started something else than the editor\'s Node on tools/sor.js: ' + JSON.stringify(odd[0] || null).slice(0, 200));
    assert(api.state.projects.length && api.state.projects.every((p) => p.index && p.status), 'every project has its index and status');
    ok(`node: a refresh started ${started.length} programs, all of them the editor's Node on tools/sor.js, none of them Python`);
  }

  // 14. projects: the folder above sor/, node_modules skipped, 20 at most (project/projects). Last: findFiles returns any 20,
  // so the example itself may drop out while the scratch projects exist.
  const prRoot = path.join(project.root, 'scratch-projects');
  const mk = (rel) => {
    fs.mkdirSync(path.join(prRoot, rel, 'sor'), { recursive: true });
    fs.writeFileSync(path.join(prRoot, rel, 'sor', 'SPECOFRECORD.md'), '# P\nWhy: p.\n\n## Rules\n- **a** — b.\n');
  };
  mk(path.join('node_modules', 'pkg'));
  for (let i = 1; i <= 21; i++) mk('p' + String(i).padStart(2, '0'));
  try {
    await api.refresh();
    const roots = api.state.projects.map((p) => p.root);
    assert(!roots.some((r) => r.includes('node_modules')), 'a sor/ folder inside node_modules is not found');
    assert(roots.length === 20, `22 projects in the workspace: 20 are found, got ${roots.length}`);
    assert(roots.every((r) => fs.existsSync(path.join(r, 'sor', 'SPECOFRECORD.md'))), 'every project is the folder above a sor/');
  } finally {
    fs.rmSync(prRoot, { recursive: true, force: true });
    await api.refresh();
  }
  assert(api.state.projects.length === 1 && path.normalize(api.state.projects[0].root) === path.normalize(project.root), 'the example is the only project again');
  ok('projects: 22 in the workspace, 20 found, none inside node_modules');
};
