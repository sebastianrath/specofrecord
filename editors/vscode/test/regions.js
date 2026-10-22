// Unit test of the small pure parts of src/extension.js, without VS Code: the code of a clause is cut out of the file between its
// `// @clause <id>` line and the next `// @clause end`, and run on its own, so what is tested is the text the clause marks.
// usage: node test/regions.js
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const lines = fs.readFileSync(path.join(__dirname, '..', 'src', 'extension.js'), 'utf8').split('\n');

/** The text of the first region (at the top level of the file) that is marked with the clause `id`. */
function regionOf(id) {
  const open = lines.findIndex((l) => {
    const m = /^\/\/ @clause (.+)$/.exec(l);
    return m && m[1] !== 'end' && m[1].split(/\s+/).includes(id);
  });
  assert.ok(open >= 0, `no region is marked ${id}`);
  const close = lines.findIndex((l, i) => i > open && /^\/\/ @clause end\s*$/.test(l));
  assert.ok(close > open, `the region of ${id} is not closed`);
  return lines.slice(open + 1, close).join('\n');
}

/** Runs the code of a clause alone and returns the names it defines. */
function load(id, ...names) {
  return vm.runInNewContext(`${regionOf(id)}\n({ ${names.join(', ')} })`, {});
}

let failed = 0;
function check(name, fn) {
  try {
    fn();
    console.log('  ok  ' + name);
  } catch (e) {
    failed++;
    console.log('  FAIL ' + name + '\n    ' + e.message.split('\n').join('\n    '));
  }
}

// state/words
const { classOf } = load('state/words', 'classOf');
check('drift is drift', () => assert.strictEqual(classOf('drift'), 'drift'));
check('stale and shared are review', () => {
  assert.strictEqual(classOf('stale'), 'review');
  assert.strictEqual(classOf('shared'), 'review');
});
check('new, changed, removed and behind are recompile', () => {
  for (const s of ['new', 'changed', 'removed', 'behind']) assert.strictEqual(classOf(s), 'recompile', s);
});
check('a status the extension does not know counts as in sync', () => {
  for (const s of ['built', 'fixing', 'glue', 'code-changed', 'something-new', undefined]) assert.strictEqual(classOf(s), null, String(s));
});

// marker-lines/which
const { MARKER_RE } = load('marker-lines/which', 'MARKER_RE');
check('a marker line is a marker of its own after any comment starter', () => {
  for (const l of ['// @clause a', '  # @clause end', '-- @clause a b', '; @clause x', '% @clause x', '! @clause x', "' @clause x", '(* @clause x',
    ':: @clause x', 'rem @clause x', 'REM @clause x', '/* @clause x', '<!-- @clause x', '//@clause x', '\t/// @clause x']) {
    assert.ok(MARKER_RE.test(l), `${l} should be a marker line`);
  }
});
check('code that ends with a marker, and other comments, are not', () => {
  for (const l of ['x = 1 // @clause a', 'const a = 1; // @clause a', 'foo(); % @clause a', '// about @clause', '// @clauses', 'REMARK @clause x',
    '@clause a', 'print("// @clause a")', '']) {
    assert.ok(!MARKER_RE.test(l), `${l} should not be a marker line`);
  }
});

// lenses/clause-lens lenses/jump
const { codeTitle, targetsOf, pickOf } = load('lenses/clause-lens', 'codeTitle', 'targetsOf', 'pickOf');
const region = (file, start, end, targetName, ids) => ({ file, start, end, targetName, ids });
check('a lens names the one region, the line when it is one', () => {
  assert.strictEqual(codeTitle([region('out/a.py', 3, 5, 'py')]), 'out/a.py:3-5');
  assert.strictEqual(codeTitle([region('out/a.py', 7, 7, 'py')]), 'out/a.py:7');
  assert.strictEqual(codeTitle([]), 'no code');
});
check('a lens names the targets when the regions are in more than one, and not otherwise', () => {
  assert.strictEqual(codeTitle([region('a.py', 1, 2, 'py'), region('b.ts', 1, 2, 'ts')]), '2 code regions (py, ts)');
  assert.strictEqual(codeTitle([region('b.ts', 1, 2, 'ts'), region('a.py', 1, 2, 'py'), region('c.py', 1, 2, 'py')]), '3 code regions (py, ts)');
  assert.strictEqual(codeTitle([region('a.py', 1, 2, 'py'), region('c.py', 5, 6, 'py')]), '2 code regions');
  assert.strictEqual(codeTitle([region('a.html', 1, 2, null), region('b.html', 5, 6, null)]), '2 code regions');
  assert.strictEqual(targetsOf([region('a.py', 1, 2, 'py')]), '');
});
check('the list of regions names the target of each only when they are in more than one', () => {
  const regs = [region('a.py', 1, 2, 'py', ['x/y']), region('b.ts', 4, 4, 'ts', ['x/y', 'x/z'])];
  const a = pickOf(regs[0], targetsOf(regs));
  const b = pickOf(regs[1], targetsOf(regs));
  assert.deepStrictEqual([a.label, a.description, b.label, b.description], ['a.py:1-2', 'py x/y', 'b.ts:4', 'ts x/y x/z']);
  assert.ok(a.region === regs[0] && b.region === regs[1], 'the entry carries its region');
  const same = [region('a.py', 1, 2, 'py', ['x/y']), region('c.py', 9, 9, 'py')];
  assert.strictEqual(pickOf(same[0], targetsOf(same)).description, 'x/y');
  assert.strictEqual(pickOf(same[1], targetsOf(same)).description, '');
});

console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
process.exit(failed ? 1 : 0);
