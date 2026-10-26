import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np

from src.chaos.bot import KnightRecruitmentBot, _Stopped
from src.chaos.exploration import ExplorationBot
from src.chaos.pause import ExplorationPause, ResumeExploration
from src.image_matcher import read_image

ROOT = Path(__file__).resolve().parents[1]


class ExplorationPauseTests(unittest.TestCase):
    def thread(self, action):
        outcomes = []
        def run():
            try:
                outcomes.append(action())
            except BaseException as exc:
                outcomes.append(exc)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        return worker, outcomes

    def bare_bot(self):
        bot = object.__new__(KnightRecruitmentBot)
        bot.stop_event = threading.Event()
        bot.pause_control = ExplorationPause()
        bot.adb = Mock()
        bot.stats = {'clicks': 0}
        bot._record = Mock()
        bot.observer = Mock(config={'poll_seconds': 0})
        self.addCleanup(bot.stop_event.set)
        self.addCleanup(bot.pause_control.resume)
        return bot

    def test_acknowledged_pause_has_no_input_and_resume_discards_old_tap(self):
        bot = self.bare_bot()
        bot.pause_control.pause()
        worker, outcomes = self.thread(lambda: bot._tap((100, 100, 20, 20)))
        self.assertTrue(bot.pause_control.acknowledged.wait(2))
        bot.adb.tap.assert_not_called()
        bot.pause_control.resume()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(outcomes[0], ResumeExploration)
        bot.adb.tap.assert_not_called()

    def test_stop_while_paused_wakes_worker(self):
        bot = self.bare_bot()
        bot.pause_control.pause()
        worker, outcomes = self.thread(bot._check_stop)
        self.assertTrue(bot.pause_control.acknowledged.wait(2))
        bot.stop_event.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertIsInstance(outcomes[0], _Stopped)
        self.assertFalse(bot.pause_control.acknowledged.is_set())

    def test_pause_requested_during_before_input_recording_stops_before_adb(self):
        bot = self.bare_bot()
        bot._record.side_effect = lambda label: bot.pause_control.pause()
        worker, outcomes = self.thread(lambda: bot._tap((100, 100, 20, 20)))
        self.assertTrue(bot.pause_control.acknowledged.wait(2))
        bot.adb.tap.assert_not_called()
        bot.pause_control.resume()
        worker.join(2)
        self.assertIsInstance(outcomes[0], ResumeExploration)
        bot.adb.tap.assert_not_called()

    def test_resume_rebuilds_handlers_and_rescans_without_increasing_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            facade = ExplorationBot(Mock(), ROOT, directory, target_clears=10)
            facade.attempt, facade.cleared_rounds, facade.failed_rounds = 7, 5, 1
            facade.nodes.stats.update(nodes=9, clicks=57)
            facade.nodes._last_event_choice_bounds = (20, 30, 40, 50)
            old = facade.nodes
            original = facade._run_stages
            stages = [0]
            def run_stages():
                stages[0] += 1
                if stages[0] == 1:
                    facade.active = facade.nodes
                    facade.nodes.pause_control = facade.pause_control
                    facade.nodes._tap((20, 30, 40, 50))
                    self.fail('stale input stack must be abandoned')
                self.assertIsNot(facade.nodes, old)
                self.assertIsNone(facade.nodes._last_event_choice_bounds)
                self.assertIsNone(facade.nodes._verified_noncombat_node)
                self.assertEqual(facade.nodes.stats['nodes'], 9)
                self.assertEqual(facade.nodes.stats['clicks'], 57)
                frame = read_image(str(ROOT / 'images/chaos/node_progression/raw/map_after_rest_live.png'))
                facade.nodes._capture = Mock(return_value=frame)
                facade.nodes.run = Mock(return_value={'status': 'completed'})
                return original()
            facade._run_stages = run_stages
            facade.set_user_action('pause')
            worker, outcomes = self.thread(facade.run)
            self.assertTrue(facade.pause_control.acknowledged.wait(3))
            self.assertEqual(facade.get_stats()['status'], 'paused')
            facade.set_user_action('resume')
            worker.join(20)
            self.assertFalse(worker.is_alive())
            self.assertEqual(outcomes[0]['status'], 'completed')
            self.assertEqual((facade.attempt, facade.cleared_rounds, facade.failed_rounds), (7, 5, 1))
            old.adb.tap.assert_not_called()
            self.assertEqual(stages[0], 2)

    def test_pause_request_status_is_distinct_from_confirmed_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            facade = ExplorationBot(Mock(), ROOT, directory)
            facade.set_user_action('pause')
            self.assertFalse(facade.paused)
            self.assertTrue(facade.pause_requested)
            self.assertEqual(facade.get_stats()['status'], 'pausing')
            facade.set_user_action('resume')
            self.assertFalse(facade.pause_requested)

    def test_facade_stop_while_paused_clears_request_and_ends_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            facade = ExplorationBot(Mock(), ROOT, directory)
            facade.set_user_action('pause')
            worker, outcomes = self.thread(facade.active._check_stop)
            self.assertTrue(facade.pause_control.acknowledged.wait(2))
            facade.set_user_action('stop')
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(outcomes[0], _Stopped)
            self.assertFalse(facade.pause_requested)

    def test_event_context_is_kept_but_previous_targets_are_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            facade = ExplorationBot(Mock(), ROOT, directory)
            facade.nodes.event_context = True
            facade.nodes._verified_noncombat_node = 'event'
            facade.nodes.rejected_event_choices.add((1, 2, 3, 4))
            facade._restart_after_pause()
            self.assertTrue(facade.nodes.event_context)
            self.assertTrue(facade.nodes._event_intro_pending)
            self.assertEqual(facade.nodes.rejected_event_choices, set())
            with np.load(ROOT / 'tests/fixtures/exploration/english_event_result_20261025.npz') as data:
                self.assertEqual(facade.nodes._classify(data['screen']), 'unknown_event_result')
