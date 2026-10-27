import tkinter as tk
import unittest
from unittest.mock import Mock

from src import i18n
from src.gui import SessionView


class ExplorationPauseUiTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: i18n.set_language('ko', persist=False))
        self.view = object.__new__(SessionView)
        self.view.name = 'pause test'
        self.view.current_mode = 'chaos'
        self.view.is_running = True
        self.view.bot = Mock(paused=False, pause_requested=False)
        self.view.chaos_pause_btn = Mock()
        self.view.chaos_resume_btn = Mock()

    def states(self, pause, resume):
        self.view._update_chaos_pause_controls()
        self.view.chaos_pause_btn.config.assert_called_with(state=pause)
        self.view.chaos_resume_btn.config.assert_called_with(state=resume)

    def test_running_pausing_paused_and_stopped_states(self):
        self.states(tk.NORMAL, tk.DISABLED)
        self.view.bot.pause_requested = True
        self.states(tk.DISABLED, tk.DISABLED)
        self.view.bot.paused = True
        self.states(tk.DISABLED, tk.NORMAL)
        self.view.is_running = False
        self.states(tk.DISABLED, tk.DISABLED)

    def test_stop_request_keeps_resume_disabled(self):
        self.view.was_stopped_by_user = True
        self.view.bot.paused = True
        self.states(tk.DISABLED, tk.DISABLED)

    def test_pause_requests_worker_without_marking_pause_complete(self):
        self.view._pause_bot()
        self.view.bot.set_user_action.assert_called_once_with('pause')
        self.view.chaos_resume_btn.config.assert_called_with(state=tk.DISABLED)

    def test_resume_requires_acknowledged_pause(self):
        self.view._resume_bot()
        self.view.bot.set_user_action.assert_not_called()
        self.view.bot.paused = True
        self.view._resume_bot()
        self.view.bot.set_user_action.assert_called_once_with('resume')

    def test_buttons_translate_when_language_changes(self):
        self.view.chaos_i18n_widgets = [(self.view.chaos_pause_btn, '⏸ 일시정지'),
                                       (self.view.chaos_resume_btn, '▶ 재개')]
        self.view.chaos_hero_combos = {}
        self.view.chaos_rank_priority_combos = {}
        self.view._check_chaos_hero_cost_warning = Mock()
        self.view.chaos_status_label = Mock()
        for language, pause, resume in (('ko', '⏸ 일시정지', '▶ 재개'),
                                         ('en', '⏸ Pause', '▶ Resume')):
            i18n.set_language(language, persist=False)
            self.view._apply_chaos_ui_language()
            self.view.chaos_pause_btn.config.assert_called_with(text=pause)
            self.view.chaos_resume_btn.config.assert_called_with(text=resume)
            for key in ('일시 정지 중 — 탐사 화면으로 돌아온 뒤 재개하세요.',
                        '일시 정지 요청 중 — 멈춤 확인 후 다른 작업을 진행하세요.'):
                if language == 'en':
                    self.assertNotEqual(i18n.tr(key), key)
