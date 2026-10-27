import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, call

import cv2
import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class MultiConsumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_two_consume_slots_20261027.npz') as data:
            cls.screen = data['screen']
            cls.actual_partial = data['partial']
            cls.actual_full = data['full']
            cls.actual_reward = data['reward']
            cls.actual_result = data['result']
        cls.selected = read_image(str(RAW / 'event_loot_consume_leaf_selected_live.png'))

    def bot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, stable_frames=2, timeout_seconds=2,
                               recognition_attempts=1)
        bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        bot.event_context = True
        bot._verified_noncombat_node = 'event'
        return bot

    def fill(self, screen, points, active=False):
        out = screen.copy()
        slots = self.observer.loot_consume_slots(screen)
        for (x, y, _, _, _), (cx, cy) in zip(slots, points):
            out[y:y+84, x:x+84] = 0
            out[y+20:y+64, x+20:x+64] = screen[cy-22:cy+22, cx-22:cx+22]
            out[y-6:y+22, x-6:x+22] = self.selected[510:538, 849:877]
        if active:
            out[636:704, 472:808] = self.selected[636:704, 472:808]
            out[644:692, 504:776] = 0  # No caption/counter is needed.
        return out

    def test_actual_report_detects_two_empty_slots_and_seven_items(self):
        self.assertEqual(self.observer.loot_consume_pluses(self.screen), [(846, 557), (946, 557)])
        self.assertEqual(len(self.observer.loot_consume_slots(self.screen)), 2)
        self.assertEqual(len(self.observer.loot_consume_choices(self.screen)), 7)
        self.assertEqual(self.observer.classify(self.screen), 'event_loot_consume')

    def test_user_followup_captures_are_recognized_in_order(self):
        bot = self.bot()
        self.assertEqual(bot._classify(self.actual_partial), 'event_loot_consume')
        self.assertEqual(sum(s[4] for s in bot.observer.loot_consume_slots(self.actual_partial)), 1)
        self.assertIsNone(bot.observer.loot_consume_confirm(self.actual_partial))
        self.assertEqual(bot._classify(self.actual_full), 'event_loot_consume')
        self.assertIsNotNone(bot.observer.loot_consume_confirm(self.actual_full))
        self.assertEqual(bot._classify(self.actual_reward), 'event_loot_popup')
        self.assertEqual(bot._classify(self.actual_result), 'unknown_event_result')

    def test_actual_two_item_choice_reward_and_result_chain_returns_to_map(self):
        from src.chaos.event_flow import run_event_flow
        bot = self.bot()
        map_frame = read_image(str(RAW / 'map_after_rest_live.png'))
        frames = [self.screen, self.actual_partial, self.actual_full,
                  self.actual_reward, self.actual_result, map_frame]
        index = [0]
        bot._capture = lambda: frames[index[0]]
        bot.adb.tap.side_effect = lambda *a, **kw: index.__setitem__(0, index[0]+1) or True
        # Replay the user's captured statue/leaf selections, independent of the
        # production policy's banned-first order (tested separately).
        with patch.object(bot.observer, 'loot_consume_targets', return_value=[(800, 192), (992, 192)]), \
             patch.object(bot.observer, 'ocr', side_effect=AssertionError('OCR forbidden')) as ocr:
            self.assertEqual(run_event_flow(bot), 'map')
            ocr.assert_not_called()
        self.assertEqual(bot.adb.tap.call_args_list[:3],
                         [call(800, 192, delay=0), call(992, 192, delay=0), call(640, 673, delay=0)])
        self.assertEqual(bot.adb.tap.call_count, 5)
        self.assertEqual(bot.stats['nodes'], 1)

    def test_actual_fully_selected_capture_resumes_through_reward_and_result(self):
        from src.chaos.event_flow import run_event_flow
        bot = self.bot()
        frames = [self.actual_full, self.actual_reward, self.actual_result,
                  read_image(str(RAW / 'map_after_rest_live.png'))]
        index = [0]
        bot._capture = lambda: frames[index[0]]
        bot.adb.tap.side_effect = lambda *a, **kw: index.__setitem__(0, index[0]+1) or True
        self.assertEqual(run_event_flow(bot), 'map')
        self.assertEqual(bot.adb.tap.call_args_list[0], call(640, 673, delay=0))
        self.assertEqual(bot.adb.tap.call_count, 3)

    def test_wide_search_detects_one_through_five_slots_at_changed_positions(self):
        tile = self.screen[515:599, 804:888].copy()
        for positions in ((650,), (705, 1005), (705, 855, 1005),
                          (650, 770, 890, 1010), (650, 750, 850, 950, 1050)):
            screen = self.screen.copy()
            screen[500:610, 650:1140] = 0
            for x in positions:
                screen[515:599, x:x+84] = tile
            with self.subTest(positions=positions):
                self.assertEqual(len(self.observer.loot_consume_slots(screen)), len(positions))
                self.assertEqual(self.observer.classify(screen), 'event_loot_consume')

    def test_partial_selection_keeps_total_slots_but_cannot_confirm(self):
        targets = self.observer.loot_consume_targets(self.screen)
        partial = self.fill(self.screen, targets[:1])
        slots = self.observer.loot_consume_slots(partial)
        self.assertEqual(len(slots), 2)
        self.assertEqual(sum(s[4] for s in slots), 1)
        self.assertIsNone(self.observer.loot_consume_confirm(partial))
        self.assertEqual(self.observer.classify(partial), 'event_loot_consume')

    def test_two_filled_slots_require_both_icons_and_active_button_without_ocr(self):
        points = self.observer.loot_consume_targets(self.screen)[:2]
        full = self.fill(self.screen, points, active=True)
        icons = [self.screen[y-22:y+22, x-22:x+22] for x, y in points]
        with patch.object(self.observer, 'ocr', side_effect=AssertionError('OCR forbidden')) as ocr:
            self.assertTrue(self.observer.loot_consume_selection_matches(full, icons, require_full=True))
            self.assertIsNotNone(self.observer.loot_consume_confirm(full))
            self.assertFalse(self.observer.loot_consume_selection_matches(full, icons[:1], require_full=True))
            dim = self.fill(self.screen, points)
            self.assertIsNone(self.observer.loot_consume_confirm(dim))
            ocr.assert_not_called()

    def test_handler_selects_distinct_items_then_confirms_once(self):
        bot = self.bot()
        points = bot.observer.loot_consume_targets(self.screen)[:2]
        result = read_image(str(RAW / 'event_magic_result_live.png'))
        frames = [self.screen, self.fill(self.screen, points[:1]), self.fill(self.screen, points, active=True), result]
        index = [0]
        bot.adb.tap.side_effect = lambda *args, **kw: index.__setitem__(0, index[0]+1) or True
        bot._capture = lambda: frames[index[0]]
        with patch.object(bot.observer, 'ocr', side_effect=AssertionError('OCR forbidden')):
            self.assertIn(bot._handle_loot_consume(), ('event_result', 'unknown_event_result'))
        self.assertEqual(bot.adb.tap.call_args_list,
                         [call(*points[0], delay=0), call(*points[1], delay=0), call(640, 673, delay=0)])
        self.assertNotEqual(points[0], points[1])

    def test_resume_partial_selection_does_not_toggle_the_already_selected_item(self):
        bot = self.bot()
        points = bot.observer.loot_consume_targets(self.screen)[:2]
        partial = self.fill(self.screen, points[:1])
        full = self.fill(self.screen, points, active=True)
        result = read_image(str(RAW / 'event_magic_result_live.png'))
        frames, index = [partial, full, result], [0]
        bot._capture = lambda: frames[index[0]]
        bot.adb.tap.side_effect = lambda *args, **kw: index.__setitem__(0, index[0]+1) or True
        self.assertIn(bot._handle_loot_consume(), ('event_result', 'unknown_event_result'))
        self.assertEqual(bot.adb.tap.call_args_list,
                         [call(*points[1], delay=0), call(640, 673, delay=0)])

    def test_insufficient_inventory_stops_before_any_input(self):
        bot = self.bot()
        screen = self.screen.copy()
        screen[145:470, 650:1140] = 0
        screen[150:234, 662:746] = self.screen[150:234, 662:746]
        bot._capture = Mock(return_value=screen)
        with self.assertRaisesRegex(RecognitionTimeout, '서로 다른'):
            bot._handle_loot_consume()
        bot.adb.tap.assert_not_called()

    def test_three_slots_select_three_distinct_items_then_confirm(self):
        bot = self.bot()
        screen = self.screen.copy()
        screen[500:610, 650:1140] = 0
        tile = self.screen[515:599, 804:888].copy()
        for x in (705, 855, 1005):
            screen[515:599, x:x+84] = tile
        points = bot.observer.loot_consume_targets(screen)[:3]
        result = read_image(str(RAW / 'event_magic_result_live.png'))
        frames = [screen] + [self.fill(screen, points[:i], active=i == 3) for i in (1, 2, 3)] + [result]
        index = [0]
        bot._capture = lambda: frames[index[0]]
        bot.adb.tap.side_effect = lambda *a, **kw: index.__setitem__(0, index[0]+1) or True
        self.assertIn(bot._handle_loot_consume(), ('event_result', 'unknown_event_result'))
        self.assertEqual(bot.adb.tap.call_args_list,
                         [call(*point, delay=0) for point in points] + [call(640, 673, delay=0)])

    def test_already_full_on_resume_confirms_without_toggling_items(self):
        bot = self.bot()
        points = bot.observer.loot_consume_targets(self.screen)[:2]
        full = self.fill(self.screen, points, active=True)
        result = read_image(str(RAW / 'event_magic_result_live.png'))
        bot._capture = lambda: result if bot.adb.tap.called else full
        self.assertIn(bot._handle_loot_consume(), ('event_result', 'unknown_event_result'))
        bot.adb.tap.assert_called_once_with(640, 673, delay=0)

    def test_changed_confirm_button_before_input_is_not_clicked(self):
        bot = self.bot()
        points = bot.observer.loot_consume_targets(self.screen)[:2]
        full, dim = self.fill(self.screen, points, active=True), self.fill(self.screen, points)
        changed = [False]
        bot._capture = lambda: dim if changed[0] else full
        original_wait = bot._wait
        def wait(phase, predicate):
            value = original_wait(phase, predicate)
            if phase.startswith('모든 소모 슬롯'):
                changed[0] = True
            return value
        bot._wait = wait
        with self.assertRaises(RecognitionTimeout):
            bot._handle_loot_consume()
        bot.adb.tap.assert_not_called()

    def test_overlapping_or_misaligned_slot_pluses_are_rejected(self):
        for points in (((800, 540), (850, 540)), ((800, 535), (950, 565))):
            screen = self.screen.copy()
            screen[500:610, 650:1140] = 0
            for x, y in points:
                cv2.line(screen, (x-15, y), (x+15, y), (255, 255, 255), 2)
                cv2.line(screen, (x, y-15), (x, y+15), (255, 255, 255), 2)
            self.assertEqual(self.observer.loot_consume_slots(screen), [])
