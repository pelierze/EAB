import json
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.secret_shop_bot import SecretShopBot
from test_shop_purchase_observer import ReplayADB, ShopPurchaseFixtures, ROOT
from src.shop_purchase_observer import PurchaseBaseline


class DebugADB(ReplayADB):
    def swipe(self, *args, **kwargs):
        return True


class ShopDebugTests(ShopPurchaseFixtures, unittest.TestCase):
    def make_bot(self, frames=(), enabled=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        bot = SecretShopBot(DebugADB(frames), runtime_dir=temporary.name, debug_mode=enabled)
        if bot._shop_debug is not None:
            self.addCleanup(bot._shop_debug.close)
        return bot

    @staticmethod
    def records(bot):
        return [json.loads(line) for line in bot._shop_debug.path.read_text(encoding='utf-8').splitlines()]

    def modal(self):
        from src.image_matcher import read_image
        from test_shop_purchase_observer import BUTTONS
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.put(screen, read_image(BUTTONS / 'buy_button.png'), 600, 450)
        return screen

    @patch('src.secret_shop_bot.time.sleep')
    def test_disabled_mode_never_creates_recorder_measures_or_saves_extra_images(self, sleep):
        with patch('src.secret_shop_bot.ShopDebugRecorder', side_effect=AssertionError('unexpected recorder')):
            bot = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(sold=True)], enabled=False)
        with patch('src.shop_debug.perf_counter', side_effect=AssertionError('unexpected measurement')):
            self.assertTrue(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 4)
        self.assertFalse((bot.runtime_dir / 'shop_debug').exists())
        self.assertIsNone(bot._purchase_baseline.button_image)

    @patch('src.secret_shop_bot.time.sleep')
    def test_enabled_fast_purchase_has_same_captures_and_no_evidence_or_ocr(self, sleep):
        bot = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(sold=True)])
        bot._scan_shop_page = Mock(side_effect=[{'mystic_medal': self.item}, {}])
        bot.run(1, 3)
        records = self.records(bot)
        self.assertEqual(bot.adb.captures, 4)
        self.assertFalse((bot._shop_debug.directory / 'evidence').exists())
        self.assertEqual([r['event'] for r in records].count('cycle_end'), 1)
        summary = next(r for r in records if r['event'] == 'cycle_end')
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual(summary['metrics']['captures'], 4)
        self.assertEqual(summary['metrics']['purchases'], 1)
        self.assertEqual(summary['metrics']['verification_attempts'], 1)
        self.assertEqual(summary['metrics']['verification_retries'], 0)
        self.assertEqual(summary['metrics']['ocr_calls'], 0)
        self.assertGreater(summary['metrics']['recognition_ms'], 0)
        self.assertGreaterEqual(summary['metrics']['diagnostic_ms'], 0)
        self.assertTrue(any(r['event'] == 'purchase_check' and r['reason'] == 'quantity_transition' for r in records))
        purchase = next(r for r in records if r['event'] == 'purchase_end')
        self.assertEqual((purchase['cycle_id'], purchase['purchase_id']), (1, 1))
        self.assertEqual(records[-1]['event'], 'run_end')
        baseline = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(sold=True)], enabled=False)
        baseline._scan_shop_page = Mock(side_effect=[{'mystic_medal': self.item}, {}])
        baseline.run(1, 3)
        self.assertEqual(bot.adb.taps, baseline.adb.taps)
        self.assertEqual(bot.adb.captures, baseline.adb.captures)

    @patch('src.secret_shop_bot.time.sleep')
    def test_retry_saves_only_existing_button_crops_and_counts_retry(self, sleep):
        bot = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(), self.scene(sold=True)])
        self.assertTrue(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 5)
        records = self.records(bot)
        summary = next(r for r in records if r['event'] == 'purchase_end')
        self.assertEqual(summary['metrics']['verification_retries'], 1)
        self.assertEqual(summary['metrics']['verification_attempts'], 2)
        images = list((bot._shop_debug.directory / 'evidence').glob('*.png'))
        self.assertEqual(len(images), 2)
        from src.image_matcher import read_image
        self.assertTrue(all(read_image(p).shape == (53, 183, 3) for p in images))

    @patch('src.secret_shop_bot.time.sleep')
    def test_failure_and_exception_finalize_partial_cycle_without_changing_result(self, sleep):
        bot = self.make_bot([None])
        bot._scan_shop_page = Mock(side_effect=[{'mystic_medal': self.item}])
        self.assertEqual(bot.run(1, 3)['status'], 'failed')
        records = self.records(bot)
        summary = next(r for r in records if r['event'] == 'cycle_end')
        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['metrics']['capture_failures'], 1)
        other = self.make_bot()
        other._scan_shop_page = Mock(side_effect=ValueError('expected failure'))
        with self.assertRaisesRegex(ValueError, 'expected failure'):
            other.run(1, 3)
        self.assertEqual(self.records(other)[-1]['status'], 'error')

    def test_ocr_is_counted_only_on_ambiguous_read_and_loading_is_separate(self):
        bot = self.make_bot()
        observer = bot._get_purchase_observer()
        self.assertEqual(observer.counter_state(self.active), 'available')
        self.assertEqual(bot._shop_debug.totals['ocr_calls'], 0)
        # Exercise the real lazy loader wrapper without loading a real model.
        import sys
        factory = Mock(return_value=Mock(return_value=([('0/1', .99)], None)))
        module = Mock(RapidOCR=factory)
        with patch.dict(sys.modules, {'rapidocr_onnxruntime': module}), patch.object(observer, '_glyphs', return_value=None):
            self.assertEqual(observer.counter_state(self.active, allow_ocr=True), 'sold')
            self.assertEqual(observer.counter_state(self.active, allow_ocr=True), 'sold')
        factory.assert_called_once()
        self.assertEqual(bot._shop_debug.totals['ocr_loads'], 1)
        self.assertEqual(bot._shop_debug.totals['ocr_calls'], 2)
        self.assertIn('ocr_load_ms', bot._shop_debug.totals)

    def test_exclusive_timers_separate_nested_recognition_ocr_and_idle_wait(self):
        bot = self.make_bot()
        trace = bot._shop_debug
        with patch('src.shop_debug.perf_counter', side_effect=[0, 1, 3, 5]):
            with trace.span('recognition'):
                with trace.span('ocr'):
                    pass
        self.assertEqual(trace.totals['recognition_ms'], 3000)
        self.assertEqual(trace.totals['ocr_ms'], 2000)
        with patch('src.shop_debug.perf_counter', side_effect=[0, 1, 899, 900]):
            with trace.span('natural_idle'):
                with trace.span('wait'):
                    pass
        self.assertEqual(trace.totals['natural_idle_ms'], 900000)
        self.assertEqual(trace.totals['wait_ms'], 0)

    def test_live_row_records_inner_anchor_scores_and_tiny_button_refinement(self):
        bot = self.make_bot()
        observer = bot._get_purchase_observer()
        with np.load(ROOT / 'tests/fixtures/shop_purchase/friendship_sold_20261023.npz', allow_pickle=False) as fixture:
            row, button = fixture['row'], fixture['before_button']
        baseline = PurchaseBaseline((24, 24, 82, 82), (526, 62, 183, 53),
                                    self.other_icon.copy(), observer.counter_mask(button))
        self.assertTrue(observer.purchase_complete(row, baseline))
        records = self.records(bot)
        anchor = next(r for r in records if r['event'] == 'item_anchor')
        self.assertEqual(anchor['match_region'], 'inner')
        self.assertLess(anchor['full_score'], .95)
        self.assertGreaterEqual(anchor['inner_score'], .95)
        completed = next(r for r in records if r['event'] == 'purchase_check')
        self.assertTrue(completed['result'])
        self.assertTrue(all(abs(v) <= 3 for v in completed['button_refinement']))
        self.assertEqual(completed['method'], 'shop_quantity_transition_v2')
        self.assertFalse((bot._shop_debug.directory / 'evidence').exists())

    @patch('src.secret_shop_bot.time.sleep')
    def test_natural_idle_is_outside_cycle_and_no_purchase_cycle_has_explicit_zero(self, sleep):
        bot = self.make_bot()
        bot._scan_shop_page = Mock(return_value={})
        def wait(seconds):
            if seconds > 100:
                bot.user_action = 'stop'
                return False
            return True
        bot._wait_natural_refresh = Mock(side_effect=wait)
        bot.run_natural_refresh(3)
        records = self.records(bot)
        cycle = next(r for r in records if r['event'] == 'cycle_end')
        self.assertEqual(cycle['mode'], 'natural')
        self.assertEqual(cycle['metrics']['purchases'], 0)
        self.assertEqual(cycle['metrics']['natural_idle_ms'], 0)
        self.assertEqual(records[-1]['status'], 'stopped')

    def test_sessions_are_separate_and_evidence_and_log_rotation_are_bounded(self):
        first, second = self.make_bot(), self.make_bot()
        first._shop_debug.MAX_EVIDENCE = 3
        crop = self.active[:, :, :3]
        for _ in range(5):
            first._shop_debug.evidence('test', crop)
        self.assertEqual(len(list((first._shop_debug.directory / 'evidence').glob('*.png'))), 3)
        self.assertFalse((second._shop_debug.directory / 'evidence').exists())
        self.assertNotEqual(first._shop_debug.run_id, second._shop_debug.run_id)
        first._shop_debug.handler.maxBytes = 450
        first._shop_debug.handler.backupCount = 2
        for _ in range(10):
            first._shop_debug.record('rotation', value='x'*50)
        self.assertLessEqual(len(list(first._shop_debug.directory.glob('events.jsonl*'))), 3)

    @patch('src.secret_shop_bot.time.sleep')
    def test_unconfirmed_initial_product_records_reason_and_never_taps(self, sleep):
        screen = self.scene()
        x, y, w, h = self.item
        screen[y:y+h, x:x+w] = 0
        bot = self.make_bot([screen])
        self.assertFalse(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.taps, [])
        self.assertEqual(bot.adb.captures, 1)
        self.assertTrue(any(r['event'] == 'purchase_check' and r['reason'] == 'same_item_not_found'
                            for r in self.records(bot)))

    @patch('src.secret_shop_bot.time.sleep')
    def test_storage_error_never_changes_purchase_behavior(self, sleep):
        bot = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(sold=True)])
        with patch.object(bot._shop_debug.handler, 'emit', side_effect=OSError('disk full')):
            self.assertTrue(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 4)
        self.assertEqual(bot.stats['mystic_medal_bought'], 1)
        self.assertTrue(bot._shop_debug.failed)
        with patch('src.secret_shop_bot.ShopDebugRecorder', side_effect=OSError('permission denied')):
            other = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(sold=True)])
        self.assertIsNone(other._shop_debug)
        self.assertTrue(other._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(other.adb.captures, 4)


if __name__ == '__main__':
    unittest.main()
