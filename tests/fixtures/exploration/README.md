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

## Reported English supply menu

`english_supply_menu_20261024.npz` contains the unmodified BGR `screen` from
`logs/report/20261024_220455_435636_세션_1_c8e7491d/screen.png`.
Tests replace chest lid/effects, party and captions, retain the lower chest
body, and replay menu selection with loot handling stubbed. Completion uses
the Korean source with captions erased. See `docs/i18n/exploration-supply-menu.md`.

## Reported English recruitment ticket

`english_recruit_ticket_20261024.npz` contains the unmodified BGR `screen` from
`logs/report/20261024_221929_282738_세션_1_347b9fad/screen.png`.
It is a real Soul Weaver ticket. Other class cases use composited references;
the confirmation replay removes text from the Korean dialog. No game inputs
are sent. See `docs/i18n/exploration-recruit-ticket.md` for recognition and limits.

## English battle loot and unclaimed warning

`english_battle_loot_20261024.npz` contains unmodified BGR `screen` from
`images/raws/epicseven 2026-10-24 22-35-24-17.png` and `warning` from
`logs/report/20261024_223840_086656_세션_1_ebee785c/screen.png`.
These are real English captures. Caption removal and missing-component cases
are synthetic. See `docs/i18n/exploration-battle-loot.md` for scope and limits.

`english_battle_background_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_080018_895193_세션_1_4b8c8d58/screen.png`.
It reproduces a translucent-card border mismatch against a different battle
background. Background replacement and missing-notch cases are synthetic.

`english_supply_background_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_080552_812310_세션_1_318b38dd/screen.png`.
It covers a supply menu with a wrapped English recruitment caption and a
different background appearance. Caption/sparkle changes and dimming are synthetic.

`english_battle_all_ticket_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_081743_242797_세션_1_bc15cb18/screen.png`.
It is a real English victory with loot and an All-Class recruitment ticket.
Claim acknowledgement and missing-component cases are synthetic; loot selection
and hero confirmation are covered separately, with no live game input.

`english_rest_active_recovery_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_082618_801870_세션_1_56731009/screen.png`.
It has an active fourth recovery option. Caption/sparkle changes and the completed
rank-up state are synthetic; the reported screen itself is a real English capture.

`english_loot_selection_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_083543_712824_세션_1_a4af2fba/screen.png`.
It is a real English unselected loot screen. Selected-edge and active-button
states use Korean reference fragments composited into this capture; the claim
replay uses a Korean victory return. No live game input is sent.

`english_supply_geometry_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_085445_188886_세션_1_116df12c/screen.png`.
It reproduces the supply menu missed by both existing frame references.
Shifted buttons and textless shop confirmations are synthetic. See
`docs/i18n/exploration-noncombat-coordinates.md` for the verified-entry workflow.

`english_shop_detail_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_134118_404480_세션_1_b56d85b8/screen.png`.
It is the actual English shop detail pane with a scales icon. Caption changes
and missing-icon cases are synthetic; the entry replay returns to a Korean shop
reference and sends no live game input.

`english_shop_live_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_141316_208863_세션_1_4095f375/screen.png`.
It is the actual English shop with Book of the Stars in the top-right slot.
Transient map frames and textless exit confirmations in replays are synthetic;
the forbidden icon detection uses the original unmodified screenshot.

`english_summary_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_150717_171001_세션_1_b281a9c6/screen.png`.
It is a real English final summary showing three defeated bosses. Label removal
and missing-icon cases are synthetic; the close replay uses a Korean entry frame.

`english_wukong_list_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_151724_706099_세션_1_8adc25ed/screen.png`.
It shows Immortal Wukong in the right column's second row. Name-area changes and
missing-portrait cases are synthetic. No scrolling or live game input is sent.

`english_event_warning_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_154241_744912_세션_1_9e9ddb79/screen.png`.
It is the actual English Vitals warning with buttons at y=465. Text removal,
button relocation, and missing controls are synthetic. Cancellation replays
return to Korean event choices and send no live game input.

`english_event_result_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_161602_505343_세션_1_aaac56c2/screen.png`.
It is the actual English Mimic result with a visible advance arrow. Arrow motion,
particles, and changed caption strokes are synthetic, and no live input is sent.

`english_rank_reward_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_174056_329023_세션_1_65a8c8b6/screen.png`.
It is the actual English rank reward after an event choice. Missing frames and
removed/randomized labels are synthetic. Rank-menu/return replays mock rank-up
selection and send no live game input.

`english_rank_result_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_202627_941056_세션_1_b8fcff98/screen.png`.
It is the actual English Wukong rank-up result in a rest node. Removed text,
numbers, portraits, symbols, and panel borders are synthetic; replay tests send
no live game input.

`english_max_rank_result_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_214241_238891_세션_1_1276a97f/screen.png`.
It shows the actual English 4-to-5(Max) result. Symbol-only screens, horizontal
spacing changes, wrong ordering/alignment, and extra marks are synthetic.

`english_event_choice_warning_20261025.npz` contains unmodified BGR `screen` from
`logs/report/20261025_223947_421098_세션_1_b68b614c/screen.png`.
Its modal top border fails the global warning check while both text-masked
buttons match. Pair-only images, missing/duplicate buttons, and choice/cancel
replays are synthetic and send no live game input.

`english_eye_intro_choices_20261026.npz` contains unmodified BGR `intro` and
`choices` from `logs/report/20261026_165257_926063_세션_1_f8a6e673/screen.png`
and `epicseven 2026-10-26 20-27-51-91.png` in that same report folder.
The choices capture was supplied by the user after the error. Partial narration,
missing/moved corners, and erased choice labels are synthetic. Replay exercises
the real bot tap wrapper against a mocked ADB client; no live input is sent.

`english_battle_rewards_20261026.npz` contains unmodified BGR `screen` from
`logs/report/20261026_231704_938283_세션_1_5e1cf611/screen.png`.
The center loot card's old border check failed despite a valid chest and pill.
Icon-only rewards and removed/changed frames, captions, and backgrounds are
synthetic. No live input is sent.

`english_two_consume_slots_20261027.npz` contains unmodified BGR `screen` from
`logs/report/20261027_064559_766741_세션_1_d08fdcaf/screen.png`.
It shows seven inventory items and two empty sacrifice slots. Keys `partial`,
`full`, `reward`, `result` contain the actual followups from `images/raws/1.PNG`
through `4.PNG`, cropped at [x=1, y=31, w=1280, h=720] to remove window chrome
without resizing. Other multi-slot states and alternate positions/counts are
synthetic. Actual statue/leaf replay overrides only the candidate order to match
the user's captures. Replays use mocked ADB and send no live game input.
