// The scenes of the README screenshots, run inside VS Code by test/screenshots.js: each scene sizes the window first (resizing
// closes a hover), sets itself up and asks for the capture. A window is only as high as the few lines a screenshot is about, and the
// ones about a state show the spec on the left and its code on the right.
const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (fn, ms = 15000) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(150); } return !!(await fn()); };

exports.run = async function run() {
  const signals = process.env.SOR_SHOTS_SIGNALS;
  const run = (c, ...a) => vscode.commands.executeCommand(c, ...a);
  const wait = async (name, what) => { if (!await until(() => fs.existsSync(path.join(signals, name + '.' + what)), 60000)) throw new Error(`${name}: no ${what}`); };
  const place = async (name, w, h) => { fs.writeFileSync(path.join(signals, name + '.place'), JSON.stringify({ w, h })); await wait(name, 'placed'); };
  const shot = async (name) => {
    await run('notifications.clearAll');   // "All installed extensions are temporarily disabled" and the like
    await sleep(300);
    fs.writeFileSync(path.join(signals, name + '.ready'), '');
    await wait(name, 'done');
  };
  const api = await vscode.extensions.getExtension('sebastianrath.sor-vscode').activate();
  if (!await until(() => api.state.projects[0] && api.state.projects[0].index, 30000)) throw new Error('the project was not found');
  const project = () => api.state.projects[0];
  const file = (...p) => path.join(project().root, ...p);
  // opens a file in a column, shows its line `firstLine` at the top and puts the cursor in `cursor` = [line, column]
  const open = (f, column, firstLine, cursor) => vscode.workspace.openTextDocument(f).then((doc) => vscode.window.showTextDocument(doc, { viewColumn: column, preview: false }))
    .then((ed) => {
      ed.selection = new vscode.Selection(cursor[0], cursor[1], cursor[0], cursor[1]);
      ed.revealRange(new vscode.Range(firstLine, 0, firstLine, 0), vscode.TextEditorRevealType.AtTop);
      return ed;
    });
  // the spec on the left, its code on the right; the cursor ends in the spec, so its block lights the code and the lens is above it
  const sideBySide = async (spec, specTop, specCursor, code, codeTop) => {
    await run('workbench.action.closeAllEditors');
    await run('workbench.action.editorLayoutSingle');
    await open(code, vscode.ViewColumn.Two, codeTop, [codeTop, 0]);
    await open(spec, vscode.ViewColumn.One, specTop, specCursor);
    await sleep(2500);
  };
  const lines = (f) => fs.readFileSync(f, 'utf8').split('\n');
  const lineOf = (f, re, from = 0) => { const at = lines(f).findIndex((t, n) => n >= from && re.test(t)); if (at < 0) throw new Error(`${f}: no line for ${re}`); return at; };
  const fresh = async () => { await run('workbench.action.closeAllEditors'); await run('workbench.action.editorLayoutSingle'); };
  const settle = async () => { await sleep(2500); };
  for (const c of ['workbench.action.closeSidebar', 'workbench.action.closePanel', 'workbench.action.closeAuxiliaryBar']) await run(c);

  const page = file('out', 'index.html'), bodies = file('sor', 'bodies.md'), rootSpec = file('sor', 'SPECOFRECORD.md'), clock = file('sor', 'clock.md');
  const regionOf = (id) => project().index.regions.find((r) => r.kind === 'code' && r.ids.includes(id));
  const sunAt = lineOf(bodies, /^- \*\*sun\*\*/), marsRow = lineOf(bodies, /^\| Mars/), moonAt = lineOf(bodies, /^- \*\*moon\*\*/);
  const marsCode = lineOf(page, /@clause bodies\/planets\/Mars/);

  // 1. a spec and its code, everything in sync: the clause under the cursor lights its code, the lens names the lines
  await place('overview', 1300, 300);
  await sideBySide(bodies, sunAt - 2, [sunAt, 12], page, regionOf('bodies/sun').start - 3);
  await shot('overview');

  // 2. hovering generated code: the spec section behind the line and its state, the spec on the left. The hovered line belongs to one short
  // section (a table or a long section gives a tall popup, and VS Code's own hover is added to it where the JavaScript server knows the name),
  // and the window is high enough that the popup opens below the line and covers only code that does not matter.
  await place('hover', 1300, 330);
  const motionAt = lineOf(bodies, /^- \*\*motion\*\*/);
  const motionCode = regionOf('bodies/motion').start;   // the line after the marker: function angle(body, days) {
  await sideBySide(bodies, motionAt - 4, [motionAt, 12], page, motionCode - 1);   // the hovered line is the first of the pane: with no room above it the hover opens below
  // the cursor moves to the code, onto the opening brace, where the JavaScript server adds no hover of its own: the lens, and the hover
  await open(page, vscode.ViewColumn.Two, motionCode - 1, [motionCode, lines(page)[motionCode].lastIndexOf('{')]);
  await sleep(1500);
  await run('editor.action.showHover');
  await settle();
  await shot('hover');

  // 3. live preview, off and on
  await place('preview-off', 760, 300);
  await fresh();
  await vscode.workspace.getConfiguration('sor').update('livePreview', false, vscode.ConfigurationTarget.Global);
  await open(bodies, vscode.ViewColumn.One, 0, [lineOf(bodies, /^- angle =/), 0]);   // the cursor far from the top: no lens over the title
  await settle();
  await shot('preview-off');
  await vscode.workspace.getConfiguration('sor').update('livePreview', true, vscode.ConfigurationTarget.Global);
  await settle();
  await shot('preview-on');

  // 4. a rule nothing implements yet
  await place('no-code', 1000, 330);
  await fresh();
  const calmAt = lineOf(rootSpec, /^- \*\*calm\*\*/);
  await open(rootSpec, vscode.ViewColumn.One, calmAt - 3, [calmAt, 14]);
  await sleep(1500);
  await run('editor.action.showHover');
  await settle();
  await shot('no-code');

  // 5. the states: a line of code edited by hand, a clause changed, a value that others refer to changed
  const zero = api.state.statusBarText;
  fs.writeFileSync(page, fs.readFileSync(page, 'utf8').replace("{ name: 'mars', size: 5,", "{ name: 'mars', size: 6,"));
  fs.writeFileSync(bodies, fs.readFileSync(bodies, 'utf8').replace('orbit {orbit: 14}', 'orbit {orbit: 16}'));
  fs.writeFileSync(rootSpec, fs.readFileSync(rootSpec, 'utf8').replace('{days: 365 days}', '{days: 366 days}'));
  if (!await until(() => api.state.statusBarText !== zero && /^[1-9]\d* drift · [1-9]\d* review · [1-9]\d* recompile$/.test(api.state.statusBarText), 40000)) throw new Error('not all three states: ' + api.state.statusBarText);
  await settle();

  // drift: the code was changed by hand, the clause was not: red on the table row and on the line of code
  await place('drift', 1300, 300);
  await sideBySide(bodies, marsRow - 5, [marsRow, 4], page, marsCode - 3);
  await shot('drift');

  // recompile: the clause changed, its code has not followed: blue on the item and on its code
  await place('recompile', 1300, 300);
  await sideBySide(bodies, moonAt - 3, [moonAt, 12], page, regionOf('bodies/moon').start - 3);
  await shot('recompile');

  // review: a value this test refers to changed (the year, in the root spec on the right)
  await place('review', 1300, 420);
  const speedAt = lineOf(clock, /^- \*\*speed\*\*/, lineOf(clock, /^## Tests/));
  await run('workbench.action.closeAllEditors');
  await run('workbench.action.editorLayoutSingle');
  await open(rootSpec, vscode.ViewColumn.Two, lineOf(rootSpec, /^- \*\*year\*\*/) - 3, [0, 0]);
  await open(clock, vscode.ViewColumn.One, speedAt - 4, [speedAt, 12]);
  await sleep(1500);
  await run('editor.action.showHover');
  await settle();
  await shot('review');
};
