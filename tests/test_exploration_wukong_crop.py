import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from src.chaos.bot import PartyRecruitmentBot
from src.chaos.observer import RecruitmentObserver

ROOT = Path(__file__).resolve().parents[1]


class WukongCropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = RecruitmentObserver(ROOT, ['wukong'])
        with np.load(ROOT / 'tests/fixtures/exploration/english_wukong_list_20261025.npz') as data:
            cls.screen = data['screen']

    def test_actual_english_portrait_is_found_without_overlapping_name(self):
        self.assertIsNotNone(self.observer.header(self.screen, self.observer.heroes[0]))
        self.assertEqual(self.observer.find(self.screen, 'wukong'), (879, 191, 84, 45))

    def test_excluded_left_name_area_can_change(self):
        screen = self.screen.copy()
        screen[191:236, 831:879] = np.random.default_rng(25).integers(0, 256, (45, 48, 3), dtype=np.uint8)
        self.assertEqual(self.observer.find(screen, 'wukong'), (879, 191, 84, 45))

    def test_missing_portrait_does_not_match_other_heroes(self):
        screen = self.screen.copy()
        screen[191:236, 879:963] = 0
        self.assertIsNone(self.observer.find(screen, 'wukong'))

    def test_actual_list_finds_wukong_without_swiping_or_recruiting_unselected_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = PartyRecruitmentBot(Mock(), ROOT, tmp)
            bot.observer.config.update(timeout_seconds=3, stable_frames=2, poll_seconds=0)
            bot.active_hero = next(hero for hero in bot.observer.heroes if hero['id'] == 'wukong')
            bot.hero_name = bot.active_hero['name']
            bot._capture = Mock(return_value=self.screen)
            bot._scroll_hero_list = Mock()
            bot._tap = Mock()
            portrait = bot._wait_hero_portrait()
            self.assertEqual(portrait, (879, 191, 84, 45))
            bot._scroll_hero_list.assert_not_called()
            bot._select_hero(portrait)
            bot._tap.assert_called_once_with(portrait)
            self.assertIsNone(bot._recruit(self.screen))
            bot.adb.tap.assert_not_called()
