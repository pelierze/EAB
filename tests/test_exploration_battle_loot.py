import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import cv2

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
        with np.load(ROOT / 'tests/fixtures/exploration/english_battle_background_20261025.npz') as data:
            cls.changed_background = data['screen']
        with np.load(ROOT / 'tests/fixtures/exploration/english_battle_all_ticket_20261025.npz') as data:
            cls.all_ticket = data['screen']
        with np.load(ROOT / 'tests/fixtures/exploration/english_battle_rewards_20261026.npz') as data:
            cls.latest = data['screen']

    def test_real_english_loot_button(self):
        self.assertEqual(self.observer.classify(self.screen), 'victory')
        self.assertEqual(self.observer.find(self.screen, 'loot_reward'), (668, 506, 212, 55))

    def test_reported_background_change_recognizes_loot(self):
        self.assertEqual(self.observer.classify(self.changed_background), 'victory')
        self.assertEqual(self.observer.find(self.changed_background, 'loot_reward'), (668, 506, 212, 55))
        self.assertIsNone(self.observer.find(self.changed_background, 'battle_unresolved_reward'))

    def test_only_icon_and_pill_are_inputs_inside_reward_card(self):
        screen = self.changed_background.copy()
        region = screen[164:590, 648:900]
        saved = region.copy()
        region[:] = np.random.default_rng(25).integers(0, 256, region.shape, dtype=np.uint8)
        region[51:131, 87:167] = saved[51:131, 87:167]
        region[342:397, 20:232] = saved[342:397, 20:232]
        self.assertIsNotNone(self.observer.find(screen, 'loot_reward'))

    def test_lower_card_notches_are_not_required(self):
        for x in (648, 884):
            screen = self.changed_background.copy()
            screen[439:474, x:x+16] = 0
            with self.subTest(x=x):
                self.assertIsNotNone(self.observer.find(screen, 'loot_reward'))

    def test_translated_captions_are_excluded(self):
        screen = self.screen.copy()
        screen[306:495, 668:880] = 0
        screen[514:552, 686:862] = 0
        self.assertIsNotNone(self.observer.find(screen, 'loot_reward'))

    def test_icon_and_active_button_are_required(self):
        for x, y, w, h in ((735, 215, 80, 80), (668, 506, 212, 55)):
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
        self.assert_loot_before_hero(rewards)

    def test_reported_loot_and_all_class_ticket_sequence(self):
        self.assertEqual(self.observer.battle_reward_controls(self.all_ticket),
                         {'loot_reward': (535, 506, 212, 55), 'reward_hero': (801, 506, 212, 55)})
        self.assertIsNone(self.observer.find(self.all_ticket, 'battle_unresolved_reward'))
        self.assert_loot_before_hero(self.all_ticket)

    def test_all_ticket_requires_icon_and_active_button(self):
        for x, y, w, h in ((875, 218, 64, 64), (801, 506, 212, 55)):
            screen = self.all_ticket.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.find(screen, 'reward_hero'))
                self.assertIsNotNone(self.observer.find(screen, 'loot_reward'))

    def test_all_ticket_caption_is_not_an_input(self):
        screen = self.all_ticket.copy()
        screen[305:430, 801:1013] = 0
        screen[514:552, 819:995] = 0
        self.assertIsNotNone(self.observer.find(screen, 'reward_hero'))

    def test_latest_report_recognizes_loot_and_all_ticket_without_card_borders(self):
        self.assertEqual(self.observer.battle_reward_controls(self.latest),
                         {'loot_reward': (535, 506, 212, 55), 'reward_hero': (801, 506, 212, 55)})
        self.assertIsNone(self.observer.find(self.latest, 'battle_unresolved_reward'))
        self.assert_loot_before_hero(self.latest)

    def test_loot_alone_needs_no_hero_ticket_or_card_outline(self):
        screen = np.zeros_like(self.latest)
        screen[:110] = self.latest[:110]  # victory context
        screen[215:295, 602:682] = self.latest[215:295, 602:682]
        screen[506:561, 535:747] = self.latest[506:561, 535:747]
        screen[514:552, 553:729] = 0  # button words
        self.assertEqual(self.observer.battle_reward_controls(screen),
                         {'loot_reward': (535, 506, 212, 55)})
        self.assertIsNone(self.observer.find(screen, 'battle_unresolved_reward'))

    def test_all_ticket_alone_needs_no_loot_or_card_outline(self):
        screen = np.zeros_like(self.latest)
        screen[:110] = self.latest[:110]
        screen[215:295, 867:947] = self.latest[215:295, 867:947]
        screen[506:561, 801:1013] = self.latest[506:561, 801:1013]
        screen[514:552, 819:995] = 0
        self.assertEqual(self.observer.battle_reward_controls(screen),
                         {'reward_hero': (801, 506, 212, 55)})

    def test_each_class_icon_pairs_with_its_own_button_without_a_card(self):
        for role in ('knight', 'warrior', 'thief', 'soul_weaver', 'ranger', 'mage'):
            screen = np.zeros_like(self.latest)
            screen[:110] = self.latest[:110]
            icon = self.observer.templates['ticket_class_'+role]
            scales = self.observer.config['markers']['ticket_class_'+role]['match_scales']
            icon = cv2.resize(icon, None, fx=scales[len(scales)//2], fy=scales[len(scales)//2])
            h, w = icon.shape[:2]
            x = 907-w//2
            screen[215:215+h, x:x+w] = icon
            screen[506:561, 801:1013] = self.latest[506:561, 801:1013]
            screen[514:552, 819:995] = 0
            with self.subTest(role=role):
                self.assertEqual(self.observer.battle_reward_controls(screen),
                                 {'reward_hero': (801, 506, 212, 55)})

    def test_rank_reward_needs_only_icon_and_its_pill(self):
        original = read_image(str(ROOT / 'images/chaos/node_progression/raw/battle/victory_rank_reward_live.png'))
        button = self.observer.find(original, 'battle_rank_reward')
        self.assertIsNotNone(button)
        screen = np.zeros_like(original)
        screen[:110] = original[:110]
        screen[215:295, 600:680] = original[215:295, 600:680]
        x, y, w, h = button
        screen[y:y+h, x:x+w] = original[y:y+h, x:x+w]
        screen[y+8:y+46, x+18:x+194] = 0
        self.assertEqual(self.observer.battle_reward_controls(screen), {'battle_rank_reward': button})

    def test_duplicate_loot_icons_are_ambiguous_not_silently_overwritten(self):
        screen = self.latest.copy()
        screen[215:295, 868:948] = self.latest[215:295, 602:682]
        self.assertNotIn('loot_reward', self.observer.battle_reward_controls(screen))
        self.assertIsNotNone(self.observer.find(screen, 'battle_unresolved_reward'))

    def test_loot_icon_crop_is_small_and_legacy_card_markers_are_removed(self):
        self.assertEqual(self.observer.templates['battle_loot_icon'].shape[:2], (60, 73))
        self.assertNotIn('battle_reward_card', self.observer.templates)
        self.assertNotIn('battle_reward_card_legacy', self.observer.templates)

    def assert_loot_before_hero(self, rewards):
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
        bot.event_context = False
        bot.observer = self.observer
        bot._capture = Mock(return_value=self.screen)
        bot._wait = lambda phase, ready: ready(self.screen)
        bot._tap = Mock()
        result = bot._guarded_tap('continue', 'victory', 'continue', exiting=True,
                                  defer_markers=('loot_reward',))
        self.assertEqual(result, 'victory')
        bot._tap.assert_not_called()
