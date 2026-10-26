// Takes the screenshots of the README (macOS): starts a real VS Code on a temporary copy of examples/solar-system, lets
// test/screenshots-suite.js set up one scene after another, and captures the window of VS Code (only that region of the
// screen) each time the suite says a scene is ready.
// usage: node test/screenshots.js [output folder] [path to Code]    (default folder: ../images)
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { runTests } = require('@vscode/test-electron');

const out = path.resolve(process.argv[2] || path.join(__dirname, '..', 'images'));
const code = process.argv[3] || '/Applications/Visual Studio Code.app/Contents/MacOS/Code';
const BOUNDS = { x: 60, y: 45 };   // in points; each scene says how big its window is, so an image shows only the few lines it is about
const TITLE = 33;   // the title bar is cropped off: it names the Extension Development Host
const WIDTH = 800;  // pixels: the images are scaled down, a README does not need the retina size

/** Removes every metadata segment of a JPEG (JFIF, EXIF, XMP, the colour profile, comments: all APPn and COM) and keeps the picture. */
function stripMetadata(file) {
  const data = fs.readFileSync(file);
  const out = [data.subarray(0, 2)];
  for (let i = 2; i < data.length;) {
    const marker = data[i + 1];
    if (marker === 0xda) { out.push(data.subarray(i)); break; }   // the picture itself follows
    const length = data.readUInt16BE(i + 2);
    if (!((marker >= 0xe0 && marker <= 0xef) || marker === 0xfe)) out.push(data.subarray(i, i + 2 + length));
    i += 2 + length;
  }
  fs.writeFileSync(file, Buffer.concat(out));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const osa = (script) => execFileSync('osascript', ['-e', script], { encoding: 'utf8' });

if (process.platform !== 'darwin') { console.error('the screenshots are taken on macOS (screencapture, osascript)'); process.exit(2); }
if (/"IOConsoleLocked"\s*=\s*Yes/.test(execFileSync('/usr/sbin/ioreg', ['-n', 'Root', '-d1'], { encoding: 'utf8' }))) {
  console.error('the screen is locked: unlock it and run this again'); process.exit(2);
}

(async () => {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'sor-shots-'));
  const project = path.join(work, 'solar-system');
  fs.cpSync(path.resolve(__dirname, '..', '..', '..', 'examples', 'solar-system'), project, { recursive: true });
  const data = path.join(work, 'user-data');
  fs.mkdirSync(path.join(data, 'User'), { recursive: true });
  fs.writeFileSync(path.join(data, 'User', 'settings.json'), JSON.stringify({
    'workbench.startupEditor': 'none', 'workbench.tips.enabled': false, 'window.restoreWindows': 'none', 'workbench.colorTheme': 'Default Dark Modern',
    'editor.minimap.enabled': false, 'breadcrumbs.enabled': false, 'workbench.layoutControl.enabled': false, 'window.commandCenter': false,
    'workbench.activityBar.location': 'hidden', 'workbench.secondarySideBar.defaultVisibility': 'hidden', 'telemetry.telemetryLevel': 'off',
    'update.mode': 'none', 'editor.fontSize': 13, 'editor.lineHeight': 21, 'workbench.editor.showTabs': 'multiple', 'editor.stickyScroll.enabled': false,
    'editor.codeLens': true, 'editor.renderWhitespace': 'none', 'editor.wordWrap': 'on', 'security.workspace.trust.enabled': false,
  }, null, 2));
  const signals = path.join(work, 'signals');
  fs.mkdirSync(signals);
  fs.mkdirSync(out, { recursive: true });

  let done = false;
  // only the window of the temporary project: another VS Code of the same user has windows of its own, which are never touched or captured.
  // The test window belongs to a process of its own that has the same name, so every process called Code is searched for a window of the project.
  const placeWindow = ({ w, h }) => osa(`tell application "System Events"
    repeat with p in (every process whose name is "Code")
      repeat with w in (every window of p)
        if name of w contains "solar-system" then
          set frontmost of p to true
          set position of w to {${BOUNDS.x}, ${BOUNDS.y}}
          set size of w to {${w}, ${h}}
          perform action "AXRaise" of w
          return "ok"
        end if
      end repeat
    end repeat
    return "none"
  end tell`).trim() === 'ok';
  // A scene first asks for its window size (`.place`), because resizing closes a hover, then sets itself up and asks for the capture (`.ready`).
  let size = { w: 1000, h: 300 };
  const place = async (name, wanted) => {
    size = wanted;
    for (let n = 0; n < 20 && !placeWindow(size); n++) await sleep(500);
    await sleep(1200);   // the editor lays itself out again
    fs.writeFileSync(path.join(signals, name + '.placed'), '');
  };
  const shoot = async (name) => {
    if (!placeWindow(size)) throw new Error('the window of the project is gone');
    const raw = path.join(signals, name + '.raw.png'), file = path.join(out, name + '.jpg');
    execFileSync('screencapture', ['-x', '-R', `${BOUNDS.x},${BOUNDS.y + TITLE},${size.w},${size.h - TITLE}`, raw]);
    // a JPEG at 80% in sRGB, WIDTH pixels wide: a fraction of the PNG, and the colours stay what they were without the profile
    execFileSync('sips', ['-Z', String(WIDTH), '-m', '/System/Library/ColorSync/Profiles/sRGB Profile.icc', '-s', 'format', 'jpeg', '-s', 'formatOptions', '80', raw, '--out', file], { stdio: 'ignore' });
    stripMetadata(file);
    console.log('  shot ' + name);
    fs.writeFileSync(path.join(signals, name + '.done'), '');
  };
  const watcher = (async () => {
    const taken = new Set();
    while (!done) {
      for (const f of fs.readdirSync(signals)) {
        const m = /^(.*)\.(place|ready)$/.exec(f);
        if (m && !taken.has(f)) {
          taken.add(f);
          if (m[2] === 'place') await place(m[1], JSON.parse(fs.readFileSync(path.join(signals, f), 'utf8')));
          else await shoot(m[1]);
        }
      }
      await sleep(300);
    }
  })();

  try {
    await runTests({
      vscodeExecutablePath: code,
      extensionDevelopmentPath: path.resolve(__dirname, '..'),
      extensionTestsPath: path.resolve(__dirname, 'screenshots-suite.js'),
      extensionTestsEnv: { SOR_SHOTS_SIGNALS: signals },
      launchArgs: [project, '--disable-extensions', '--user-data-dir', data],
    });
  } finally {
    done = true;
    await watcher;
    fs.rmSync(work, { recursive: true, force: true });
  }
})().catch((e) => { console.error('screenshots failed', e.message); process.exit(1); });
