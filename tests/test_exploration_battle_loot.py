import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from src.chaos.node_observer import NodeObserver
from src.chaos.exploration import NodeProgressionBot
from src.chaos.bot import RecognitionTimeout
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]


class BattleLootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_battle_loot_20261024.npz') as data:
            cls.screen = data['screen']
            cls.warning = data['warning']

    def test_real_english_loot_button(self):
        self.assertEqual(self.observer.classify(self.screen), 'victory')
        self.assertEqual(self.observer.find(self.screen, 'loot_reward'), (668, 506, 212, 55))

    def test_translated_captions_are_excluded(self):
        screen = self.screen.copy()
        screen[306:495, 668:880] = 0
        screen[514:552, 686:862] = 0
        self.assertIsNotNone(self.observer.find(screen, 'loot_reward'))

    def test_icon_card_and_active_button_are_required(self):
        for x, y, w, h in ((735, 215, 80, 80), (648, 164, 14, 426), (668, 506, 212, 55)):
            screen = self.screen.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.find(screen, 'loot_reward'))

    def test_three_columns_with_hero_ticket(self):
        screen = read_image(str(ROOT / 'images/chaos/node_progression/raw/boss_victory_rewards_live.png'))
        controls = self.observer.battle_reward_controls(screen)
        self.assertEqual(controls['loot_reward'], (535, 506, 212, 55))
        self.assertEqual(controls['reward_hero'], (801, 506, 212, 55))

    def test_loot_and_hero_together_claims_loot_before_skipping_hero(self):
        rewards = read_image(str(ROOT / 'images/chaos/node_progression/raw/boss_victory_rewards_live.png'))
        claimed = rewards.copy()
        claimed[495:570, 535:747] = 0  # Simulate the acknowledged loot button disappearing.
        bot = object.__new__(NodeProgressionBot)
        bot.stats = {'nodes': 0}
        bot.event_context = False
        bot.observer = self.observer
        bot._capture = Mock(return_value=rewards)
        bot._guarded_tap = Mock()
        bot._state = Mock(return_value='loot')
        def claim():
            bot._capture.return_value = claimed
            return 'victory'
        bot._loot = Mock(side_effect=claim)
        bot._settle_reward_popups = lambda state, allowed: state
        bot._wait_skipped_hero = Mock(return_value='map')

        self.assertEqual(bot._victory(), 'victory')
        self.assertEqual(bot._guarded_tap.call_args.args[2], 'loot_reward')
        bot._wait_skipped_hero.assert_not_called()
        self.assertEqual(bot.stats['nodes'], 0)
        self.assertIsNotNone(self.observer.find(claimed, 'reward_hero'))
        bot._victory()
        self.assertEqual([call.args[2] for call in bot._guarded_tap.call_args_list],
                         ['loot_reward', 'continue'])
        bot._wait_skipped_hero.assert_called_once()
        self.assertEqual(bot.stats['nodes'], 1)

    def test_received_loot_is_not_actionable(self):
        screen = read_image(str(ROOT / 'images/chaos/node_progression/raw/elite_victory_claimed_live.png'))
        self.assertIsNone(self.observer.find(screen, 'loot_reward'))

    def test_unknown_active_reward_stops_before_continue(self):
        screen = self.screen.copy()
        screen[215:295, 735:815] = 0
        self.assertIsNotNone(self.observer.find(screen, 'battle_unresolved_reward'))
        bot = object.__new__(NodeProgressionBot)
        bot.stats = {}
        bot.observer = self.observer
        bot._capture = Mock(return_value=screen)
        bot._guarded_tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            bot._victory()
        bot._guarded_tap.assert_not_called()

    def test_actual_warning_recovers_by_cancel(self):
        self.assertEqual(self.observer.classify(self.warning), 'battle_unclaimed_reward')
        self.assertEqual(self.observer.find(self.warning, 'battle_warning_cancel'), (434, 430, 198, 60))
        screen = self.warning.copy()
        screen[:110] = 0
        self.assertIsNone(self.observer.battle_unclaimed_cancel(screen))
        bot = object.__new__(NodeProgressionBot)
        bot._guarded_tap = Mock()
        bot._state = Mock(return_value='victory')
        self.assertEqual(bot._dispatch_event_screen('battle_unclaimed_reward'), 'victory')
        self.assertEqual(bot._guarded_tap.call_args.args[2], 'battle_warning_cancel')

    def test_loot_claim_returns_for_rescan_without_continue(self):
        bot = object.__new__(NodeProgressionBot)
        bot.stats = {}
        bot.event_context = False
        bot.observer = self.observer
        bot._capture = Mock(return_value=self.screen)
        bot._guarded_tap = Mock()
        bot._state = Mock(return_value='loot')
        bot._loot = Mock(return_value='victory')
        bot._settle_reward_popups = Mock(return_value='victory')
        self.assertEqual(bot._victory(), 'victory')
        self.assertEqual(bot._guarded_tap.call_count, 1)
        self.assertEqual(bot._guarded_tap.call_args.args[2], 'loot_reward')

    def test_continue_guard_defers_to_newly_visible_loot(self):
        bot = object.__new__(NodeProgressionBot)
        bot.observer = self.observer
        bot._capture = Mock(return_value=self.screen)
        bot._wait = lambda phase, ready: ready(self.screen)
        bot._tap = Mock()
        result = bot._guarded_tap('continue', 'victory', 'continue', exiting=True,
                                  defer_markers=('loot_reward',))
        self.assertEqual(result, 'victory')
        bot._tap.assert_not_called()
