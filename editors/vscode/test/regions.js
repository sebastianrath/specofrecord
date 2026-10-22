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

console.log(failed ? `${failed} check(s) failed` : 'all checks passed');
process.exit(failed ? 1 : 0);
