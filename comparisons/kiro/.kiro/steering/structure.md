---
inclusion: always
---

# Structure

- `out/index.html` is the whole app. Its first comment block lists the choices and
  assumptions made while building (the "notes"), and names the spec it was built from.
- Inside the file, code is grouped by component, in this order, each under a heading comment:
  `// == Bodies ==`, `// == Clock ==`, `// == Camera ==`, `// == Scene ==`,
  `// == Controls ==`, `// == Selection ==`, `// == Probe ==`.
  Markup comments use `<!-- -->`, CSS `/* */`, JavaScript `//`.
- Where a block implements an acceptance criterion, its heading comment names it, for example
  `// Req 6.1 zoom step`. (Guess: Kiro has no traceability marker of its own; this is a
  convention the agent follows because this file tells it to, nothing checks it.)
- `tests/` holds one test file per component, named after it (`clock.test.js` ...). Each test
  names the requirement it validates in its title, for example `"Req 4.2 speed curve"`.
- Never edit `out/index.html` without the matching requirement first; see `spec-first.md`.
