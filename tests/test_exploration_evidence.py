import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.chaos.debug import ExplorationEvidence
from src.chaos.exploration import NodeProgressionBot
from src.failure_report import save_failure_report


class ExplorationEvidenceTests(unittest.TestCase):
    def test_sampling_is_bounded_owns_frames_and_never_encodes_during_run(self):
        evidence = ExplorationEvidence()
        frame = np.zeros((720, 1280, 3), np.uint8)
        with patch('src.chaos.debug.time.monotonic', return_value=0) as clock, \
                patch('src.chaos.debug.cv2.imencode') as encode:
            for second in range(30):
                clock.return_value = second
                frame.fill(second)
                evidence.remember(frame, phase='waiting')
                evidence.remember(frame, phase='waiting')
                evidence.remember(frame, state=str(second), label='before_input')
            encode.assert_not_called()
        self.assertEqual(len(evidence.recent), 12)
        self.assertEqual(len(evidence.transitions), 8)
        frame.fill(255)
        self.assertEqual(int(evidence.recent[-1]['frame'][0, 0, 0]), 29)
        self.assertEqual(sum(r['frame'].nbytes for r in [*evidence.recent, *evidence.transitions]),
                         20 * 720 * 1280 * 3)

    def test_failure_report_includes_history_without_debug_mode_or_new_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'bot.log'
            log.write_text('recognition timeout', encoding='utf-8')
            history = ExplorationEvidence()
            frame = np.full((20, 30, 3), 65, np.uint8)
            history.remember(frame, state='story', label='before_input')
            history.remember(frame, state='levelup', pending=True)
            controller = Mock()
            active = SimpleNamespace(last_screen=frame, diagnostic_history=history)
            report = save_failure_report(root, log, {}, SimpleNamespace(active=active), 's', 'chaos', controller)
            metadata = json.loads((report/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['history']['frames'], 2)
            manifest = json.loads((report/'history/frames.json').read_text(encoding='utf-8'))
            self.assertEqual([r['state'] for r in manifest], ['story', 'levelup'])
            self.assertTrue(manifest[-1]['skip_confirmation_pending'])
            saved = cv2.imdecode(np.frombuffer((report/'history/02.png').read_bytes(), np.uint8), 1)
            np.testing.assert_array_equal(saved, frame)
            controller.screenshot.assert_not_called()

    def test_history_save_failure_preserves_main_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root/'bot.log'
            log.write_text('failed', encoding='utf-8')
            active = SimpleNamespace(last_screen=np.zeros((4, 5, 3), np.uint8),
                                     diagnostic_history=ExplorationEvidence())
            with patch.object(ExplorationEvidence, 'export', side_effect=OSError('disk full')):
                report = save_failure_report(root, log, {}, active, 's', 'chaos')
            self.assertTrue((report/'screen.png').is_file())
            self.assertTrue((report/'recent.log').is_file())
            self.assertIn('disk full', (report/'report.json').read_text(encoding='utf-8'))

    def test_capture_and_state_hooks_share_frames_without_extra_backend_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            observer = Mock(config={'recognition_attempts': 1})
            observer.classify.return_value = 'battle'
            bot = NodeProgressionBot(Mock(), Path(__file__).resolve().parents[1], directory, observer)
            bot.adb.capture_frame.return_value = np.zeros((720, 1280, 3), np.uint8)
            frame = bot._capture()
            self.assertEqual(bot._classify(frame), 'battle')
            bot._record('before_input')
            bot.adb.capture_frame.assert_called_once()
            self.assertEqual(len(bot.diagnostic_history.recent), 1)
            self.assertEqual(len(bot.diagnostic_history.transitions), 2)


if __name__ == '__main__':
    unittest.main()
