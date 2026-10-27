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


class EventChoiceWarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(ROOT / 'tests/fixtures/exploration/english_event_choice_warning_20261025.npz') as data:
            cls.screen = data['screen']
        cls.observer = NodeObserver(ROOT)

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, stable_frames=2, timeout_seconds=3,
                               recognition_attempts=1)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        bot.event_context = True
        bot._verified_noncombat_node = 'event'
        return bot

    def test_actual_weak_border_warning_has_a_valid_button_pair(self):
        self.assertIsNone(self.observer.event_warning_controls(self.screen))
        self.assertEqual(self.observer.event_choice_warning_controls(self.screen),
                         dict(cancel=(434, 465, 198, 60), confirm=(649, 465, 198, 60)))

    def test_pair_only_without_text_or_panel_is_enough_in_choice_context(self):
        screen = np.zeros_like(self.screen)
        for x in (434, 649):
            screen[465:525, x:x+198] = self.screen[465:525, x:x+198]
            screen[475:515, x+15:x+183] = 0
        self.assertIsNotNone(self.observer.event_choice_warning_controls(screen))
        self.assertIsNone(self.observer.event_warning_controls(screen))

    def test_button_pair_fallback_is_scoped_to_immediate_choice_transition(self):
        bot = self.bot()
        bot._capture = Mock(return_value=self.screen)
        self.assertEqual(bot._event_transition('choice', choice_warning=True), 'event_warning')
        def wait(phase, predicate):
            self.assertIsNone(predicate(self.screen))
            raise RecognitionTimeout('not a general choice transition')
        bot._wait = wait
        with self.assertRaises(RecognitionTimeout):
            bot._event_transition('choice')
        bot.adb.tap.assert_not_called()

    def test_choice_cancel_then_other_choice_never_confirms_or_repeats(self):
        bot = self.bot()
        choices = read_image(str(RAW / 'event_wall_torch_live.png'))
        map_frame = read_image(str(RAW / 'map_after_rest_live.png'))
        frames = [choices, self.screen, choices, map_frame]
        index = [0]
        taps = []
        bot._capture = lambda: frames[index[0]]
        def tap(bounds):
            taps.append(tuple(bounds))
            index[0] += 1
        bot._tap = tap
        with patch('src.chaos.exploration.random.choice', side_effect=lambda candidates: candidates[0]):
            self.assertIn(bot._unknown_event(), ('event', 'unknown_event'))
            self.assertIn(taps[0], bot.rejected_event_choices)
            self.assertEqual(bot._unknown_event(), 'map')
        self.assertEqual(taps, [(268, 556, 362, 131), (434, 465, 198, 60),
                                (648, 556, 362, 131)])
        self.assertNotIn((649, 465, 198, 60), taps)
        bot.adb.tap.assert_not_called()

    def test_cancel_waits_until_the_pair_disappears_before_accepting_choices(self):
        bot = self.bot()
        choices = read_image(str(RAW / 'event_wall_torch_live.png'))
        calls = [0]
        def wait(phase, predicate):
            calls[0] += 1
            if calls[0] == 1:
                return predicate(self.screen)
            self.assertIsNone(predicate(self.screen))
            return predicate(choices)
        bot._wait = wait
        bot._capture = Mock(return_value=self.screen)
        bot._tap = Mock()
        self.assertIn(bot._handle_event_confirm((268, 556, 362, 131), choice_warning=True),
                      ('event', 'unknown_event'))
        bot._tap.assert_called_once_with((434, 465, 198, 60))

    def test_missing_or_duplicate_buttons_are_not_accepted(self):
        for missing_x in (434, 649):
            screen = self.screen.copy()
            screen[465:525, missing_x:missing_x+198] = 0
            self.assertIsNone(self.observer.event_choice_warning_controls(screen))
        duplicate = self.screen.copy()
        duplicate[535:595, 434:632] = self.screen[465:525, 434:632]
        self.assertIsNone(self.observer.event_choice_warning_controls(duplicate))

    def test_changed_pair_before_cancel_never_uses_stale_button(self):
        bot = self.bot()
        missing = self.screen.copy()
        missing[465:525, 434:632] = 0
        bot._wait = lambda phase, predicate: predicate(self.screen)
        bot._capture = Mock(return_value=missing)
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._handle_event_confirm((268, 556, 362, 131), choice_warning=True)
        bot._tap.assert_not_called()
        self.assertEqual(bot.rejected_event_choices, set())

    def test_all_choices_rejected_stops_without_more_input(self):
        bot = self.bot()
        choices = read_image(str(RAW / 'event_wall_torch_live.png'))
        bot.rejected_event_choices.update(map(tuple, bot.observer.event_cards(choices)))
        bot._capture = Mock(return_value=choices)
        bot._tap = Mock()
        with self.assertRaisesRegex(RuntimeError, '후보 없음'):
            bot._unknown_event()
        bot._tap.assert_not_called()
