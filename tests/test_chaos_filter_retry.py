import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.chaos.bot import KnightRecruitmentBot, RecognitionTimeout, _Stopped
from tests.test_chaos_knight import ScriptedObserver

ROOT = Path(__file__).resolve().parents[1]


class FilterRetryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.observer = ScriptedObserver()
        self.observer.config = dict(self.observer.config, timeout_seconds=.01)
        self.bot = KnightRecruitmentBot(Mock(), ROOT, tmp.name, self.observer)
        self.filter = (740, 20, 40, 30)
        self.element = (780, 120, 30, 36)
        self.closed = {'knight_header': self.filter, 'filter': self.filter}
        self.plain = {'filter_panel': self.filter, 'dark_1': self.element}
        self.selected = {'filter_panel': self.filter, 'dark_2': self.element}
        self.screen = self.closed
        self.bot._capture = lambda: self.screen
        self.taps = []
        self.bot._tap = self.tap

    def tap(self, bounds):
        self.taps.append(bounds)
        self.screen = self.plain if bounds == self.filter else self.selected

    def test_hidden_class_icon_after_open_does_not_block_selection(self):
        self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter, self.element])

    def test_filter_click_not_applied_is_retried_from_verified_closed_menu(self):
        def tap(bounds):
            self.taps.append(bounds)
            if len(self.taps) > 1:
                self.screen = self.plain if bounds == self.filter else self.selected
        self.bot._tap = tap
        self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter, self.filter, self.element])

    def test_element_click_not_applied_retries_only_element(self):
        def tap(bounds):
            self.taps.append(bounds)
            if bounds == self.filter:
                self.screen = self.plain
            elif self.taps.count(self.element) == 2:
                self.screen = self.selected
        self.bot._tap = tap
        self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter, self.element, self.element])

    def test_already_selected_element_is_not_toggled(self):
        def tap(bounds):
            self.taps.append(bounds)
            self.screen = self.selected
        self.bot._tap = tap
        self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter])

    def test_selection_arriving_at_fresh_check_is_not_toggled(self):
        capture_count = [0]
        def capture():
            if self.screen is self.plain:
                capture_count[0] += 1
                if capture_count[0] == 3:
                    self.screen = self.selected
            return self.screen
        self.bot._capture = capture
        self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter])

    def test_unapplied_element_clicks_stop_after_three_attempts(self):
        def tap(bounds):
            self.taps.append(bounds)
            self.screen = self.plain
        self.bot._tap = tap
        with self.assertRaisesRegex(RecognitionTimeout, '3회'):
            self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter] + [self.element]*3)

    def test_unapplied_filter_clicks_stop_after_three_attempts(self):
        self.bot._tap = self.taps.append
        with self.assertRaisesRegex(RecognitionTimeout, '3회'):
            self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter]*3)

    def test_missing_class_icon_before_open_never_authorizes_click(self):
        self.screen = {'filter': self.filter}
        with self.assertRaises(RecognitionTimeout):
            self.bot._configure_element_filter()
        self.assertEqual(self.taps, [])

    def test_filter_closed_during_selection_is_reopened_with_class_check(self):
        def tap(bounds):
            self.taps.append(bounds)
            if bounds == self.filter:
                self.screen = self.plain
            else:
                self.screen = self.closed if self.taps.count(self.element) == 1 else self.selected
        self.bot._tap = tap
        self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter, self.element, self.filter, self.element])

    def test_stop_during_settle_does_not_send_another_click(self):
        def tap(bounds):
            self.taps.append(bounds)
            self.bot.stop_event.set()
        self.bot._tap = tap
        with self.assertRaises(_Stopped):
            self.bot._configure_element_filter()
        self.assertEqual(self.taps, [self.filter])
