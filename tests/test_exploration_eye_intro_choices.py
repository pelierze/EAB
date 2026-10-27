import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import numpy as np

from src.chaos.event_flow import run_event_flow
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]


class EyeIntroChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(ROOT / 'tests/fixtures/exploration/english_eye_intro_choices_20261026.npz') as data:
            cls.intro = data['intro']
            cls.choices = data['choices']
        cls.observer = NodeObserver(ROOT)

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, stable_frames=2, timeout_seconds=3,
                               recognition_attempts=1)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        bot.event_context = True
        bot._event_intro_pending = True
        bot._verified_noncombat_node = 'event'
        return bot

    def test_actual_images_connect_intro_to_three_choices(self):
        bot = self.bot()
        self.assertEqual(bot._classify(self.intro), 'event_intro')
        self.assertEqual(bot._classify(self.choices), 'unknown_event')
        self.assertEqual(self.observer.event_cards(self.choices),
                         [(78, 556, 362, 131), (458, 556, 362, 131), (838, 556, 362, 131)])
        self.assertEqual(len(self.observer.available_event_cards(self.choices,
                         self.observer.event_cards(self.choices))), 3)

    def test_each_choice_is_detected_without_its_words(self):
        screen = self.choices.copy()
        for x in (78, 458, 838):
            screen[590:676, x+25:x+335] = 0
        self.assertEqual(self.observer.event_cards(screen), self.observer.event_cards(self.choices))

    def test_right_grid_requires_a_real_matching_left_corner(self):
        screen = self.choices.copy()
        screen[640:705, 445:480] = 0  # the only matching bottom-left ornament
        self.assertEqual(self.observer.event_cards(screen), [])

    def test_irregular_right_corner_grid_does_not_infer_three_cards(self):
        screen = self.choices.copy()
        corner = screen[552:588, 1170:1203].copy()
        screen[552:588, 1170:1203] = 0
        screen[552:588, 1180:1213] = corner
        self.assertLess(len(self.observer.event_cards(screen)), 3)

    def replay(self, frames):
        bot = self.bot()
        index = [0]
        bot._capture = lambda: frames[index[0]]
        # Keep the real _tap: its four-value bounds contract caused this report.
        def tap(x, y, delay=0):
            index[0] += 1
            return True
        bot.adb.tap.side_effect = tap
        with patch('src.chaos.exploration.random.choice', side_effect=lambda options: options[0]) as choose, \
             patch.object(bot.observer, 'ocr', side_effect=AssertionError('OCR forbidden')) as ocr:
            self.assertEqual(run_event_flow(bot), 'map')
            self.assertEqual(len(choose.call_args.args[0]), 3)
            ocr.assert_not_called()
        self.assertEqual(bot.stats['nodes'], 1)
        return bot

    def test_real_tap_contract_then_provided_choices_and_existing_map_flow(self):
        map_frame = read_image(str(ROOT / 'images/chaos/node_progression/raw/map_after_rest_live.png'))
        bot = self.replay([self.intro, self.choices, map_frame])
        self.assertEqual(bot.adb.tap.call_args_list,
                         [call(640, 490, delay=0), call(259, 621, delay=0)])
        self.assertEqual(bot.stats['clicks'], 2)

    def test_partial_caption_reveal_then_second_click_reaches_provided_choices(self):
        partial = self.intro.copy()
        partial[504:526, 280:1000] = 0  # synthetic unfinished narration
        map_frame = read_image(str(ROOT / 'images/chaos/node_progression/raw/map_after_rest_live.png'))
        bot = self.replay([partial, self.intro, self.choices, map_frame])
        self.assertEqual(bot.adb.tap.call_args_list,
                         [call(640, 490, delay=0), call(640, 490, delay=0), call(259, 621, delay=0)])
        self.assertEqual(bot.stats['clicks'], 3)
