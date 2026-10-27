"""Departure and rank-up share a textless, event-scoped hero picker."""
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
        cls.active = read_image(str(RAW / 'rest_wukong_selected_live.png'))
        cls.popup = read_image(str(RAW / 'story/Screenshot_2026.09.24_13.49.26.082.png'))
        cls.map = read_image(str(RAW / 'map_after_rest_live.png'))

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        observer = NodeObserver(ROOT)
        observer.config.update(poll_seconds=0, stable_frames=2, timeout_seconds=2,
                               recognition_attempts=1)
        self.bot = NodeProgressionBot(Mock(), ROOT, directory.name, observer)
        self.bot.event_context = True
        self.bot._verified_noncombat_node = 'event'

    def selected(self, row=3, active=True):
        screen = self.screen.copy()
        y = 85+row*105
        # Synthetic selected border; the action frame is copied from a real
        # enabled rank-up button. An enabled departure capture is unavailable.
        screen[y-3:y, 375:620] = (20, 180, 220)
        screen[y+81:y+84, 375:620] = (20, 180, 220)
        screen[y+10:y+70, 343:346] = (20, 180, 220)
        if active:
            screen[628:692, 938:1238] = self.active[628:692, 938:1238]
        return screen

    def replay(self, frames):
        index = [0]
        taps = []
        self.bot._capture = lambda: frames[index[0]]
        def tap(bounds):
            taps.append(tuple(bounds))
            index[0] += 1
        self.bot._tap = tap
        return taps

    def test_departure_and_rankup_are_common_menus_only_in_event_context(self):
        for filename in ('event_hero_departure_local_live.png', 'rest_rank_menu_live.png'):
            screen = read_image(str(RAW / filename))
            self.assertEqual(self.bot._classify(screen), 'event_hero_menu')
            self.assertEqual(self.observer.event_hero_candidates(screen),
                             [(350, y, 290, 80) for y in (85, 190, 295, 400)])
        self.bot.event_context = False
        self.assertEqual(self.bot._classify(read_image(str(RAW / 'rest_rank_menu_live.png'))), 'rank_menu')

    def test_title_names_and_action_words_are_not_inputs(self):
        screen = self.selected()
        screen[12:55, 60:300] = 0
        for y in (85, 190, 295, 400):
            screen[y+15:y+45, 400:505] = 0
        screen[634:686, 956:1220] = 0
        with patch.object(self.bot.observer, 'ocr', side_effect=AssertionError('OCR forbidden')) as ocr:
            self.assertEqual(self.bot._classify(screen), 'event_hero_menu')
            portrait = screen[406:471, 510:630].copy()
            self.assertEqual(self.bot.observer.event_hero_selected(screen, TARGET, portrait)[0], 'active')
            ocr.assert_not_called()

    def test_each_row_needs_class_and_rank_marks(self):
        for region in ((350, 90, 60, 40), (345, 125, 55, 40)):
            screen = self.screen.copy()
            x, y, w, h = region
            screen[y:y+h, x:x+w] = 0
            self.assertNotIn((350, 85, 290, 80), self.observer.event_hero_candidates(screen))

    def test_duplicate_classes_are_independent_candidates(self):
        screen = self.screen.copy()
        screen[190:270, 350:640] = screen[85:165, 350:640]
        self.assertEqual(len(self.observer.event_hero_candidates(screen)), 4)

    def test_fewer_heroes_only_offer_visible_rows(self):
        screen = self.screen.copy()
        screen[285:490, 330:660] = 0
        self.assertEqual(self.observer.event_hero_candidates(screen),
                         [(350, 85, 290, 80), (350, 190, 290, 80)])

    def test_other_screens_do_not_offer_hero_candidates(self):
        for filename in ('map_after_rest_live.png', 'event_rank_reward_live.png',
                         'event_recruit_reward_live.png', 'loot_cards_live.png', 'rank_result_event_live.png'):
            self.assertEqual(self.observer.event_hero_candidates(read_image(str(RAW / filename))), [])

    def test_selected_border_portrait_and_button_state_are_checked(self):
        portrait = self.screen[406:471, 510:630].copy()
        self.assertIsNone(self.observer.event_hero_selected(self.screen, TARGET, portrait))
        self.assertEqual(self.observer.event_hero_selected(self.selected(), TARGET, portrait)[0], 'active')
        self.assertEqual(self.observer.event_hero_selected(self.selected(active=False), TARGET, portrait), ('disabled',))
        self.assertIsNone(self.observer.event_hero_selected(self.selected(), TARGET,
                                                          self.screen[91:156, 510:630]))

    def test_verified_action_then_textless_confirmation_then_map(self):
        taps = self.replay([self.screen, self.selected(), self.popup, self.map])
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            self.assertEqual(self.bot._event_hero_menu(), 'map')
        self.assertEqual(taps, [TARGET, (938, 628, 300, 64),
                                self.observer.event_choice_warning_controls(self.popup)['confirm']])
        self.assertEqual(self.bot.stats['event_hero_actions'], 1)
        self.assertNotIn('departed_heroes', self.bot.stats)
        self.bot.adb.tap.assert_not_called()

    def test_rank_result_reward_card_and_continue_are_handled_without_reselecting(self):
        result = read_image(str(RAW / 'rank_result_event_live.png'))
        reward = read_image(str(RAW / 'event_rank_reward_live.png'))
        taps = self.replay([self.screen, self.selected(), result, reward, self.map])
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            self.assertEqual(run_event_flow(self.bot), 'map')
        self.assertEqual(len(taps), 4)
        self.assertEqual(taps[2], tuple(self.observer.config['rank_result_close_bounds']))
        self.assertEqual(taps[3], self.observer.find(reward, 'event_reward_continue'))
        self.assertEqual(self.bot.stats['event_hero_actions'], 1)
        self.assertEqual(self.bot.stats['nodes'], 1)

    def test_disabled_candidate_is_excluded_then_another_hero_is_used(self):
        other = (350, 85, 290, 80)
        taps = self.replay([self.screen, self.selected(active=False), self.selected(row=0), self.map])
        with patch('src.chaos.exploration.random.choice', side_effect=[TARGET, other]) as choose:
            self.assertEqual(self.bot._event_hero_menu(), 'map')
        self.assertNotIn(TARGET, choose.call_args.args[0])
        self.assertEqual(taps, [TARGET, other, (938, 628, 300, 64)])

    def test_all_disabled_candidates_stop_without_execution(self):
        self.bot._capture = Mock(return_value=self.screen)
        self.bot._wait = Mock(side_effect=[((350, 85, 290, 80),), ('disabled',)])
        self.bot._tap = Mock()
        with patch.object(self.bot.observer, 'event_hero_candidates', return_value=[(350, 85, 290, 80)]), \
             patch.object(self.bot.observer, 'event_hero_selected', return_value=('disabled',)):
            with self.assertRaisesRegex(RecognitionTimeout, '실행 가능한'):
                self.bot._event_hero_menu()
        self.bot._tap.assert_called_once_with((350, 85, 290, 80))

    def test_changed_party_before_selection_never_clicks(self):
        self.bot._capture = Mock(return_value=np.zeros_like(self.screen))
        self.bot._wait = Mock(return_value=tuple(self.observer.event_hero_candidates(self.screen)))
        self.bot._tap = Mock()
        with self.assertRaises(RecognitionTimeout):
            self.bot._event_hero_menu()
        self.bot._tap.assert_not_called()

    def test_changed_selected_hero_never_executes(self):
        self.bot._capture = Mock(side_effect=[self.screen, self.screen])
        self.bot._wait = Mock(side_effect=[tuple(self.observer.event_hero_candidates(self.screen)),
                                          ('active', (938, 628, 300, 64))])
        self.bot._tap = Mock()
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            with self.assertRaises(RecognitionTimeout):
                self.bot._event_hero_menu()
        self.bot._tap.assert_called_once_with(TARGET)

    def test_confirmation_without_prior_hero_action_is_not_authorized(self):
        self.bot._capture = Mock(return_value=self.popup)
        self.bot._tap = Mock()
        def wait(phase, predicate):
            self.assertIsNone(predicate(self.popup))
            raise RecognitionTimeout('no hero list')
        self.bot._wait = wait
        with self.assertRaises(RecognitionTimeout):
            self.bot._event_hero_menu()
        self.bot._tap.assert_not_called()

    def test_changed_confirmation_is_not_approved(self):
        self.bot._capture = Mock(side_effect=[self.screen, self.selected(), self.map])
        self.bot._wait = Mock(side_effect=[tuple(self.observer.event_hero_candidates(self.screen)),
            ('active', (938, 628, 300, 64)),
            ('confirm', self.observer.event_choice_warning_controls(self.popup)['confirm'])])
        self.bot._tap = Mock()
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            with self.assertRaises(RecognitionTimeout):
                self.bot._event_hero_menu()
        self.assertEqual(self.bot._tap.call_count, 2)

    def test_unrecognized_outcome_never_repeats_execution(self):
        self.bot._capture = Mock(side_effect=[self.screen, self.selected()])
        self.bot._wait = Mock(side_effect=[tuple(self.observer.event_hero_candidates(self.screen)),
            ('active', (938, 628, 300, 64)), RecognitionTimeout('unknown outcome')])
        self.bot._tap = Mock()
        with patch('src.chaos.exploration.random.choice', return_value=TARGET):
            with self.assertRaises(RecognitionTimeout):
                self.bot._event_hero_menu()
        self.assertEqual(self.bot._tap.call_count, 2)
