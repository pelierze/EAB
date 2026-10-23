"""Internationalization (i18n) module for Epic7 Assist Bot (EAB).

Supports language switching between Korean (ko, default) and English (en).
Language preference is persisted across restarts and application updates.
"""
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from .auto_update import get_runtime_root

logger = logging.getLogger(__name__)

LANG_KO = "ko"
LANG_EN = "en"
SUPPORTED_LANGUAGES = (LANG_KO, LANG_EN)
DEFAULT_LANGUAGE = LANG_KO

# Display labels for UI buttons / selectors
LANGUAGE_LABELS = {
    LANG_KO: "한국어",
    LANG_EN: "English",
}

# Per-language feature availability
FEATURE_SUPPORT: dict[str, dict[str, bool]] = {
    LANG_KO: {
        "secret_shop": True,
        "dimensional_exploration": True,
        "penguin": True,
        "event": True,
    },
    LANG_EN: {
        "secret_shop": True,
        "dimensional_exploration": False,
        "penguin": False,
        "event": False,
    },
}

UNSUPPORTED_FEATURE_MESSAGES: dict[str, str] = {
    LANG_KO: "이 언어 환경에서는 지원하지 않는 기능입니다.",
    LANG_EN: "This feature is not supported in this language environment.",
}

# Full titles shown on hover when a mode tab uses an abbreviated label (e.g., DE)
FEATURE_HOVER_TITLES: dict[str, dict[str, str]] = {
    LANG_KO: {},
    LANG_EN: {
        "dimensional_exploration": "Dimensional Exploration",
    },
}


def is_feature_supported(feature: str, lang: Optional[str] = None) -> bool:
    """Return True if the given feature is supported in the specified (or current) language."""
    if lang is None:
        lang = get_language()
    lang_features = FEATURE_SUPPORT.get(lang, {})
    if feature in lang_features:
        return bool(lang_features[feature])
    return lang == LANG_KO


def get_unsupported_feature_message(lang: Optional[str] = None) -> str:
    """Return localized message explaining that a feature is not supported in the language."""
    if lang is None:
        lang = get_language()
    return UNSUPPORTED_FEATURE_MESSAGES.get(lang, UNSUPPORTED_FEATURE_MESSAGES[DEFAULT_LANGUAGE])


def get_mode_tab_tooltip(
    feature: Optional[str],
    is_disabled: bool = False,
    lang: Optional[str] = None,
) -> Optional[str]:
    """Return tooltip text for a mode tab (full title if abbreviated, and/or unsupported message)."""
    if lang is None:
        lang = get_language()
    hover_title = FEATURE_HOVER_TITLES.get(lang, {}).get(feature or "")
    if is_disabled:
        unsupported_msg = get_unsupported_feature_message(lang)
        if hover_title:
            return f"{hover_title} — {unsupported_msg}"
        return unsupported_msg
    return hover_title


_current_language: str = DEFAULT_LANGUAGE
_listeners: list[Callable[[str], None]] = []


def get_persistent_settings_path() -> Path:
    """Return primary settings path in LOCALAPPDATA to survive app updates."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    return base / "SecretShopBot-E7" / "settings.json"


def get_fallback_settings_path() -> Path:
    """Return fallback settings path inside runtime directory."""
    return get_runtime_root() / "updates" / "settings.json"


def load_saved_language() -> str:
    """Load saved language preference from persistent storage or return default."""
    for path in (get_persistent_settings_path(), get_fallback_settings_path()):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                lang = data.get("language")
                if lang in SUPPORTED_LANGUAGES:
                    return lang
        except Exception as exc:
            logger.warning("설정 파일(%s)에서 언어 설정을 읽지 못했습니다: %s", path, exc)
    return DEFAULT_LANGUAGE


def save_language_preference(lang: str) -> None:
    """Save language preference to persistent storage so it survives updates."""
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    paths = [get_persistent_settings_path(), get_fallback_settings_path()]
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            current_data = {}
            if path.exists():
                try:
                    current_data = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(current_data, dict):
                        current_data = {}
                except Exception:
                    current_data = {}
            current_data["language"] = lang
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(current_data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(path)
        except Exception as exc:
            logger.warning("언어 설정 저장 실패 (%s): %s", path, exc)


def get_language() -> str:
    """Return currently active language code."""
    global _current_language
    return _current_language


def set_language(lang: str, persist: bool = True) -> str:
    """Set active language, optionally persisting to disk, and notify listeners."""
    global _current_language
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    _current_language = lang
    if persist:
        save_language_preference(lang)

    for listener in list(_listeners):
        try:
            listener(_current_language)
        except Exception as exc:
            logger.exception("언어 변경 리스너 실행 중 오류: %s", exc)

    return _current_language


def toggle_language() -> str:
    """Toggle between Korean and English, then persist and return new language."""
    new_lang = LANG_EN if get_language() == LANG_KO else LANG_KO
    return set_language(new_lang, persist=True)


def get_language_button_text(lang: Optional[str] = None) -> str:
    """Return label formatted for the language switch button."""
    if lang is None:
        lang = get_language()
    label = LANGUAGE_LABELS.get(lang, "한국어")
    return f"Language: {label}"


def add_language_listener(callback: Callable[[str], None]) -> None:
    """Register callback to be invoked on language changes."""
    if callback not in _listeners:
        _listeners.append(callback)


def remove_language_listener(callback: Callable[[str], None]) -> None:
    """Unregister language change callback."""
    if callback in _listeners:
        _listeners.remove(callback)


# Translation catalog for UI internationalization
_CATALOG: dict[str, dict[str, str]] = {
    LANG_KO: {},
    LANG_EN: {
        # Header & Main Tabs
        "제작자 후원 · Buy Me a Coffee": "Support Creator · Buy Me a Coffee",
        "세션 1": "Session 1",
        "세션 2": "Session 2",
        "세션 {index}": "Session {index}",

        # Mode Tabs
        "비밀상점": "Secret Shop",
        "펭귄": "Penguins",
        "자동 탐사": "Auto_DE",
        "이벤트": "Event",

        # Connection Section
        "연결 설정": "Connection Settings",
        "연결 설정 (ADB)": "Connection Settings (ADB)",
        "연결 설정 (STOVE PC 클라이언트)": "Connection Settings (STOVE PC Client)",
        "실행 환경:": "Environment:",
        "앱플레이어 (ADB)": "Emulator (ADB)",
        "STOVE PC 클라이언트": "STOVE PC Client",
        "연결": "Connect",
        "연결 해제": "Disconnect",
        "● 연결 안됨": "● Disconnected",
        "● 연결됨": "● Connected",
        "● 연결됨 (STOVE)": "● Connected (STOVE)",
        "● 창 없음": "● No Window",
        "● 통신 실패": "● Comm. Failed",
        "● 연결 실패": "● Conn. Failed",
        "● 사용 중": "● In Use",

        # Release / Update Status
        "릴리즈 확인 중...": "Checking for updates...",
        "최신 버전  v{version}": "Up to date  v{version}",
        "새 버전 {version}": "New version {version}",
        "업데이트 후 재시작": "Update & Restart",

        # ADB Controls
        "IP 주소:": "IP Address:",
        "포트:": "Port:",
        "장치 검색": "Scan Devices",
        "장치:": "Device:",

        # STOVE Controls
        "에픽세븐 창:": "Epic Seven Window:",
        "창 새로고침": "Refresh Windows",
        "1280×720으로 맞추기": "Resize to 1280×720",
        "⚠️ 관리자 권한으로 재실행": "⚠️ Restart as Admin",
        "감지된 에픽세븐 창 없음 (게임을 먼저 실행하세요)": "No Epic Seven window found (Launch the game first)",
        "게임 화면 크기 확인 중…": "Checking game window size…",
        "게임 화면 1280×720 확인": "Verified 1280×720 window size",
        "현재 {w}×{h} — 크기 조정이 적용되지 않았습니다.": "Current {w}×{h} — Resize was not applied.",
        "봇을 중지한 뒤 크기를 조정하세요.": "Stop the bot before resizing the window.",
        "창 새로고침 후 에픽세븐 창을 선택하세요.": "Refresh windows and select an Epic Seven window.",
        "선택한 게임 창을 확인할 수 없습니다. 창을 다시 검색하세요.": "Could not verify the selected game window. Please scan again.",
        "이 게임 창을 사용하는 봇을 중지한 뒤 크기를 조정하세요.": "Stop the bot using this game window before resizing.",

        # Common Options
        "디버그 모드 (상세 로그)": "Debug Mode (Detailed Logs)",
        "MuMu 앱플레이어 사용 (호환 드래그 사용)": "MuMu Player Mode (Compatible Drag)",

        # Secret Shop Settings
        "매크로 설정": "Macro Settings",
        "리프레시 횟수:": "Refresh Count:",
        "회": "times",
        "사용 하늘석:": "Skystones to Use:",
        "개": "ea",
        "구매 완료 확인 최대 횟수:": "Max Purchase Verify Retries:",
        "구매 완료 검증 횟수:": "Max Purchase Verify Retries:",
        "(steps 매크로 미사용)": "(Unused in steps macro)",
        "우정 포인트 구매": "Buy Friendship Points",
        "자연 갱신만 구매 (하늘석 0개 / 15분 간격 / 중지까지)": "Free Refresh Only (0 Skystones / 15m Interval / Until Stopped)",
        "=== 이미지 매칭 정확도 (70-99) ===": "=== Image Match Threshold (70-99) ===",
        "신비의 메달:": "Mystic Medals:",
        "성약의 책갈피:": "Covenant Bookmarks:",
        "우정 포인트:": "Friendship Points:",
        "구입 버튼:": "Shop Buy Button:",
        "구매 버튼:": "Confirm Buy Button:",
        "갱신 버튼:": "Refresh Button:",

        # Secret Shop Controls
        "매크로:": "Macro:",
        "비밀상점 갱신": "Secret Shop Refresh",
        "▶ 시작": "▶ Start",
        "⏸ 일시정지": "⏸ Pause",
        "▶ 재개": "▶ Resume",
        "■ 중지": "■ Stop",
        "💡 이미지 테스트": "💡 Image Test",
        "⏸️  일시정지 중": "⏸️  Paused",

        # Secret Shop Statistics
        "통계": "Statistics",
        "진행 완료:": "Refreshes:",
        "경과 시간:": "Elapsed Time:",
        "하늘석 사용량:": "Skystones Used:",
        "성약 획득량/하늘석:": "Covenant / Skystone:",
        "신비 획득량/하늘석:": "Mystic / Skystone:",
        "1뽑당 {value}개": "{value} SS / pull",

        # Penguin Tab
        "펭귄 구매 설정": "Penguin Purchase Settings",
        "구매 사이클 횟수:": "Purchase Cycles:",
        "펭귄런 시작": "Start Penguin Run",
        "펭귄런 중지": "Stop Penguin Run",
        "펭귄 통계": "Penguin Statistics",
        "완료 사이클:": "Completed Cycles:",
        "구매 시도:": "Purchase Attempts:",
        "구매 완료:": "Purchased:",

        # Exploration Tab
        "영웅 영입": "Hero Recruitment",
        "랭크업:": "Rank Up:",
        "코스트 초과 시 대체 영웅 자동 영입": "Auto-recruit fallback hero if cost exceeded",
        "탐사 초기 화면 또는 노드 지도에서 시작하세요.\n현재 설정된 난이도를 사용합니다.": "Start from the Exploration main screen or node map.\nUses the currently selected difficulty.",
        "미등록 이벤트 처리": "Unregistered Event Handling",
        "무작위 선택 (선택지 내용 미판독)": "Random Choice (Does not read option text)",
        "미확인 이벤트 저장(제보용)": "Save unrecognized events (for reporting)",
        "상점": "Shop",
        "미래 투자만 구매 (상점마다 1회)": "Buy 'Future Investment' only (once per shop)",
        "등록된 이벤트는 기존 규칙 우선. 저장은 기본 꺼짐이며 자동 전송하지 않습니다.": "Registered events follow preset rules first. Saving is off by default and never sent automatically.",
        "자동 탐사 시작": "Start Dimensional Exploration",
        "중지": "Stop",
        "목표 완주:": "Target Clears:",
        "대기 중": "Idle",

        # Event Tab
        "현재 지원하는 이벤트가 없습니다": "No active events supported at this time.",

        # Log Frame
        "로그": "Logs",
        "로그 클리어": "Clear Logs",
        "로그 확대": "Expand Logs",
        "옵션 다시 보기": "Show Options",

        # Dialogs & Alerts
        "오류": "Error",
        "경고": "Warning",
        "종료": "Exit",
        "IP 주소와 포트를 입력하세요.": "Please enter the IP address and port.",
        "포트는 숫자여야 합니다.": "Port must be a number.",
        "장치(ADB/STOVE)가 연결되지 않았습니다.": "No device (ADB/STOVE) is connected.",
        "설정값이 올바르지 않습니다.\n{error}\n리프레시 횟수와 사용할 하늘석, 구매 횟수는 양수여야 하며,\n매칭 정확도는 70~99 사이여야 합니다.": "Invalid settings.\n{error}\nRefresh count, Skystones to use, and verify retries must be positive numbers,\nand match thresholds must be between 70 and 99.",
        "봇이 실행 중일 때는 연결을 해제할 수 없습니다.": "Cannot disconnect while the bot is running.",
        "봇이 실행 중일 때는 테스트할 수 없습니다.": "Cannot run image test while the bot is running.",
        "테스트할 이미지 선택": "Select Image to Test",
        "이미지 파일": "Image Files",
        "모든 파일": "All Files",
        "후원 페이지 열기 실패": "Failed to Open Support Page",
        "기본 브라우저를 열지 못했습니다.\n아래 주소를 브라우저에 입력해 주세요.\n\n{url}": "Could not open the default web browser.\nPlease enter the address below in your browser:\n\n{url}",
        "{names} 매크로가 실행 중입니다. 정말로 종료하시겠습니까?": "{names} macro is currently running. Are you sure you want to exit?",

        # Update Dialog & Updater
        "업데이트 안내": "Update Available",
        "현재 v{current} → 새 버전 {new}": "Current v{current} → New {new}",
        "이번 버전에서 달라진 점": "What's New in This Version",
        "이 버전의 릴리즈 노트가 등록되지 않았습니다.": "No release notes available for this version.",
        "다운로드가 끝나면 실행 중인 봇을 중지합니다.\n설정과 로그는 유지되며 봇은 자동 재개하지 않습니다.": "Running bots will be stopped once the download completes.\nYour settings and logs will be preserved, and bots will not resume automatically.",
        "릴리즈 페이지": "Release Page",
        "나중에": "Later",
        "자동 업데이트 안내": "Auto Update Notice",
        "{error}\n\n다운로드 페이지를 여시겠습니까?": "{error}\n\nWould you like to open the download page?",
        "앱 업데이트": "App Update",
        "다운로드 준비 중...": "Preparing download...",
        "봇 중지 및 업데이트 준비 중...": "Stopping bots and preparing update...",
        "업데이트 실패": "Update Failed",
        # Validation, runtime errors and update preparation
        "{key} 임계값은 70~99 사이여야 합니다.": "The {key} threshold must be between 70 and 99.",
        "구매 사이클 횟수는 1 이상의 정수여야 합니다.": "Purchase cycles must be a whole number of at least 1.",
        "{name} 실행 중 오류 발생:\n{error}": "An error occurred while running {name}:\n{error}",
        "{name} 펭귄 구매 중 오류 발생:\n{error}": "An error occurred while purchasing penguins in {name}:\n{error}",
        "자동 업데이트 프로그램이 없습니다. 이번 버전은 수동 설치해 주세요.": "The automatic updater is missing. Please install this version manually.",
        "{error}\n\n현재 버전은 그대로 사용할 수 있습니다.\n진단 로그: {path}": "{error}\n\nYou can continue using the current version.\nDiagnostic log: {path}",
        "파일 교체 프로그램 시작 시간이 초과되었습니다.": "Timed out while starting the update worker.",
        "파일 교체 프로그램을 시작하지 못했습니다.": "Could not start the update worker.",
        "게임 창이 닫혔습니다. 창을 다시 검색하세요.": "The game window has closed. Please scan again.",
        "게임 창의 최소화·최대화를 해제한 뒤 사용하세요.": "Restore the game window before resizing it.",
        "게임을 일반 창 모드로 전환한 뒤 사용하세요.": "Switch the game to windowed mode first.",
        "게임 화면 크기를 확인할 수 없습니다.": "Could not determine the game screen size.",
        "게임 창 테두리 크기를 확인할 수 없습니다.": "Could not determine the game window border size.",
        "자동 업데이트는 정식 버전만 지원합니다.": "Automatic updates support stable releases only.",
        "중복된 업데이트 배포 파일이 있습니다.": "Duplicate update assets were found.",
        "릴리즈 ZIP 또는 SHA256 파일이 없습니다. 다운로드 페이지를 이용해 주세요.": "The release ZIP or SHA256 file is missing. Please use the download page.",
        "공식 저장소의 배포 파일 주소가 아닙니다.": "The asset URL does not belong to an official repository.",
        "ZIP과 SHA256 파일의 저장소가 일치하지 않습니다.": "The ZIP and SHA256 files belong to different repositories.",
        "업데이트 파일 크기 제한을 초과했습니다.": "The update file exceeds the size limit.",
        "다운로드 중 {percent}%": "Downloading {percent}%",
        "다운로드 중...": "Downloading...",
        "업데이트 다운로드가 완료되지 않았습니다.": "The update download is incomplete.",
        "SHA256 파일 형식이 올바르지 않습니다.": "The SHA256 file format is invalid.",
        "업데이트 파일 검증 실패: SHA256 불일치": "Update verification failed: SHA256 mismatch",
        "압축 해제 크기 제한을 초과했습니다.": "The extracted files exceed the size limit.",
        "안전하지 않은 ZIP 경로입니다.": "The ZIP contains an unsafe path.",
        "ZIP 링크는 허용하지 않습니다.": "Links are not allowed in the ZIP.",
        "중복 ZIP 경로입니다.": "The ZIP contains duplicate paths.",
        "허용되지 않은 배포 파일입니다: {name}": "The package contains an unsupported file: {name}",
        "배포 폴더 이름이 버전과 일치하지 않습니다.": "The package folder name does not match the version.",
        "필수 실행 파일 또는 업데이트 프로그램이 없습니다.": "A required executable or updater is missing.",
        "다운로드 검증 및 압축 해제 중...": "Verifying and extracting the download...",
        "업데이트를 위해 디스크 여유 공간 2GB가 필요합니다.": "The update requires 2 GB of free disk space.",

    },
}


def tr(text: str, default: Optional[str] = None, **kwargs) -> str:
    """Translate text for current language.

    When translation is absent, falls back to default if provided, else text itself.
    """
    lang = get_language()
    catalog = _CATALOG.get(lang, {})
    translated = catalog.get(text, default if default is not None else text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except Exception:
            return translated
    return translated


# Initialize language from storage at module import
_current_language = load_saved_language()
