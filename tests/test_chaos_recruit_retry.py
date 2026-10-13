import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.chaos.bot import KnightRecruitmentBot, RecognitionTimeout, _Stopped
from tests.test_chaos_knight import ScriptedObserver

ROOT = Path(__file__).resolve().parents[1]


class RecruitRetryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        observer = ScriptedObserver()
        observer.config = dict(observer.config, timeout_seconds=15)
        self.bot = KnightRecruitmentBot(Mock(), ROOT, tmp.name, observer)
        self.portrait = (500, 100, 100, 40)
        self.button = (1030, 630, 110, 60)
        self.bot._selection_target = self.portrait
        self.selected = {'rose': self.portrait, 'rose_selected': True,
                         'recruit_active': self.button}
        self.screen = self.selected
        self.bot._capture = lambda: self.screen
        self.taps = []
        self.bot._tap = self.tap
        self.clock = patch('src.chaos.bot.time.monotonic', side_effect=itertools.count(step=.25))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def tap(self, bounds):
        self.taps.append(bounds)
        self.screen = {'done': True}

    def test_unapplied_initial_click_retries_same_button_then_confirms(self):
        self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [self.button])

    def test_completed_hero_never_receives_another_click(self):
        self.screen = dict(self.selected, done=True)
        self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [])

    def test_loading_and_missing_completion_marker_do_not_authorize_retry(self):
        self.screen = {}
        with self.assertRaises(RecognitionTimeout):
            self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [])

    def test_button_without_same_hero_gold_selection_does_not_authorize_retry(self):
        for screen in ({'recruit_active': self.button},
                       {'rose': self.portrait, 'recruit_active': self.button},
                       {'other_hero': self.portrait, 'rose_selected': True, 'recruit_active': self.button},
                       dict(self.selected, filter_panel=self.button)):
            with self.subTest(screen=screen):
                self.screen = screen
                with self.assertRaises(RecognitionTimeout):
                    self.bot._confirm_recruitment()
                self.assertEqual(self.taps, [])

    def test_disabled_button_is_not_retried(self):
        self.screen = {'rose': self.portrait, 'rose_selected': True}
        with self.assertRaises(RecognitionTimeout):
            self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [])

    def test_no_more_than_two_additional_clicks_and_three_second_spacing(self):
        times = []
        def tap(bounds):
            self.taps.append(bounds)
            from src.chaos.bot import time
            times.append(time.monotonic())
        self.bot._tap = tap
        with self.assertRaises(RecognitionTimeout):
            self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [self.button]*2)
        self.assertGreaterEqual(times[0], 3)
        self.assertGreaterEqual(times[1]-times[0], 3)

    def test_transition_after_retry_readiness_prevents_stale_click(self):
        wait = self.bot._wait
        def changed(phase, predicate):
            state = wait(phase, predicate)
            if state[0] == 'retry':
                self.screen = {'done': True}
            return state
        self.bot._wait = changed
        self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [])

    def test_stop_before_retry_does_not_send_input(self):
        self.bot.stop_event.set()
        with self.assertRaises(_Stopped):
            self.bot._confirm_recruitment()
        self.assertEqual(self.taps, [])
