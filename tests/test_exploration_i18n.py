import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

from src import i18n
from src.chaos.ui_values import priority_index, selected_priority
from src.gui import SessionView


class ExplorationI18nTests(unittest.TestCase):
    def setUp(self):
        self.language = i18n.get_language()
        i18n.set_language('ko', persist=False)
        self.addCleanup(i18n.set_language, self.language, persist=False)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'presets.json'
        patcher = patch.object(SessionView, '_chaos_preset_path', return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.view = object.__new__(SessionView)
        self.view.root = self.root
        self.view.session_id = 'session_1'
        self.view.debug_mode_var = tk.BooleanVar(self.root, value=False)
        messageboxes = patch('src.gui.messagebox')
        self.messageboxes = messageboxes.start()
        self.addCleanup(messageboxes.stop)
        self.view.chaos_tab = ttk.Frame(self.root)
        self.view._create_chaos_widgets()

    def switch(self, lang):
        i18n.set_language(lang, persist=False)
        self.view._apply_chaos_ui_language()

    def test_language_switch_keeps_hero_ids_and_numeric_priorities(self):
        view = self.view
        view.chaos_hero_combos['knight'].current(view.chaos_hero_choices['knight'].index('ras'))
        view.chaos_rank_priority_combos['knight'].current(0)
        expected = {role: selected_priority(combo) for role, combo in view.chaos_rank_priority_combos.items()}
        for lang in ('en', 'ko', 'en'):
            self.switch(lang)
            self.assertEqual(view.chaos_hero_choices['knight'][view.chaos_hero_combos['knight'].current()], 'ras')
            self.assertEqual({role: selected_priority(combo) for role, combo in view.chaos_rank_priority_combos.items()}, expected)
        self.assertEqual(view.chaos_rank_priority_combos['knight'].get(), 'Priority 1')
        self.assertIn('Adventurer Ras', view.chaos_hero_combos['knight'].get())
        view._save_chaos_preset()
        saved = json.loads(self.path.read_text(encoding='utf-8'))['sessions']['session_1']
        self.assertEqual(saved['heroes']['knight'], 'ras')
        self.assertEqual(saved['rank_priorities']['knight'], 1)
        self.assertIsNone(saved['rank_priorities']['soul_weaver'])

    def test_legacy_korean_preset_restores_under_english_ui(self):
        self.path.write_text(json.dumps({'sessions': {'session_1': {
            'heroes': {'knight': 'ras'}, 'rank_priorities': {'knight': '2순위', 'thief': '제외'},
            'auto_fallback': False,
        }}}), encoding='utf-8')
        self.switch('en')
        self.view._restore_chaos_preset()
        self.assertEqual(self.view.chaos_rank_priority_combos['knight'].get(), 'Priority 2')
        self.assertEqual(self.view.chaos_rank_priority_combos['thief'].get(), 'Exclude')
        self.assertIn('Adventurer Ras', self.view.chaos_hero_combos['knight'].get())
        self.assertFalse(self.view.chaos_cost_fallback.get())

    def test_numeric_preset_restores_independent_of_display_language(self):
        self.path.write_text(json.dumps({'sessions': {'session_1': {
            'rank_priorities': {'knight': 4, 'warrior': None},
        }}}), encoding='utf-8')
        for lang in ('en', 'ko'):
            self.switch(lang)
            self.view._restore_chaos_preset()
            self.assertEqual(selected_priority(self.view.chaos_rank_priority_combos['knight']), 4)
            self.assertIsNone(selected_priority(self.view.chaos_rank_priority_combos['warrior']))

    def test_duplicate_first_priority_is_resolved_using_indices(self):
        self.switch('en')
        combos = self.view.chaos_rank_priority_combos
        combos['warrior'].current(0)
        combos['thief'].current(0)
        self.view._on_chaos_rank_priority_changed('thief')
        self.assertEqual(selected_priority(combos['thief']), 1)
        self.assertEqual(selected_priority(combos['warrior']), 2)

    def test_static_exploration_controls_and_cost_warning_are_english(self):
        self.switch('en')
        for widget, key in self.view.chaos_i18n_widgets:
            with self.subTest(key=key):
                self.assertNotRegex(widget.cget('text'), '[가-힣]')
        role = 'soul_weaver'
        self.view.chaos_hero_combos[role].current(self.view.chaos_hero_choices[role].index('lisette'))
        self.view._check_chaos_hero_cost_warning()
        self.assertIn('Lisette', self.view.chaos_cost_warning_label.cget('text'))
        self.assertNotRegex(self.view.chaos_cost_warning_label.cget('text'), '[가-힣]')

    def test_priority_codec_rejects_invalid_values_and_translated_text(self):
        for value in (True, False, 0, 5, -1, 'Priority 1', 'unknown', [], 1.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                priority_index(value)
        combo = Mock(current=Mock(return_value=-1))
        with self.assertRaises(ValueError):
            selected_priority(combo)

    def test_language_refresh_preserves_status_instead_of_showing_idle(self):
        self.view._update_chaos_stats({'phase': '전투 진행 확인', 'attempt': 2, 'cleared_rounds': 1,
                                       'target_clears': 3, 'failed_rounds': 1})
        self.switch('en')
        text = self.view.chaos_status_label.cget('text')
        self.assertIn('Run 2 [Clears 1/3, Defeats 1]', text)
        self.assertIn('Checking battle progress', text)
        self.assertNotIn('Idle', text)

    def test_english_controls_send_ids_and_numeric_order_to_the_runner(self):
        self.switch('en')
        view = self.view
        view.name = 'test'
        view.is_running = False
        view.bot_thread = None
        view.adb_controller = Mock()
        view.runtime_dir = self.path.parent
        view._set_running_ui = Mock()
        for role, hero_id in (('knight', 'ras'), ('thief', 'jenua')):
            view.chaos_hero_combos[role].current(view.chaos_hero_choices[role].index(hero_id))
        view.chaos_rank_priority_combos['thief'].current(0)
        view.chaos_rank_priority_combos['warrior'].current(1)
        view.chaos_rank_priority_combos['knight'].current(2)
        with patch('src.gui.ExplorationBot') as runner, patch('src.gui.threading.Thread'):
            view._start_chaos_bot()
        self.assertTrue(view.is_running)
        self.messageboxes.showerror.assert_not_called()
        self.assertFalse(runner.call_args.kwargs['debug_mode'])
        self.assertEqual(runner.call_args.kwargs['rank_priority'], ['jenua', 'wukong', 'ras'])
        self.assertEqual(view.chaos_status_label.cget('text'), 'Checking the starting screen')


if __name__ == '__main__':
    unittest.main()
