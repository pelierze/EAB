import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class RestMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_rest_menu_20261024.npz') as data:
            cls.english = data['screen']
        with np.load(ROOT / 'tests/fixtures/exploration/english_rest_active_recovery_20261025.npz') as data:
            cls.latest = data['screen']

    def frame(self, name):
        return read_image(str(RAW / name))

    def test_real_english_menu_uses_active_top_option_and_textless_leave(self):
        self.assertEqual(self.observer.classify(self.english), 'rest')
        self.assertEqual(self.observer.find(self.english, 'detail_rest'), (905, 148, 330, 94))
        self.assertEqual(self.observer.find(self.english, 'leave'), (938, 628, 300, 64))

    def test_latest_rest_with_active_fourth_option(self):
        self.assertEqual(self.observer.classify(self.latest), 'rest')
        self.assertEqual(self.observer.find(self.latest, 'detail_rest'), (905, 148, 330, 94))
        self.assertEqual(self.observer.find(self.latest, 'rest_option_4'), (905, 478, 330, 94))

    def test_latest_wrapped_captions_and_sparkles_are_excluded(self):
        screen = self.latest.copy()
        rng = np.random.default_rng(25)
        for y in (148, 258, 368, 478):
            for x0, y0, w, h in self.observer.config['markers']['detail_rest']['exclude']:
                screen[y+y0:y+y0+h, 905+x0:905+x0+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        self.assertEqual(self.observer.rest_controls(screen), self.observer.rest_controls(self.latest))

    def test_latest_fourth_option_cannot_replace_missing_scene_or_top_activation(self):
        for x, y, w, h in ((250, 235, 90, 65), (905, 478, 330, 94)):
            screen = self.latest.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.find(screen, 'detail_rest'))
        screen = self.latest.copy()
        screen[148:242, 905:1235] //= 2
        self.assertIsNone(self.observer.find(screen, 'detail_rest'))
        self.assertIsNone(self.observer.find(screen, 'rest_done'))

    def test_fire_flag_and_character_animation_are_outside_observation_regions(self):
        screen = self.english.copy()
        rng = np.random.default_rng(24)
        for x, y, w, h in ((540, 40, 240, 140), (500, 450, 245, 175),
                           (350, 330, 140, 295), (750, 350, 150, 275)):
            screen[y:y+h, x:x+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        self.assertEqual(self.observer.rest_controls(screen), self.observer.rest_controls(self.english))
        self.assertEqual(self.observer.classify(screen), 'rest')

    def test_menu_and_leave_captions_can_change(self):
        screen = self.english.copy()
        rng = np.random.default_rng(42)
        for y in (148, 258, 368, 478):
            screen[y+20:y+78, 925:1215] = rng.integers(0, 256, (58, 290, 3), dtype=np.uint8)
        screen[634:686, 956:1220] = 0
        self.assertEqual(self.observer.classify(screen), 'rest')
        self.assertIsNotNone(self.observer.find(screen, 'detail_rest'))
        self.assertIsNotNone(self.observer.find(screen, 'leave'))

    def test_menu_geometry_and_both_static_patches_are_required(self):
        for x, y, w, h in ((250, 235, 90, 65), (700, 230, 80, 50), (905, 368, 330, 94)):
            screen = self.english.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(rectangle=(x, y, w, h)):
                self.assertIsNone(self.observer.rest_controls(screen))
                self.assertIsNone(self.observer.find(screen, 'detail_rest'))

    def test_other_options_may_change_activation_without_changing_top_selection(self):
        screen = self.english.copy()
        for y in (258, 368, 478):
            screen[y:y+94, 905:1235] = np.minimum(
                screen[y:y+94, 905:1235].astype(np.float32) * 1.5, 255).astype(np.uint8)
        self.assertEqual(self.observer.rest_controls(screen), self.observer.rest_controls(self.english))
        active_frame = self.english[148:242, 905:1235]
        for y in (258, 368, 478):
            screen[y:y+94, 905:1235] = active_frame
        self.assertEqual(self.observer.rest_controls(screen), self.observer.rest_controls(self.english))

    def test_inactive_top_option_is_not_clicked_and_completion_needs_check(self):
        completed = self.frame('rest_completed_live.png')
        self.assertIsNotNone(self.observer.find(completed, 'rest_done'))
        self.assertIsNone(self.observer.find(completed, 'detail_rest'))
        completed[172:214, 1170:1213] = 0
        self.assertIsNone(self.observer.find(completed, 'rest_done'))
        self.assertIsNone(self.observer.find(completed, 'detail_rest'))
        dimmed = self.english.copy()
        dimmed[148:242, 905:1235] = (dimmed[148:242, 905:1235] * .5).astype(np.uint8)
        self.assertIsNone(self.observer.find(dimmed, 'detail_rest'))

    def no_rank_captions(self, screen):
        screen = screen.copy()
        screen[10:55, 60:300] = 0
        screen[82:107, 80:290] = 0
        for y in (98, 203, 308, 413):
            screen[y:y+27, 397:490] = 0
        screen[634:686, 956:1220] = 0
        return screen

    def test_rank_menu_and_target_selection_do_not_require_korean_names(self):
        unselected = self.no_rank_captions(self.frame('rest_rank_menu_live.png'))
        selected = self.no_rank_captions(self.frame('rest_wukong_selected_live.png'))
        self.assertEqual(self.observer.classify(unselected), 'rank_menu')
        self.assertIsNone(self.observer.find(unselected, 'rank_button'))
        self.assertEqual(self.observer.classify(selected), 'rank_menu')
        self.assertTrue(self.observer.rank_hero_selected(selected, 'wukong'))
        self.assertFalse(self.observer.rank_hero_selected(selected, 'shadow_rose'))
        self.assertIsNotNone(self.observer.find(selected, 'rank_button'))
        selected[393:407, 365:630] = 0
        self.assertIsNone(self.observer.find(selected, 'rank_button'))

    def test_class_icons_without_rank_layout_are_insufficient(self):
        screen = self.frame('rest_rank_menu_live.png')
        screen[65:605, :12] = 0
        self.assertFalse(self.observer.is_rank_menu(screen))
        for filename in ('battle_setup_live.png', 'rest_menu_live.png', 'map_after_rest_live.png'):
            self.assertFalse(self.observer.is_rank_menu(self.frame(filename)))

    def test_rank_menu_can_have_three_heroes_after_a_departure(self):
        screen = self.no_rank_captions(self.frame('rest_rank_menu_live.png'))
        screen[390:480, 345:645] = 0
        self.assertEqual(len(self.observer._rank_menu_rows(screen)), 3)
        self.assertTrue(self.observer.is_rank_menu(screen))
        screen[634:689, 308:366] = 0
        self.assertFalse(self.observer.is_rank_menu(screen))

    def test_rest_replay_selects_top_then_target_then_rank_then_leave(self):
        self.assert_rest_replay(self.english)

    def test_latest_rest_replay_selects_only_top_and_leaves_after_rankup(self):
        self.assert_rest_replay(self.latest)

    def assert_rest_replay(self, start):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=8, stable_frames=2, poll_seconds=0)
        complete = start.copy()
        complete[148:242, 905:1235] = self.frame('rest_completed_live.png')[148:242, 905:1235]
        complete[168:226, 925:1165] = 0  # synthetic translated completion, preserve check icon
        screens = [start, self.no_rank_captions(self.frame('rest_rank_menu_live.png')),
                   self.no_rank_captions(self.frame('rest_wukong_selected_live.png')),
                   self.frame('rest_wukong_rankup_live.png'), complete, self.frame('map_after_rest_live.png')]
        with tempfile.TemporaryDirectory() as tmp, patch.object(observer, 'forbidden', return_value=[]):
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=observer, rank_priority=['wukong'])
            index = [0]
            taps = []
            bot._capture = lambda: screens[index[0]]
            bot._record = Mock()
            def tap(bounds):
                taps.append(bounds)
                index[0] += 1
            bot._tap = tap
            bot._rest()
            self.assertEqual(len(taps), 5)
            self.assertEqual(taps[0], (905, 148, 330, 94))
            self.assertEqual(taps[-1], (938, 628, 300, 64))
            self.assertEqual(bot.stats['nodes'], 1)
            bot.adb.tap.assert_not_called()


if __name__ == '__main__':
    unittest.main()
