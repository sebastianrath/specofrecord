# Security

## Reporting a problem

Please report a security problem privately, not in a public issue. Use GitHub's private reporting:
[report a vulnerability](https://github.com/sebastianrath/specofrecord/security/advisories/new).
Say what you found, the steps to reproduce it and which part is affected. You will get an answer as soon as it can be
looked at, and a fix is credited to you if you want that.

## What is in scope

The tools run on your machine, so these matter most:

- **The Claude Code plugin's hooks** (`plugins/specofrecord/hooks/hooks.json`) run `python3` on `tools/sor.py` before and
  after edits, reads and shell commands. A way to make them run something else, or to read or write outside the project,
  is a vulnerability.
- **The `sor` command** reads and writes a project's `sor/` folder, its code files, `sor-lock.json` and the claims files,
  and `sor test` starts a headless Chrome. A path or input that makes it touch files outside the project is a vulnerability.
- **The VS Code extension** runs the bundled JavaScript tool (`tools/`) on the editor's own Node and never changes the
  files it shows.
- **The release builds** attach the plugin zip and the `.vsix` to a GitHub release with a build attestation. Check a
  download with `gh attestation verify <file> --repo sebastianrath/specofrecord`.

The tools use only the standard library of Python and Node's own modules, so there are no runtime dependencies to track.

## Supported versions

Only the latest release of the plugin and of the extension gets fixes.
