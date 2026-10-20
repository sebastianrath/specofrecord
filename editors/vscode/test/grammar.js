// Runs the Spec of Record grammar on test/sample.md (and on any file given as argument) and checks scopes.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vsctm = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');

(async () => {
  const wasm = fs.readFileSync(path.join(require.resolve('vscode-oniguruma'), '..', 'onig.wasm')).buffer;
  await oniguruma.loadWASM(wasm);
  const registry = new vsctm.Registry({
    onigLib: Promise.resolve({
      createOnigScanner: (p) => new oniguruma.OnigScanner(p),
      createOnigString: (s) => new oniguruma.OnigString(s),
    }),
    loadGrammar: async (scope) => (scope === 'text.html.markdown.sor'
      ? vsctm.parseRawGrammar(fs.readFileSync(path.join(__dirname, '..', 'syntaxes', 'sor.tmLanguage.json'), 'utf8'), 'sor.json')
      : null),   // text.html.markdown is VS Code's own; not needed for these checks
  });
  const grammar = await registry.loadGrammar('text.html.markdown.sor');

  /** [{text, scopes}] per line (scopes without the root). */
  function tokenize(text) {
    let stack = vsctm.INITIAL;
    return text.split(/\r?\n/).map((line) => {
      const r = grammar.tokenizeLine(line, stack);
      stack = r.ruleStack;
      return r.tokens.map((t) => ({ text: line.slice(t.startIndex, t.endIndex), scopes: t.scopes.slice(1) }));
    });
  }
  const lines = tokenize(fs.readFileSync(path.join(__dirname, 'sample.md'), 'utf8'));
  const has = (token, scope) => token.scopes.some((s) => s.startsWith(scope));
  const find = (text, scope, from = 0) => {
    for (const l of lines.slice(from)) for (const t of l) if (t.text.trim() === text && has(t, scope)) return true;
    return false;
  };
  const table = [
    ['Why', 'keyword.other.header.sor'], ['Owner', 'keyword.other.header.sor'],
    ['Rules', 'markup.heading.section.rules.sor'], ['Approach', 'markup.heading.section.approach.sor'],
    ['Contract', 'markup.heading.section.contract.sor'], ['Tests', 'markup.heading.section.tests.sor'],
    ['limits', 'entity.name.type.item.sor'], ['gives', 'keyword.other.contract.sor'],
    ['needs', 'keyword.other.contract.sor'], ['owns', 'keyword.other.contract.sor'],
    ['max', 'variable.other.constant.value-name.sor'], ['200', 'constant.numeric.value.sor'],
    ['characters', 'keyword.other.unit.sor'], ['#FFC93C', 'constant.numeric.value.sor'],
    ['50', 'constant.numeric.value.sor'], ['ms', 'keyword.other.unit.sor'],
    ['clock/now', 'variable.other.reference.sor'], ['list-time.budget', 'variable.other.reference.sor'],
    ['because', 'keyword.control.approach.sor'], ['limit', 'keyword.control.approach.sor'],
    ['do', 'keyword.control.test.sor'], ['expect', 'keyword.control.test.sor'], ['each', 'keyword.control.test.sor'],
    ['measure', 'keyword.control.test.sor'], ['bug', 'keyword.control.test.sor'], ['proves', 'keyword.control.test.sor'],
    ['is', 'keyword.operator.word.sor'], ['changed by', 'keyword.operator.word.sor'],
    ['unchanged', 'keyword.operator.word.sor'], ['remember', 'keyword.other.remember.sor'],
    ['=', 'keyword.operator.comparison.sor'], ['±', 'keyword.operator.comparison.sor'],
    ['≤', 'keyword.operator.comparison.sor'], ['body', 'entity.name.function.probe.sor'],
    ['`people`', 'markup.inline.raw'],
    // the plain format: the same scopes for the words that mean the same
    ['Run', 'keyword.other.header.sor'],
    ['Rules', 'markup.heading.section.rules.sor'], ['How it works', 'markup.heading.section.approach.sor'],
    ['Checks', 'markup.heading.section.tests.sor'],
    ['offers', 'keyword.other.contract.sor'], ['uses', 'keyword.other.contract.sor'],
    ['given', 'keyword.control.test.sor'], ['then', 'keyword.control.test.sor'],
    ['by eye', 'keyword.control.test.sor'], ['fixes', 'keyword.control.test.sor'],
    ['code', 'keyword.other.code.sor'], ['out/index.html#zoomAt', 'markup.underline.link.code.sor'],
  ];
  const seen = [];
  for (const [text, scope] of table) {
    const ok = find(text, scope) || [...lines.flat()].some((t) => t.text.startsWith(text) && has(t, scope));
    assert(ok, `"${text}" should have scope ${scope}`);
    seen.push(`${text.padEnd(18)} ${scope}`);
  }
  // nothing leaks: a plain sentence word carries no grammar scope
  const plain = lines.flat().find((t) => t.text.includes('keep a todo list'));
  assert(plain && !plain.scopes.some((s) => s.endsWith('.sor')), 'plain text stays plain');
  console.log(seen.join('\n'));
  console.log(`grammar ok: ${table.length} scope checks`);

  const extra = process.argv[2];
  if (extra) {   // dump the scopes of a real spec file
    tokenize(fs.readFileSync(extra, 'utf8')).forEach((l, n) => {
      const marks = l.filter((t) => t.scopes.some((s) => s.endsWith('.sor')))
        .map((t) => `${t.text}→${t.scopes.filter((s) => s.endsWith('.sor')).pop()}`);
      if (marks.length) console.log(`${String(n + 1).padStart(3)}  ${marks.join('  ')}`);
    });
  }
})().catch((e) => { console.error(e.message); process.exit(1); });
