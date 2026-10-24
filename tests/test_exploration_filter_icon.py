"""Keep the filter click anchored to its symbol rather than Korean lettering."""
from pathlib import Path
import unittest

import numpy as np

from src.chaos.observer import RecruitmentObserver
from src.image_matcher import read_image


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/hero_selection/raw'


class ExplorationFilterIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = RecruitmentObserver(ROOT)

    def test_all_saved_hero_lists_find_the_symbol_inside_the_filter_button(self):
        paths = sorted(RAW.glob('*full*.png'))
        self.assertGreater(len(paths), 10)
        for path in paths:
            with self.subTest(capture=path.name):
                bounds = self.observer.find(read_image(path), 'filter')
                if path.name == 'full_party.png':
                    self.assertIsNone(bounds)
                else:
                    self.assertEqual(bounds, (700, 24, 21, 18))
                    x, y, w, h = bounds
                    self.assertTrue(686 <= x+w//2 < 828 and 7 <= y+h//2 < 60)

    def test_replaced_lettering_does_not_change_the_match_but_missing_icon_does(self):
        screen = read_image(RAW / 'knight_full.png')
        rng = np.random.default_rng(24)
        screen[10:58, 728:823] = rng.integers(0, 256, (48, 95, 3), dtype=np.uint8)
        self.assertEqual(self.observer.find(screen, 'filter'), (700, 24, 21, 18))
        screen[24:42, 700:721] = 0
        self.assertIsNone(self.observer.find(screen, 'filter'))


if __name__ == '__main__':
    unittest.main()
