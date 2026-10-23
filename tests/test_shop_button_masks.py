import json
import shutil
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from build_support.release_assets import used_images
from src.image_matcher import ImageMatcher, read_image


ROOT = Path(__file__).resolve().parents[1]
BUTTONS = ROOT / 'images/buttons'


class ShopButtonMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.matcher = ImageMatcher()

    def write(self, name, image):
        path = self.root / name
        cv2.imencode('.png', image)[1].tofile(str(path))
        return path

    def test_changed_text_is_ignored_by_every_matching_entry_point(self):
        rng = np.random.default_rng(52)
        definitions = json.loads((BUTTONS / 'template_masks.json').read_text())
        for name, definition in definitions.items():
            with self.subTest(button=name):
                source = read_image(BUTTONS / name)
                changed = source.copy()
                for x, y, w, h in definition['exclude']:
                    changed[y:y+h, x:x+w] = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
                height, width = source.shape[:2]
                screen = rng.integers(0, 256, (height+40, width+50, 3), dtype=np.uint8)
                screen[17:17+height, 23:23+width] = changed
                path = self.write('screen.png', screen)
                location = (23, 17, width, height)
                template = BUTTONS / name
                self.assertEqual(self.matcher.find_image(path, template, .99), location)
                self.assertIn(location, self.matcher.find_all_images(path, template, .99))
                self.assertGreater(self.matcher.get_similarity(path, template), .99)
                self.assertGreater(self.matcher.get_similarity_at_location(path, template, location), .99)
                self.assertEqual(self.matcher.get_center(location), (23+width//2, 17+height//2))

    def test_active_and_disabled_buttons_remain_distinct(self):
        active = BUTTONS / 'purchase_button.png'
        disabled = BUTTONS / 'purchase_button_disabled.png'
        for target, opposite in ((active, disabled), (disabled, active)):
            with self.subTest(target=target.name):
                self.assertGreater(self.matcher.get_similarity(target, target), .99)
                self.assertLess(self.matcher.get_similarity(target, opposite), .85)
                self.assertIsNone(self.matcher.find_image(target, opposite, .85))

    def test_blank_screens_never_produce_nonfinite_or_successful_matches(self):
        for value in (0, 80, 255):
            screen = np.full((90, 230, 3), value, dtype=np.uint8)
            for name in ('buy_button.png', 'confirm_button.png', 'refresh_button.png',
                         'purchase_button.png', 'purchase_button_disabled.png'):
                with self.subTest(value=value, button=name):
                    result = self.matcher.match_template(screen, self.matcher.load_template(BUTTONS / name))
                    self.assertTrue(np.isfinite(result).all())
                    self.assertLess(float(result.max()), .85)

    def test_mask_changes_invalidate_cache_and_bad_masks_fail_closed(self):
        path = self.root / 'buy_button.png'
        shutil.copyfile(BUTTONS / path.name, path)
        config = self.root / 'template_masks.json'
        original = self.matcher.load_template(path)
        self.assertEqual(original.shape[2], 3)
        config.write_text(json.dumps({path.name: {'size': [63, 39], 'exclude': [[3, 6, 57, 29]]}}))
        masked = self.matcher.load_template(path)
        self.assertEqual(masked.shape[2], 4)
        self.assertFalse(masked.flags.writeable)
        config.write_text(json.dumps({path.name: {'size': [63, 39], 'exclude': [[0, 0, 63, 39]]}}))
        self.assertIsNone(self.matcher.find_image(path, path))
        self.assertEqual(self.matcher.get_similarity(path, path), 0)
        config.write_text('{bad json')
        self.assertIsNone(self.matcher.find_image(path, path))
        config.unlink()
        np.testing.assert_array_equal(self.matcher.load_template(path), original)

    def test_wrong_size_mask_is_rejected_and_local_comparison_stays_local(self):
        path = self.root / 'buy_button.png'
        shutil.copyfile(BUTTONS / path.name, path)
        for definition in (
                {'size': [64, 39], 'exclude': [[3, 6, 57, 29]]},
                {'size': [63, 39], 'exclude': [[63, 0, 1, 1]]},
                {'size': [63, 39], 'exclude': [[-1, 0, 1, 1]]},
                {'size': [63, 39], 'exclude': [[0, 0, 0, 1]]}):
            with self.subTest(definition=definition):
                (self.root / 'template_masks.json').write_text(json.dumps({path.name: definition}))
                self.assertIsNone(self.matcher.find_image(path, path))
        self.assertEqual(self.matcher.get_similarity_at_location(
            BUTTONS / path.name, BUTTONS / path.name, (0, 0, 1, 1)), 0)

    def test_mask_definition_is_in_release_assets(self):
        self.assertIn('images/buttons/template_masks.json', used_images(ROOT))

    def test_exported_alpha_template_works_without_sidecar(self):
        source = BUTTONS / 'purchase_button.png'
        effective = self.matcher.load_template(source)
        path = self.write('exported.png', effective)
        changed = read_image(source)
        changed[effective[:, :, 3] == 0] = 255
        screen = self.write('changed.png', changed)
        self.assertGreater(self.matcher.get_similarity(screen, path), .99)


if __name__ == '__main__':
    unittest.main()
