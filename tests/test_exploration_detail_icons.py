import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import DETAIL_STATES, NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class DetailIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_rest_detail_20261024.npz') as data:
            cls.reported = data['screen']

    def test_reported_english_rest_is_detail_and_authorizes_enter(self):
        self.assertEqual(self.observer.classify(self.reported), 'rest_detail')
        self.assertEqual(self.observer.find(self.reported, 'enter_node'), (939, 629, 300, 64))
        self.assertIsNotNone(self.observer.find(self.reported, 'rest_detail'))

    def test_all_six_headers_use_distinct_icons_without_title_or_description(self):
        rng = np.random.default_rng(24)
        for kind in ('battle', 'rest', 'supply', 'elite', 'boss', 'event'):
            screen = read_image(str(RAW / f'{kind}_detail_live.png'))
            bx, by, _, _ = self.observer.find(screen, 'action_frame')
            # Preserve the separate icon at the right of the header. All text,
            # including the Enter caption, can change without changing meaning.
            screen[90:130, 935:1200] = rng.integers(0, 256, (40, 265, 3), dtype=np.uint8)
            screen[140:600, 930:1270] = 0
            screen[by+6:by+58, bx+18:bx+282] = 0
            with self.subTest(kind=kind):
                self.assertEqual(self.observer.classify(screen), kind + '_detail')
                self.assertIsNotNone(self.observer.find(screen, 'enter_node'))
                matches = [key for key in DETAIL_STATES if self.observer.find(screen, key)]
                self.assertEqual(matches, ['detail_battle' if kind == 'battle' else kind + '_detail'])

    def test_missing_icon_does_not_authorize_enter_or_another_map_click(self):
        screen = self.reported.copy()
        screen[85:150, 1200:1270] = 0
        self.assertIsNone(self.observer.find(screen, 'enter_node'))
        self.assertIsNone(self.observer.classify(screen))

    def test_missing_or_dim_button_is_not_a_map(self):
        for dim in (False, True):
            screen = self.reported.copy()
            screen[629:693, 939:1239] = (
                (screen[629:693, 939:1239] * .5).astype(np.uint8) if dim else 0)
            with self.subTest(dim=dim):
                self.assertIsNone(self.observer.find(screen, 'enter_node'))
                self.assertIsNone(self.observer.classify(screen))

    def test_conflicting_or_duplicate_header_candidates_are_not_a_known_kind(self):
        for result in ({'rest_detail': [(1210, 96, 45, 40)],
                        'event_detail': [(1210, 96, 45, 40)]},
                       {'rest_detail': [(1210, 96, 45, 40), (1210, 106, 45, 40)]}):
            with patch.object(self.observer, 'all', side_effect=lambda screen, name: result.get(name, [])):
                self.assertIsNone(self.observer.detail_state(self.reported))

    def test_rest_node_replay_enters_reported_english_detail_once(self):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        screens = [read_image(str(RAW / 'map_after_battle_live.png')), self.reported,
                   read_image(str(RAW / 'rest_menu_live.png'))]
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=observer)
            index = [0]
            taps = []
            bot._capture = lambda: screens[index[0]]
            bot._record = Mock()
            def tap(bounds):
                taps.append(bounds)
                index[0] += 1
            bot._tap = tap
            self.assertTrue(bot._select_node())
            self.assertEqual(bot.current_node_kind, 'rest')
            self.assertEqual(len(taps), 2)
            self.assertEqual(taps[-1], (939, 629, 300, 64))
            bot.adb.tap.assert_not_called()

    def test_basic_failure_report_includes_detail_and_enter_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=self.observer)
            bot.last_screen = self.reported
            bot._save_failure_diagnostic('detail_failure', 'detail')
            data = json.loads((bot.runtime_dir / 'detail_failure.json').read_text(encoding='utf-8'))
            self.assertEqual(data['state'], 'rest_detail')
            self.assertIsNotNone(data['markers']['rest_detail'])
            self.assertIsNotNone(data['markers']['enter_node'])


if __name__ == '__main__':
    unittest.main()
