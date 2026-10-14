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


class StorySkipConfirmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        cls.observer.config.update(poll_seconds=0, stable_frames=2,
                                   timeout_seconds=5, recognition_attempts=1)
        cls.story = read_image(str(RAW/'story/Screenshot_2026.09.24_13.49.22.466.png'))
        cls.dialog = read_image(str(RAW/'story/story_skip_confirm_issue21.png'))
        cls.map_frame = read_image(str(RAW/'map_after_rest_live.png'))

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return NodeProgressionBot(Mock(), ROOT, directory.name, self.observer)

    def test_issue_dialog_requires_own_skip_context(self):
        bot = self.bot()
        self.assertIsNone(self.observer.find(self.dialog, 'story_dialog'))
        self.assertEqual(bot._classify(self.dialog), 'event_warning')
        bot._story_skip_confirmation_pending = True
        self.assertEqual(bot._classify(self.dialog), 'story_confirm')
        bot._story_skip_confirmation_pending = False
        self.assertEqual(bot._classify(self.dialog), 'event_warning')

    def test_real_story_skip_dialog_and_map_playback(self):
        for event_context in (False, True):
            with self.subTest(event_context=event_context):
                bot = self.bot()
                bot.event_context = event_context
                frames = [self.story, self.dialog, self.map_frame]
                index = [0]
                taps = []
                bot._capture = lambda: frames[index[0]]
                def tap(bounds):
                    taps.append(bounds)
                    index[0] += 1
                bot._tap = tap
                bot._story('story')
                self.assertEqual(taps, [self.observer.find(self.story, 'skip'),
                                        self.observer.find(self.dialog, 'story_confirm')])
                self.assertFalse(bot._story_skip_confirmation_pending)
                self.assertEqual(bot._classify(self.dialog), 'event_warning')

    def test_both_buttons_required_in_skip_context(self):
        bot = self.bot()
        bot._story_skip_confirmation_pending = True
        for x1,x2 in ((470,620), (680,830)):
            with self.subTest(x=x1):
                frame = self.dialog.copy()
                frame[420:540,x1:x2] = 0
                self.assertNotEqual(bot._classify(frame), 'story_confirm')

    def test_dialog_buttons_remaining_are_not_mistaken_for_closed_popup(self):
        bot = self.bot()
        bot._guarded_tap = Mock()
        bot._state = Mock(return_value='story_confirm')
        def wait(phase, predicate):
            self.assertIsNone(predicate(self.dialog))
            self.assertIsNone(predicate(np.zeros((720,1280,3), dtype=np.uint8)))
            self.assertEqual(predicate(self.map_frame), ('closed',))
            return ('closed',)
        bot._wait = wait
        bot._story('story')
        self.assertFalse(bot._story_skip_confirmation_pending)

    def test_timeout_clears_context(self):
        bot = self.bot()
        bot._guarded_tap = Mock()
        bot._state = Mock(side_effect=RecognitionTimeout('unknown'))
        with self.assertRaises(RecognitionTimeout):
            bot._story('story')
        self.assertFalse(bot._story_skip_confirmation_pending)
        self.assertEqual(bot._classify(self.dialog), 'event_warning')

    def test_confirm_input_failure_clears_context(self):
        bot = self.bot()
        bot._guarded_tap = Mock(side_effect=[None, RuntimeError('input failed')])
        bot._state = Mock(return_value='story_confirm')
        with self.assertRaisesRegex(RuntimeError, 'input failed'):
            bot._story('story')
        self.assertFalse(bot._story_skip_confirmation_pending)

    def test_direct_reward_followup_clears_context_without_confirm_click(self):
        bot = self.bot()
        bot.event_context = True
        bot._guarded_tap = Mock()
        bot._state = Mock(return_value='rank_reward')
        self.assertEqual(bot._story('story'), 'rank_reward')
        bot._guarded_tap.assert_called_once_with('스토리 건너뛰기', 'story', 'skip')
        self.assertFalse(bot._story_skip_confirmation_pending)

    def test_legacy_story_dialog_still_resumes_without_skip_context(self):
        bot = self.bot()
        legacy = read_image(str(RAW/'story/Screenshot_2026.09.24_13.49.26.082.png'))
        screen = [legacy]
        taps = []
        bot._capture = lambda: screen[0]
        def tap(bounds):
            taps.append(bounds)
            screen[0] = self.map_frame
        bot._tap = tap
        bot._story('story_confirm')
        self.assertEqual(taps, [self.observer.find(legacy, 'story_confirm')])
        self.assertFalse(bot._story_skip_confirmation_pending)
