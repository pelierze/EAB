import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.chaos.bot import RecognitionTimeout
from src.chaos.event_flow import run_event_flow
from src.chaos.exploration import NodeProgressionBot
from src.chaos.node_observer import NodeObserver
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'
TARGET = (350, 400, 290, 80)


class HeroDepartureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        cls.screen = read_image(str(RAW / 'event_hero_departure_local_live.png'))
        # Replay the real selected border from the shared rank menu. Departure
        # confirmation and enabled label are simulated until live captures exist.
        cls.selected = cls.screen.copy()
        rank = read_image(str(RAW / 'rest_wukong_selected_live.png'))
        cls.selected[390:490, 335:655] = rank[390:490, 335:655]
        label = cls.selected[646:675, 1034:1141]
        text = label.mean(axis=2) >= 100
        label[text] = np.clip(label[text].astype(int)+90, 0, 255)
        cls.portrait = cls.screen[406:471, 510:630].copy()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bot = NodeProgressionBot(Mock(), ROOT, self.tmp.name, self.observer)
        self.bot._tap = Mock()

    def test_latest_report_classifies_and_lists_four_heroes_without_names(self):
        self.assertEqual(self.observer.classify(self.screen), 'hero_departure')
        self.assertEqual(self.observer.hero_departure_candidates(self.screen),
                         [(350, y, 290, 80) for y in (85, 190, 295, 400)])

    def test_fewer_heroes_only_offer_visible_rows(self):
        screen = self.screen.copy()
        screen[285:490, 330:660] = 0
        self.assertEqual(self.observer.hero_departure_candidates(screen),
                         [(350, 85, 290, 80), (350, 190, 290, 80)])

    def test_hero_names_and_class_icons_do_not_limit_candidates(self):
        screen = self.screen.copy()
        for y in (85, 190, 295, 400):
            screen[y+15:y+45, 365:505] = 0
        self.assertEqual(self.observer.hero_departure_candidates(screen),
                         [(350, y, 290, 80) for y in (85, 190, 295, 400)])

    def test_other_captured_pages_never_offer_departure_candidates(self):
        for path in RAW.rglob('*.png'):
            if path.name == 'event_hero_departure_local_live.png':
                continue
            screen = read_image(str(path))
            if screen is not None and screen.shape[:2] == (720, 1280):
                with self.subTest(page=path.name):
                    self.assertEqual(self.observer.hero_departure_candidates(screen), [])

    def test_selected_border_enabled_button_and_same_portrait_are_required(self):
        self.assertIsNone(self.observer.hero_departure_selected(self.screen, TARGET, self.portrait))
        self.assertIsNotNone(self.observer.hero_departure_selected(self.selected, TARGET, self.portrait))
        self.assertIn(TARGET, self.observer.hero_departure_candidates(self.selected))
        dim = self.selected.copy()
        dim[646:675, 1034:1141] = self.screen[646:675, 1034:1141]
        self.assertIsNone(self.observer.hero_departure_selected(dim, TARGET, self.portrait))
        no_border = self.screen.copy()
        no_border[646:675, 1034:1141] = self.selected[646:675, 1034:1141]
        self.assertIsNone(self.observer.hero_departure_selected(no_border, TARGET, self.portrait))
        wrong = self.screen[91:156, 510:630].copy()
        self.assertIsNone(self.observer.hero_departure_selected(self.selected, TARGET, wrong))

    def test_random_selection_then_departure_continues_to_existing_event(self):
        self.bot._capture = Mock(side_effect=[self.screen, self.selected, self.selected])
        followup = read_image(str(RAW / 'event_mushroom_result_live.png'))

        def wait(phase, predicate):
            if phase == '이탈 가능한 영웅 목록 확인':
                return predicate(self.screen)
            if phase == '이탈 영웅 금색 선택 테두리 및 활성 버튼 확인':
                value = predicate(self.selected)
                self.assertIsNotNone(value)
                return value
            return predicate(followup)

        self.bot._wait = wait
        with patch('src.chaos.exploration.random.choice', return_value=TARGET) as choose:
            result = self.bot._event_hero_departure()
        choose.assert_called_once_with(tuple((350, y, 290, 80) for y in (85, 190, 295, 400)))
        self.assertEqual(result, 'event_result')
        self.assertEqual(self.bot._tap.call_count, 2)
        self.assertEqual(self.bot._tap.call_args_list[0].args[0], TARGET)
        self.assertEqual(self.bot.stats['departed_heroes'], 1)

    def test_no_confirmation_when_selection_never_registers(self):
        self.bot._capture = Mock(return_value=self.screen)
        self.bot._wait = Mock(side_effect=[tuple(self.observer.hero_departure_candidates(self.screen)),
                                           RecognitionTimeout('not selected')])
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            with self.assertRaises(RecognitionTimeout):
                self.bot._event_hero_departure()
        self.bot._tap.assert_called_once_with(TARGET)

    def test_changed_party_before_selection_never_clicks(self):
        self.bot._capture = Mock(return_value=np.zeros_like(self.screen))
        self.bot._wait = Mock(return_value=tuple(self.observer.hero_departure_candidates(self.screen)))
        with self.assertRaises(RecognitionTimeout):
            self.bot._event_hero_departure()
        self.bot._tap.assert_not_called()

    def test_changed_selected_hero_never_confirms_departure(self):
        self.bot._capture = Mock(side_effect=[self.screen, self.screen])
        button = self.observer.hero_departure_selected(self.selected, TARGET, self.portrait)
        self.bot._wait = Mock(side_effect=[tuple(self.observer.hero_departure_candidates(self.screen)), button])
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            with self.assertRaises(RecognitionTimeout):
                self.bot._event_hero_departure()
        self.bot._tap.assert_called_once_with(TARGET)

    def test_departure_enters_existing_flow_and_defeat_is_terminal(self):
        self.bot._state = Mock(side_effect=['hero_departure', 'defeat'])
        self.bot._capture = Mock(return_value=self.screen)
        self.bot._event_hero_departure = Mock(return_value='defeat')
        self.assertEqual(run_event_flow(self.bot), 'defeat')
        self.bot._event_hero_departure.assert_called_once_with()
        self.assertEqual(self.bot.stats['nodes'], 0)

    def test_confirmation_is_confirmed_only_after_verified_departure(self):
        popup = read_image(str(RAW / 'story/Screenshot_2026.09.24_13.49.26.082.png'))
        self.assertIsNotNone(self.observer.find(popup, 'story_confirm'))
        self.assertIsNotNone(self.observer.find(popup, 'story_cancel'))
        self.bot._capture = Mock(side_effect=[self.screen, self.selected, popup])

        def wait(phase, predicate):
            if phase == '이탈 가능한 영웅 목록 확인':
                return predicate(self.screen)
            if phase == '이탈 영웅 금색 선택 테두리 및 활성 버튼 확인':
                return predicate(self.selected)
            return predicate(popup)

        self.bot._wait = wait
        self.bot._state = Mock(return_value='map')
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            self.assertEqual(self.bot._event_hero_departure(), 'map')
        self.assertEqual(self.bot._tap.call_count, 3)
        self.assertEqual(self.bot._tap.call_args.args[0], self.observer.find(popup, 'story_confirm'))
        self.assertEqual(self.bot.stats['departed_heroes'], 1)

    def test_changed_confirmation_popup_is_not_confirmed(self):
        popup = read_image(str(RAW / 'story/Screenshot_2026.09.24_13.49.26.082.png'))
        self.bot._capture = Mock(side_effect=[self.screen, self.selected, self.screen])
        self.bot._wait = Mock(side_effect=[tuple(self.observer.hero_departure_candidates(self.screen)),
            self.observer.hero_departure_selected(self.selected, TARGET, self.portrait),
            ('confirm', self.observer.find(popup, 'story_confirm'))])
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            with self.assertRaises(RecognitionTimeout):
                self.bot._event_hero_departure()
        self.assertEqual(self.bot._tap.call_count, 2)
        self.assertNotIn('departed_heroes', self.bot.stats)


if __name__ == '__main__':
    unittest.main()
