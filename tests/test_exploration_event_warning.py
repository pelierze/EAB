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


class EventWarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_event_warning_20261025.npz') as data:
            cls.screen = data['screen']

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=4, recognition_attempts=1, poll_seconds=0, stable_frames=2)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        bot.event_context = True
        bot._verified_noncombat_node = 'event'
        return bot

    def test_actual_warning_detects_lower_button_row(self):
        controls = self.observer.event_warning_controls(self.screen)
        self.assertEqual(controls['cancel'], (434, 465, 198, 60))
        self.assertEqual(controls['confirm'], (649, 465, 198, 60))
        self.assertEqual(self.observer.classify(self.screen), 'event_warning')

    def test_title_body_and_button_words_are_not_recognition_inputs(self):
        screen = self.screen.copy()
        screen[195:245, 400:900] = 0
        screen[285:440, 280:1000] = 0
        screen[475:515, 449:617] = 0
        screen[475:515, 664:832] = 0
        self.assertEqual(self.observer.classify(screen), 'event_warning')
        self.assertEqual(self.observer.event_warning_controls(screen)['cancel'], (434, 465, 198, 60))

    def test_button_coordinates_are_searched_instead_of_reusing_old_row(self):
        screen = self.screen.copy()
        for x in (434, 649):
            button = self.screen[465:525, x:x+198].copy()
            screen[465:525, x:x+198] = (20, 10, 5)
            screen[445:505, x:x+198] = button
        controls = self.observer.event_warning_controls(screen)
        self.assertEqual(controls['cancel'], (434, 445, 198, 60))
        self.assertEqual(controls['confirm'], (649, 445, 198, 60))

    def test_both_buttons_and_both_modal_borders_are_required(self):
        for x, y, w, h in ((434, 465, 198, 60), (649, 465, 198, 60),
                           (0, 100, 1280, 95), (0, 530, 1280, 40)):
            screen = self.screen.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.event_warning_controls(screen))

    def test_duplicate_button_candidates_are_rejected(self):
        screen = self.screen.copy()
        for x in (434, 649):
            screen[535:595, x:x+198] = self.screen[465:525, x:x+198]
        self.assertIsNone(self.observer.event_warning_controls(screen))

    def test_event_choices_and_other_popups_are_not_generic_warnings(self):
        for filename in ('event_wall_torch_live.png', 'rest_menu_live.png', 'loot_cards_live.png',
                         'event_loot_popup_live.png'):
            with self.subTest(filename=filename):
                screen = read_image(str(RAW/filename))
                self.assertIsNone(self.observer.event_warning_controls(screen))

    def test_cancel_rejects_previous_choice_then_selects_the_other_without_confirm(self):
        bot = self.bot()
        frames = [self.screen, read_image(str(RAW/'event_wall_torch_live.png')),
                  read_image(str(RAW/'map_after_rest_live.png'))]
        index = [0]
        taps = []
        bot._capture = lambda: frames[index[0]]
        def tap(bounds):
            taps.append(tuple(bounds))
            index[0] += 1
        bot._tap = tap
        failed = (268, 556, 362, 131)
        self.assertIn(bot._handle_event_confirm(failed), ('event', 'unknown_event'))
        self.assertIn(failed, bot.rejected_event_choices)
        with patch('src.chaos.exploration.random.choice', side_effect=lambda choices: choices[0]):
            self.assertEqual(bot._unknown_event(), 'map')
        self.assertEqual(taps, [(434, 465, 198, 60), (648, 556, 362, 131)])
        self.assertNotIn((649, 465, 198, 60), taps)
        bot.adb.tap.assert_not_called()

    def test_changed_screen_before_cancel_never_uses_stale_coordinates(self):
        bot = self.bot()
        changed = self.screen.copy()
        changed[465:525, 434:632] = 0
        bot._wait = lambda phase, predicate: predicate(self.screen)
        bot._capture = Mock(return_value=changed)
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._handle_event_confirm((268, 556, 362, 131))
        bot._tap.assert_not_called()
        self.assertEqual(bot.rejected_event_choices, set())
