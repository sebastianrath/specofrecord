// Integration test: starts VS Code on a copy of a Spec of Record project and checks the four features.
// usage: node test/run.js <project folder> [path to Code.exe]
const path = require('path');
const { execFile, execFileSync } = require('child_process');
const { runTests } = require('@vscode/test-electron');

// The test drives a real editor window: folding and the viewport only change when that window can take focus. On a
// locked macOS screen no window can, and the failure then looks like a bug in the folding ("marker line 72 is folded
// away"), so the locked screen is named before VS Code is started.
function screenIsLocked() {
  if (process.platform !== 'darwin') return false;
  try {
    return /"IOConsoleLocked"\s*=\s*Yes/.test(execFileSync('/usr/sbin/ioreg', ['-n', 'Root', '-d1'], { encoding: 'utf8' }));
  } catch (e) {
    return false;
  }
}
if (screenIsLocked()) {
  console.error('the screen is locked: this test needs a window that can take focus. Unlock the screen and run it again.');
  process.exit(2);
}

// Folding, the viewport and the cursor only react in a window that has focus, and a window started from a script is not put
// in front by macOS: another app in front (a terminal, a chat) made the test fail in different places on different runs.
// So the test window is brought to the front every two seconds while the test runs (macOS only).
function keepInFront() {
  if (process.platform !== 'darwin') return () => {};
  const bring = () => execFile('osascript', ['-e', 'tell application "System Events" to set frontmost of process "Code" to true'], () => {});
  const timer = setInterval(bring, 2000);
  return () => clearInterval(timer);
}

(async () => {
  const stopFront = keepInFront();
  // an argument is relative to where the command runs; the default is relative to this file, so it works from any folder
  const project = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(__dirname, '..', '..', '..', 'examples', 'solar-system');
  try {
    await runTests({
      vscodeExecutablePath: process.argv[3] || undefined,
      extensionDevelopmentPath: path.resolve(__dirname, '..'),
      extensionTestsPath: path.resolve(__dirname, 'suite.js'),
      launchArgs: [project, '--disable-extensions', '--user-data-dir', path.join(require('os').tmpdir(), 'sor-vscode-test')],
    });
    stopFront();
  } catch (e) {
    stopFront();
    console.error('tests failed', e.message);
    process.exit(1);
  }
})();
