// Checks the copy of the `sor` tool that ships inside the extension (tools/, made by plugins/sync-tools.sh from the repository's tools/js).
//   1. It is the repository's tools/js (when this runs inside the repository): sor.js and sorlib/*.js, not the tests that sit next to them.
//   2. Run away from the repository, on the Node that runs this test, it answers `status --json`, `markers --json` and `parts --json`.
// usage: node test/bundle.js [project folder]     (default: examples/solar-system of this repository)
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const ext = path.resolve(__dirname, '..');
const bundled = path.join(ext, 'tools');
const repoTools = path.resolve(ext, '..', '..', 'tools', 'js');
const project = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(ext, '..', '..', 'examples', 'solar-system');
const ok = (name) => console.log('  ok  ' + name);

// the files plugins/sync-tools.sh ships: sor.js and the library
const files = (dir) => [
  'sor.js',
  ...fs.readdirSync(path.join(dir, 'sorlib')).filter((f) => f.endsWith('.js')).map((f) => path.join('sorlib', f)),
].sort();

// 1. the copy is there, and equals the repository's tools/js
assert(fs.existsSync(path.join(bundled, 'sor.js')), 'tools/sor.js is in the extension folder: run sh plugins/sync-tools.sh');
assert(fs.existsSync(path.join(bundled, 'sorlib', 'status.js')), 'tools/sorlib is in the extension folder: run sh plugins/sync-tools.sh');
assert(!fs.existsSync(path.join(bundled, 'sor.py')), 'the extension carries no Python tool any more: run sh plugins/sync-tools.sh');
if (fs.existsSync(path.join(repoTools, 'sor.js'))) {
  assert.deepStrictEqual(files(bundled), files(repoTools), 'the same files as the repository tools/js: run sh plugins/sync-tools.sh');
  for (const f of files(bundled)) {
    assert(fs.readFileSync(path.join(bundled, f)).equals(fs.readFileSync(path.join(repoTools, f))), f + ' differs from the repository tools/js: run sh plugins/sync-tools.sh');
  }
  ok(`the bundled tool is the repository's tools/js (${files(bundled).length} files)`);
} else {
  ok('not inside the repository: the comparison with tools/js was skipped');
}

// 2. away from the repository it answers with JSON
const away = fs.mkdtempSync(path.join(os.tmpdir(), 'sor bundle '));
try {
  fs.cpSync(bundled, path.join(away, 'tools'), { recursive: true });
  fs.cpSync(project, path.join(away, 'a project'), { recursive: true, filter: (p) => !/node_modules|\.vscode-test/.test(p) });
  const ask = (...args) => {
    let out;
    try {
      out = execFileSync(process.execPath, [path.join(away, 'tools', 'sor.js'), '-C', path.join(away, 'a project'), ...args], {
        cwd: away, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (e) {
      out = e.stdout;   // exit codes 1 and 2 still count, as in the extension
      if (!out) throw new Error(`sor ${args.join(' ')} gave no output: ${e.stderr || e.message}`);
    }
    return JSON.parse(out);
  };
  const status = ask('status', '--json');
  assert(Array.isArray(status.findings), 'status --json has a list of findings');
  const index = ask('markers', '--json');
  assert(Array.isArray(index.items) && index.items.length > 0, 'markers --json has items');
  const parts = ask('parts', '--json');
  assert(Array.isArray(parts) && parts.length > 0 && parts[0].id === 'ROOT', 'parts --json lists the parts, the root first');
  ok(`away from the repository the bundled tool answers: ${index.items.length} items, ${status.findings.length} findings, ${parts.length} parts`);
} finally {
  fs.rmSync(away, { recursive: true, force: true });
}
