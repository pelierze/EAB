import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]


class RankResultBandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_max_rank_result_20261025.npz') as data:
            cls.screen = data['screen']

    def symbols_only(self, positions=None):
        controls = self.observer.rank_result_controls(self.screen)
        names = ('rank_result_before_icon', 'rank_result_arrow', 'rank_result_after_icon')
        screen = np.zeros_like(self.screen)
        for i, name in enumerate(names):
            x, y, w, h = controls[name]
            dx, dy = positions[i] if positions else (x, y)
            screen[dy:dy+h, dx:dx+w] = self.screen[y:y+h, x:x+w]
        return screen

    def test_actual_max_rank_report_requires_no_ocr(self):
        with patch.object(self.observer, 'ocr', Mock(side_effect=AssertionError('OCR forbidden'))) as ocr:
            self.assertEqual(self.observer.classify(self.screen), 'rank_result')
            self.assertIsNotNone(self.observer.find(self.screen, 'rank_close'))
            ocr.assert_not_called()

    def test_only_two_marks_and_arrow_suffice_without_panel_or_text(self):
        screen = self.symbols_only()
        self.assertEqual(self.observer.classify(screen), 'rank_result')

    def test_horizontal_spacing_is_variable_in_the_same_band(self):
        for positions in (((720, 220), (810, 217), (970, 220)),
                          ((780, 220), (900, 217), (1000, 220))):
            with self.subTest(positions=positions):
                screen = self.symbols_only(positions)
                controls = self.observer.rank_result_controls(screen)
                self.assertIsNotNone(controls)
                self.assertEqual(controls['rank_result_before_icon'][:2], positions[0])
                self.assertEqual(controls['rank_result_arrow'][:2], positions[1])
                self.assertEqual(controls['rank_result_after_icon'][:2], positions[2])

    def test_wrong_order_or_vertical_misalignment_is_rejected(self):
        for positions in (((780, 220), (720, 217), (970, 220)),
                          ((720, 210), (810, 217), (970, 225))):
            with self.subTest(positions=positions):
                self.assertIsNone(self.observer.rank_result_controls(self.symbols_only(positions)))

    def test_extra_mark_is_ambiguous(self):
        screen = self.symbols_only()
        x, y, w, h = self.observer.find(self.screen, 'rank_result_before_icon')
        screen[y:y+h, 990:990+w] = self.screen[y:y+h, x:x+w]
        self.assertIsNone(self.observer.rank_result_controls(screen))

    def test_latest_max_rank_screen_closes_once(self):
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, stable_frames=2, timeout_seconds=3,
                               recognition_attempts=1)
        map_frame = read_image(str(ROOT / 'images/chaos/node_progression/raw/map_after_rest_live.png'))
        taps = []
        with tempfile.TemporaryDirectory() as directory:
            bot = NodeProgressionBot(Mock(), ROOT, directory, observer)
            bot._capture = lambda: map_frame if taps else self.screen
            bot._tap = lambda bounds: taps.append(tuple(bounds))
            self.assertEqual(bot._dismiss_popup('max rank', 'rank_result', 'rank_close', {'map'}), 'map')
            self.assertEqual(taps, [tuple(observer.config['rank_result_close_bounds'])])
            bot.adb.tap.assert_not_called()
