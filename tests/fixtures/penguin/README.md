# Penguin visual anchors, 2026-10-24

`english_shop_20261024.npz` contains the user's unmodified 1280×720 English
captures as `listing` and `popup` BGR arrays:

- `images/raws/epicseven 2026-10-24 01-12-19-27.png`
- `images/raws/epicseven 2026-10-24 01-12-31-48.png`

`stigma.png` (39×42) and `+1.png` (60×48) from the same raw directory are
copied to `images/penguin/`. `quantity_button.png` is the popup crop
`[x=869, y=449, width=78, height=48]`. Its central text is excluded by
`template_masks.json`.

Tests replay these captures, remove or change regions to check negative cases,
and simulate the numeric change to 50/50 after MAX. The completion frame uses
the existing close-arrow template on a blank image; no real completion capture
was provided. Tests do not connect to the game, spend currency, or prove live
purchase completion.
