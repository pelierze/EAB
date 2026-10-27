"""Replay the English screenshots added after the Stigma reference."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from build_support.release_assets import used_images
from src.chaos.bot import PartyRecruitmentBot
from src.chaos.node_observer import NodeObserver
from src.chaos.observer import RecruitmentObserver
from src.chaos.template_masks import apply_exclusions
from src.image_matcher import read_image


ROOT = Path(__file__).resolve().parents[1]


class ExplorationEnglishAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(ROOT / 'tests/fixtures/exploration/english_entry_20261024.npz') as data:
            cls.frames = {key: data[key] for key in data.files}
        cls.recruitment = RecruitmentObserver(ROOT, ['shadow_rose', 'wukong', 'lisette', 'rhianna_luciella'])
        cls.nodes = NodeObserver(ROOT)

    def test_language_free_theme_icons_work_on_english_and_legacy_korean_sources(self):
        for key, expected in (('theme_unselected', 'unselected'), ('theme_selected', 'selected'),
                              ('legacy_theme_1', 'unselected'), ('legacy_theme_2', 'selected')):
            with self.subTest(frame=key):
                self.assertEqual(self.recruitment.theme.observe(self.frames[key]).state, expected)
        for key in ('tickets', 'party_complete', 'knight_list', 'map'):
            self.assertEqual(self.recruitment.theme.observe(self.frames[key]).state, 'unknown')

    def test_english_recruitment_tickets_are_located_by_class_and_button_border(self):
        for hero, x in zip(self.recruitment.heroes, (112, 392, 672, 952)):
            with self.subTest(hero=hero['id']):
                self.assertEqual(self.recruitment.class_button(self.frames['tickets'], hero), (x, 490, 216, 48))
                self.assertIsNone(self.recruitment.class_button(self.frames['party_complete'], hero))
        self.assertFalse(self.recruitment.completed(self.frames['tickets']))
        self.assertTrue(self.recruitment.completed(self.frames['party_complete']))

    def test_filter_symbol_and_hero_portrait_do_not_use_english_names(self):
        screen = self.frames['knight_list']
        observer = RecruitmentObserver(ROOT, ['ras'])
        self.assertEqual(observer.find(screen, 'filter'), (700, 24, 21, 18))
        self.assertIsNotNone(observer.header(screen, observer.heroes[0]))
        self.assertIsNotNone(observer.find(screen, 'ras'))
        self.assertIsNone(observer.find(screen, 'filter_panel'))

    def test_select_and_entry_borders_reject_inactive_buttons(self):
        self.assertIsNotNone(self.nodes.find(self.frames['party_complete'], 'enter'))
        self.assertIsNotNone(self.recruitment.find(self.frames['theme_selected'], 'confirm_theme'))
        for key in ('theme_unselected', 'tickets', 'knight_list', 'map'):
            with self.subTest(frame=key):
                self.assertIsNone(self.nodes.find(self.frames[key], 'enter'))
                self.assertIsNone(self.recruitment.find(self.frames[key], 'recruit_active'))

    def test_changed_button_text_does_not_affect_recognition(self):
        rng = np.random.default_rng(24)
        party = self.frames['party_complete'].copy()
        party[634:686, 956:1220] = rng.integers(0, 256, (52, 264, 3), dtype=np.uint8)
        self.assertEqual(self.nodes.find(party, 'enter'), (938, 628, 300, 64))
        tickets = self.frames['tickets'].copy()
        for x in (112, 392, 672, 952):
            tickets[497:531, x+22:x+194] = rng.integers(0, 256, (34, 172, 3), dtype=np.uint8)
        for hero in self.recruitment.heroes:
            self.assertIsNotNone(self.recruitment.class_button(tickets, hero))

    def test_shared_purple_button_alone_does_not_authorize_theme_or_hero_action(self):
        bot = object.__new__(PartyRecruitmentBot)
        bot.observer = self.recruitment
        bot.active_hero = self.recruitment.heroes[0]
        # A completed party has the same purple button, but no theme card.
        self.assertIsNotNone(self.recruitment.find(self.frames['party_complete'], 'confirm_theme'))
        self.assertIsNone(bot._theme_confirm(self.frames['party_complete']))
        # Force an active button onto an unselected hero list. Its portrait
        # does not have a verified selection border, so recruitment is denied.
        screen = self.frames['knight_list'].copy()
        screen[628:692, 938:1238] = self.frames['theme_selected'][628:692, 938:1238]
        self.assertIsNotNone(self.recruitment.find(screen, 'recruit_active'))
        self.assertIsNone(bot._recruit(screen))

    def test_resume_from_english_theme_selects_once_then_waits_for_ticket_screen(self):
        observer = RecruitmentObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        with tempfile.TemporaryDirectory() as tmp:
            bot = PartyRecruitmentBot(Mock(), ROOT, tmp, observer=observer)
            current = ['theme_unselected']
            taps = []
            bot._capture = lambda: self.frames[current[0]]
            bot._record = Mock()
            def tap(bounds):
                taps.append(bounds)
                current[0] = 'theme_selected' if len(taps) == 1 else 'tickets'
            bot._tap = tap
            def recruit():
                self.assertEqual(current[0], 'tickets')
                current[0] = 'party_complete'
            bot._recruit_all = recruit
            self.assertEqual(bot.run()['status'], 'completed')
            self.assertEqual(taps, [(123, 150, 76, 88), (938, 628, 300, 64)])

    def test_english_map_is_recognized_without_text(self):
        self.assertEqual(self.nodes.classify(self.frames['map']), 'map')
        self.assertIsNone(self.nodes.find(self.frames['map'], 'enter'))
        self.assertEqual(self.nodes.choose_node(self.frames['map']), ('battle', (190, 310, 83, 79)))

    def test_mask_definition_errors_and_duplicate_targets_fail_closed(self):
        template = np.ones((10, 20, 3), dtype=np.uint8)
        for rectangles in ([[-1, 0, 2, 2]], [[0, 0, 21, 10]], [[0, 0, 20, 10]]):
            with self.subTest(rectangles=rectangles), self.assertRaises(ValueError):
                apply_exclusions(template, rectangles, 'invalid')
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        source = self.nodes.templates['enter'][:, :, :3]
        for x in (100, 700):
            screen[200:264, x:x+300] = source
        self.assertIsNone(self.nodes.find(screen, 'enter', (0, 0, 1280, 720)))

    def test_runtime_assets_are_included_without_raw_english_captures(self):
        assets = set(used_images(ROOT))
        self.assertIn('images/chaos/hero_selection/templates/controls/exploration_action.png', assets)
        self.assertIn('images/chaos/hero_selection/templates/controls/filter_symbol.png', assets)
        self.assertFalse(any(path.startswith('images/raws/') for path in assets))

    def test_open_english_filter_panel_uses_frame_and_element_symbols(self):
        screen = self.frames['filter_open']
        self.assertEqual(self.recruitment.find(screen, 'filter_panel'), (65, 65, 870, 335))
        bot = object.__new__(PartyRecruitmentBot)
        bot.observer = self.recruitment
        bot.active_hero = self.recruitment.heroes[0]
        self.assertIsNone(bot._filter_button(screen))
        self.assertEqual(bot._element_state(screen),
                         ('unselected', *self.recruitment.find(screen, 'dark_1')))
        # Text labels are neither loaded nor used to authorize filter actions.
        self.assertNotIn('filter_element_label', self.recruitment.templates)

    def test_filter_lettering_can_change_but_frame_alone_is_insufficient(self):
        screen = self.frames['filter_open'].copy()
        rng = np.random.default_rng(24)
        for x, y, w, h in ((82, 80, 320, 31), (432, 80, 280, 31),
                           (82, 178, 320, 32), (432, 177, 260, 31),
                           (98, 124, 300, 37), (460, 288, 300, 70)):
            screen[y:y+h, x:x+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        self.assertIsNotNone(self.recruitment.find(screen, 'filter_panel'))
        screen[110:170, 495:840] = 0
        self.assertIsNone(self.recruitment.find(screen, 'filter_panel'))

    def test_filter_open_select_sequence_uses_symbols_with_no_game_input(self):
        observer = RecruitmentObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0, filter_settle_seconds=0)
        selected = self.frames['filter_open'].copy()
        x, y, w, h = observer.find(selected, 'dark_1')
        template = observer.templates['dark_2']
        th, tw = template.shape[:2]
        tx, ty = x + (w-tw)//2, y + (h-th)//2
        selected[y-4:y+h+4, x-4:x+w+4] = 245
        selected[ty:ty+th, tx:tx+tw] = template
        with tempfile.TemporaryDirectory() as tmp:
            bot = PartyRecruitmentBot(Mock(), ROOT, tmp, observer=observer)
            frames = [self.frames['knight_list'], self.frames['filter_open'], selected]
            index = [0]
            taps = []
            bot._capture = lambda: frames[index[0]]
            bot._record = Mock()
            def tap(bounds):
                taps.append(bounds)
                index[0] += 1
            bot._tap = tap
            bot._configure_element_filter()
            self.assertEqual(taps, [(700, 24, 21, 18), (x, y, w, h)])


if __name__ == '__main__':
    unittest.main()
