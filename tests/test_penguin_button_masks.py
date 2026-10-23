"""Recognition contract for future full-button penguin templates."""
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.penguin_bot import PenguinBot


class PenguinButtonMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        assets = self.root / 'images/penguin'
        assets.mkdir(parents=True)
        self.rng = np.random.default_rng(20261024)
        # A distinct border, with deliberately unrelated lettering in its hole.
        self.original = self.rng.integers(40, 240, (40, 100, 3), dtype=np.uint8)
        cv2.imencode('.png', self.original)[1].tofile(str(assets / 'buy_button.png'))
        (assets / 'template_masks.json').write_text(json.dumps({
            'buy_button.png': {'size': [100, 40], 'exclude': [[10, 6, 80, 28]]},
        }), encoding='utf-8')
        self.bot = PenguinBot(None, 1, runtime_dir=self.root / 'logs', base_dir=self.root)

    def changed_button(self):
        changed = self.original.copy()
        changed[6:34, 10:90] = self.rng.integers(0, 256, (28, 80, 3), dtype=np.uint8)
        return changed

    def test_text_changes_are_ignored_in_search_and_scoring(self):
        button = self.changed_button()
        screen = np.zeros((100, 180, 3), dtype=np.uint8)
        screen[23:63, 31:131] = button
        expected = (31, 23, 100, 40)
        self.assertEqual(self.bot._find_best_match(screen, 'buy_button.png', .99), expected)
        self.assertIn(expected, self.bot._find_all_matches(screen, 'buy_button.png', .99))
        self.assertGreater(self.bot._match_score_for_box(screen, 'buy_button.png', expected), .99)
        self.assertEqual(self.bot._find_in_roi(screen, (20, 10, 160, 90), 'buy_button.png', .99), expected)

    def test_scaled_search_preserves_holes_and_click_geometry(self):
        for scale in (.95, 1., 1.05, 1.1, 1.15):
            with self.subTest(scale=scale):
                interpolation = cv2.INTER_LINEAR if scale > 1 else cv2.INTER_AREA
                button = cv2.resize(self.changed_button(), None, fx=scale, fy=scale,
                                    interpolation=interpolation)
                h, w = button.shape[:2]
                screen = np.zeros((120, 190, 3), dtype=np.uint8)
                screen[21:21+h, 30:30+w] = button
                template = self.bot._load_template('buy_button.png', scale)
                self.assertEqual(set(np.unique(template[:, :, 3])), {0, 255})
                expected = (30, 21, w, h)
                self.assertEqual(self.bot._find_in_roi(
                    screen, (15, 10, 180, 110), 'buy_button.png', .99, scales=(scale,)), expected)
                self.assertGreater(self.bot._match_score_for_box(
                    screen, 'buy_button.png', expected, scale=scale), .99)

    def test_empty_and_dimmed_screens_do_not_match(self):
        screens = [np.full((80, 160, 3), value, dtype=np.uint8) for value in (0, 80, 255)]
        screens.append((self.original.astype(float) * .4).astype(np.uint8))
        for screen in screens:
            self.assertIsNone(self.bot._find_best_match(screen, 'buy_button.png', .9))
            self.assertEqual(self.bot._find_all_matches(screen, 'buy_button.png', .9), [])

    def test_existing_unmasked_assets_keep_color_and_geometry(self):
        from src.image_matcher import read_image
        root = Path(__file__).resolve().parents[1]
        bot = PenguinBot(None, 1, runtime_dir=self.root / 'legacy', base_dir=root)
        for name in ('egg.png', 'close.png', '50check.png', 'buy_button.png', 'max_button.png'):
            source = read_image(root / 'images/penguin' / name)
            np.testing.assert_array_equal(bot._load_template(name), source)
            h, w = source.shape[:2]
            self.assertEqual(bot._find_best_match(source, name, .99), (0, 0, w, h))


if __name__ == '__main__':
    unittest.main()
