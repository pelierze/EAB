# English exploration entry captures, 2026-10-24

`english_entry_20261024.npz` stores unmodified BGR arrays from the user's raw
screenshots. Raw files are ignored by Git, so these arrays make tests repeatable.

| Array | Original under `images/raws/` |
| --- | --- |
| `theme_unselected` | `employment_1.png` |
| `theme_selected` | `employment_2.png` |
| `tickets` | `hero_full_eng.png` |
| `knight_list` | `knight_filter_full_eng.png` |
| `party_complete` | `hero_full_selectd_eng.png` |
| `map` | `node_eng.png` |
| `filter_open` | `knight_filter_panel_eng.png` (added during implementation) |

`legacy_theme_1/2` are the original Korean theme template images from commit
49ef06e, retained to check recognition after replacing them with icon-only crops.

The other three new user inputs are runtime templates: `Employment_Pledge_1/2.png`
replace `select_supply_1/2.png`, and `filter.png` becomes `filter_symbol.png`.
The shared action-button reference is `[938,628,300,64]` from `employment_2.png`.

No selected individual hero card, initial exploration screen, node detail,
battle, or completion summary was supplied in this set.
Tests simulate phase changes and change button lettering to test exclusions;
they do not connect to the game or prove a complete English exploration run.

## Second batch: entry and battle

`english_battle_20261024.npz` contains seven unmodified BGR frames. Source names
and limitations are documented in `docs/i18n/exploration-english-battle.md`.
It adds actual selected hero/attribute, initial entry, battle detail/setup,
level-up and victory. The offline replay skips combat and sends no game inputs.

## Reported English rest detail

`english_rest_detail_20261024.npz` contains the unmodified BGR `screen` from
`logs/report/20261024_173442_158401_세션_1_30b8995c/screen.png`.
It reproduces the timeout after choosing Rest with the detail pane still open.
See `docs/i18n/exploration-detail-icons.md` for icon crops and validation scope.

## Reported English rest menu

`english_rest_menu_20261024.npz` contains the unmodified BGR `screen` from
`logs/report/20261024_213111_679066_세션_1_d0ef9bca/screen.png`.
The rest-menu tests mutate fire, flag, characters and captions; rank-menu text
is removed from Korean captures, and the English completion is synthetic.
See `docs/i18n/exploration-rest-menu.md` for scope and animation exclusions.
