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
