import subprocess
import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src import i18n
from src.adb_controller import ADBController
from src.gui import SessionView, ShopResolutionDialog


class ShopResolutionStartTests(unittest.TestCase):
    def setUp(self):
        self.view = object.__new__(SessionView)
        self.view.name = "test"
        self.view.is_running = False
        self.view.was_stopped_by_user = True
        self.view.root = Mock()
        self.view.runtime_dir = Mock()
        self.view.app = Mock(remote_settings={})
        self.view._get_selected_macro = Mock(return_value={"runner": "secret_shop"})
        self.view._build_shop_automation_settings = Mock(return_value={})
        self.view._set_running_ui = Mock()
        self.view._update_stats = Mock()
        for key, value in {
            "natural_refresh_var": False,
            "refresh_count_entry": "1",
            "sky_stone_budget_entry": "3",
            "buy_count_entry": "1",
            "mystic_medal_threshold": "95",
            "covenant_bookmark_threshold": "95",
            "friendship_point_threshold": "95",
            "purchase_button_threshold": "92",
            "buy_button_threshold": "92",
            "refresh_button_threshold": "92",
            "debug_mode_var": False,
        }.items():
            setattr(self.view, key, Mock(get=Mock(return_value=value)))
        self.view.adb_controller = Mock(spec=ADBController)
        self.dialog = self.enterContext(patch("src.gui.ShopResolutionDialog"))
        self.bot = self.enterContext(patch("src.gui.SecretShopBot"))
        self.worker = self.enterContext(patch("src.gui.threading.Thread"))

    def test_matching_adb_capture_starts_without_prompt(self):
        self.view.adb_controller.get_capture_size.return_value = (1280, 720)
        self.view._start_bot()
        self.dialog.assert_not_called()
        self.view.adb_controller.get_screen_size.assert_not_called()
        self.worker.return_value.start.assert_called_once()

    def test_stove_uses_raw_size_and_does_not_start_when_dismissed(self):
        backend = Mock(get_raw_size=Mock(return_value=(1600, 900)))
        self.view.adb_controller = Mock(capture_backend=backend, get_screen_size=Mock(return_value=(1280, 720)))
        self.dialog.return_value.result = None
        self.view._start_bot()
        self.dialog.assert_called_once_with(self.view.root.winfo_toplevel.return_value, (1600, 900))
        self.view.adb_controller.get_screen_size.assert_not_called()
        self.bot.assert_not_called()
        self.worker.assert_not_called()
        self.assertFalse(self.view.is_running)
        self.assertTrue(self.view.was_stopped_by_user)

    def test_confirmed_mismatch_starts_natural_refresh(self):
        self.view.natural_refresh_var.get.return_value = True
        self.view.adb_controller.get_capture_size.return_value = (1920, 1080)
        self.dialog.return_value.result = True
        self.view._start_bot()
        self.dialog.assert_called_once_with(self.view.root.winfo_toplevel.return_value, (1920, 1080))
        self.worker.return_value.start.assert_called_once()
        self.assertEqual(self.worker.call_args.kwargs["args"], (0, 1, True))

    def test_missing_capture_size_does_not_report_a_mismatch(self):
        self.view.adb_controller.get_capture_size.return_value = None
        with self.assertLogs("src.gui", level="WARNING"):
            self.view._start_bot()
        self.dialog.assert_not_called()
        self.worker.return_value.start.assert_called_once()


class AdbCaptureSizeTests(unittest.TestCase):
    def test_capture_dimensions_come_from_png(self):
        controller = object.__new__(ADBController)
        controller.device_id = "test-device"
        _, png = cv2.imencode(".png", np.zeros((900, 1600, 3), dtype=np.uint8))
        controller._run_adb = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=png.tobytes()))
        self.assertEqual(controller.get_capture_size(), (1600, 900))
        controller._run_adb.assert_called_once_with(
            ["-s", "test-device", "exec-out", "screencap", "-p"], timeout=3,
        )


class ShopResolutionDialogTests(unittest.TestCase):
    def test_only_continue_confirms(self):
        previous_language = i18n.get_language()
        self.addCleanup(i18n.set_language, previous_language, persist=False)
        i18n.set_language("ko", persist=False)
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()

        for action, expected in [("취소", None), ("닫기", None), ("계속하기", True)]:
            with self.subTest(action=action):
                def respond():
                    dialog = next(widget for widget in root.winfo_children() if isinstance(widget, ShopResolutionDialog))
                    if action == "닫기":
                        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
                    else:
                        buttons = (child for frame in dialog.winfo_children() for child in frame.winfo_children())
                        next(button for button in buttons if isinstance(button, ttk.Button) and button.cget("text") == action).invoke()

                root.after(100, respond)
                self.assertIs(ShopResolutionDialog(root, (1600, 900)).result, expected)
