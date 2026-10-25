import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class EventResultAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(ROOT / 'tests/fixtures/exploration/english_event_result_20261025.npz') as data:
            cls.screen = data['screen']
        cls.observer = NodeObserver(ROOT)

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=4, recognition_attempts=1, poll_seconds=0, stable_frames=2)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        bot.event_context = True
        bot._verified_noncombat_node = 'event'
        return bot

    def animated(self):
        screen = self.screen.copy()
        x, y, w, h = self.observer.find(screen, 'event_advance')
        arrow = screen[y:y+h, x:x+w].copy()
        screen[y:y+h, x:x+w] = 0
        screen[y+6:y+6+h, x+6:x+6+w] = arrow
        screen[600:606, 90:96] = 255  # particles inside the former hash region
        return screen

    def test_actual_report_is_a_result_with_a_visible_arrow(self):
        bot = self.bot()
        self.assertEqual(bot._classify(self.screen), 'unknown_event_result')
        self.assertEqual(self.observer.event_cards(self.screen), [])

    def test_arrow_and_background_motion_do_not_acknowledge_a_new_page(self):
        animated = self.animated()
        self.assertNotEqual(NodeProgressionBot._event_signature(self.screen),
                            NodeProgressionBot._event_signature(animated))
        self.assertFalse(self.observer.event_result_page_changed(self.screen, animated))

    def test_tiny_caption_rendering_noise_is_ignored_but_new_caption_is_detected(self):
        noise = self.screen.copy()
        noise[540:542, 300:302] = 255
        self.assertFalse(self.observer.event_result_page_changed(self.screen, noise))
        changed = self.screen.copy()
        changed[455:550, 260:1020] = 0
        for x in range(300, 950, 30):
            changed[475:505, x:x+7] = 255
        self.assertTrue(self.observer.event_result_page_changed(self.screen, changed))

    def test_stable_result_type_then_clicks_fresh_arrow_despite_animation(self):
        bot = self.bot()
        animated = self.animated()
        frames = iter([self.screen, animated, animated])
        tapped = []
        map_frame = read_image(str(RAW/'map_after_rest_live.png'))
        bot._capture = lambda: map_frame if tapped else next(frames, animated)
        bot._tap = lambda bounds: tapped.append(tuple(bounds))
        self.assertEqual(bot._event_result(), 'map')
        self.assertEqual(tapped, [self.observer.find(animated, 'event_advance')])
        self.assertNotEqual(tapped[0], self.observer.find(self.screen, 'event_advance'))
        bot.adb.tap.assert_not_called()

    def test_choices_appearing_before_click_are_routed_without_stale_input(self):
        bot = self.bot()
        bot.observer.config['recognition_attempts'] = 2
        choices = read_image(str(RAW/'event_wall_torch_live.png'))
        waits = [0]
        def wait(phase, predicate):
            waits[0] += 1
            return predicate(self.screen if waits[0] == 1 else choices)
        bot._wait = wait
        bot._capture = Mock(return_value=choices)
        bot._tap = Mock()
        self.assertIn(bot._event_result(), ('event', 'unknown_event'))
        bot._tap.assert_not_called()

    def test_arrow_disappearing_before_click_never_reuses_previous_coordinates(self):
        bot = self.bot()
        missing = self.screen.copy()
        missing[670:715, 600:680] = 0
        bot._wait = lambda phase, predicate: predicate(self.screen)
        bot._capture = Mock(return_value=missing)
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._event_result()
        bot._tap.assert_not_called()

    def test_same_animated_page_after_click_is_not_closed_again(self):
        bot = self.bot()
        animated = self.animated()
        waits = [0]
        def wait(phase, predicate):
            waits[0] += 1
            if waits[0] == 1:
                return predicate(self.screen)
            for frame in (animated, self.screen, animated):
                self.assertIsNone(predicate(frame))
            raise RecognitionTimeout('input not acknowledged')
        bot._wait = wait
        bot._capture = Mock(return_value=self.screen)
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._event_result()
        bot._tap.assert_called_once_with(self.observer.find(self.screen, 'event_advance'))
