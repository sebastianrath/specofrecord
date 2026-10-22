'use strict';
// Answers the questions in a job file with the JavaScript copy of the rules, so that tools/test_sor_js.py can put the answers next
// to the Python tool's own. Not a test by itself.
//
//   node tools/js/test/crosscheck.js jobs.json   prints the answers as JSON on one line
//
// A job file is {normalize: [{lines, style}], marker: [{path, line, starters}], scan: [{path, text, starters}], render: [{entries, fmt}],
// anchor: [{path, text, names}]}, and the answers come in the same shape: a SHA-256 (12 hex digits) of each normalized text, the marker as
// [code, words] or null, the regions, problems and unmarked lines of a scan, the text of a lock or "error", and for each of the names of an
// anchor job its first and last line or null.
const crypto = require('crypto');
const fs = require('fs');
const { markers, lock, anchors } = require('../sorlib');

const sha = (text) => crypto.createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 12);
const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

const answers = {
  normalize: (jobs.normalize || []).map((j) => sha(markers.normalized(j.lines, j.style))),
  marker: (jobs.marker || []).map((j) => {
    const m = markers.parseMarker(j.path, j.line, j.starters);
    return m === null ? null : [m.code, m.words];
  }),
  scan: (jobs.scan || []).map((j) => {
    const { regions, problems, unmarked } = markers.scanText(j.path, j.text, j.starters);
    return {
      regions: regions.map((r) => [r.kind, r.ids, r.start, r.end, r.lines]),
      problems: problems.map((p) => [p.kind, p.where, p.text]),
      unmarked,
    };
  }),
  anchor: (jobs.anchor || []).map((j) => j.names.map((name) => anchors.find(j.text, j.path, name))),
  render: (jobs.render || []).map((j) => {
    try {
      return lock.render(j.entries, j.fmt);
    } catch (e) {
      return 'error';
    }
  }),
};
process.stdout.write(`${JSON.stringify(answers)}\n`);
