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


class LootSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_loot_selection_20261025.npz') as data:
            cls.screen = data['screen']
        cls.selected_source = read_image(str(RAW / 'loot_selected_live.png'))

    def selected(self, column=0):
        # Actual English selected capture is not yet supplied. Composite the
        # known selection edge and active button, leaving English card contents.
        screen = self.screen.copy()
        x = 185 + 320 * column
        screen[285:404, x:x+27] = self.selected_source[285:404, 185:212]
        screen[626:696, 473:807] = self.selected_source[626:696, 473:807]
        screen[634:688, 501:779] = 0  # arbitrary caption, excluded from matching
        return screen

    def test_actual_english_unselected_screen_is_recognized(self):
        self.assertEqual(self.observer.classify(self.screen), 'loot')
        self.assertIsNotNone(self.observer.find(self.screen, 'loot_button_dim'))
        self.assertIsNone(self.observer.find(self.screen, 'loot_button'))
        self.assertIsNone(self.observer.selected_loot(self.screen))

    def test_selected_card_and_active_frame_authorize_claim(self):
        for column in range(3):
            screen = self.selected(column)
            with self.subTest(column=column):
                self.assertEqual(self.observer.classify(screen), 'loot')
                self.assertEqual(self.observer.selected_loot(screen), (195+320*column, 96, 250, 425))
                self.assertEqual(self.observer.find(screen, 'loot_button'), (473, 626, 334, 70))

    def test_dim_button_does_not_authorize_claim_even_with_selected_edge(self):
        screen = self.selected()
        screen[626:696, 473:807] = self.screen[626:696, 473:807]
        self.assertIsNotNone(self.observer.selected_loot(screen))
        self.assertIsNone(self.observer.find(screen, 'loot_button'))

    def test_active_frame_without_selected_edge_does_not_authorize_claim(self):
        screen = self.selected()
        screen[:620] = self.screen[:620]
        self.assertIsNone(self.observer.find(screen, 'loot_button'))

    def test_ambiguous_button_between_active_and_dim_does_not_authorize_claim(self):
        screen = self.selected()
        active = self.selected_source[626:696, 473:807].astype(np.uint16)
        dim = self.screen[626:696, 473:807].astype(np.uint16)
        screen[626:696, 473:807] = ((active+dim)//2).astype(np.uint8)
        self.assertIsNone(self.observer.find(screen, 'loot_button'))

    def test_multiple_selected_edges_do_not_authorize_claim(self):
        screen = self.selected()
        screen[285:404, 505:532] = self.selected_source[285:404, 185:212]
        self.assertIsNone(self.observer.selected_loot(screen))
        self.assertIsNone(self.observer.find(screen, 'loot_button'))

    def test_missing_scene_anchor_or_button_rejects_loot_screen(self):
        for x, y, w, h in ((180, 530, 290, 55), (470, 620, 340, 80)):
            screen = self.selected()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.find(screen, 'loot_button'))
                self.assertNotEqual(self.observer.classify(screen), 'loot')

    def test_unselected_caption_can_change(self):
        screen = self.screen.copy()
        screen[634:688, 501:779] = np.random.default_rng(25).integers(0, 256, (54, 278, 3), dtype=np.uint8)
        self.assertEqual(self.observer.classify(screen), 'loot')
        self.assertIsNone(self.observer.find(screen, 'loot_button'))

    def test_claim_replay_skips_forbidden_first_card_and_waits_for_selection(self):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        frames = [self.screen, self.selected(1), read_image(str(RAW / 'elite_victory_claimed_live.png'))]
        index = [0]
        taps = []
        with tempfile.TemporaryDirectory() as tmp, patch.object(observer, 'forbidden', return_value=[('blocked', (300, 200, 40, 40))]):
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=observer)
            bot._capture = lambda: frames[index[0]]
            def tap(bounds):
                taps.append(bounds)
                index[0] += 1
            bot._tap = tap
            self.assertEqual(bot._loot(), 'victory')
            self.assertEqual(taps, [(515, 96, 250, 425), (473, 626, 334, 70)])
            bot.adb.tap.assert_not_called()
