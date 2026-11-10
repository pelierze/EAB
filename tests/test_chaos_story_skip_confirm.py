import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.bot import RecognitionTimeout, _Stopped
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
                                   timeout_seconds=5, recognition_attempts=1,
                                   story_retry_seconds=0)
        cls.story = read_image(str(RAW/'story/Screenshot_2026.09.24_13.49.22.466.png'))
        cls.dialog = read_image(str(RAW/'story/story_skip_confirm_issue21.png'))
        cls.map_frame = read_image(str(RAW/'map_after_rest_live.png'))
        with np.load(ROOT/'tests/fixtures/exploration/story_issue30_20261110.npz') as data:
            cls.levelup = data['levelup']

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return NodeProgressionBot(Mock(), ROOT, directory.name, self.observer)

    def replay(self, bot, frames, drop_first=False):
        index = [0]
        taps = []
        def capture():
            bot.last_screen = frames[index[0]]
            return bot.last_screen
        def tap(bounds):
            taps.append(bounds)
            if not drop_first or len(taps) > 1:
                index[0] += 1
        bot._capture, bot._tap = capture, tap
        return taps

    def test_dialog_requires_own_skip_context_including_legacy_sources(self):
        bot = self.bot()
        for dialog in [self.dialog, read_image(str(RAW/'story/Screenshot_2026.09.24_13.49.26.082.png'))]:
            self.assertIsNone(self.observer.find(dialog, 'story_dialog'))
            self.assertEqual(bot._classify(dialog), 'event_warning')
            bot._story_skip_confirmation_pending = True
            self.assertEqual(bot._classify(dialog), 'story_confirm')
            bot._story_skip_confirmation_pending = False
            self.assertEqual(bot._classify(dialog), 'event_warning')

    def test_real_story_skip_dialog_and_map_playback(self):
        for event_context in (False, True):
            with self.subTest(event_context=event_context):
                bot = self.bot()
                bot.event_context = event_context
                taps = self.replay(bot, [self.story, self.dialog, self.map_frame])
                self.assertEqual(bot._story('story'), 'map')
                self.assertEqual(taps, [self.observer.find(self.story, 'skip'),
                                        self.observer.find(self.dialog, 'story_confirm')])
                self.assertFalse(bot._story_skip_confirmation_pending)

    def test_direct_levelup_without_confirmation_in_both_contexts(self):
        for event_context in (False, True):
            bot = self.bot()
            bot.event_context = event_context
            taps = self.replay(bot, [self.story, self.levelup])
            self.assertEqual(bot._story('story'), 'levelup')
            self.assertEqual(len(taps), 1)
            self.assertFalse(bot._story_skip_confirmation_pending)

    def test_story_already_ended_before_skip_input(self):
        bot = self.bot()
        taps = self.replay(bot, [self.levelup])
        self.assertEqual(bot._story('story'), 'levelup')
        self.assertEqual(taps, [])

    def test_story_returns_to_verified_noncombat_node(self):
        for kind, filename in (('rest', 'rest_menu_live.png'), ('supply', 'supply_menu_live.png'),
                               ('shop', 'shop_animated_npc_live.png')):
            bot = self.bot()
            bot._verified_noncombat_node = kind
            destination = read_image(str(RAW/filename))
            taps = self.replay(bot, [self.story, destination])
            self.assertEqual(bot._story('story'), kind)
            self.assertEqual(len(taps), 1)

    def test_issue30_transition_at_final_confirm_check_never_taps_old_button(self):
        for event_context in (False, True):
            bot = self.bot()
            bot.event_context = event_context
            state = ['story']
            counts = [0]
            taps = []
            # Real final screenshot, synthetic intermediate timing: two dialog
            # samples for outcome, two for input readiness, then levelup.
            def capture():
                if state[0] == 'story':
                    return self.story
                counts[0] += 1
                return self.dialog if counts[0] <= 4 else self.levelup
            def tap(bounds):
                taps.append(bounds)
                state[0] = 'dialog'
            bot._capture, bot._tap = capture, tap
            self.assertEqual(bot._story('story'), 'levelup')
            self.assertEqual(taps, [self.observer.find(self.story, 'skip')])
            self.assertFalse(bot._story_skip_confirmation_pending)

    def test_dropped_skip_is_retried_only_on_same_verified_story(self):
        bot = self.bot()
        taps = self.replay(bot, [self.story, self.dialog, self.map_frame], drop_first=True)
        self.assertEqual(bot._story('story'), 'map')
        self.assertEqual(taps[:2], [self.observer.find(self.story, 'skip')]*2)
        self.assertEqual(len(taps), 3)

    def test_dropped_confirm_is_retried_and_bounded(self):
        bot = self.bot()
        bot._story_skip_confirmation_pending = True
        taps = self.replay(bot, [self.dialog, self.map_frame], drop_first=True)
        self.assertEqual(bot._story('story_confirm'), 'map')
        self.assertEqual(len(taps), 2)
        bot = self.bot()
        bot._story_skip_confirmation_pending = True
        bot._capture = lambda: self.dialog
        bot._tap = Mock()
        # Limit only the terminal wait after all authorized retries.
        original_wait = bot._wait
        def wait(phase, predicate):
            if bot._tap.call_count >= 3:
                raise RecognitionTimeout('unchanged popup')
            return original_wait(phase, predicate)
        bot._wait = wait
        with self.assertRaises(RecognitionTimeout):
            bot._story('story_confirm')
        self.assertEqual(bot._tap.call_count, 3)
        self.assertFalse(bot._story_skip_confirmation_pending)

    def test_next_story_is_returned_without_replaying_previous_skip(self):
        bot = self.bot()
        taps = self.replay(bot, [self.story, self.dialog, self.story])
        self.assertEqual(bot._story('story'), 'story')
        self.assertEqual(len(taps), 2)
        self.assertFalse(bot._story_skip_confirmation_pending)

    def test_unknown_or_partial_dialog_does_not_authorize_confirm(self):
        bot = self.bot()
        bot._story_skip_confirmation_pending = True
        for x1, x2 in ((430, 635), (645, 850)):
            frame = self.dialog.copy()
            frame[420:500, x1:x2] = 0
            self.assertEqual(bot._classify(frame), 'event_warning')
            self.assertIsNone(self.observer.find(frame, 'story_confirm'))
        self.assertIsNone(bot._classify(np.zeros((720, 1280, 3), np.uint8)))
        self.assertEqual(bot._classify(self.levelup), 'levelup')

    def test_unverified_popup_resume_refuses_input(self):
        bot = self.bot()
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._story('story_confirm')
        bot._tap.assert_not_called()
        self.assertFalse(bot._story_skip_confirmation_pending)

    def test_timeout_exception_and_stop_clear_context(self):
        for exc in (RecognitionTimeout('timeout'), RuntimeError('input failed'), _Stopped()):
            bot = self.bot()
            bot._story_skip_confirmation_pending = True
            bot._dismiss_popup = Mock(side_effect=exc)
            with self.assertRaises(type(exc)):
                bot._story('story_confirm')
            self.assertFalse(bot._story_skip_confirmation_pending)

    def test_text_changes_do_not_affect_story_or_popup_controls(self):
        story = self.story.copy()
        story[15:65, 1130:1234] = 0  # Caption, leaving arrow/playback symbols.
        story[505:720, :] = 0       # Dialogue and speaker name.
        self.assertEqual(self.observer.find(story, 'skip'), self.observer.find(self.story, 'skip'))
        self.assertEqual(self.observer.classify(story), 'story')
        dialog = self.dialog.copy()
        dialog[290:350, 350:920] = 0
        dialog[440:480, 449:617] = 0
        dialog[440:480, 664:832] = 0
        self.assertEqual(self.observer.recruit_skip_buttons(dialog), self.observer.recruit_skip_buttons(self.dialog))
        bot = self.bot()
        self.assertEqual(bot._classify(dialog), 'event_warning')
        bot._story_skip_confirmation_pending = True
        self.assertEqual(bot._classify(dialog), 'story_confirm')
        levelup = self.levelup.copy()
        levelup[120:155, 580:700] = 0
        self.assertEqual(self.observer.classify(levelup), 'levelup')

    def test_skip_arrow_alone_is_insufficient(self):
        frame = self.story.copy()
        frame[10:65, 968:1095] = 0
        self.assertIsNone(self.observer.find(frame, 'skip'))
        history_only = self.story.copy()
        history_only[10:65, 1228:1268] = 0
        self.assertIsNone(self.observer.find(history_only, 'skip'))

    def test_issue31_bright_and_autoplay_stories_skip_to_victory(self):
        with np.load(ROOT/'tests/fixtures/exploration/story_issue31_20261110.npz', allow_pickle=False) as data:
            bright_story = data['bright_story']
            autoplay_story = data['autoplay_story']
            victory = data['victory']
        for name, frame in (('bright_story', bright_story), ('autoplay_story', autoplay_story)):
            with self.subTest(frame=name):
                self.assertEqual(self.observer.classify(frame), 'story')
                self.assertIsNotNone(self.observer.find(frame, 'skip'))
                bot = self.bot()
                taps = self.replay(bot, [frame, self.dialog, victory])
                self.assertEqual(bot._story('story'), 'victory')
                self.assertEqual(len(taps), 2)
                self.assertFalse(bot._story_skip_confirmation_pending)

    def test_battle_hands_story_destinations_back_to_dispatch_without_counting(self):
        for destination in ('levelup', 'battle_setup', 'exploration_entry', 'map', 'story'):
            bot = self.bot()
            bot.stats['nodes'] = 7
            bot._capture = Mock(return_value=self.story)
            bot._classify = Mock(return_value='story')
            bot._story = Mock(return_value=destination)
            self.assertEqual(bot._battle(), destination)
            self.assertEqual(bot.stats['nodes'], 7)
            bot._capture.assert_called_once()
