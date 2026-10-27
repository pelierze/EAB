import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class SupplyMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_supply_menu_20261024.npz') as data:
            cls.english = data['screen']
        with np.load(ROOT / 'tests/fixtures/exploration/english_supply_background_20261025.npz') as data:
            cls.latest = data['screen']

    def frame(self, name):
        return read_image(str(RAW / name))

    def test_real_english_supply_uses_chest_and_second_option(self):
        self.assertEqual(self.observer.classify(self.english), 'supply')
        self.assertEqual(self.observer.find(self.english, 'supply_loot'), (905, 368, 330, 94))
        self.assertEqual(self.observer.find(self.english, 'leave'), (938, 628, 300, 64))

    def test_latest_report_with_wrapped_caption_and_different_background(self):
        self.assertEqual(self.observer.classify(self.latest), 'supply')
        self.assertEqual(self.observer.find(self.latest, 'supply_loot'), (905, 368, 330, 94))
        self.assertIsNone(self.observer.find(self.latest, 'supply_done'))

    def test_latest_captions_and_edge_sparkle_are_excluded(self):
        screen = self.latest.copy()
        rng = np.random.default_rng(25)
        for y in (258, 368):
            for x0, y0, w, h in self.observer.config['markers']['supply_loot_variant']['exclude']:
                screen[y+y0:y+y0+h, 905+x0:905+x0+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        self.assertEqual(self.observer.supply_controls(screen), self.observer.supply_controls(self.latest))

    def test_latest_still_requires_chest_and_both_frames(self):
        for x, y, w, h in ((570, 505, 180, 65), (905, 258, 330, 94), (905, 368, 330, 94)):
            screen = self.latest.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.find(screen, 'supply_loot'))

    def test_dimmed_latest_second_option_never_authorizes_loot_click(self):
        screen = self.latest.copy()
        screen[368:462, 905:1235] //= 2
        self.assertIsNone(self.observer.find(screen, 'supply_loot'))

    def test_caption_lid_effects_and_party_are_not_matching_inputs(self):
        screen = self.english.copy()
        rng = np.random.default_rng(24)
        for x, y, w, h in ((0, 200, 500, 425), (560, 370, 220, 130),
                           (925, 278, 290, 58), (925, 388, 290, 58), (956, 634, 264, 52)):
            screen[y:y+h, x:x+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        self.assertEqual(self.observer.supply_controls(screen), self.observer.supply_controls(self.english))
        self.assertEqual(self.observer.classify(screen), 'supply')

    def test_chest_and_both_option_frames_are_required(self):
        for x, y, w, h in ((570, 505, 180, 65), (905, 258, 330, 94), (905, 368, 330, 94)):
            screen = self.english.copy()
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=(x, y, w, h)):
                self.assertIsNone(self.observer.find(screen, 'supply_loot'))
                self.assertIsNone(self.observer.supply_controls(screen))
                self.assertNotEqual(self.observer.classify(screen), 'supply')

    def test_open_chest_completion_uses_check_and_rejects_second_option(self):
        screen = self.frame('supply_done_live.png')
        self.assertEqual(self.observer.classify(screen), 'supply')
        self.assertIsNone(self.observer.find(screen, 'supply_loot'))
        self.assertIsNotNone(self.observer.find(screen, 'supply_done'))
        screen[396:438, 1174:1214] = 0
        self.assertIsNone(self.observer.find(screen, 'supply_done'))
        self.assertIsNone(self.observer.find(screen, 'supply_loot'))

    def test_no_second_click_after_loot_transition_and_leave_after_completion(self):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0)
        complete = self.frame('supply_done_live.png')
        # Simulate translated completion captions while retaining its check.
        complete[278:336, 925:1215] = 0
        complete[388:446, 925:1168] = 0
        complete[634:686, 956:1220] = 0
        screens = [self.english, self.frame('loot_cards_live.png'), complete,
                   self.frame('map_after_rest_live.png')]
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
            def loot():
                self.assertEqual(index[0], 1)
                index[0] = 2
                return 'supply'
            bot._loot = Mock(side_effect=loot)
            bot._supply()
            self.assertEqual(taps, [(905, 368, 330, 94), (938, 628, 300, 64)])
            self.assertEqual(bot.stats['nodes'], 1)
            bot.adb.tap.assert_not_called()

    def test_no_leave_when_completion_is_not_verified(self):
        observer = NodeObserver(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=observer)
            bot._capture = Mock(return_value=self.english)
            bot._tap = Mock()
            def wait(phase, predicate):
                if phase == '보급: 전리품 획득 버튼 확인':
                    return ('already_done',)  # Isolate the departure guard.
                self.assertIsNone(predicate(self.english))
                raise RecognitionTimeout('completion missing')
            bot._wait = wait
            with self.assertRaisesRegex(RecognitionTimeout, 'completion missing'):
                bot._supply()
            bot._tap.assert_not_called()


if __name__ == '__main__':
    unittest.main()
