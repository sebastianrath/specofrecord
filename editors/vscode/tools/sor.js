'use strict';
// The sor tool's reading half in JavaScript, for an editor that has no Python: `markers --json`, `status --json` and `parts --json`
// print what `python3 tools/py/sor.py` prints for them (same fields, same positions). It reads the project and writes nothing: no claim is
// touched, no lock is written, no test is run, and the `problems` the Python status lists are not worked out here.
const index = require('./sorlib/index');

const USAGE = `usage: sor.js [-C PROJECT] markers --json [ID | FILE:LINE]
       sor.js [-C PROJECT] status --json
       sor.js [-C PROJECT] parts --json

The reading half of sor in JavaScript. Every other command, and every output without --json, is the Python tool's: python3 tools/py/sor.py.`;

function parse(argv) {
  const args = { root: '.', cmd: null, json: false, rest: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '-C' && i + 1 < argv.length) args.root = argv[++i];
    else if (a.startsWith('-C') && a.length > 2) args.root = a.slice(2);
    else if (a === '--json') args.json = true;
    else if (a === '-h' || a === '--help') args.help = true;
    else if (args.cmd === null && !a.startsWith('-')) args.cmd = a;
    else if (!a.startsWith('-')) args.rest.push(a);
    else return Object.assign(args, { bad: a });
  }
  return args;
}

/** The `markers --json` answer: the whole index, the regions around FILE:LINE, or the regions of one id. */
function markers(project, scan, target) {
  const { views, model } = index;
  if (!target) return views.fullIndex(project, scan);
  const at = /^(.*):(\d+)$/su.exec(target);
  if (at) return views.atLine(project, scan, at[1], parseInt(at[2], 10), views.describe);
  const found = project.find(target);
  const key = found === null ? target : (found[0] === 'part' ? found[1].key : found[1].id);
  const [head, , tail] = model.rpartition(key, '/');
  const testKey = `${head}/test:${tail}`.replace(/^\/+/, '');
  const rows = scan.regionsFor(key).concat(scan.regionsFor(testKey));
  return views.forId(project, scan, key, rows, found);
}

function status(project, scan) {
  const { status: st, views } = index;
  const old = st.read(project);
  const [findings, notPassed] = st.status(project, scan, old);
  views.annotate(project, findings);
  return {
    locked: Object.keys(old).length > 0,
    findings: findings.map((f) => f.asDict()),
    tests_not_passed: notPassed,
    tests_pending: st.pendingTests(project, findings, notPassed),
    tests_deferred: st.deferredTests(project),
    claims: st.activeClaims(project),
  };
}

/** {code, out, err} of one command line: what the program would exit with and print. */
function run(argv) {
  const args = parse(argv);
  const json = (data) => `${JSON.stringify(data, null, 2)}\n`;
  if (args.help || args.bad || !args.cmd || !args.json || !['markers', 'status', 'parts'].includes(args.cmd)) {
    const text = `${args.bad ? `sor.js: unknown option ${args.bad}\n` : ''}${USAGE}\n`;
    return args.help ? { code: 0, out: text, err: '' } : { code: 2, out: '', err: text };
  }
  if (args.cmd !== 'markers' && args.rest.length) return { code: 2, out: '', err: `sor.js: ${args.cmd} takes no ${args.rest[0]}\n${USAGE}\n` };
  try {
    const project = new index.model.Project(args.root);
    if (args.cmd === 'parts') return { code: 0, out: json(index.views.inOrder(project).map((pid) => index.views.partInfo(project.parts.get(pid)))), err: '' };
    const scan = new index.scan.Scan(project);
    return { code: 0, out: json(args.cmd === 'markers' ? markers(project, scan, args.rest[0]) : status(project, scan)), err: '' };
  } catch (e) {
    return { code: 2, out: '', err: `sor: ${e && e.message ? e.message : e}\n` };
  }
}

if (require.main === module) {
  const done = run(process.argv.slice(2));
  process.stdout.write(done.out);
  process.stderr.write(done.err);
  process.exitCode = done.code;
}
module.exports = { run, parse, markers, status };
