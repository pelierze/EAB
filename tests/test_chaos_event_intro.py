import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.exploration import NodeProgressionBot
from src.chaos.event_flow import run_event_flow
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class EventIntroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        cls.screen = read_image(str(RAW / 'event_intro_issue17.png'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bot = NodeProgressionBot(Mock(), ROOT, self.tmp.name, self.observer)
        self.bot.event_context = True

    def test_issue17_requires_confirmed_event_entry(self):
        self.assertTrue(self.observer.event_intro_panel(self.screen))
        self.assertIsNone(self.observer.classify(self.screen))
        self.assertIsNone(self.bot._classify(self.screen))
        self.bot._event_intro_pending = True
        self.assertEqual(self.bot._classify(self.screen), 'event_intro')
        self.bot.event_context = False
        self.assertIsNone(self.bot._classify(self.screen))

    def test_other_captured_pages_never_match_intro_panel(self):
        checked = 0
        for path in RAW.rglob('*.png'):
            if path.name == 'event_intro_issue17.png':
                continue
            screen = read_image(str(path))
            if screen is not None and screen.shape[:2] == (720, 1280):
                with self.subTest(page=path.name):
                    self.assertFalse(self.observer.event_intro_panel(screen))
                checked += 1
        self.assertGreater(checked, 30)

    def test_missing_ornament_or_text_does_not_match(self):
        for region in ((slice(429, 452), slice(612, 668)),
                       (slice(460, 526), slice(280, 1000))):
            screen = self.screen.copy()
            screen[region] = 0
            self.assertFalse(self.observer.event_intro_panel(screen))
        self.assertFalse(self.observer.event_intro_panel(np.zeros_like(self.screen)))

    def test_existing_choices_end_intro_window(self):
        self.bot._event_intro_pending = True
        screen = read_image(str(RAW / 'event_bent_bars_live.png'))
        self.assertIn(self.bot._classify(screen), ('event', 'unknown_event'))
        self.assertFalse(self.bot._event_intro_pending)
        self.assertIsNone(self.bot._classify(self.screen))

    def test_entry_detail_does_not_end_intro_window(self):
        self.bot._event_intro_pending = True
        screen = read_image(str(RAW / 'event_detail_live.png'))
        self.assertEqual(self.bot._classify(screen), 'event_detail')
        self.assertTrue(self.bot._event_intro_pending)
        self.assertEqual(self.bot._classify(self.screen), 'event_intro')

    def test_one_tap_waits_for_changed_page_without_replaying_input(self):
        self.bot._event_intro_pending = True
        self.bot._capture = Mock(return_value=self.screen.copy())
        self.bot._tap = Mock()
        changed = self.screen.copy()
        changed[470:485, 400:550] = 0

        def wait(phase, predicate):
            self.assertIsNone(predicate(self.screen.copy()))
            animated = self.screen.copy()
            animated[550:688, 280:1000] = 255
            self.assertIsNone(predicate(animated))
            self.assertEqual(predicate(changed), ('event_intro',))
            return ('event_intro',)

        self.bot._wait = Mock(side_effect=wait)
        self.assertEqual(self.bot._event_intro(), 'event_intro')
        self.bot._tap.assert_called_once_with((640, 490, 0, 0))

    def test_stalled_page_stops_after_single_input(self):
        self.bot._event_intro_pending = True
        self.bot._capture = Mock(return_value=self.screen)
        self.bot._tap = Mock()
        self.bot._wait = Mock(side_effect=RecognitionTimeout('unchanged'))
        with self.assertRaises(RecognitionTimeout):
            self.bot._event_intro()
        self.bot._tap.assert_called_once()

    def test_changed_screen_before_input_is_not_clicked(self):
        self.bot._event_intro_pending = True
        self.bot._capture = Mock(return_value=np.zeros_like(self.screen))
        self.bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            self.bot._event_intro()
        self.bot._tap.assert_not_called()

    def test_intro_dispatch_hands_choices_back_to_existing_flow(self):
        self.bot._event_intro_pending = True
        self.bot._capture = Mock(return_value=self.screen)
        self.bot._state = Mock(side_effect=['event_intro', 'unknown_event', 'map'])
        self.bot._event_intro = Mock(return_value='unknown_event')
        self.bot._event = Mock(return_value='map')
        self.assertEqual(run_event_flow(self.bot), 'map')
        self.bot._event_intro.assert_called_once_with()
        self.bot._event.assert_called_once_with()
        self.assertFalse(self.bot._event_intro_pending)
        self.assertFalse(self.bot.event_context)
        self.assertEqual(self.bot.stats['nodes'], 1)


if __name__ == '__main__':
    unittest.main()
