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


class DefeatIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        cls.screen = read_image(str(RAW / 'battle_defeat_live.png'))

    def without_label(self):
        screen = self.screen.copy()
        screen[275:375, 350:930] = 0
        return screen

    def test_reported_defeat_and_erased_label_are_both_detected(self):
        for screen in (self.screen, self.without_label()):
            with self.subTest(label_present=screen is self.screen):
                self.assertEqual(self.observer.classify(screen), 'defeat')

    def test_arbitrary_localized_label_pixels_are_not_inputs(self):
        screen = self.without_label()
        screen[275:375, 350:930] = np.random.default_rng(7).integers(
            0, 256, (100, 580, 3), dtype=np.uint8)
        self.assertEqual(self.observer.find(screen, 'defeat'),
                         self.observer.find(self.screen, 'defeat'))

    def test_each_crest_patch_is_required_even_with_original_failed_label(self):
        for name in ('defeat', 'defeat_ornament'):
            screen = self.screen.copy()
            x, y, w, h = self.observer.config['markers'][name]['crop']
            screen[y:y+h, x:x+w] = 0
            with self.subTest(missing=name):
                self.assertIsNone(self.observer.find(screen, 'defeat'))

    def test_ornament_must_align_with_central_crest(self):
        screen = self.screen.copy()
        x, y, w, h = self.observer.config['markers']['defeat_ornament']['crop']
        ornament = screen[y:y+h, x:x+w].copy()
        screen[y:y+h, x:x+w] = 0
        screen[y+8:y+8+h, x:x+w] = ornament
        self.assertTrue(self.observer.all(screen, 'defeat_ornament'))
        self.assertTrue(self.observer.all(screen, 'defeat'))
        self.assertIsNone(self.observer.find(screen, 'defeat'))

    def test_shared_motion_of_crest_patches_is_allowed(self):
        screen = np.zeros_like(self.screen)
        screen[5:, 5:] = self.screen[:-5, :-5]
        expected = self.observer.find(self.screen, 'defeat')
        self.assertEqual(self.observer.find(screen, 'defeat'),
                         (expected[0]+5, expected[1]+5, *expected[2:]))

    def test_other_registered_screens_are_not_defeat(self):
        files = {d['file'] for d in self.observer.config['markers'].values()}
        files.discard('images/chaos/node_progression/raw/battle_defeat_live.png')
        for filename in sorted(files):
            with self.subTest(filename=filename):
                screen = read_image(str(ROOT / filename))
                self.assertIsNone(self.observer.find(screen, 'defeat'))

    def test_textless_defeat_closes_summary_and_returns_failed_without_count_ocr(self):
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, recognition_attempts=1,
                               timeout_seconds=5, stable_frames=2)
        frames = [self.without_label(), read_image(str(RAW / 'expedition_summary_live.png')),
                  read_image(str(RAW / 'entry_after_defeat_live.png'))]
        current = [0]
        taps = []
        with tempfile.TemporaryDirectory() as directory:
            bot = NodeProgressionBot(Mock(), ROOT, directory, observer)
            bot._capture = lambda: frames[current[0]]
            def tap(bounds):
                taps.append(tuple(bounds))
                current[0] += 1
            bot._tap = tap
            bot._battle()
            self.assertEqual(bot.stats['outcome'], 'defeat')
            with patch.object(observer, 'summary_boss_count', side_effect=AssertionError('defeat already known')):
                result = bot.run()
            self.assertEqual(result['status'], 'round_failed', result)
            self.assertEqual(result['outcome'], 'defeat')
            self.assertEqual(len(taps), 2)
            self.assertEqual(taps[0], observer.find(frames[0], 'defeat'))
            bot.adb.tap.assert_not_called()
