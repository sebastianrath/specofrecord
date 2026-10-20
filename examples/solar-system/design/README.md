# Solar system design assets

Colors and bodies of the solar-system example, as a Figma file and as design tokens.

**Figma file:** [Solar System — assets and colors](https://www.figma.com/design/dWBbuElrInc7hOc6yaxdxP)

The design is the source of the colors: the clauses point at the tokens (`{design/planet/mars}`)
instead of holding colors themselves.

## What's in the file

- A variable collection "Solar System" with 24 color variables (`sky/background`, `body/sun`,
  `planet/mercury` … `planet/neptune`, `body/moon`, `saturn/ring`, `ui/…`, `comet/…`). Each has
  a scope, so it only shows up where it fits: fills, text or strokes.
- A page "Solar System" with two frames:
  - **Colors**: one labelled swatch per variable, its fill bound to that variable.
  - **Bodies**: the sun, the 8 planets and the moon on the sky color, with name and size under
    each. Diameter = 2 × size from `bodies.md`, drawn at 3× (1 space unit = 3 px). Saturn's
    ring is its own layer (`saturn/ring`).

## Change a color in Figma

Open the local variables panel (deselect everything, then Local variables in the right panel),
pick the "Solar System" collection and edit the value. Everything bound to that variable
updates: the swatch, the body and any design that uses it.

## Getting the change back as tokens.json

`tokens.json` uses the W3C Design Tokens format, with the same names as the variables
(`planet/mars` is `planet.mars`). Colors with transparency are 8-digit hex (`#RRGGBBAA`).
To bring Figma changes back, export the collection with a W3C/DTCG token export (Tokens Studio,
or a variables export) and replace `tokens.json` with the result.

The sor tool reads `tokens.json` (see `Design:` in `sor/SPECOFRECORD.md`): every token is a clause the
page is built from, `design/planet/mars` and so on, and every SVG in `assets/` is one too.
After an export, run `python tools/sor.py -C examples/solar-system status`. It lists the
changed tokens and the lines in `out/index.html` to rebuild. The colors are copied into the page
when it's built, so the page stays one file that works offline. The tests compare what is really
painted with the tokens (`colorOf`), so a color that didn't make it into the page fails a test.
