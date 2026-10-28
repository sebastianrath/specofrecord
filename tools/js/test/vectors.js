'use strict';
// Runs vectors/hashing.json: rows of input and expected output for how the tool hashes code and writes the lock (SPEC §11). The
// Python tool runs the same rows in tools/py/test_sor_vectors.py, and the two have to give the same answer for every one, or a lock
// written by one would show as drift in the other.
//
//   node tools/js/test/vectors.js
//
// Plain `assert`, no dependencies, and nothing newer than Node 16 (the Node of VS Code 1.80).
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { markers, lock, model } = require('../sorlib');

const FILE = path.join(__dirname, '..', '..', '..', 'vectors', 'hashing.json');
const VECTORS = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const FORMAT = 3;   // the format of the vectors file this port reads: a rule that changes bumps it, and this port has to follow
const CATEGORIES = ['style_of', 'split_lines', 'normalize', 'code_hash', 'text_hash', 'asset_digest', 'targets_digest', 'fold', 'marker', 'starters_of',
  'lock_render'];

const sha = (text) => crypto.createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 12);
const copy = (value) => JSON.parse(JSON.stringify(value));
const rows = (category) => VECTORS[category].rows;

let checks = 0;
const failures = [];

function check(label, fn) {
  checks += 1;
  try {
    fn();
  } catch (e) {
    failures.push(`${label}\n${String(e.message).split('\n').slice(0, 14).map((l) => `    ${l}`).join('\n')}`);
  }
}

function eachRow(category, fn) {
  for (const r of rows(category)) check(`${category}: ${r.name}`, () => fn(r));
}

// ---- the file ----------------------------------------------------------------------------------------------------------------

check('the file is in the format this port reads', () => assert.strictEqual(VECTORS.format, FORMAT));

check('it has every category with rows and a name for each row', () => {
  for (const c of CATEGORIES) {
    assert.ok(VECTORS[c].how, `${c} has no description`);
    assert.ok(rows(c).length > 0, `${c} has no rows`);
    assert.ok(rows(c).every((r) => r.name), `${c} has a row without a name`);
  }
  const names = [].concat(...CATEGORIES.map((c) => rows(c).map((r) => r.name)));
  assert.strictEqual(names.length, new Set(names).size, 'a failing row must be found by its name');
});

check('every type this port knows has a row, so that it cannot map one differently', () => {
  const styles = new Set(rows('style_of').map((r) => r.path));
  const starters = new Set(rows('starters_of').map((r) => r.path));
  const missing = [];
  for (const ext of markers.STYLES.keys()) {
    if (!styles.has(`a.${ext}`)) missing.push(`style_of .${ext}`);
    if (!starters.has(`a.${ext}`)) missing.push(`starters_of .${ext}`);
  }
  for (const n of [...markers.LANGUAGES_BY_NAME.keys(), ...markers.LANGUAGES_BY_EXACT_NAME.keys()]) {
    if (!styles.has(`x/${n}`)) missing.push(`style_of ${n}`);
  }
  assert.deepStrictEqual(missing, [], 'a type without a row: the table here has drifted from the one in tools/py/sorlib/markers.py');
});

// ---- every row ---------------------------------------------------------------------------------------------------------------

eachRow('style_of', (r) => assert.strictEqual(markers.styleOf(r.path), r.style));

eachRow('split_lines', (r) => assert.deepStrictEqual(model.splitLines(r.text), r.lines));

eachRow('normalize', (r) => {
  const got = markers.normalized(r.lines, r.style);
  assert.strictEqual(got, r.normalized);
  assert.strictEqual(sha(got), r.hash);
});

eachRow('code_hash', (r) => {
  const regions = r.regions.map((g) => {
    const region = new markers.Region(g.file, g.start, 'code', ['x']);
    region.lines = g.lines;
    return region;
  });
  assert.strictEqual(markers.codeHash(regions), r.hash);
});

eachRow('text_hash', (r) => assert.strictEqual(lock.h(r.input), r.hash));

eachRow('asset_digest', (r) => assert.strictEqual(model.assetDigest(Buffer.from(r.hex, 'hex')), r.hash));

eachRow('marker', (r) => {
  const got = markers.parseMarker(r.path, r.line, r.starters);
  assert.deepStrictEqual(got, r.marker);
  // and scanning the text of a file with that one line reads it the same way
  const { regions, unmarked } = markers.scanText(r.path, `${r.line}\n`, r.starters);
  if (r.marker === null) {
    assert.deepStrictEqual([regions, unmarked], [[], [1]]);
  } else if (r.marker.code) {
    assert.deepStrictEqual(regions.map((g) => [g.kind, g.ids, g.lines]), [['line', r.marker.words, [r.marker.code]]]);
  } else {
    assert.deepStrictEqual(unmarked, []);
  }
});

eachRow('starters_of', (r) => assert.deepStrictEqual(markers.startersOf(r.path), r.starters));

eachRow('targets_digest', (r) => assert.strictEqual(lock.digest(r.targets), r.digest));

eachRow('fold', (r) => assert.deepStrictEqual(lock.fold(copy(r.file)), r.entries));

eachRow('lock_render', (r) => assert.strictEqual(lock.render(copy(r.entries), r.fmt, Math.max(lock.FORMAT, r.fmt || 1)), r.text));

// ---- the result --------------------------------------------------------------------------------------------------------------

for (const f of failures) console.log(`FAIL ${f}`);
console.log(`Ran ${checks} checks, ${failures.length} failed`);
process.exit(failures.length ? 1 : 0);
