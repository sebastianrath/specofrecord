"""Runs `do:` / `expect:` / `each:` tests (SPEC §8) against a web target's probes (SPEC §9).

Each test becomes JavaScript. The runner injects the tests into a copy of the target's page, next
to the original, opens it in headless Chrome or Edge over the DevTools protocol, and reads the
results and Chrome's coverage back.

The page must define `window.__probe`. Reads and actions are its members: a function is called
with the test's arguments (`body(earth)` → `__probe.body('earth')`), anything else is read as is.
Before each test the target's `before each test:` actions run. Built in: `count(x)` (length of a
list, or keys of an object), `overlaps(boxes)` (pairs of `{x, y, w, h}` boxes that intersect),
`offset(a, b)` (`{x, y}` of point a seen from point b) and `sentences(text)`.

Built-in metrics for `measure:`: `clause-coverage` (share of Rules and `gives` items proven by a
passing test, or by a manual check a person confirmed with `sor lock --confirm`; a rule that is
`Refined by` others is proven when all of them are) and `line-coverage` (share of marked code
lines that Chrome's coverage saw run).
Test strength (`strength`): every passing test is rerun with each value it refers to changed.
Not run yet: other `measure:` metrics (benchmarks) and `each: N × x = gen()` (generators).
"""
import json
import os
import re
import shutil
import time

from . import cdp
from . import lock as lockfile
from .invoke import getenv
from .markers import Scan
from .model import Item, ROOT_ALIASES, Row, join

NUM = re.compile(r'^-?\d+(?:\.\d+)?')
OPS = ['contains', 'is', '≈', '≤', '≥', '<=', '>=', '=', '<', '>']
BUILTINS = {'count', 'overlaps', 'offset', 'sentences'}
METRICS = {'clause-coverage', 'line-coverage'}
CHROMES = [
    getenv('CHROME'),
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
]


class Unsupported(Exception):
    pass


class TestError(Exception):
    """The test itself is wrong: a probe the target does not declare, an undefined value."""


def find_chrome():
    for c in CHROMES:
        if c and os.path.isfile(c):
            return c
    for name in ('google-chrome', 'chromium', 'chrome', 'msedge'):
        p = shutil.which(name)
        if p:
            return p
    return None


# --- the target ------------------------------------------------------------------------------
class WebTarget:
    def __init__(self, project, part):
        self.project, self.part = project, part
        delivery = next(i for i in part.items.values() if i.section == 'Rules' and 'path' in i.values)
        self.page = os.path.join(project.root, delivery.values['path'])
        probes = part.items.get('probes')
        if probes is None:
            raise TestError(f'{part.key} has no `gives **probes**` item')
        self.reads, self.actions, self.before = set(), set(), ''
        fields, cur = {}, None
        for _, t in probes.lines[1:]:
            m = re.match(r'^\s+(read|do|gen|metrics|before each test):\s*(.*)$', t)
            if m:
                cur = m.group(1)
                fields[cur] = m.group(2)
            elif cur:
                fields[cur] += ' ' + t.strip()
        self.metrics = set(_names(fields.get('metrics', '')))
        self.reads = set(_names(fields.get('read', '')))
        self.actions = set(_names(fields.get('do', '')))
        self.before = fields.get('before each test', '')


def _names(s):
    out, depth, word = [], 0, ''
    for ch in s + ',':
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            name = re.match(r'\s*([A-Za-z_]\w*)', word)
            if name:
                out.append(name.group(1))
            word = ''
        else:
            word += ch
    return out


def web_targets(project):
    out = []
    for p in project.parts.values():
        if p.id.startswith('targets/'):
            for it in p.items.values():
                if it.section == 'Rules' and it.values.get('path', '').endswith('.html'):
                    out.append(WebTarget(project, p))
                    break
    return out


# --- values ----------------------------------------------------------------------------------
def value_of(project, pid, ref, guard=()):
    """A {reference} in a test, as a JavaScript literal."""
    hits = project.resolve(pid, ref)
    if len(hits) != 1:
        raise TestError(f'{{{ref}}} does not resolve to one value')
    vid = hits[0]
    owner_id, _, name = vid.rpartition('.')
    owner = project.items.get(owner_id)
    if not owner_id or not isinstance(owner, (Item, Row)) or name not in owner.values:
        raise TestError(f'{{{ref}}} is not a value (write {{item.value}})')
    text = owner.values[name]
    if text.startswith('='):
        if vid in guard:
            raise TestError(f'{{{ref}}} refers to itself')
        item = owner if isinstance(owner, Item) else project.items[owner_id.rsplit('/', 1)[0]]
        return value_of(project, item.part.id, text[1:].strip(), guard + (vid,))
    m = NUM.match(text)
    if m:
        return m.group(0)
    return json.dumps(text)


# --- expressions -----------------------------------------------------------------------------
TOKEN = re.compile(r'\s*(?:(\{[^{}]+\})|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?)|([A-Za-z_][\w-]*)|(.))')


class Expr:
    """Turns a test expression into JavaScript, checking every probe against the target."""

    def __init__(self, test, src):
        self.test, self.src = test, src
        self.toks = [t for t in TOKEN.findall(src) if any(t)]
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else ('', '', '', '', '')

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def expect(self, ch):
        if self.take()[4] != ch:
            raise TestError(f'cannot read `{self.src}`: expected "{ch}"')

    def done(self):
        if self.i != len(self.toks):
            raise TestError(f'cannot read `{self.src}`')

    def literal(self):
        ref, string, num, ident, punct = self.take()
        if ref:
            return self.test.value(ref[1:-1])
        if string:
            return string
        if num:
            return num
        if ident:
            if ident in self.test.vars:
                return f'V[{json.dumps(ident)}]'
            return {'true': 'true', 'false': 'false', 'null': 'null'}.get(ident, json.dumps(ident))
        raise TestError(f'cannot read `{self.src}`')

    def args(self, each):
        out = []
        self.expect('(')
        if self.peek()[4] == ')':
            self.take()
            return out
        while True:
            out.append(each())
            t = self.take()[4]
            if t == ')':
                return out
            if t != ',':
                raise TestError(f'cannot read `{self.src}`: expected "," or ")"')

    def value(self):
        ref, string, num, ident, punct = self.peek()
        if not ident or ident in ('true', 'false', 'null'):
            return self.literal()
        self.take()
        if ident in self.test.vars and self.peek()[4] != '(':
            js = f'V[{json.dumps(ident)}]'
        elif ident in BUILTINS:
            js = f'B.{ident}({", ".join(self.args(self.value))})'
        else:
            if ident not in self.test.target.reads:
                raise TestError(f'`{ident}` is not a read probe of {self.test.target.part.key}')
            args = self.args(self.literal) if self.peek()[4] == '(' else []
            js = 'R(' + ', '.join([json.dumps(ident)] + args) + ')'
        while self.peek()[4] == '.':
            self.take()
            field = self.take()[3]
            if not field:
                raise TestError(f'cannot read `{self.src}`: a field name must follow "."')
            js = f'F({js}, {json.dumps(field)})'
        return js

    def sum(self):
        """Values added or subtracted: `{bars.top} + {fit.room}`. Clauses hold the values; a test
        may combine them, never write new ones."""
        js = self.value()
        while self.peek()[4] in ('+', '-') or (self.peek()[2].startswith('-') and self.i):
            if self.peek()[4]:
                op = self.take()[4]
                js = f'({js} {op} {self.value()})'
            else:  # `- 5` written as `-5`
                js = f'({js} + {self.take()[2]})'
        return js

    def action(self):
        ident = self.take()[3]
        if ident not in self.test.target.actions:
            raise TestError(f'`{ident}` is not an action probe of {self.test.target.part.key}')
        args = self.args(self.literal) if self.peek()[4] == '(' else []
        return 'A(' + ', '.join([json.dumps(ident)] + args) + ')'


def split_op(src):
    """`lhs op rhs` at the first operator outside parentheses and quotes."""
    depth, quote = 0, False
    for i, ch in enumerate(src):
        if ch == '"':
            quote = not quote
        elif not quote and ch == '(':
            depth += 1
        elif not quote and ch == ')':
            depth -= 1
        elif not quote and depth == 0 and ch == ' ':
            for op in OPS:
                if src.startswith(f' {op} ', i):
                    return src[:i].strip(), op, src[i + len(op) + 2:].strip()
    return None


# --- tests -----------------------------------------------------------------------------------
class Test:
    def __init__(self, project, target, item):
        self.project, self.target, self.item = project, target, item
        self.id = item.id
        self.vars = set()
        self.used = []         # the {refs} the JavaScript refers to, in order
        self.override = None   # (ref, literal): test strength swaps one value
        self.steps = item.steps()   # (keyword, text)

    @property
    def manual(self):
        return any(k == 'manual' for k, _ in self.steps)

    def value(self, ref):
        js = value_of(self.project, self.item.part.id, ref)
        if ref not in self.used:
            self.used.append(ref)
        if self.override and self.override[0] == ref:
            return self.override[1]
        return js

    def js(self):
        """The test as the body of a JavaScript function, or None for a test that only measures."""
        loops = [v for k, v in self.steps if k == 'each']
        for v in loops:  # loop variables must be known before the body is translated
            m = re.match(r'^([A-Za-z_]\w*) in ', v)
            if m and m.group(1) != 'size':
                self.vars.add(m.group(1))
        body, remembered = [], set()
        for k, v in self.steps:
            if k == 'do':
                for act in [a.strip() for a in v.split('·') if a.strip()]:
                    body.append(self.do(act, remembered))
            elif k == 'expect':
                body.append(self.expectation(v, remembered))
        if not body:
            if self.measures():
                return None
            raise TestError('the test has no `do:`, `expect:` or `measure:` lines')
        code = '\n'.join(body)
        for loop in reversed(loops):
            code = self.loop(loop, code)
        return code

    def measures(self):
        """[(metric, op, wanted number)] of the test's `measure:` lines."""
        out = []
        for k, v in self.steps:
            if k != 'measure':
                continue
            m = re.match(r'^([a-z][\w-]*)\b.*?\s(≥|>=|≤|<=|>|<|=)\s*(.+)$', v)
            if not m:
                raise TestError(f'cannot read `measure: {v}`')
            metric, op, rhs = m.groups()
            if metric not in METRICS:
                if metric in self.target.metrics:
                    raise Unsupported(f'benchmarks (`measure: {metric}`) are not run yet')
                raise TestError(f'`{metric}` is not a metric of {self.target.part.key} '
                                f'(built in: {", ".join(sorted(METRICS))})')
            wanted = Expr(self, rhs.strip())
            js = wanted.literal()
            wanted.done()
            try:
                out.append((metric, op, float(js)))
            except ValueError:
                raise TestError(f'`measure: {v}` must compare with a number')
        return out

    def proves(self):
        """Ids of the items this test proves: the item it is named after, and every item that a
        reference in its `expect:` or `measure:` lines points into (SPEC §8)."""
        return self.project.proves(self.item)

    def loop(self, src, inner):
        m = re.match(r'^(\d+) rounds?$', src)
        if m:
            return f'for (let round = 0; round < {m.group(1)}; round++) {{\n{inner}\n}}'
        m = re.match(r'^([A-Za-z_]\w*) in (.+)$', src)
        if m:
            name, cases = m.group(1), [c.strip() for c in m.group(2).split(',')]
            if name == 'size':
                sizes = []
                for c in cases:
                    wh = re.match(r'^(\d+)x(\d+)$', c)
                    if not wh:
                        raise TestError(f'`{c}` is not a size like 1280x720')
                    sizes.append(f'[{wh.group(1)}, {wh.group(2)}]')
                if 'resize' not in self.target.actions:
                    raise TestError(f'`each: size` needs a resize action probe in {self.target.part.key}')
                return (f'for (const [w, h] of [{", ".join(sizes)}]) {{\nA("resize", w, h);\n'
                        f'{inner}\n}}')
            self.vars.add(name)
            lits = [NUM.match(c).group(0) if NUM.fullmatch(c) else json.dumps(c) for c in cases]
            return (f'for (const x of [{", ".join(lits)}]) {{\nV[{json.dumps(name)}] = x;\n'
                    f'{inner}\n}}')
        if '×' in src:
            raise Unsupported('generated inputs (`each: N × x = gen()`) are not run yet')
        raise TestError(f'cannot read `each: {src}`')

    def do(self, act, remembered):
        m = re.match(r'^remember (.+)$', act)
        if m:
            what = m.group(1).strip()
            e = Expr(self, what)
            js = e.value()
            e.done()
            remembered.add(what)
            return f'M[{json.dumps(what)}] = clone({js});'
        m = re.match(r'^([A-Za-z_]\w*) = (.+)$', act)
        if m:
            e = Expr(self, m.group(2))
            js = e.action() if re.match(r'^[A-Za-z_]\w*\s*\(', m.group(2)) and \
                m.group(2).split('(')[0].strip() in self.target.actions else e.value()
            e.done()
            self.vars.add(m.group(1))
            return f'V[{json.dumps(m.group(1))}] = {js};'
        e = Expr(self, act)
        js = e.action()
        e.done()
        return js + ';'

    def old(self, lhs, remembered):
        """JavaScript for the remembered reading that lhs compares against."""
        for r in sorted(remembered, key=len, reverse=True):
            if lhs == r or lhs.startswith(r + '.'):
                js = f'M[{json.dumps(r)}]'
                for field in [f for f in lhs[len(r):].split('.') if f]:
                    js = f'F({js}, {json.dumps(field)})'
                return js
        raise TestError(f'`{lhs}` is compared with an earlier reading, but nothing was remembered')

    def expectation(self, src, remembered):
        msg = json.dumps(f'expect: {src}')
        m = re.match(r'^(.+?) unchanged$', src)
        if m:
            lhs = m.group(1).strip()
            e = Expr(self, lhs)
            now = e.value()
            e.done()
            return (f'{{ const a = {now}, b = {self.old(lhs, remembered)}; '
                    f'check(same(a, b), {msg}, a, b); }}')
        m = re.match(r'^(.+?) changed by (.+)$', src)
        if m:
            lhs, rhs = m.group(1).strip(), m.group(2).strip()
            e = Expr(self, lhs)
            now = e.value()
            e.done()
            delta = f'(({now}) - ({self.old(lhs, remembered)}))'
            for op, js_op in (('≤', '<='), ('≥', '>='), ('<', '<'), ('>', '>')):
                if rhs.startswith(op + ' '):
                    return (f'{{ const a = {delta}, b = {self.rhs(rhs[len(op):].strip())}; '
                            f'check(a {js_op} b, {msg}, a, b); }}')
            want, tol = self.tolerance(rhs)
            return f'{{ const a = {delta}, b = {want}; check(near(a, b, {tol}), {msg}, a, b); }}'
        parts = split_op(src)
        if not parts:
            raise TestError(f'cannot read `expect: {src}`')
        lhs, op, rhs = parts
        e = Expr(self, lhs)
        now = e.value()
        e.done()
        if op in ('=', '≈', 'is'):
            want, tol = self.tolerance(rhs)
            test = f'near(a, b, {tol})' if tol != 'null' else 'same(a, b)'
        elif op == 'contains':
            want, test = self.rhs(rhs), 'has(a, b)'
        else:
            want = self.rhs(rhs)
            test = f'a {dict(zip(["≤", "≥", "<=", ">=", "<", ">"], ["<=", ">=", "<=", ">=", "<", ">"]))[op]} b'
        return f'{{ const a = {now}, b = {want}; check({test}, {msg}, a, b); }}'

    def rhs(self, src):
        e = Expr(self, src)
        js = e.sum()
        e.done()
        return js

    def tolerance(self, src):
        """(value, tolerance) for `v`, `v ± t` or `v ± t%`; tolerance 'null' means exact."""
        if '±' not in src:
            return self.rhs(src), 'null'
        v, t = [s.strip() for s in src.split('±', 1)]
        want = self.rhs(v)
        if t.endswith('%'):
            return want, f'Math.abs({want}) * {float(t[:-1]) / 100}'
        if not NUM.fullmatch(t):
            raise TestError(f'a tolerance is a number or a percentage, not `{t}`')
        return want, t


PRELUDE = r'''
const clone = v => v === undefined ? undefined : JSON.parse(JSON.stringify(v));
const show = v => { try { return JSON.stringify(v); } catch (e) { return String(v); } };
function P() {
  if (!window.__probe) throw new Error('window.__probe is missing: the target probes are not built');
  return window.__probe;
}
function R(name, ...args) {
  const p = P();
  if (!(name in p)) throw new Error('read probe "' + name + '" is not built');
  return typeof p[name] === 'function' ? p[name](...args) : p[name];
}
function A(name, ...args) {
  const p = P();
  if (typeof p[name] !== 'function') throw new Error('action probe "' + name + '" is not built');
  return p[name](...args);
}
function F(v, field) {
  if (v === null || v === undefined) throw new Error('no field "' + field + '" on ' + show(v));
  return v[field];
}
const B = {
  count: v => Array.isArray(v) ? v.length : v == null ? 0 : typeof v === 'object' ? Object.keys(v).length : Number(v),
  offset: (a, b) => ({ x: a.x - b.x, y: a.y - b.y }),
  sentences: s => (String(s).match(/[.!?](\s|$)/g) || []).length,
  overlaps: boxes => {
    let n = 0;
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) n++;
    }
    return n;
  },
};
const same = (a, b) => typeof a === 'number' && typeof b === 'number'
  ? Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b)) : show(a) === show(b);
const near = (a, b, tol) => typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) <= tol + 1e-9;
const has = (a, b) => typeof a === 'string' ? a.includes(b)
  : Array.isArray(a) && (Array.isArray(b) ? b : [b]).every(x => a.some(y => same(x, y)));
function check(ok, what, a, b) { if (!ok) throw new Error(what + ' — got ' + show(a) + ', want ' + show(b)); }
'''


def harness(target, compiled, before_js):
    tests = ',\n'.join(
        f'[{json.dumps(tid)}, function (M, V) {{\n{js}\n}}]' for tid, js in compiled)
    return f'''
<script>
(function () {{
{PRELUDE}
const TESTS = [
{tests}
];
function before() {{
{before_js}
}}
function run() {{
  // one test per page load, so no test sees what an earlier one left behind
  const which = Number(new URLSearchParams(location.search).get('sor-test'));
  const out = [];
  for (const [id, fn] of TESTS.filter((t, i) => i === which)) {{
    try {{
      try {{ before(); }} catch (e) {{ throw new Error('before each test: ' + e.message); }}
      fn({{}}, {{}});
      out.push({{id, status: 'pass'}});
    }} catch (e) {{
      out.push({{id, status: 'fail', message: e.message}});
    }}
  }}
  return out;
}}
window.addEventListener('load', () => setTimeout(() => {{
  let res;
  try {{ res = run(); }} catch (e) {{ res = [{{id: '*', status: 'fail', message: e.message}}]; }}
  window.__sorResults = {{run: location.search, out: res}};
}}, 100));
}})();
</script>
'''


RUNNABLE = ('do', 'expect', 'measure')   # the steps `sor test` itself runs


def runnable(item):
    """Whether the test has steps (`do:`, `expect:`, `measure:`) for `sor test` to run."""
    return any(k in RUNNABLE for k, _ in item.steps())


def external(item, scan):
    """Whether the test is written in the project's own framework: it has no steps of its own and its code is marked
    `@clause test`. `sor test` neither runs nor fails it; its result comes from `sor lock --results`."""
    return not runnable(item) and bool(scan.regions_for(item.id))


def selects(project, item, only):
    """Whether the ids given to `sor test` choose this test: its own id, an item it proves (SPEC §8), a part, or a folder of parts."""
    if not item.is_test:
        return False
    proves = project.proves(item) | {join(item.part.id, item.target_name)}
    only = ['' if o in ROOT_ALIASES else o for o in only]   # the root part is called ROOT
    return any(item.id == o or item.id.startswith(o + '/') or item.part.id == o or o in proves for o in only)


def deferral(item, only=None, provides=None, everything=False):
    """Why a test that says `runs on:` is not run now, or None when it is. A run provides the environments it was given
    (`--provides`), says `--all`, or names the test by its own id; any other run leaves the test to the CI jobs that provide
    one of its environments. A test that does not say `runs on:` is always run."""
    envs = item.runs_on()
    if not envs or everything or item.id in (only or ()):
        return None
    if provides and any(set(env) <= provides for env in envs):
        return None
    return 'runs on ' + ', '.join('+'.join(env) for env in envs) + ': left to the CI jobs that provide it'


def run(project, only=None, timeout=90, confirmed=(), provides=None, everything=False):
    """Runs the tests. Returns (results, summary): results is {test id: {'status': pass|fail|
    skipped|manual|external|deferred, 'message': …}}; deferred says `runs on:` and this run does not provide its environments;
    external is a test without steps whose code is marked `@clause test`:
    it is not run here and not failed, and its result comes from the project's own run. The summary holds clause
    coverage and the line coverage per clause."""
    results, tests, measured = {}, {}, []
    targets = web_targets(project)
    if not targets:
        raise SystemExit('no web target: a targets/*.md part whose Rules give a `path` ending in .html')
    target = targets[0]
    compiled = []
    # confirmed: manual checks a person confirms in the same `sor lock` that runs these tests
    scan = Scan(project)
    checked = lockfile.checked_manual(project, scan, lockfile.read(project)) | set(confirmed)
    for item in project.all_items():
        if not item.is_test or (only and not selects(project, item, only)):
            continue
        why = None if lockfile.is_manual(item) else deferral(item, only, provides, everything)
        if why:
            results[item.id] = {'status': 'deferred', 'message': why}
            continue
        t = Test(project, target, item)
        tests[t.id] = t
        if t.manual:
            why = next(v for k, v in t.steps if k == 'manual')
            ok = t.id in checked
            results[t.id] = {'status': 'manual', 'checked': ok,
                             'message': why + (' · confirmed by a person' if ok else '')}
            continue
        if not runnable(item):
            # no steps for `sor test` to run: a test written in the project's own framework, when its code is marked
            made = scan.regions_for(t.id)   # only `@clause test` code is ever keyed to a test
            if external(item, scan):
                results[t.id] = {'status': 'external', 'message': f'test code at {made[0].where}; its result comes from '
                                                                   'your own test run (sor lock --results)'}
            else:
                results[t.id] = {'status': 'fail', 'message': 'test error: the test has no `do:`, `expect:` or `measure:` lines. '
                                 'Written in your own framework? Mark its code `// @clause test <id>`, in a folder the web '
                                 'target declares (a rule with `{path: test/}`)'}
            continue
        try:
            ms = t.measures()
            js = t.js()
        except Unsupported as e:
            results[t.id] = {'status': 'skipped', 'message': str(e)}
            continue
        except TestError as e:
            results[t.id] = {'status': 'fail', 'message': f'test error: {e}'}
            continue
        if js is not None:
            compiled.append((t.id, js))
        if ms:
            measured.append((t, ms))
    before_js = before_each(project, target)
    lines = {}
    if compiled or measured:
        page_results, lines = run_page(target, harness(target, compiled, before_js),
                                       [c[0] for c in compiled], timeout)
        for r in page_results:
            results[r['id']] = {k: v for k, v in r.items() if k != 'id'}
    summary = coverage(project, target, tests, results, lines, {t.id for t, _ in measured})
    for t, ms in measured:
        if results.get(t.id, {}).get('status') == 'fail':
            continue
        got = {'clause-coverage': summary['clause_coverage'], 'line-coverage': summary['line_coverage']}
        bad, said = [], []
        for metric, op, want in ms:
            value = got[metric]
            if value is None:
                bad.append(f'{metric}: nothing was measured')
                continue
            said.append(f'{metric} {value:.0f}%')
            ok = {'≥': value >= want, '>=': value >= want, '>': value > want, '≤': value <= want,
                  '<=': value <= want, '<': value < want, '=': abs(value - want) < 1e-9}[op]
            if not ok:
                bad.append(f'{metric} is {value:.1f}%, want {op} {want:g}%')
        results[t.id] = ({'status': 'fail', 'message': '; '.join(bad)} if bad
                         else {'status': 'pass', 'message': ', '.join(said)})
    return dict(sorted(results.items())), summary


def before_each(project, target):
    """JavaScript for the target's `before each test:` actions."""
    try:
        before_test = Test(project, target, target.part.items['probes'])
        return '\n'.join(before_test.do(a.strip(), set()) for a in target.before.split('·') if a.strip())
    except TestError as e:
        raise SystemExit(f'before each test in {target.part.key}: {e}')


def changed(literal):
    """The changed versions of a value's JavaScript literal: a number 10% up and down (0 becomes
    1 and -1), a text with a character added."""
    if NUM.fullmatch(literal):
        n = float(literal)
        return [format(n * 1.1, '.12g'), format(n / 1.1, '.12g')] if n else ['1', '-1']
    return [json.dumps(json.loads(literal) + '~')]


def strength(project, only=None, timeout=90, provides=None, everything=False):
    """Test strength (SPEC §8). Each passing test is rerun once for every changed version of every
    {value} its `do:` and `expect:` lines refer to; only the literal in the test's JavaScript
    changes, not the clauses or the page. Returns (results, weak, reruns, idle): weak is {test id:
    [(ref, value, changed values)]} for the values whose every change still passes (the test cannot
    fail on it); idle is {test id: why} for the passing tests with nothing to change, which strength
    says nothing about."""
    results, _ = run(project, only, timeout, provides=provides, everything=everything)
    target = web_targets(project)[0]
    mutants, keys, idle = [], [], {}
    for item in project.all_items():
        if item.id not in results or results[item.id]['status'] != 'pass':
            continue
        t = Test(project, target, item)
        if t.js() is None:
            idle[t.id] = 'it only measures'
            continue
        before = len(mutants)
        for ref in list(t.used):
            literal = t.value(ref)
            for alt in changed(literal):
                t.override = (ref, alt)
                mutants.append((f'{t.id} {{{ref}}} = {alt}', t.js()))
                keys.append((t.id, ref, literal, alt))
            t.override = None
        if len(mutants) == before:
            idle[t.id] = 'it refers to no {value} to change' if not t.used else 'the values it refers to cannot be changed'
    passed = {}
    if mutants:
        out, _ = run_page(target, harness(target, mutants, before_each(project, target)),
                          [m[0] for m in mutants], timeout)
        status = {r['id']: r['status'] for r in out}
        for (tid, ref, literal, alt), (mid, _) in zip(keys, mutants):
            passed.setdefault((tid, ref, literal), []).append((alt, status.get(mid) == 'pass'))
    weak = {}
    for (tid, ref, literal), alts in passed.items():
        if all(ok for _, ok in alts):
            weak.setdefault(tid, []).append((ref, literal, [a for a, _ in alts]))
    return results, dict(sorted(weak.items())), len(mutants), dict(sorted(idle.items()))


def coverage(project, target, tests, results, lines, exclude):
    """Clause coverage (SPEC §8: share of Rules and `gives` items proven by a passing test) and line
    coverage (share of marked code lines that ran), overall and per clause."""
    universe = sorted(i.id for i in project.all_items() if i.section == 'Rules' or i.kind == 'gives')
    proven = set()
    for tid, r in results.items():
        passed = r['status'] == 'pass' or (r['status'] == 'manual' and r.get('checked'))
        if passed and tid in tests and tid not in exclude:
            proven |= tests[tid].proves()
    # SPEC §5: following refinements down to tested rules is how a goal is proven
    refined = {}
    for item in project.all_items():
        for n, t in item.lines:
            if 'Refined by' in t:
                refs = [ref for m, ref in item.refs if m == n]
                hits = [project.resolve(item.part.id, ref) for ref in refs]
                refined[item.id] = [h[0] for h in hits if len(h) == 1]
    grew = True
    while grew:
        grew = False
        for iid, parts in refined.items():
            if iid not in proven and parts and all(p in proven for p in parts):
                proven.add(iid)
                grew = True
    by_clause, ran, total = {}, 0, 0
    rel = os.path.relpath(target.page, project.root).replace(os.sep, '/')
    for r in Scan(project).regions:
        if r.file != rel:
            continue
        lines_of = [r.start] if r.kind == 'line' else range(r.start + 1, (r.end or r.start))
        for n in lines_of:
            if n not in lines:
                continue
            total += 1
            ran += lines[n]
            for k in r.keys:
                c = by_clause.setdefault(k, [0, 0])
                c[0] += lines[n]
                c[1] += 1
    return {
        'clause_coverage': 100 * len(proven & set(universe)) / len(universe) if universe else None,
        'unproven': [i for i in universe if i not in proven],
        'line_coverage': 100 * ran / total if total else None,
        'lines': (ran, total),
        'by_clause': dict(sorted(by_clause.items())),
    }


def lines_run(source, functions, start_line):
    """{file line: ran} for the code lines of one script, from Chrome's block coverage. Ranges
    nest, so the innermost range at a line's first character decides. Offsets are UTF-16 units."""
    units = len(source.encode('utf-16-le')) // 2
    counts = [0] * units
    ranges = sorted((r for f in functions for r in f['ranges']),
                    key=lambda r: r['startOffset'] - r['endOffset'])
    for r in ranges:
        a, b = r['startOffset'], min(r['endOffset'], units)
        counts[a:b] = [r['count']] * (b - a)
    out, offset = {}, 0
    for i, line in enumerate(source.split('\n')):
        code = line.strip()
        if code and not code.startswith('//'):
            lead = len(line[:len(line) - len(line.lstrip())].encode('utf-16-le')) // 2
            out[start_line + 1 + i] = counts[offset + lead] > 0 if offset + lead < units else False
        offset += len(line.encode('utf-16-le')) // 2 + 1
    return out


def run_page(target, script, ids, timeout):
    """(results, {line: ran}) for the tests in `script`, run inside the target's page."""
    if not os.path.isfile(target.page):
        return ([{'id': i, 'status': 'fail', 'message': f'{target.page} does not exist: nothing is built'}
                 for i in ids], {})
    chrome = find_chrome()
    if not chrome:
        raise SystemExit('no Chrome or Edge found; set SOR_CHROME to its path')
    with open(target.page, encoding='utf8') as fh:
        page = fh.read()
    cut = page.lower().rfind('</body>')
    cut = cut if cut >= 0 else len(page)
    injected_at = page[:cut].count('\n') + 1          # first line of the tests in the copy
    page = page[:cut] + script + page[cut:]
    # next to the original, so relative paths in the page still work
    path = os.path.join(os.path.dirname(target.page), '.sor-test-' + os.path.basename(target.page))
    url = 'file:///' + os.path.abspath(path).replace(os.sep, '/').lstrip('/')
    results, lines = [], {}
    try:
        with open(path, 'w', encoding='utf8', newline='\n') as fh:
            fh.write(page)
        try:
            started = cdp.Chrome(chrome, timeout=timeout)
        except RuntimeError as e:   # it exited, or never opened its debugging port (a sandbox, a bad install)
            raise SystemExit(f'{e} ({chrome}); set SOR_CHROME to the path of another Chrome or Edge')
        with started as browser:
            p = browser.page
            p.call('Debugger.enable')
            p.call('Profiler.enable')
            p.call('Profiler.startPreciseCoverage', callCount=True, detailed=True)
            deadline = time.time() + timeout
            # a fresh page for every test; with no tests, one load still measures coverage
            for i, tid in (list(enumerate(ids)) or [(-1, None)]):
                query = f'?sor-test={i}'
                p.call('Page.navigate', url=url + query)
                raw = ''
                while not raw and time.time() < deadline:
                    try:
                        raw = p.call('Runtime.evaluate', returnByValue=True, expression=(
                            f"window.__sorResults && window.__sorResults.run === {json.dumps(query)}"
                            " ? JSON.stringify(window.__sorResults.out) : ''")).get('result', {}).get('value') or ''
                    except RuntimeError:
                        pass  # the page is still loading
                    if not raw:
                        time.sleep(0.05)
                if tid is not None:
                    out = json.loads(raw) if raw else [{'id': tid, 'status': 'fail',
                                                        'message': 'the page reported no result in time'}]
                    results += [{**o, 'id': tid} if o.get('id') == '*' else o for o in out]
                covered = p.call('Profiler.takePreciseCoverage')['result']
                parsed = {e['params']['scriptId']: e['params'] for e in p.events
                          if e.get('method') == 'Debugger.scriptParsed'}
                for entry in covered:
                    info = parsed.get(entry['scriptId'])
                    if not info or info.get('url') != url + query or info['startLine'] + 1 >= injected_at:
                        continue  # another page's script, or the tests themselves
                    source = p.call('Debugger.getScriptSource', scriptId=entry['scriptId'])['scriptSource']
                    for n, ran in lines_run(source, entry['functions'], info['startLine']).items():
                        lines[n] = lines.get(n, False) or ran
    finally:
        if os.path.exists(path):
            os.remove(path)
    return results, lines
