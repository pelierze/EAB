import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.image_matcher import ImageMatcher, read_image
from src.secret_shop_bot import SecretShopBot
from src.shop_purchase_observer import ShopPurchaseObserver, PurchaseBaseline


ROOT = Path(__file__).resolve().parents[1]
BUTTONS = ROOT / 'images/buttons'


def recolor(image, saturation=.25, brightness=.6):
    hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * brightness, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


class ReplayADB:
    def __init__(self, frames):
        self.frames = list(frames)
        self.captures = 0
        self.taps = []

    def screenshot(self, path):
        self.captures += 1
        frame = self.frames.pop(0) if self.frames else None
        if frame is None:
            return False
        cv2.imencode('.png', frame)[1].tofile(path)
        return True

    def tap(self, *args, **kwargs):
        self.taps.append((args, kwargs))
        return True

    def get_screen_size(self):
        return 1280, 720


class ShopPurchaseFixtures:
    def setUp(self):
        self.matcher = ImageMatcher()
        self.active = self.matcher.load_template(BUTTONS / 'purchase_button.png')
        self.disabled = self.matcher.load_template(BUTTONS / 'purchase_button_disabled.png')
        self.observer = ShopPurchaseObserver(self.active, self.disabled)
        self.icon = read_image(ROOT / 'images/items/mystic_medal.png')
        self.other_icon = read_image(ROOT / 'images/items/friendship_point.png')
        self.item = (200, 230, self.icon.shape[1], self.icon.shape[0])
        self.button = (950, 240, 183, 53)

    @staticmethod
    def put(screen, image, x, y):
        h, w = image.shape[:2]
        screen[y:y+h, x:x+w] = image[:, :, :3]

    def scene(self, sold=False, shift=(0, 0), other_sold=True, tint=False):
        screen = np.random.default_rng(90).integers(0, 40, (720, 1280, 3), dtype=np.uint8)
        dx, dy = shift
        self.put(screen, self.icon, self.item[0]+dx, self.item[1]+dy)
        button = self.disabled if sold else self.active
        self.put(screen, recolor(button) if tint else button, self.button[0]+dx, self.button[1]+dy)
        self.put(screen, self.other_icon, 200, 430)
        self.put(screen, self.disabled if other_sold else self.active, 950, 440)
        return screen

    def baseline(self):
        return self.observer.baseline(self.scene(), self.item, self.button)


class ShopPurchaseObserverTests(ShopPurchaseFixtures, unittest.TestCase):
    def test_counter_states_survive_saturation_and_brightness_changes_without_ocr(self):
        for state, template in (('available', self.active), ('sold', self.disabled)):
            for saturation in (0, .25, 1, 2):
                for brightness in (.4, 1):
                    with self.subTest(state=state, saturation=saturation, brightness=brightness):
                        self.assertEqual(self.observer.counter_state(recolor(template, saturation, brightness)), state)
        self.assertIsNone(self.observer.ocr)

    def test_initial_button_detection_uses_quantity_despite_changed_colors(self):
        for sold, expected in ((False, 'available'), (True, 'sold')):
            with self.subTest(sold=sold):
                bounds, state = self.observer.find_button(self.scene(sold=sold, tint=True), self.item)
                self.assertEqual(bounds, self.button)
                self.assertEqual(state, expected)
        self.assertIsNone(self.observer.ocr)

    def test_only_same_item_quantity_transition_completes_purchase(self):
        before = self.baseline()
        self.assertFalse(self.observer.purchase_complete(self.scene(sold=False, other_sold=True), before))
        self.assertFalse(self.observer.purchase_complete(self.scene(sold=False, tint=True), before))
        self.assertTrue(self.observer.purchase_complete(self.scene(sold=True, tint=True), before))
        self.assertIsNone(self.observer.ocr)

    def test_small_row_movement_is_reanchored_to_the_product_icon(self):
        self.assertTrue(self.observer.purchase_complete(self.scene(sold=True, shift=(7, -9)), self.baseline()))

    def test_live_purchased_friendship_row_recovers_inner_anchor_and_button_alignment(self):
        with np.load(ROOT / 'tests/fixtures/shop_purchase/friendship_sold_20261023.npz', allow_pickle=False) as fixture:
            row, before_button = fixture['row'], fixture['before_button']
        item = (24, 24, 82, 82)
        button = (526, 62, 183, 53)
        # Confirm this fixture reproduces the original strict-anchor failure.
        self.assertIsNone(self.observer.locate_item(row, self.other_icon, item))
        recovered = self.observer.locate_item(row, self.other_icon, item, stable_inner=True)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered[0], item[0])
        self.assertLessEqual(abs(recovered[1]-item[1]), 1)
        baseline = PurchaseBaseline(item, button, self.other_icon.copy(),
                                    self.observer.counter_mask(before_button))
        self.assertTrue(self.observer.purchase_complete(row, baseline))
        self.assertIsNone(self.observer.ocr)

    def test_inner_anchor_rejects_different_missing_covered_and_other_row_products(self):
        before = self.baseline()
        scenes = []
        for replacement in (np.zeros_like(self.icon), self.other_icon):
            screen = self.scene(sold=True)
            x, y, w, h = self.item
            screen[y:y+h, x:x+w] = 0
            self.put(screen, replacement, x, y)
            scenes.append(screen)
        # A copy of the real target plus a sold button on a different row must
        # not rescue a missing target at the recorded slot.
        screen = self.scene(sold=True)
        x, y, w, h = self.item
        screen[y:y+h, x:x+w] = 0
        self.put(screen, self.icon, x, y+100)
        self.put(screen, self.disabled, self.button[0], self.button[1]+100)
        scenes.append(screen)
        covered = self.scene(sold=True)
        covered[200:310, 150:1150] = 35
        scenes.append(covered)
        for index, screen in enumerate(scenes):
            with self.subTest(case=index):
                self.assertFalse(self.observer.purchase_complete(screen, before))
        self.assertIsNone(self.observer.ocr)

    def test_unstable_icon_border_uses_inner_art_at_same_threshold(self):
        screen = self.scene(sold=True)
        x, y, w, h = self.item
        patch = screen[y:y+h, x:x+w]
        changed = np.random.default_rng(30).integers(0, 256, patch.shape, dtype=np.uint8)
        cx, cy, right, bottom = round(w*.12), round(h*.12), round(w*.88), round(h*.80)
        dimmed = np.clip(patch.astype(np.float32)*.6, 0, 255).astype(np.uint8)
        changed[cy:bottom, cx:right] = dimmed[cy:bottom, cx:right]
        screen[y:y+h, x:x+w] = changed
        self.assertIsNone(self.observer.locate_item(screen, self.icon, self.item))
        self.assertTrue(self.observer.purchase_complete(screen, self.baseline()))

    def test_button_refinement_never_searches_another_row_for_completion(self):
        screen = self.scene(sold=False)
        x, y, w, h = self.button
        screen[y:y+h, x:x+w] = 0
        self.put(screen, self.disabled, x, y+100)
        self.assertFalse(self.observer.purchase_complete(screen, self.baseline()))
        self.assertIsNone(self.observer.ocr)

    def test_missing_or_different_product_and_covered_row_never_complete(self):
        before = self.baseline()
        for replacement in (np.zeros_like(self.icon), self.other_icon):
            screen = self.scene(sold=True)
            x, y, w, h = self.item
            screen[y:y+h, x:x+w] = 0
            self.put(screen, replacement, x, y)
            self.assertFalse(self.observer.purchase_complete(screen, before))
        screen[200:310, 150:1150] = 35
        self.assertFalse(self.observer.purchase_complete(screen, before))
        self.assertIsNone(self.observer.ocr)

    def test_ocr_is_only_used_for_ambiguous_glyphs_and_requires_exact_counter(self):
        self.observer.ocr = Mock(return_value=([('0 / 1', .99)], None))
        self.assertEqual(self.observer.counter_state(self.active), 'available')
        self.observer.ocr.assert_not_called()
        with patch.object(self.observer, '_glyphs', return_value=None):
            self.assertIsNone(self.observer.counter_state(self.active))
            self.observer.ocr.assert_not_called()
            self.assertEqual(self.observer.counter_state(self.active, allow_ocr=True), 'sold')
            for text, confidence in (('0/10', .99), ('10/1', .99), ('0/1', .89), ('01', .99)):
                self.observer.ocr.return_value = ([(text, confidence)], None)
                self.assertIsNone(self.observer.counter_state(self.active, allow_ocr=True))

    def test_ocr_alone_cannot_confirm_an_unchanged_counter(self):
        self.observer.ocr = Mock(return_value=([('0/1', .99)], None))
        with patch.object(self.observer, '_glyphs', return_value=None):
            self.assertFalse(self.observer.purchase_complete(self.scene(sold=False), self.baseline()))


class ShopPurchaseFlowTests(ShopPurchaseFixtures, unittest.TestCase):
    def make_bot(self, frames):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return SecretShopBot(ReplayADB(frames), runtime_dir=temp.name)

    def modal(self):
        screen = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.put(screen, read_image(BUTTONS / 'buy_button.png'), 600, 450)
        return screen

    @patch('src.secret_shop_bot.time.sleep')
    def test_normal_purchase_returns_after_one_existing_verification_capture(self, sleep):
        bot = self.make_bot([self.scene(tint=True), self.modal(), self.modal(), self.scene(sold=True, tint=True)])
        self.assertTrue(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 4)
        self.assertEqual(bot.stats['mystic_medal_bought'], 1)
        self.assertEqual(len(bot.adb.taps), 3)
        self.assertIsNone(bot._purchase_observer.ocr)

    @patch('src.secret_shop_bot.time.sleep')
    def test_only_uncertain_completion_retries_and_never_clicks_buy_again(self, sleep):
        bot = self.make_bot([self.scene(), self.modal(), self.modal(), self.scene(), self.scene(sold=True)])
        self.assertTrue(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 5)
        self.assertEqual(bot.stats['mystic_medal_bought'], 1)
        self.assertEqual(len(bot.adb.taps), 3)

    @patch('src.secret_shop_bot.time.sleep')
    def test_failed_purchase_with_other_sold_row_never_increments_statistics(self, sleep):
        bot = self.make_bot([self.scene(), self.modal(), self.modal()] + [self.scene()] * 3)
        self.assertFalse(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 6)
        self.assertEqual(bot.stats['mystic_medal_bought'], 0)
        self.assertEqual(len(bot.adb.taps), 3)

    @patch('src.secret_shop_bot.time.sleep')
    def test_already_sold_product_is_skipped_without_taps_or_new_purchase_count(self, sleep):
        bot = self.make_bot([self.scene(sold=True, other_sold=False, tint=True)])
        self.assertTrue(bot._purchase_item('mystic_medal', self.item, 3))
        self.assertEqual(bot.adb.captures, 1)
        self.assertEqual(bot.adb.taps, [])
        self.assertEqual(bot.stats['mystic_medal_bought'], 0)

    @patch('src.secret_shop_bot.time.sleep')
    def test_failed_capture_does_not_reuse_old_success_image(self, sleep):
        bot = self.make_bot([None])
        bot._purchase_baseline = self.baseline()
        cv2.imencode('.png', self.scene(sold=True))[1].tofile(str(bot.screenshot_path))
        with patch('src.secret_shop_bot.read_image') as read:
            self.assertFalse(bot._verify_purchase_complete())
        read.assert_not_called()

    def test_stop_never_captures_or_verifies(self):
        bot = self.make_bot([])
        bot._purchase_baseline = self.baseline()
        bot.user_action = 'stop'
        self.assertFalse(bot._verify_purchase_complete())
        self.assertEqual(bot.adb.captures, 0)


if __name__ == '__main__':
    unittest.main()
