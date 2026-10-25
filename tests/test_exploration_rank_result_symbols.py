import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class RankResultSymbolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_rank_result_20261025.npz') as data:
            cls.screen = data['screen']

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, stable_frames=2, timeout_seconds=3,
                               recognition_attempts=1)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        bot._verified_noncombat_node = 'rest'
        return bot

    def test_actual_report_recognized_without_any_ocr(self):
        with patch.object(self.observer, 'ocr', side_effect=AssertionError('OCR is forbidden')) as ocr:
            self.assertEqual(self.observer.classify(self.screen), 'rank_result')
            self.assertIsNotNone(self.observer.find(self.screen, 'rank_close'))
            ocr.assert_not_called()

    def test_text_portrait_and_stat_numbers_are_not_required(self):
        screen = self.screen.copy()
        screen[140:590, 300:580] = 0
        screen[255:515, 655:1035] = 0
        screen[209:249, 785:812] = 0
        screen[209:249, 923:954] = 0
        screen[679:710, 580:720] = 0
        self.assertEqual(self.observer.classify(screen), 'rank_result')
        self.assertEqual(self.observer.find(screen, 'rank_close'),
                         self.observer.find(self.screen, 'rank_close'))

    def test_each_transition_symbol_is_required(self):
        names = ('rank_result_arrow', 'rank_result_before_icon',
                 'rank_result_after_icon')
        for name in names:
            screen = self.screen.copy()
            bounds = self.observer.rank_result_controls(screen)[name]
            x, y, w, h = bounds
            sample = screen[y:y+h, x:x+w]
            sample[:] = 0
            with self.subTest(missing=name):
                self.assertFalse(self.observer.is_rank_result(screen))
                self.assertIsNone(self.observer.find(screen, 'rank_close'))
                if name != 'rank_result_arrow':
                    self.assertIsNone(self.observer.classify(screen))

    def test_arrow_and_generic_close_alone_never_authorize_rank_close(self):
        screen = np.zeros_like(self.screen)
        for name in ('rank_result_arrow', 'event_loot_close'):
            bounds = self.observer.find(self.screen, name)
            if bounds:
                x, y, w, h = bounds
                screen[y:y+h, x:x+w] = self.screen[y:y+h, x:x+w]
        self.assertIsNone(self.observer.find(screen, 'rank_close'))
        self.assertIsNone(self.observer.classify(screen))

    def test_other_registered_screens_cannot_authorize_rank_close(self):
        files = {d['file'] for d in self.observer.config['markers'].values()}
        for filename in sorted(files):
            screen = read_image(str(ROOT / filename))
            if filename.endswith(('rank_result_event_live.png', 'rest_wukong_rankup_live.png',
                                  'rest_shadow_rose_rankup_local_live.png')):
                continue
            with self.subTest(filename=filename):
                self.assertIsNone(self.observer.find(screen, 'rank_close'))

    def test_actual_result_is_closed_once_and_returns_to_map(self):
        bot = self.bot()
        map_frame = read_image(str(RAW / 'map_after_rest_live.png'))
        taps = []
        bot._capture = lambda: map_frame if taps else self.screen
        bot._tap = lambda bounds: taps.append(tuple(bounds))
        with patch.object(bot.observer, 'ocr', side_effect=AssertionError('OCR is forbidden')) as ocr:
            self.assertEqual(bot._dismiss_popup('rank result', 'rank_result', 'rank_close', {'map', 'rest'}), 'map')
            ocr.assert_not_called()
        self.assertEqual(taps, [tuple(bot.observer.config['rank_result_close_bounds'])])
        bot.adb.tap.assert_not_called()

    def test_preclick_missing_mark_does_not_reuse_close_coordinates(self):
        bot = self.bot()
        missing = self.screen.copy()
        x, y, w, h = bot.observer.find(missing, 'rank_result_after_icon')
        missing[y:y+h, x:x+w] = 0
        bot._wait = lambda phase, predicate: predicate(self.screen)
        bot._capture = Mock(return_value=missing)
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._guarded_tap('rank result', 'rank_result', 'rank_close', exiting=True)
        bot._tap.assert_not_called()
