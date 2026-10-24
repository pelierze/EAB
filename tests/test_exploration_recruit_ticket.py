import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from build_support.release_assets import used_images
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class RecruitTicketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        with np.load(ROOT / 'tests/fixtures/exploration/english_recruit_ticket_20261024.npz') as data:
            cls.english = data['screen']

    def frame(self, filename):
        return read_image(str(RAW / filename))

    def test_real_english_soul_weaver_reward_is_recognized(self):
        self.assertEqual(self.observer.classify(self.english), 'recruit_reward')
        self.assertEqual(self.observer.recruit_reward_controls(self.english)['role'], 'soul_weaver')
        self.assertEqual(self.observer.find(self.english, 'recruit_continue'), (473, 615, 334, 75))

    def test_all_six_icon_patterns_in_ticket_slot(self):
        for role in ('knight', 'warrior', 'thief', 'soul_weaver', 'ranger', 'mage'):
            screen = self.english.copy()
            screen[145:255, 585:700] = (45, 35, 40)
            icon = self.observer.templates['ticket_class_' + role]
            if role == 'mage':
                icon = cv2.resize(icon, None, fx=2.5, fy=2.5)
            h, w = icon.shape[:2]
            x, y = 640-w//2, 200-h//2
            screen[y:y+h, x:x+w] = icon
            with self.subTest(role=role):
                controls = self.observer.recruit_reward_controls(screen)
                self.assertIsNotNone(controls)
                self.assertEqual(controls['role'], role)

    def test_caption_changes_do_not_affect_ticket_detection(self):
        screen = self.english.copy()
        screen[250:395, 530:750] = 0
        screen[462:500, 553:729] = 0
        screen[623:681, 501:779] = 0
        self.assertEqual(self.observer.classify(screen), 'recruit_reward')

    def test_legacy_korean_recruit_caption_keeps_existing_non_class_tickets_compatible(self):
        screen = self.frame('event_recruit_reward_live.png')
        screen[145:255, 585:700] = 0
        self.assertEqual(self.observer.recruit_reward_controls(screen)['role'], 'legacy')

    def test_ambiguous_class_icons_are_rejected_even_with_valid_card(self):
        with patch.object(self.observer, '_ticket_icon', return_value=(600, 160, 80, 80)):
            self.assertIsNone(self.observer.recruit_reward_controls(self.english))

    def test_icon_requires_card_and_both_buttons(self):
        for bounds in ((585, 145, 115, 110), (514, 114, 14, 426),
                       (535, 454, 212, 55), (473, 615, 334, 75)):
            screen = self.english.copy()
            x, y, w, h = bounds
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=bounds):
                self.assertIsNone(self.observer.recruit_reward_controls(screen))
        isolated = np.zeros_like(self.english)
        isolated[145:255, 585:700] = self.english[145:255, 585:700]
        self.assertIsNone(self.observer.recruit_reward_controls(isolated))

    def test_rank_reward_and_other_screens_are_not_recruitment_tickets(self):
        for filename in ('event_rank_reward_live.png', 'rest_rank_menu_live.png',
                         'battle/victory_live.png', 'event_loot_popup_live.png'):
            self.assertIsNone(self.observer.recruit_reward_controls(self.frame(filename)), filename)

    def masked_dialog(self):
        screen = self.frame('recruit_skip_confirm_local_live.png')
        for x in (434, 649):
            screen[440:480, x+15:x+183] = 0
        return screen

    def test_textless_confirmation_is_local_to_skip_handler(self):
        screen = self.masked_dialog()
        self.assertIsNone(self.observer.find(screen, 'story_confirm'))
        self.assertIsNone(self.observer.find(screen, 'story_cancel'))
        self.assertIsNotNone(self.observer.recruit_skip_buttons(screen))
        screen[415:505, 420:645] = 0
        self.assertIsNone(self.observer.recruit_skip_buttons(screen))

    def test_real_ticket_continue_then_textless_confirmation_then_map(self):
        observer = NodeObserver(ROOT)
        observer.config.update(timeout_seconds=5, stable_frames=2, poll_seconds=0, recognition_attempts=1)
        screens = [self.english, self.masked_dialog(), self.frame('map_after_rest_live.png')]
        with tempfile.TemporaryDirectory() as tmp, patch.object(observer, 'forbidden', return_value=[]):
            bot = NodeProgressionBot(Mock(), ROOT, tmp, observer=observer)
            index = [0]
            taps = []
            bot._capture = lambda: screens[index[0]]
            bot._record = Mock()
            def tap(bounds):
                taps.append(bounds)
                index[0] += 1
            bot._tap = tap
            self.assertEqual(bot._skip_recruit_reward(), 'map')
            self.assertEqual(taps, [(473, 615, 334, 75), (649, 430, 198, 60)])
            self.assertFalse(bot._recruit_skip_confirmation_pending)
            bot.adb.tap.assert_not_called()

    def test_mage_reference_is_packaged(self):
        self.assertIn('images/chaos/node_progression/templates/recruitment/mage_filter_symbol.png', used_images(ROOT))


if __name__ == '__main__':
    unittest.main()
