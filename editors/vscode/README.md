# Spec of Record for VS Code

[Spec of Record](https://specofrecord.org) is a way to build software from a written spec: short, plain sections, with the code built from them. This extension shows you, right in the editor, which code belongs to which section of the spec, and whether the two still match.

It turns on by itself in a project that uses Spec of Record, and there is nothing to set up. It only reads: it never changes a spec or a code file.

## Spec and code, side by side

![The spec on the left, the code built from it on the right: the spec section under the cursor lights its code](images/overview.jpg)

**What to expect here:** the spec section under your cursor is lit, and so is the code that was built from it on the other side. A small line above the section says where that code is (`out/index.html:72-74`), and clicking it jumps there. There is no colour in the margin, and the status bar at the bottom reads `0 drift · 0 review · 0 recompile`. That means the spec and the code match each other, and there is nothing to do.

It works the other way round too: put the cursor in the code and the spec sections it comes from are lit.

## Which spec section is this line of code for?

![Hovering a line of code shows the spec sections behind it](images/hover.jpg)

**What to expect here:** hover over any line of generated code and you see every spec section behind it, with its own words and its state. `in sync` means the code matches the section. The comment lines that tie code to a spec section are folded out of the way, so the code reads normally. (The files themselves never change.)

## When spec and code disagree

A coloured dot in the margin, a note on the lens above the section, and the counts in the status bar tell you where. Hover the line to read what a mark means in words.

### Red: the code changed, the spec section did not

![A red dot on the table row and on the line of code, and a drift flag on the lens](images/drift.jpg)

**What to expect here:** someone, or an AI, changed this code, and the spec still says the old thing. The spec is the source of truth, so decide which one is right. Either update the spec so it says what the code now does, or put the code back. The status bar counts it as `1 drift`. When the project is in git, the hover also says who changed the line.

### Blue: the spec section changed, the code has not followed

![A blue dot on the changed spec section and on its code, and a to-recompile flag on the lens](images/recompile.jpg)

**What to expect here:** the spec section was changed (or is new), and its code has not been rebuilt from it yet. Update the code to match the section, by hand or with your AI assistant. The lens says `● to recompile`.

### Amber: something this depends on changed

![Amber dots on a test that refers to a value which changed on the right](images/review.jpg)

**What to expect here:** this spec section, or this test, refers to something that changed. Here the test uses the length of the year, and the year was changed to 366 days on the right. Nothing is necessarily wrong, but check that it still holds.

### Grey ring: nothing implements this spec section yet

![Grey rings on spec sections without code, and a hover that explains them](images/no-code.jpg)

**What to expect here:** no code is marked for this spec section, and none for the part of the spec it belongs to. For a section about a quality, like "calm" or "no errors in the console", that is often fine. For a section that describes behaviour it is a gap that still needs building. It is a quiet note: when a spec section also has a red, amber or blue state, that colour is shown instead.

When several states apply to one line, the worst one wins: red, then amber, then blue.

## Live preview of spec files

Spec files read like a formatted note while you work. Bold text, `code`, headings, `{references}` and `{name: value}` lose their marks and show styled, and inline code is one small box. The marks come back only where your cursor or selection touches that one piece, so you can still edit it. Nothing in the file changes; it is only how the editor draws it.

| Live preview off | Live preview on |
|---|---|
| ![A spec file with all its marks](images/preview-off.jpg) | ![The same spec file formatted](images/preview-on.jpg) |

## More

- **Jump to what a reference names.** In a spec file, Ctrl+click (Cmd+click on macOS) a `{reference}` to go to the spec section or value it points to. A reference that points to nothing says so on hover. Typing `{` offers the spec sections and values you can refer to.
- **Jump to the code.** Go to Definition on a `code: out/index.html#name` line opens that code.
- **Syntax colours** for the spec files.

## Commands and settings

Open the Command Palette and type `Spec of Record`.

| Command | Does |
|---|---|
| Spec of Record: Refresh | reads the project again (it also happens by itself when files change) |
| Spec of Record: Toggle marker lines | shows or hides the comment lines that tie code to a spec section |
| Spec of Record: Toggle live preview | formatted or plain spec files |
| Spec of Record: Show code of this clause | jumps to the code of a spec section, and asks which when it has several places |

| Setting | Default | Does |
|---|---|---|
| `sor.hideMarkerLines` | `true` | hide the comment lines that tie code to a spec section (display only; the files never change) |
| `sor.livePreview` | `true` | show spec files formatted while you type |

## Requirements

VS Code 1.80 or later, and a project that uses [Spec of Record](https://specofrecord.org). Nothing else has to be installed: everything is read by a small JavaScript program that ships inside the extension and runs on the editor's own Node.

## Developing the extension

`npm test` runs the grammar test, a check of the bundled tool, and a real VS Code on `examples/solar-system`. The bundled copy in `tools/` is made from the repository's `tools/js` by `sh plugins/sync-tools.sh`; never edit it by hand.

The screenshots above come from a real VS Code on a temporary copy of `examples/solar-system`: `node test/screenshots.js` takes them again into `images/` (macOS, with VS Code installed and the screen unlocked; it only touches the window it starts, and anything typed meanwhile goes into that window). They are not part of the packaged extension.
