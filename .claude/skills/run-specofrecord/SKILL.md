---
name: run-specofrecord
description: Run, start, smoke test and screenshot Spec of Record in this repository. Drives the sor command on a temporary copy of examples/solar-system, serves and screenshots the project page (index.html) and the solar system example in the browser pane, and runs the tool's tests. Use it when asked to run, try, test or look at the tool, the website or the example.
---

# Running Spec of Record

Paths below are relative to the repository root. There are three things to drive. The `sor` command (a Python 3.9
standard library program), the project page `index.html` with its claims demo, and the solar system example page. The VS Code
extension is not covered, it was not run here.

Ground rules from `CLAUDE.md` still apply. Never run `lock` or `claim` against `examples/` or `editors/vscode`, always use a
temporary copy. `sor` here means `python3 tools/py/sor.py -C <project>`.

## Run (agent path)

### The sor command
The smoke script copies `examples/solar-system` into a temporary folder, runs eleven commands against the copy and
checks every exit code. It leaves `examples/` untouched and deletes its copy at the end. It takes a few seconds.

```bash
sh .claude/skills/run-specofrecord/smoke.sh
```

It ends with `smoke passed`. The commands it covers are `parts --tree`, `status`, `check`, `show clock`,
`markers out/index.html:137`, `claim clock --as smoke`, a refused second claim on the same clause and one on `year`, which only shares code with `clock` (both exit 3), `lock` (exit 2, see below),
`release --all --as smoke` and `test --list`. To try one command yourself, copy a project first. `sor.py` always needs `-C`.

```bash
T=$(mktemp -d) && cp -R examples/solar-system "$T/p" && python3 tools/py/sor.py -C "$T/p" show clock
```

### The project page and its claims demo
Start a static server from the repository root and open the page in the browser pane. Run the server from your own shell,
not from `.claude/launch.json` (see Gotchas). It blocks, so start it in the background (the Bash tool's `run_in_background`),
and check that it answers.

```bash
python3 -m http.server 8765 > /dev/null 2>&1 &
```

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/index.html
```

Then `preview_start` with the url `http://localhost:8765/index.html`. The demo under "Several agents can work on one
project at once" steps through eight stages by itself every 3.1 seconds. Read its state instead of waiting for a screenshot, using
`javascript_tool`.

```js
(async()=>{const sleep=ms=>new Promise(r=>setTimeout(r,ms));const out=[];for(let i=0;i<14;i++){await sleep(1700);out.push({a:document.querySelector('.clawd.a').dataset.mode,b:document.querySelector('.clawd.b').dataset.mode,cap:document.querySelector('.cl-text').textContent.slice(0,80)});}return JSON.stringify(out)})()
```

`data-mode` goes idle, then `detective` (agent on a spec) or `typing` (agent in code) once the jump has landed, and
`waiting` for the refused agent. To look at it, scroll the demo into view first. A plain `scrollIntoView` is smooth and
lands wrong, so do this and then take the screenshot in the next call.

```js
document.documentElement.style.scrollBehavior='auto';const r=document.querySelector('.cl-agents').getBoundingClientRect();window.scrollTo({top:scrollY+r.top-250,behavior:'instant'});await new Promise(r=>setTimeout(r,400));JSON.stringify({y:scrollY,mode:document.querySelector('.clawd.a').dataset.mode})
```

### The solar system example
Navigate to `http://localhost:8765/examples/solar-system/out/index.html`. The page exposes `window.__probe`, the same
hook the project's tests use. Body ids are lowercase.

```js
const p=window.__probe;p.setPaused(true);p.clickBody('saturn');await new Promise(r=>setTimeout(r,300));JSON.stringify({sel:p.selected,panel:p.panel,errors:p.errors})
```

That selects Saturn, and the panel reads "Saturn is less dense than water." with `errors` empty (the `no-errors` rule).

### Tests
```bash
python3 -m unittest discover -s tools/py -p 'test_sor_docs.py'
```

```bash
node tools/js/test/vectors.js
```

```bash
sh plugins/sync-tools.sh --check
```

The first two take a few seconds each. The third currently fails, see Gotchas. The whole suite is
`python3 -m unittest discover -s tools/py -p 'test_*.py'`. It takes about a minute here. The twelve minutes in `CLAUDE.md` are for the run with `SOR_COMPARE_JS=1`.

## Run (human path)
Open `examples/solar-system/out/index.html` from disk, or `index.html`, in any browser. Only the server path above was tried here.

## Gotchas
- **No Chrome or Edge on this machine.** `sor test` stops with `no Chrome or Edge found; set SOR_CHROME to its path`, so
  `sor lock --run-tests` is out too. A plain `sor lock` on a clause with tests is refused, exit 2, with `8 test(s) did not pass
  (0 failed, 8 not run)`. The smoke script expects that refusal. With a Chrome, set `SOR_CHROME=<path>` and run `sor test`
  on a copy of the example.
- **`sor test --list` runs nothing.** It is the only test command that works without Chrome.
- **`sor markers clock` says "clock has no code".** It is a part id, and the code hangs off its items (`clock/start`).
  Use an item id or a `file:line`.
- **A claim holds more than its own clause.** `sor claim clock` also locks out `screen/hud/controls`,
  `screen/hud/space`, `screen/ui-colors` and `year`, because they share code regions. The smoke script shows the line.
- **`preview_start` with a name fails.** A server started from `.claude/launch.json` by the app dies with
  `PermissionError: [Errno 1] Operation not permitted` in `os.getcwd()` (this repository sits under `~/Desktop`). Start the
  server from the shell and pass a `url` instead.
- **A pane screenshot is not a file on disk.** It lives in the tool results. To keep one, copy it out by hand.
- **`sh plugins/sync-tools.sh --check` can fail for no real reason.** A macOS `.DS_Store` inside
  `plugins/specofrecord/tools/` makes it say "the plugin is out of date" even though every tracked file matches. Delete that
  file and run it again. The `diff` in the script does not exclude it.
- **A console warning from PostHog on `index.html` is normal.** It is about `persistence: memory`, not an error.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `no such file or directory: python3 tools/py/sor.py -C ...` in zsh | The command was held in a variable and zsh did not split it. Use a function (`sor() { python3 tools/py/sor.py -C "$T/p" "$@"; }`) or the smoke script. |
| `Error: no body "Saturn"` from `clickBody` | Use the lowercase id, `clickBody('saturn')`. |
| Screenshot shows the footer, not the demo | The page scrolled on its own. Use the scroll snippet above, then screenshot. |
| `env: sor: No such file or directory` inside a script | `sor` is a shell function there, `env` cannot run it. Call `python3 tools/py/sor.py` or run it in a subshell. |

Stop the server with Ctrl-C, or run `pkill -f "http.server 8765"`.
