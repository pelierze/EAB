import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import i18n
from src.app_updater import download, release_assets
from src.gui import SecretShopGUI, SessionView


class UiErrorTranslationTests(unittest.TestCase):
    def setUp(self):
        language = i18n.get_language()
        self.addCleanup(i18n.set_language, language, persist=False)
        i18n.set_language('en', persist=False)

    def test_runtime_dialog_keeps_exception_after_worker_returns(self):
        for method in (SessionView._run_bot, SessionView._run_penguin_bot):
            with self.subTest(method=method.__name__):
                session = MagicMock()
                session.name = '세션 1'
                session.app.is_closing = False
                session.bot.run.side_effect = RuntimeError('offline')
                callbacks = []
                session.root.after.side_effect = lambda delay, cb: callbacks.append(cb) if delay == 0 else None
                if method == SessionView._run_bot:
                    method(session, 1, 1)
                else:
                    method(session)
                # Tk executes after the except block has deleted its exception variable.
                with patch('src.gui.messagebox.showerror') as show:
                    for callback in callbacks:
                        callback()
                title, body = show.call_args.args
                self.assertEqual(title, 'Error')
                self.assertIn('Session 1', body)
                self.assertIn('offline', body)
                self.assertNotRegex(body, '[가-힣]')

    def test_invalid_penguin_cycles_are_localized_before_starting(self):
        for value in ('0', '-1', 'abc', '1.5'):
            session = MagicMock()
            session.name = 'test'
            session.is_running = False
            session._stove_resize_pending = False
            session.penguin_cycle_entry.get.return_value = value
            with patch('src.gui.messagebox.showerror') as show:
                SessionView._start_penguin_bot(session)
            self.assertEqual(show.call_args.args, (
                'Error', 'Purchase cycles must be a whole number of at least 1.'))

    def test_update_failure_localizes_reason_and_recovery_hint(self):
        gui = MagicMock()
        with patch('src.runtime_diagnostics.diagnostic_logger'), \
             patch('src.runtime_diagnostics.diagnostic_path', return_value=Path('updater.log')), \
             patch('src.gui.messagebox.showerror') as show:
            SecretShopGUI._app_update_failed(gui, '파일 교체 프로그램 시작 시간이 초과되었습니다.')
        title, body = show.call_args.args
        self.assertEqual(title, 'Update Failed')
        self.assertIn('Timed out', body)
        self.assertIn('continue using the current version', body)
        self.assertIn('updater.log', body)
        self.assertNotRegex(body, '[가-힣]')

    def test_updater_progress_and_known_errors_are_localized(self):
        response = io.BytesIO(b'zip')
        response.headers = {'Content-Length': '3'}
        progress = []
        with tempfile.TemporaryDirectory() as tmp, \
             patch('src.app_updater.urllib.request.urlopen', return_value=response):
            download('https://example.com/file', Path(tmp) / 'download', 100, progress.append)
        self.assertEqual(progress, ['Downloading 100%'])
        release = MagicMock(version='v1.0.0-beta')
        with self.assertRaisesRegex(ValueError, 'stable releases only'):
            release_assets(release)

    def test_window_resize_errors_are_translated_at_the_ui_boundary(self):
        session = MagicMock()
        session._stove_resize_pending = False
        session.backend_type_var.get.return_value = 'stove'
        session.is_running = False
        session.bot_thread = None
        session.stove_combo.current.return_value = 0
        session.scanned_stove_windows = [MagicMock(hwnd=123)]
        session.app.sessions = []
        info = MagicMock(class_name='GLFW30', process_name='epicseven.exe')
        with patch('src.gui.WindowFinder.get_window_info', return_value=info), \
             patch('src.gui.WindowResizer') as resizer:
            resizer.return_value.request.side_effect = ValueError('게임을 일반 창 모드로 전환한 뒤 사용하세요.')
            SessionView._resize_stove_window(session)
        session.stove_resize_status.config.assert_called_with(text='Switch the game to windowed mode first.')


if __name__ == '__main__':
    unittest.main()
