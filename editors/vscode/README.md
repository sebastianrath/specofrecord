# Spec of Record for VS Code

[Spec of Record](https://specofrecord.org) is a way to build software from a written spec: short, plain sections, with the code built from them. This extension shows which code belongs to which section, and whether the two still match.

It starts on its own in a project that uses Spec of Record, needs no setup, and never changes a file.

## Spec and code, side by side

![The spec on the left, the code built from it on the right: the spec section under the cursor lights its code](images/overview.jpg)

Put your cursor in a spec section and the code built from it lights up on the other side. A small line above the section says where that code is (`out/index.html:72-74`); click it to jump there. It works the other way too: click into the code and its spec sections light up.

When the status bar reads `0 drift · 0 review · 0 recompile` and there are no colored dots in the margin, spec and code match and there is nothing to do.

## Which section is this line for?

![Hovering a line of code shows the spec sections behind it](images/hover.jpg)

Hover over a line of generated code to see the spec sections behind it, in their own words, with their state. `in sync` means the code matches the section.

The comment lines that tie code to a section are folded out of sight so the code reads normally. The files themselves don't change.

## When spec and code disagree

A colored dot in the margin, a note above the section and the counts in the status bar tell you where. Hover a line to read what its mark means.

When more than one applies to a line, the most urgent shows: red, then amber, then blue.

### Red: the code changed, the spec didn't

![A red dot on the table row and on the line of code, and a drift flag above it](images/drift.jpg)

Someone, or an AI, changed this code, and the spec still says the old thing. Decide which is right: update the spec to match the code, or put the code back. The status bar counts it as `1 drift`. In a git project, the hover also says who changed the line.

### Blue: the spec changed, the code hasn't caught up

![A blue dot on the changed spec section and on its code, and a to-recompile flag above it](images/recompile.jpg)

The section was changed or is new, and its code hasn't been rebuilt yet. Update the code to match, by hand or with your AI assistant. The note above the section says `● to recompile`.

### Amber: something this depends on changed

![Amber dots on a test that refers to a value which changed on the right](images/review.jpg)

This section or test refers to something that changed. Here the test uses the length of the year, and the year was changed to 366 days on the right. Nothing is necessarily wrong, but check that it still holds.

### Grey ring: no code yet

![Grey rings on spec sections without code, and a hover that explains them](images/no-code.jpg)

No code is marked for this section, or for the part of the spec it belongs to. For a quality like "calm" or "no errors in the console" that's often fine. For a section that describes behavior, it's something still to build. The ring is a quiet hint: any red, amber or blue on the same section replaces it.

## Spec files that read like notes

While you work, spec files show formatted: bold, `code`, headings, `{references}` and `{name: value}` lose their marks. The marks come back where your cursor or selection touches them, so you can still edit. Only the display changes, never the file.

| Preview off | Preview on |
|---|---|
| ![A spec file with all its marks](images/preview-off.jpg) | ![The same spec file formatted](images/preview-on.jpg) |

## Also

- **Follow a reference.** In a spec file, Ctrl+click (Cmd+click on macOS) a `{reference}` to go to the section or value it names. If it names nothing, the hover says so. Typing `{` lists what you can refer to.
- **Jump to code.** Go to Definition on a `code: out/index.html#name` line opens that code.
- **Syntax colors** for spec files.

## Commands and settings

Open the Command Palette and type `Spec of Record`.

| Command | Does |
|---|---|
| Spec of Record: Refresh | reads the project again (this also happens when files change) |
| Spec of Record: Toggle marker lines | shows or hides the comment lines that tie code to a section |
| Spec of Record: Toggle live preview | switches spec files between formatted and plain |
| Spec of Record: Show code of this clause | jumps to a section's code, and asks which when there are several places |

| Setting | Default | Does |
|---|---|---|
| `sor.hideMarkerLines` | `true` | hides those comment lines (display only) |
| `sor.livePreview` | `true` | shows spec files formatted while you type |

## Requirements

VS Code 1.80 or later, and a project that uses [Spec of Record](https://specofrecord.org). Nothing else to install: a small JavaScript program inside the extension reads the project, using the editor's own Node.

## Developing the extension

`npm test` runs the grammar test, a check of the bundled tool, and a real VS Code on `examples/solar-system`. The bundled copy in `tools/` comes from the repository's `tools/js` via `sh plugins/sync-tools.sh`; never edit it by hand.

The screenshots come from a real VS Code on a temporary copy of `examples/solar-system`. `node test/screenshots.js` retakes them into `images/` (macOS, VS Code installed, screen unlocked). It only touches the window it starts, and anything you type meanwhile goes into that window. They aren't part of the packaged extension.
