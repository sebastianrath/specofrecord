// Checks the copy of the `sor` tool that ships inside the extension (tools/, made by plugins/sync-tools.sh).
//   1. It is the repository's tools/ (when this runs inside the repository).
//   2. Run away from the repository, with no tool in or above the project, it answers `status --json` and `markers --json`.
// usage: node test/bundle.js [project folder]     (default: examples/solar-system of this repository)
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const ext = path.resolve(__dirname, '..');
const bundled = path.join(ext, 'tools');
const repoTools = path.resolve(ext, '..', '..', 'tools');
const project = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(ext, '..', '..', 'examples', 'solar-system');
const ok = (name) => console.log('  ok  ' + name);

// the files plugins/sync-tools.sh ships: sor.py and the library, not the tests that sit next to them in the repository
const pyFiles = (dir) => [
  'sor.py',
  ...fs.readdirSync(path.join(dir, 'sorlib')).filter((f) => f.endsWith('.py')).map((f) => path.join('sorlib', f)),
].sort();

// 1. the copy is there, and equals the repository's tools/
assert(fs.existsSync(path.join(bundled, 'sor.py')), 'tools/sor.py is in the extension folder: run sh plugins/sync-tools.sh');
assert(fs.existsSync(path.join(bundled, 'sorlib', 'cli.py')), 'tools/sorlib is in the extension folder: run sh plugins/sync-tools.sh');
if (fs.existsSync(path.join(repoTools, 'sor.py'))) {
  assert.deepStrictEqual(pyFiles(bundled), pyFiles(repoTools), 'the same files as the repository tools/: run sh plugins/sync-tools.sh');
  for (const f of pyFiles(bundled)) {
    assert(fs.readFileSync(path.join(bundled, f)).equals(fs.readFileSync(path.join(repoTools, f))), f + ' differs from the repository tools/: run sh plugins/sync-tools.sh');
  }
  ok(`the bundled tool is the repository's tools/ (${pyFiles(bundled).length} files)`);
} else {
  ok('not inside the repository: the comparison with tools/ was skipped');
}

// 2. away from the repository it answers with JSON
const [py, pyArgs] = process.platform === 'win32' ? ['py', ['-3']] : ['python3', []];
const away = fs.mkdtempSync(path.join(os.tmpdir(), 'sor bundle '));
try {
  fs.cpSync(bundled, path.join(away, 'tools'), { recursive: true, filter: (p) => !p.includes('__pycache__') });
  fs.cpSync(project, path.join(away, 'a project'), { recursive: true, filter: (p) => !/node_modules|\.vscode-test/.test(p) });
  const ask = (...args) => {
    let out;
    try {
      out = execFileSync(py, [...pyArgs, path.join(away, 'tools', 'sor.py'), '-C', path.join(away, 'a project'), ...args], {
        cwd: away, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONUTF8: '1' },
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (e) {
      if (e.code === 'ENOENT') throw new Error(`${py} was not found: the bundled tool needs Python 3.9 or newer`);
      out = e.stdout;   // exit codes 1 and 2 still count, as in the extension
      if (!out) throw new Error(`sor ${args.join(' ')} gave no output: ${e.stderr || e.message}`);
    }
    return JSON.parse(out);
  };
  const status = ask('status', '--json');
  assert(Array.isArray(status.findings), 'status --json has a list of findings');
  const index = ask('markers', '--json');
  assert(Array.isArray(index.items) && index.items.length > 0, 'markers --json has items');
  ok(`away from the repository the bundled tool answers: ${index.items.length} items, ${status.findings.length} findings`);
} finally {
  fs.rmSync(away, { recursive: true, force: true });
}
