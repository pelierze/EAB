import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.chaos.node_observer import NodeObserver
from src.chaos.exploration import NodeProgressionBot
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'images/chaos/node_progression/raw'


class RankResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        cls.observer.config['poll_seconds'] = 0

    def frame(self, name='rank_result_event_live.png'):
        return read_image(str(RAW/name))

    def test_rest_and_event_backgrounds_use_same_result(self):
        for name in ('rank_result_event_live.png', 'rest_wukong_rankup_live.png'):
            with self.subTest(name=name):
                self.assertEqual(self.observer.classify(self.frame(name)), 'rank_result')
                self.assertIsNotNone(self.observer.find(self.frame(name), 'rank_close'))

    def test_hero_name_portrait_and_card_number_are_not_required(self):
        frame = self.frame()
        frame[140:330,310:575] = 0
        frame[420:590,310:575] = 0
        self.assertEqual(self.observer.classify(frame), 'rank_result')

    def test_glowing_rank_text_is_not_required(self):
        frame = self.frame()
        frame[330:420, 310:575] = 0
        with patch.object(self.observer, 'ocr') as ocr:
            self.assertTrue(self.observer.is_rank_result(frame))
            ocr.assert_not_called()

    def test_arrow_and_rank_symbols_are_required(self):
        frame = self.frame()
        frame[195:265,805:895] = 0
        with patch.object(self.observer, 'ocr') as ocr:
            self.assertFalse(self.observer.is_rank_result(frame))
            ocr.assert_not_called()
        frame = self.frame()
        frame[209:253, 882:927] = 0
        self.assertFalse(self.observer.is_rank_result(frame))

    def test_other_rewards_cannot_authorize_rank_close(self):
        for name in ('event_loot_popup_live.png', 'event_rank_reward_live.png', 'loot_cards_live.png'):
            self.assertIsNone(self.observer.find(self.frame(name), 'rank_close'))

    def test_latest_rest_result_ignores_unreadable_rank_text(self):
        frame = self.frame('rest_shadow_rose_rankup_local_live.png')
        self.assertEqual(self.observer.classify(frame), 'rank_result')
        self.assertIsNotNone(self.observer.find(frame, 'event_loot_close'))
        for rows in (None, [['LEVEL UP', .99]], [['RANK UP', .3]]):
            with self.subTest(rows=rows), patch.object(
                    self.observer, 'ocr', Mock(return_value=(rows, None))) as ocr:
                self.assertEqual(self.observer.classify(frame), 'rank_result')
                self.assertIsNotNone(self.observer.find(frame, 'rank_close'))
                ocr.assert_not_called()

    def test_actual_loot_popup_still_classifies_with_unreadable_rank_text(self):
        with patch.object(self.observer, 'ocr', Mock(return_value=(None, None))):
            self.assertEqual(self.observer.classify(self.frame('event_loot_popup_live.png')),
                             'event_loot_popup')

    def test_rank_close_does_not_call_ocr(self):
        frame = self.frame('rest_shadow_rose_rankup_local_live.png')
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, self.observer)
            bot._capture = lambda: frame
            taps = []
            bot._tap = lambda bounds: taps.append(tuple(bounds))
            classify = self.observer.classify
            with patch.object(self.observer, 'ocr', side_effect=AssertionError('text OCR must not run')) as ocr, \
                 patch.object(self.observer, 'classify', side_effect=lambda s: 'rest' if taps else classify(s)), \
                 patch.object(self.observer, 'forbidden', return_value=[]):
                self.assertEqual(bot._dismiss_popup('결과 닫기', 'rank_result', 'rank_close',
                                                   {'rest', 'event_loot_popup'}), 'rest')
            self.assertEqual(taps, [tuple(self.observer.config['rank_result_close_bounds'])])
            ocr.assert_not_called()

    def test_rankup_flow_uses_common_result_without_card_digit_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, self.observer)
            menu = self.frame('event_rank_reward_live.png')
            result = self.frame()
            current = [0]
            bot._capture = lambda: menu if current[0] < 2 else result
            bot._rank_target = Mock(return_value=('unregistered_hero', 1, 10, 20, 30, 40))
            bot._tap = lambda bounds: current.__setitem__(0, current[0]+1)
            bot._dismiss_popup = Mock()
            original_classify = self.observer.classify
            original_find = self.observer.find
            with patch.object(self.observer, 'classify', side_effect=lambda s: 'rank_menu' if s is menu else original_classify(s)), \
                 patch.object(self.observer, 'find', side_effect=lambda s,n: (10,20,30,40) if s is menu else original_find(s,n)), \
                 patch.object(self.observer, 'forbidden', return_value=[]), \
                   patch.object(self.observer, 'rank_hero_selected', return_value=True), \
                   patch.dict(self.observer.config, timeout_seconds=3, recognition_attempts=1), \
                 patch.object(self.observer, 'read_rank_digit') as digit:
                bot._rankup()
                digit.assert_not_called()
                bot._dismiss_popup.assert_called_once()
                self.assertEqual(bot._dismiss_popup.call_args.args[1:3], ('rank_result', 'rank_close'))
                self.assertIn('rest', bot._dismiss_popup.call_args.args[3])

    def test_resume_result_continues_reward_without_second_rankup(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, self.observer, max_nodes=1)
            frames = [self.frame(), self.frame('event_rank_reward_live.png'), self.frame('boss_map_live.png')]
            current = [0]
            taps = []
            bot._capture = lambda: frames[current[0]]
            def tap(bounds):
                taps.append(tuple(bounds))
                current[0] += 1
            bot._tap = tap
            bot._rankup = Mock()
            self.assertEqual(bot.run()['status'], 'completed')
            self.assertEqual(taps, [tuple(self.observer.config['rank_result_close_bounds']),
                                   self.observer.find(frames[1], 'event_reward_continue')])
            bot._rankup.assert_not_called()


class RestResultReturnTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.observer = Mock()
        self.bot = NodeProgressionBot(Mock(), ROOT, tmp.name, self.observer)
        self.bot._capture = Mock(return_value='rest')
        self.observer.classify.side_effect = lambda screen: screen
        self.observer.find.side_effect = lambda screen, marker: (
            (10, 20, 30, 40) if screen == 'rest' and marker == 'leave' else None)
        self.bot._guarded_tap = Mock()
        self.bot._rankup = Mock(return_value='event_loot_popup')
        self.bot._record = Mock()

    def test_remaining_result_is_closed_before_rest_completion_check(self):
        calls = []
        self.bot._dismiss_popup = Mock(side_effect=lambda *args: calls.append('close') or 'rest')
        self.bot._state = Mock(side_effect=lambda phase, allowed: (
            calls.append('state') or ('rank_menu' if allowed == {'rank_menu'} else
                                     'rest' if 'rest' in allowed else 'map')))
        def wait(phase, predicate):
            calls.append('disabled')
            self.assertIsNone(predicate('rank_result'))
            return predicate('rest')
        self.bot._wait = wait
        self.bot._rest()
        self.assertEqual(calls, ['state', 'close', 'state', 'disabled', 'state'])
        self.assertEqual(self.bot.stats['nodes'], 1)
        self.assertEqual(self.bot._guarded_tap.call_args.args[1:3], ('rest', 'leave'))

    def test_verified_map_return_does_not_tap_stale_rest_controls(self):
        self.bot._dismiss_popup = Mock(return_value='map')
        self.bot._state = Mock(side_effect=['rank_menu', 'map'])
        self.bot._wait = Mock()
        self.bot._rest()
        self.bot._wait.assert_not_called()
        self.bot._guarded_tap.assert_called_once()
        self.assertEqual(self.bot.stats['nodes'], 1)


class BattleRankCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)
        cls.observer.config['poll_seconds'] = 0

    def frame(self):
        return read_image(str(RAW / 'battle/victory_rank_complete_warrior_local_live.png'))

    def test_reported_completion_ignores_name_text_art_and_continue_prefix(self):
        screen = self.frame()
        screen[170:535, 525:750] = 0
        screen[645:672, 582:625] = 0
        self.assertEqual(self.observer.classify(screen), 'battle_rank_complete')
        self.assertEqual(self.observer.find(screen, 'continue'), (625, 645, 75, 27))

    def test_class_icon_victory_and_continue_control_are_all_required(self):
        for bounds in ((704, 532, 48, 48), (480, 15, 350, 75), (473, 626, 334, 70)):
            screen = self.frame()
            x, y, w, h = bounds
            screen[y:y+h, x:x+w] = 0
            with self.subTest(bounds=bounds):
                self.assertIsNone(self.observer.find(screen, 'battle_rank_complete'))
                self.assertNotEqual(self.observer.classify(screen), 'battle_rank_complete')

    def test_continue_lettering_is_not_required_when_the_frame_is_verified(self):
        screen = self.frame()
        screen[645:672, 625:700] = 0
        self.assertIsNotNone(self.observer.find(screen, 'battle_rank_complete'))
        self.assertEqual(self.observer.classify(screen), 'battle_rank_complete')

    def test_other_rewards_do_not_complete_rankup(self):
        for name in ('battle/victory_live.png', 'battle/victory_rank_reward_live.png',
                     'event_rank_reward_live.png', 'event_recruit_reward_live.png'):
            with self.subTest(name=name):
                screen = read_image(str(RAW / name))
                self.assertIsNone(self.observer.find(screen, 'battle_rank_complete'))

    def test_completion_returns_to_map_without_another_rankup(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = NodeProgressionBot(Mock(), ROOT, tmp, self.observer)
            screens = [self.frame(), read_image(str(RAW / 'boss_map_live.png'))]
            position = [0]
            taps = []
            bot._capture = lambda: screens[position[0]]
            def tap(bounds):
                taps.append(tuple(bounds))
                position[0] += 1
            bot._tap = tap
            bot._rankup = Mock()
            self.assertEqual(bot._dispatch_event_screen(self.observer.classify(screens[0])), 'map')
            self.assertEqual(taps, [(625, 645, 75, 27)])
            bot._rankup.assert_not_called()


class EventRankRewardIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observer = NodeObserver(ROOT)

    def test_existing_issue_and_local_reports_are_rank_rewards(self):
        for name in ('event_rank_reward_live.png', 'event_rank_reward_issue16.png',
                     'event_rank_reward_local_live.png'):
            with self.subTest(name=name):
                screen = read_image(str(RAW / name))
                self.assertEqual(self.observer.classify(screen), 'rank_reward')
                self.assertIsNotNone(self.observer.find(screen, 'event_rank_reward_button'))

    def test_title_and_description_are_not_required(self):
        screen = read_image(str(RAW / 'event_rank_reward_local_live.png'))
        screen[260:380, 540:745] = 0
        self.assertEqual(self.observer.classify(screen), 'rank_reward')

    def test_icon_and_continue_are_both_required(self):
        for x, y, w, h in ((590,145,110,105), (480,615,330,85)):
            screen = read_image(str(RAW / 'event_rank_reward_local_live.png'))
            screen[y:y+h, x:x+w] = 0
            self.assertNotEqual(self.observer.classify(screen), 'rank_reward')

    def test_other_rewards_and_rankup_results_are_not_rank_rewards(self):
        for name in ('event_recruit_reward_live.png', 'event_loot_popup_live.png',
                     'rank_result_event_live.png', 'battle/victory_rank_complete_warrior_local_live.png'):
            with self.subTest(name=name):
                self.assertNotEqual(self.observer.classify(read_image(str(RAW / name))), 'rank_reward')
