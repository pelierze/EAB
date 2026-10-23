import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import i18n


class TestI18n(unittest.TestCase):
    def setUp(self):
        # Reset listeners and set language to default
        i18n._listeners.clear()
        i18n.set_language(i18n.DEFAULT_LANGUAGE, persist=False)

    def test_default_language_is_korean(self):
        self.assertEqual(i18n.DEFAULT_LANGUAGE, "ko")

    def test_toggle_language(self):
        i18n.set_language("ko", persist=False)
        self.assertEqual(i18n.get_language(), "ko")

        new_lang = i18n.toggle_language()
        self.assertEqual(new_lang, "en")
        self.assertEqual(i18n.get_language(), "en")

        next_lang = i18n.toggle_language()
        self.assertEqual(next_lang, "ko")
        self.assertEqual(i18n.get_language(), "ko")

    def test_button_text(self):
        self.assertEqual(i18n.get_language_button_text("ko"), "Language: 한국어")
        self.assertEqual(i18n.get_language_button_text("en"), "Language: English")

    def test_listener_notification(self):
        calls = []

        def listener(lang):
            calls.append(lang)

        i18n.add_language_listener(listener)
        i18n.set_language("en", persist=False)
        self.assertEqual(calls, ["en"])

        i18n.remove_language_listener(listener)
        i18n.set_language("ko", persist=False)
        self.assertEqual(calls, ["en"])

    def test_persistence_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_persistent = Path(tmpdir) / "app_data" / "settings.json"
            fake_fallback = Path(tmpdir) / "runtime" / "updates" / "settings.json"

            with patch.object(i18n, "get_persistent_settings_path", return_value=fake_persistent), \
                 patch.object(i18n, "get_fallback_settings_path", return_value=fake_fallback):

                # Initially no file -> default "ko"
                self.assertEqual(i18n.load_saved_language(), "ko")

                # Save "en"
                i18n.save_language_preference("en")
                self.assertTrue(fake_persistent.exists())
                self.assertTrue(fake_fallback.exists())

                data = json.loads(fake_persistent.read_text(encoding="utf-8"))
                self.assertEqual(data.get("language"), "en")

                # Load back
                self.assertEqual(i18n.load_saved_language(), "en")

    def test_tr_fallback(self):
        # When no translation exists, returns original text or default
        self.assertEqual(i18n.tr("시작"), "시작")
        self.assertEqual(i18n.tr("알 수 없는 키", default="기본값"), "기본값")

    def test_tr_english_epic_seven_terminology(self):
        i18n.set_language("en", persist=False)
        self.assertEqual(i18n.tr("비밀상점"), "Secret Shop")
        self.assertEqual(i18n.tr("자동 탐사"), "Auto_DE")
        self.assertEqual(i18n.tr("신비의 메달:"), "Mystic Medals:")
        self.assertEqual(i18n.tr("성약의 책갈피:"), "Covenant Bookmarks:")
        self.assertEqual(i18n.tr("우정 포인트:"), "Friendship Points:")
        self.assertEqual(i18n.tr("사용 하늘석:"), "Skystones to Use:")
        self.assertEqual(i18n.tr("1뽑당 {value}개", value="65.5"), "65.5 SS / pull")
        self.assertEqual(i18n.tr("최신 버전  v{version}", version="1.2.0"), "Up to date  v1.2.0")
        self.assertEqual(
            i18n.get_mode_tab_tooltip("dimensional_exploration", is_disabled=False, lang="en"),
            "Dimensional Exploration",
        )
        self.assertEqual(
            i18n.get_mode_tab_tooltip("dimensional_exploration", is_disabled=True, lang="en"),
            "Dimensional Exploration — This feature is not supported in this language environment.",
        )

    def test_feature_support_per_language(self):
        self.assertTrue(i18n.is_feature_supported("secret_shop", "ko"))
        self.assertTrue(i18n.is_feature_supported("dimensional_exploration", "ko"))
        self.assertTrue(i18n.is_feature_supported("penguin", "ko"))
        self.assertTrue(i18n.is_feature_supported("event", "ko"))

        self.assertTrue(i18n.is_feature_supported("secret_shop", "en"))
        self.assertFalse(i18n.is_feature_supported("dimensional_exploration", "en"))
        self.assertTrue(i18n.is_feature_supported("penguin", "en"))
        self.assertFalse(i18n.is_feature_supported("event", "en"))

    def test_unsupported_feature_message_localized(self):
        self.assertEqual(
            i18n.get_unsupported_feature_message("ko"),
            "이 언어 환경에서는 지원하지 않는 기능입니다.",
        )
        self.assertEqual(
            i18n.get_unsupported_feature_message("en"),
            "This feature is not supported in this language environment.",
        )


if __name__ == "__main__":
    unittest.main()
