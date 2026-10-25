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


class RankRewardFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_rank_reward_20261025.npz') as data:
            cls.screen = data['screen']

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

    def test_actual_english_report_exposes_both_controls(self):
        self.assertEqual(self.observer.classify(self.screen), 'rank_reward')
        for name in ('event_rank_reward_button', 'event_reward_continue'):
            self.assertIsNotNone(self.observer.find(self.screen, name))

    def test_all_localized_card_and_button_text_is_excluded(self):
        for randomize in (False, True):
            screen = self.screen.copy()
            screen[260:390, 535:746] = 0  # title and description
            for name in ('event_rank_reward_button', 'event_reward_continue'):
                definition = self.observer.config['markers'][name]
                x, y, _, _ = definition['crop']
                for ex, ey, w, h in definition['exclude']:
                    screen[y+ey:y+ey+h, x+ex:x+ex+w] = (
                        np.random.default_rng(17).integers(0, 256, (h, w, 3), dtype=np.uint8)
                        if randomize else 0)
            with self.subTest(randomize=randomize):
                self.assertEqual(self.observer.classify(screen), 'rank_reward')
                for name in ('event_rank_reward_button', 'event_reward_continue'):
                    self.assertEqual(self.observer.find(screen, name), self.observer.find(self.screen, name))

    def test_rank_icon_card_and_continue_frame_are_required(self):
        for name in ('event_rank_reward_icon', 'recruit_card_frame', 'event_reward_continue'):
            screen = self.screen.copy()
            x, y, w, h = self.observer.config['markers'][name]['crop']
            screen[y:y+h, x:x+w] = 0
            with self.subTest(missing=name):
                self.assertIsNone(self.observer.rank_reward_controls(screen))
                self.assertIsNone(self.observer.find(screen, 'event_rank_reward_button'))
                self.assertIsNone(self.observer.find(screen, 'event_reward_continue'))

    def test_missing_use_frame_does_not_authorize_use(self):
        screen = self.screen.copy()
        screen[454:508, 535:745] = 0
        self.assertIsNone(self.observer.find(screen, 'event_rank_reward_button'))
        self.assertEqual(self.observer.classify(screen), 'rank_reward')

    def test_other_reward_screens_do_not_expose_rank_controls(self):
        for filename in ('event_recruit_reward_live.png', 'event_loot_popup_live.png',
                         'rank_result_event_live.png', 'battle/victory_live.png'):
            with self.subTest(filename=filename):
                screen = read_image(str(RAW / filename))
                self.assertIsNone(self.observer.rank_reward_controls(screen))
                self.assertIsNone(self.observer.find(screen, 'event_reward_continue'))

    def test_choice_result_then_use_rank_reward_and_continue_once(self):
        bot = self.bot()
        menu = read_image(str(RAW / 'rest_rank_menu_live.png'))
        map_frame = read_image(str(RAW / 'map_after_rest_live.png'))
        frames = [self.screen, menu, self.screen, map_frame]
        index = [0]
        taps = []
        bot._capture = lambda: frames[index[0]]
        def tap(bounds):
            taps.append(tuple(bounds))
            index[0] += 1
        bot._tap = tap
        bot._rankup = Mock(side_effect=lambda: index.__setitem__(0, 2))
        self.assertEqual(bot._event_transition('previous choice'), 'rank_reward')
        self.assertEqual(bot._event_rank_reward(), 'map')
        bot._rankup.assert_called_once()
        self.assertEqual(taps, [bot.observer.find(self.screen, 'event_rank_reward_button'),
                                bot.observer.find(self.screen, 'event_reward_continue')])
        self.assertEqual(bot.stats['nodes'], 1)
        bot.adb.tap.assert_not_called()

    def test_stale_reward_screen_does_not_click_previous_button(self):
        bot = self.bot()
        bot._wait = lambda phase, predicate: predicate(self.screen)
        bot._capture = Mock(return_value=read_image(str(RAW / 'map_after_rest_live.png')))
        bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._guarded_tap('rank reward', 'rank_reward', 'event_rank_reward_button')
        bot._tap.assert_not_called()
