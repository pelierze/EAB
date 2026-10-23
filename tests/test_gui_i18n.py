import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import i18n
from src.gui import SecretShopGUI, SessionView


class TestGuiI18n(unittest.TestCase):
    def setUp(self):
        i18n._listeners.clear()
        i18n.set_language("ko", persist=False)

    def test_toggle_language_updates_button_text(self):
        gui = MagicMock()
        gui.lang_button = MagicMock()
        gui.support_button = MagicMock()
        gui.sessions = []
        gui._on_language_changed.side_effect = lambda lang: SecretShopGUI._on_language_changed(gui, lang)

        # Call the actual unbound method on gui mock
        SecretShopGUI._on_toggle_language(gui)
        self.assertEqual(i18n.get_language(), "en")
        gui.lang_button.config.assert_called_with(text="Language: English")
        gui.support_button.config.assert_called_with(text="Support Creator · Buy Me a Coffee")

        SecretShopGUI._on_toggle_language(gui)
        self.assertEqual(i18n.get_language(), "ko")
        gui.lang_button.config.assert_called_with(text="Language: 한국어")
        gui.support_button.config.assert_called_with(text="제작자 후원 · Buy Me a Coffee")

    def test_apply_language_feature_support_disables_unsupported_tabs_in_english(self):
        session = MagicMock()
        session.shop_tab = "tab_shop"
        session.penguin_tab = "tab_penguin"
        session.chaos_tab = "tab_chaos"
        session.event_tab = "tab_event"
        # Exploration remains unsupported; Penguin is now available in English.
        session.mode_notebook.select.return_value = "tab_chaos"

        SessionView._apply_language_feature_support(session, "en")

        session.mode_notebook.tab.assert_any_call("tab_shop", state="normal")
        session.mode_notebook.tab.assert_any_call("tab_penguin", state="normal")
        session.mode_notebook.tab.assert_any_call("tab_chaos", state="disabled")
        session.mode_notebook.tab.assert_any_call("tab_event", state="disabled")
        session.mode_notebook.select.assert_called_with("tab_shop")

        # Switch back to Korean -> all tabs normal
        session.mode_notebook.reset_mock()
        session.mode_notebook.select.return_value = "tab_shop"
        SessionView._apply_language_feature_support(session, "ko")
        session.mode_notebook.tab.assert_any_call("tab_shop", state="normal")
        session.mode_notebook.tab.assert_any_call("tab_penguin", state="normal")
        session.mode_notebook.tab.assert_any_call("tab_chaos", state="normal")
        session.mode_notebook.tab.assert_any_call("tab_event", state="normal")

    def test_disabled_tab_hover_shows_localized_tooltip(self):
        session = MagicMock()
        session._get_mode_tab_index_at.return_value = 1
        session.mode_notebook.tab.return_value = "disabled"

        i18n.set_language("en", persist=False)
        event = MagicMock(x=60, y=10, x_root=200, y_root=150)
        SessionView._on_mode_notebook_motion(session, event)
        session._show_disabled_tab_tooltip.assert_called_once_with(
            200, 150, "This feature is not supported in this language environment."
        )

        # Hovering over normal tab hides tooltip
        session._show_disabled_tab_tooltip.reset_mock()
        session.mode_notebook.tab.return_value = "normal"
        SessionView._on_mode_notebook_motion(session, event)
        session._show_disabled_tab_tooltip.assert_not_called()
        session._hide_disabled_tab_tooltip.assert_called_once()

        # Hovering over Auto_DE tab (index 2) shows full name even if normal, or full name + message if disabled
        session._show_disabled_tab_tooltip.reset_mock()
        session._get_mode_tab_index_at.return_value = 2
        session.mode_notebook.tab.return_value = "disabled"
        SessionView._on_mode_notebook_motion(session, event)
        session._show_disabled_tab_tooltip.assert_called_once_with(
            200, 150, "Dimensional Exploration — This feature is not supported in this language environment."
        )

        session._show_disabled_tab_tooltip.reset_mock()
        session.mode_notebook.tab.return_value = "normal"
        SessionView._on_mode_notebook_motion(session, event)
        session._show_disabled_tab_tooltip.assert_called_once_with(
            200, 150, "Dimensional Exploration"
        )


    def test_save_and_restore_update_settings_preserves_language(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_file = Path(tmpdir) / "updates" / "app-update-settings.json"

            gui = MagicMock()
            gui.sessions = []
            gui.lang_button = MagicMock()
            gui._update_variables = MagicMock(return_value=[])
            gui._apply_update_settings = MagicMock()

            # Set language to en
            i18n.set_language("en", persist=False)

            with patch("src.gui.sys") as mock_sys:
                mock_sys.executable = str(Path(tmpdir) / "EAB.exe")
                mock_sys.frozen = True

                # Save update settings
                SecretShopGUI._save_update_settings(gui)
                self.assertTrue(settings_file.exists())

                content = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertIn("language", content)
                self.assertEqual(content["language"], "en")

                # Reset language to ko before restore
                i18n.set_language("ko", persist=False)

                # Restore
                SecretShopGUI._restore_update_settings(gui)
                self.assertEqual(i18n.get_language(), "en")
                gui.lang_button.config.assert_called_with(text="Language: English")
                gui._apply_update_settings.assert_called_once_with(content["sessions"])


if __name__ == "__main__":
    unittest.main()
