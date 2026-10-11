import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from src.chaos.bot import _Stopped
from src.chaos.exploration import NodeProgressionBot

ROOT = Path(__file__).resolve().parents[1]
A = (78, 556, 362, 131)
B = (458, 556, 362, 131)


def frame(signature, cards=(A, B), available=None, state='unknown_event'):
    return {'signature': signature, 'cards': cards,
            'available': cards if available is None else available, 'state': state}


class EventChoiceRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        observer = Mock()
        observer.config = {'timeout_seconds': 1, 'stable_frames': 2, 'poll_seconds': 0}
        observer.event_cards.side_effect = lambda s: s['cards']
        observer.available_event_cards.side_effect = lambda s, cards: s['available']
        self.bot = NodeProgressionBot(Mock(), ROOT, self.tmp.name, observer)
        self.bot._classify = lambda s: s['state']
        self.bot._event_signature = lambda s: s['signature']
        self.bot._tap = Mock()
        self.bot._start_report = Mock()
        self.bot._report = Mock()
        self.bot._event_transition = Mock(return_value='map')
        self.bot.stop_event = Mock()
        self.bot.stop_event.is_set.return_value = False
        self.bot.stop_event.wait.return_value = False

    def run_frames(self, frames):
        self.bot._capture = Mock(side_effect=frames)
        with patch('src.chaos.exploration.random.choice', side_effect=lambda cs: cs[0]) as choose:
            result = self.bot._unknown_event()
        return result, choose

    def test_changed_page_discards_old_candidate_and_rechecks_two_stable_frames(self):
        old = frame('before', cards=(A,))
        new = frame('after', cards=(B,))
        # Stable wait, review, final check; the changed final check is not clicked.
        result, choose = self.run_frames([old, old, old, new, new, new, new, new])
        self.assertEqual(result, 'map')
        self.assertEqual(choose.call_args_list, [call([A]), call([B])])
        self.bot._tap.assert_called_once_with(B)
        self.bot._event_transition.assert_called_once_with('after')
        self.assertEqual(self.bot.stop_event.wait.call_args_list.count(call(1)), 1)

    def test_change_during_review_restarts_before_random_selection(self):
        old = frame('before', cards=(A,))
        new = frame('after', cards=(B,))
        _, choose = self.run_frames([old, old, new, new, new, new, new])
        choose.assert_called_once_with([B])
        self.bot._tap.assert_called_once_with(B)

    def test_newly_forbidden_or_disabled_candidate_is_reselected(self):
        old = frame('same')
        restricted = frame('same', available=(B,))
        _, choose = self.run_frames([old, old, old, restricted,
                                     restricted, restricted, restricted, restricted])
        self.assertEqual(choose.call_args_list, [call([A, B]), call([B])])
        self.bot._tap.assert_called_once_with(B)
        self.assertEqual(self.bot.observer.available_event_cards.call_count, 4)

    def test_rejected_choices_remain_excluded_after_retry(self):
        self.bot.rejected_event_choices.add(A)
        old, new = frame('before'), frame('after')
        _, choose = self.run_frames([old, old, old, new, new, new, new, new])
        self.assertEqual(choose.call_args_list, [call([B]), call([B])])
        self.bot._tap.assert_called_once_with(B)

    def test_followup_during_retry_returns_without_stale_click(self):
        old, new = frame('before'), frame('after')
        followup = frame('map', cards=(), state='map')
        self.bot._accept_event_page = Mock()
        result, choose = self.run_frames([old, old, old, new, followup, followup])
        self.assertEqual(result, 'map')
        choose.assert_called_once()
        self.bot._tap.assert_not_called()
        self.bot._accept_event_page.assert_called_once_with('map')

    def test_user_stop_interrupts_retry_delay_without_click(self):
        old, new = frame('before'), frame('after')
        self.bot.stop_event.wait.side_effect = lambda seconds: seconds == 1
        with self.assertRaises(_Stopped):
            self.run_frames([old, old, old, new])
        self.bot._tap.assert_not_called()

    def test_unchanged_page_uses_existing_single_click(self):
        page = frame('stable')
        _, choose = self.run_frames([page] * 4)
        choose.assert_called_once()
        self.bot._tap.assert_called_once_with(A)
        self.assertNotIn(call(1), self.bot.stop_event.wait.call_args_list)


if __name__ == '__main__':
    unittest.main()
