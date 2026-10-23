"""Replay real English captures without connecting to or purchasing in the game."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from build_support.release_assets import used_images
from src.image_matcher import read_image
from src.penguin_bot import PenguinBot


ROOT = Path(__file__).resolve().parents[1]


class PenguinVisualAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(ROOT / 'tests/fixtures/penguin/english_shop_20261024.npz') as data:
            cls.listing = data['listing']
            cls.popup = data['popup']

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.bot = PenguinBot(Mock(), 1, runtime_dir=temp.name)
        self.bot._sleep_with_stop = lambda _seconds: True

    def test_real_english_frames_find_only_the_intended_click_targets(self):
        egg = self.bot._find_egg_match(self.listing)
        self.assertEqual(egg, (169, 288, 57, 71))
        self.assertEqual(self.bot._find_buy_button_for_egg(self.listing, egg), (96, 515, 39, 42))
        self.assertEqual(self.bot._find_popup_plus_one_button(self.popup), (805, 449, 60, 48))
        self.assertEqual(self.bot._find_popup_max_button(self.popup), (869, 449, 78, 48))
        self.assertEqual(self.bot._find_popup_final_buy_button(self.popup), (596, 570, 37, 40))
        self.assertTrue(self.bot._has_popup_fifty_check(self.popup))
        self.assertIsNone(self.bot._find_egg_match(self.popup))
        self.assertIsNone(self.bot._find_buy_button_for_egg(self.popup, egg))
        self.assertIsNone(self.bot._find_popup_max_button(self.listing))
        self.assertIsNone(self.bot._find_popup_final_buy_button(self.listing))

    def test_other_products_and_header_currency_are_not_list_purchase_targets(self):
        screen = self.listing.copy()
        # Leave the header and all three other products' Stigma icons intact.
        screen[515:557, 96:135] = 0
        self.assertIsNone(self.bot._find_buy_button_for_egg(screen, (169, 288, 57, 71)))

    def test_localized_buy_and_max_lettering_is_not_used(self):
        rng = np.random.default_rng(24)
        listing = self.listing.copy()
        listing[520:555, 230:280] = rng.integers(0, 256, (35, 50, 3), dtype=np.uint8)
        self.assertEqual(self.bot._find_buy_button_for_egg(listing, (169, 288, 57, 71)),
                         (96, 515, 39, 42))
        popup = self.popup.copy()
        popup[454:492, 876:940] = rng.integers(0, 256, (38, 64, 3), dtype=np.uint8)
        popup[575:610, 800:866] = rng.integers(0, 256, (35, 66, 3), dtype=np.uint8)
        self.assertEqual(self.bot._find_popup_max_button(popup), (869, 449, 78, 48))
        self.assertEqual(self.bot._find_popup_final_buy_button(popup), (596, 570, 37, 40))

    def test_plus_one_is_required_and_an_empty_or_left_hand_box_is_rejected(self):
        missing_plus = self.popup.copy()
        missing_plus[449:497, 805:865] = 0
        self.assertIsNone(self.bot._find_popup_max_button(missing_plus))
        self.assertIsNone(self.bot._find_popup_final_buy_button(missing_plus))
        missing_max = self.popup.copy()
        missing_max[449:497, 869:947] = 0
        # Even an exact duplicate box to the left must not be clicked as MAX.
        missing_max[449:497, 690:768] = self.popup[449:497, 869:947]
        self.assertIsNone(self.bot._find_popup_max_button(missing_max))

    def replay_cycle(self, requires_max):
        initial = self.popup.copy()
        if requires_max:
            initial[415:452, 591:687] = 0
        result = np.zeros_like(self.popup)
        close = read_image(ROOT / 'images/penguin/close.png')
        h, w = close.shape[:2]
        result[500:500+h, 600:600+w] = close
        frames = [self.listing, self.listing, initial]
        if requires_max:
            frames.append(self.popup)
        frames.append(result)
        self.bot._capture_screen_image = Mock(side_effect=frames)
        self.assertTrue(self.bot._run_single_cycle())
        taps = [call.args[:2] for call in self.bot.adb.tap.call_args_list]
        expected = [(115, 536)]
        if requires_max:
            expected.append((908, 473))
        expected.extend([(614, 590), (600+w//2, 500+h//2)])
        self.assertEqual(taps, expected)
        self.assertEqual(self.bot.stats['penguins_bought'], 1)

    def test_cycle_at_fifty_skips_max_and_clicks_currency(self):
        self.replay_cycle(requires_max=False)

    def test_cycle_below_fifty_clicks_anchored_max_then_currency(self):
        self.replay_cycle(requires_max=True)

    def test_failed_max_change_never_clicks_final_purchase(self):
        initial = self.popup.copy()
        initial[415:452, 591:687] = 0
        self.bot._capture_screen_image = Mock(side_effect=[
            self.listing, self.listing, initial, *([initial] * self.bot.POPUP_RETRY_COUNT),
        ])
        self.assertFalse(self.bot._run_single_cycle())
        self.assertEqual([call.args[:2] for call in self.bot.adb.tap.call_args_list],
                         [(115, 536), (908, 473)])
        self.assertEqual(self.bot.stats['penguins_bought'], 0)

    def test_runtime_assets_include_visual_anchors_and_exclude_korean_button_crops(self):
        assets = set(used_images(ROOT))
        for name in ('stigma.png', '+1.png', 'quantity_button.png', 'template_masks.json'):
            self.assertIn('images/penguin/' + name, assets)
        for name in ('buy_button.png', 'max_button.png', 'masked/quantity_button.png'):
            self.assertNotIn('images/penguin/' + name, assets)
        self.assertFalse(any(name.startswith('images/raws/') for name in assets))


if __name__ == '__main__':
    unittest.main()
