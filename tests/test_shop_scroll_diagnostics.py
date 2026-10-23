import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.failure_report import save_failure_report
from src.secret_shop_bot import SecretShopBot


class ScrollDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.adb = Mock()
        self.adb.get_screen_size.return_value = (1280, 720)
        self.adb.swipe.return_value = True
        self.pixel = 10
        def capture(path):
            ok, data = cv2.imencode('.png', np.full((20,30,3), self.pixel, np.uint8))
            self.assertTrue(ok)
            Path(path).write_bytes(data.tobytes())
            return True
        self.adb.screenshot.side_effect = capture
        self.bot = SecretShopBot(self.adb, runtime_dir=self.root/'session')

    def capture(self, label, pixel):
        self.pixel = pixel
        self.assertTrue(self.bot._capture_screenshot(label))

    def report(self):
        log = self.root/'bot.log'
        log.write_text('갱신 복구 실패\n', encoding='utf8')
        return save_failure_report(self.root, log, {'status':'failed'}, self.bot,
                                   '세션 1', 'shop', self.adb)

    def test_normal_and_recovery_reuse_only_existing_captures(self):
        self.capture('상점 스캔 1페이지', 10)
        before = self.bot.screenshot_path.read_bytes()
        self.bot._scroll_down()
        self.assertEqual(self.adb.screenshot.call_count, 1)
        self.capture('상점 스캔 2페이지', 20)
        middle = self.bot.screenshot_path.read_bytes()
        self.bot._scroll_up()
        self.capture('버튼 탐색 - refresh', 30)
        after = self.bot.screenshot_path.read_bytes()
        # A later scan must not overwrite the first post-drag observation.
        self.capture('다음 화면', 40)
        first, second = self.bot.scroll_diagnostics
        self.assertEqual((first['kind'],second['kind']), ('normal','recovery'))
        self.assertEqual(first['before']['png'], before)
        self.assertEqual(first['after']['png'], middle)
        self.assertEqual(second['before']['png'], middle)
        self.assertEqual(second['after']['png'], after)
        self.assertEqual(first['start'], [960,540])
        self.assertEqual(second['start'], [960,180])
        self.assertEqual(self.adb.screenshot.call_count, 4)
        self.assertFalse((self.root/'session/scrolls').exists())

    def test_report_exports_four_images_and_metadata_without_extra_capture(self):
        self.capture('1페이지', 10)
        self.bot._scroll_down()
        self.capture('2페이지', 20)
        self.bot._scroll_up()
        self.capture('복구 후 갱신 버튼', 30)
        calls = self.adb.screenshot.call_count
        folder = self.report()
        self.assertIsNotNone(folder)
        self.assertEqual(len(list((folder/'scrolls').glob('*.png'))), 4)
        metadata = json.loads((folder/'report.json').read_text(encoding='utf8'))
        for entry in metadata['scroll_diagnostics']:
            self.assertTrue(entry['input_success'])
            self.assertEqual(entry['duration_ms'], self.bot.swipe_duration)
            for stage in ('before','after'):
                self.assertIn('captured_at', entry[stage])
                self.assertIn('context', entry[stage])
                self.assertTrue((folder/entry[stage]['file']).is_file())
                self.assertNotIn('png', entry[stage])
        self.assertEqual(self.adb.screenshot.call_count, calls)

    def test_only_last_two_drags_are_retained(self):
        for n in range(8):
            self.capture('페이지', n)
            self.bot._scroll_down()
            self.capture('다음 페이지', n+1)
        self.assertEqual(len(self.bot.scroll_diagnostics), 2)
        self.assertEqual([r['sequence'] for r in self.bot.scroll_diagnostics], [7,8])

    def test_capture_failure_does_not_attach_stale_file(self):
        self.capture('1페이지', 10)
        self.bot._scroll_down()
        self.adb.screenshot.side_effect = None
        self.adb.screenshot.return_value = False
        self.assertFalse(self.bot._capture_screenshot('2페이지 실패'))
        self.bot._scroll_up()
        first,second = self.bot.scroll_diagnostics
        self.assertIsNone(first['after'])
        self.assertEqual(first['after_capture_error'], '2페이지 실패')
        self.assertNotIn('png', second['before'])
        folder = self.report()
        metadata = json.loads((folder/'report.json').read_text(encoding='utf8'))
        self.assertIn('error', metadata['scroll_diagnostics'][0]['after'])

    def test_swipe_failure_and_missing_post_capture_remain_reportable(self):
        self.capture('1페이지', 10)
        self.adb.swipe.return_value = False
        self.bot._scroll_down()
        folder = self.report()
        entry = json.loads((folder/'report.json').read_text(encoding='utf8'))['scroll_diagnostics'][0]
        self.assertFalse(entry['input_success'])
        self.assertIn('error', entry['after'])
        self.assertTrue((folder/entry['before']['file']).is_file())

    def test_optional_image_write_failure_does_not_lose_core_report(self):
        self.capture('1페이지', 10)
        self.bot._scroll_down()
        original = Path.write_bytes
        def write(path, data):
            if path.parent.name == 'scrolls':
                raise OSError('disk full')
            return original(path, data)
        with patch.object(Path, 'write_bytes', write):
            folder = self.report()
        self.assertTrue((folder/'screen.png').is_file())
        self.assertTrue((folder/'recent.log').is_file())
        entry = json.loads((folder/'report.json').read_text(encoding='utf8'))['scroll_diagnostics'][0]
        self.assertIn('disk full', entry['before']['error'])

    def test_new_run_clears_previous_drag_history(self):
        self.capture('이전 실행', 10)
        self.bot._scroll_down()
        self.bot.run(0, 1)
        self.assertEqual(self.bot.scroll_diagnostics, [])
        self.assertIsNone(self.bot._pending_scroll_diagnostic)
        self.assertIsNone(self.bot._last_capture_info)

    def test_is_screen_scrolled_detects_difference(self):
        img1 = np.full((720, 1280, 3), 10, dtype=np.uint8)
        img2 = np.full((720, 1280, 3), 10, dtype=np.uint8)
        img3 = np.full((720, 1280, 3), 50, dtype=np.uint8)
        self.assertFalse(SecretShopBot._is_screen_scrolled(img1, img2))
        self.assertTrue(SecretShopBot._is_screen_scrolled(img1, img3))
        self.assertTrue(SecretShopBot._is_screen_scrolled(None, img3))

    def test_page2_scan_retries_scroll_when_screen_unmoved(self):
        self.bot.enabled_items = []
        self.capture('상점 스캔 1페이지', 10)
        self.bot._scroll_down()
        self.assertEqual(self.adb.swipe.call_count, 1)

        # When scanning page 2, first capture is identical to page 1 (pixel=10, unmoved).
        # On retry swipe, pixel becomes 60 (moved).
        def on_swipe(*args, **kwargs):
            self.pixel = 60
            return True

        self.adb.swipe.side_effect = on_swipe
        self.pixel = 10
        self.bot._scan_shop_page(page_num=2)

        # Verified that swipe was retried because screen had not moved, then succeeded
        self.assertEqual(self.adb.swipe.call_count, 2)
