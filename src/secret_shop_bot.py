"""
에픽세븐 비밀상점 자동화 매크로 핵심 로직

ADB 사용 이유:
- 비활성 매크로 구현 (매크로 동작 중 키보드/마우스 자유롭게 사용 가능)
- 앱플레이어와 독립적으로 동작
- 안정적인 화면 캡처 및 입력 제어
"""
import os
import sys
import time
import logging
from typing import Optional, Dict
from pathlib import Path

from .adb_controller import ADBController
from .image_matcher import ImageMatcher, read_image
from .shop_purchase_observer import ShopPurchaseObserver
from .shop_debug import ShopDebugRecorder, debug_timed, debug_run, debug_purchase

logger = logging.getLogger(__name__)


def get_resource_root() -> Path:
    """Return the folder that contains bundled read-only resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def get_runtime_root() -> Path:
    """Return the writable folder next to the executable while bundled."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


class SecretShopBot:
    """에픽세븐 비밀상점 자동화 봇"""
    
    # 이미지 파일 경로 (상대 경로)
    ITEMS_DIR = "images/items"
    BUTTONS_DIR = "images/buttons"
    NATURAL_REFRESH_INTERVAL = 15 * 60
    
    # 구매할 아이템 이미지 파일명
    MYSTIC_MEDAL = "mystic_medal.png"  # 신비의 메달
    COVENANT_BOOKMARK = "covenant_bookmark.png"  # 성약의 책갈피
    FRIENDSHIP_POINT = "friendship_point.png"  # 우정 포인트
    
    # 버튼 이미지 파일명
    # 상점 갱신 프로세스: 갱신 버튼 -> 확인 버튼
    REFRESH_BUTTON = "refresh_button.png"  # 갱신 버튼 (상점 리프레시)
    REFRESH_CONFIRM_BUTTON = "confirm_button.png"  # 갱신 확인 버튼
    
    # 아이템 구매 프로세스: 구입 버튼 -> 구매 버튼
    PURCHASE_BUTTON = "purchase_button.png"  # 구입 버튼 (첫 번째 단계)
    BUY_BUTTON = "buy_button.png"  # 구매 버튼 (두 번째 단계, 최종 구매)
    PURCHASE_BUTTON_DISABLED = "purchase_button_disabled.png"  # 구매 완료 후 비활성화된 구입 버튼
    
    def _find_image_file(self, directory: Path, base_name: str) -> Optional[Path]:
        """
        대소문자 구분 없이 이미지 파일 찾기
        
        Args:
            directory: 디렉토리 경로
            base_name: 파일명 (확장자 포함)
            
        Returns:
            찾은 파일 경로 또는 None
        """
        # 정확한 파일명으로 먼저 찾기
        exact_path = directory / base_name
        if exact_path.exists():
            return exact_path

        if not directory.exists():
            logger.warning(f"이미지 폴더를 찾을 수 없음: {directory}")
            return None
        
        # 대소문자 구분 없이 찾기
        base_name_lower = base_name.lower()
        for file in directory.iterdir():
            if file.is_file() and file.name.lower() == base_name_lower:
                return file
        
        return None
    
    def __init__(
        self,
        adb_controller: ADBController,
        base_dir: str = None,
        thresholds: dict = None,
        debug_mode: bool = False,
        automation_settings: dict = None,
        runtime_dir = None,
    ):
        """
        Args:
            adb_controller: ADB 컨트롤러 인스턴스
            base_dir: 프로젝트 기본 디렉토리
            thresholds: 이미지별 매칭 임계값 딕셔너리 (기본값: 모두 0.92)
                {
                    "mystic_medal": 0.92,
                    "covenant_bookmark": 0.92,
                    "purchase_button": 0.92,
                    "buy_button": 0.92,
                    "refresh_button": 0.92,
                }
            debug_mode: 디버그 모드 (상세 로그 출력)
        """
        self.adb = adb_controller
        self.resource_dir = Path(base_dir) if base_dir else get_resource_root()
        self.runtime_dir = Path(runtime_dir) if runtime_dir else get_runtime_root() / "logs"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.debug_mode = debug_mode
        self.automation_settings = automation_settings or {}
        self.macro_settings = self.automation_settings.get("macro", {})
        self.item_definitions = self._build_item_definitions()
        self.enabled_items = self._build_enabled_items()
        self.button_images = self._build_button_images()
        self.timings = self.macro_settings.get("timings", {})
        self.macro_thresholds = self.macro_settings.get("thresholds", {})
        self.macro_layout = self.macro_settings.get("layout", {})
        
        # 이미지별 임계값 설정
        default_thresholds = {
            "mystic_medal": 0.95,
            "covenant_bookmark": 0.95,
            "friendship_point": 0.95,
            "purchase_button": 0.92,
            "buy_button": 0.92,
            "refresh_button": 0.92,
        }
        self.thresholds = thresholds if thresholds else default_thresholds
        
        # 기본 매칭 객체 (범용)
        self.matcher = ImageMatcher(threshold=0.92)
        self._purchase_observer = None
        self._purchase_baseline = None
        self._shop_debug = None
        
        # 스크린샷 임시 저장 경로
        self.screenshot_path = self.runtime_dir / "current_screen.png"
        self._reset_scroll_diagnostics()
        
        # 통계
        self.stats = {
            "total_refreshes": 0,
            "completed_runs": 0,
            "successful_refreshes": 0,
            "mystic_medal_bought": 0,
            "covenant_bookmark_bought": 0,
            "friendship_point_bought": 0,
            "total_cost": 0,
            "start_time": None,
            "end_time": None,
            "elapsed_time": 0
        }
        for item in self.item_definitions.values():
            stat_key = item.get("stat_key")
            if stat_key:
                self.stats.setdefault(stat_key, 0)
        
        # 일시정지 제어
        self.paused = False
        self.user_action = None  # 'buy', 'refresh', 'stop'
        
        # 화면 스와이프 좌표 (화면 크기에 따라 조정 필요)
        # 기본 해상도: 1280x720 (240dpi)
        # 2번 구역(오른쪽 위) 중앙에서 위로 드래그
        self.screen_width, self.screen_height = self.adb.get_screen_size()
        logger.info(f"화면 해상도: {self.screen_width}x{self.screen_height}")
        
        swipe_settings = self.automation_settings.get("swipe", {})
        self.swipe_duration = int(swipe_settings.get("duration_ms", 200))
        self.swipe_x = int(self.screen_width * float(swipe_settings.get("x_ratio", 0.75)))
        self.swipe_start_y = int(self.screen_height * float(swipe_settings.get("start_y_ratio", 0.75)))
        self.swipe_end_y = int(self.screen_height * float(swipe_settings.get("end_y_ratio", 0.25)))
        self.refresh_recovery_attempts = int(self.timings.get("refresh_recovery_attempts", 1))
        if self.debug_mode:
            try:
                self._shop_debug = ShopDebugRecorder(self.runtime_dir)
                self.matcher._shop_debug = self._shop_debug
            except OSError:
                logger.warning("비밀상점 디버그 파일을 만들지 못했습니다.", exc_info=True)

    def _build_item_definitions(self) -> Dict[str, Dict[str, str]]:
        defaults = {
            "mystic_medal": {
                "label": "신비의 메달",
                "image": self.MYSTIC_MEDAL,
                "stat_key": "mystic_medal_bought",
                "log_prefix": "신비의 메달",
            },
            "covenant_bookmark": {
                "label": "성약의 책갈피",
                "image": self.COVENANT_BOOKMARK,
                "stat_key": "covenant_bookmark_bought",
                "log_prefix": "성약의 책갈피",
            },
            "friendship_point": {
                "label": "우정 포인트",
                "image": self.FRIENDSHIP_POINT,
                "stat_key": "friendship_point_bought",
                "log_prefix": "우정 포인트",
            },
        }
        remote_items = self.macro_settings.get("items", {})
        if isinstance(remote_items, dict):
            for key, value in remote_items.items():
                if isinstance(value, dict):
                    merged = defaults.get(key, {}).copy()
                    merged.update(value)
                    defaults[key] = merged
        return defaults

    def _build_enabled_items(self) -> list:
        enabled = self.macro_settings.get("enabled_items", [])
        if isinstance(enabled, list):
            filtered = [item for item in enabled if item in self.item_definitions]
            if filtered:
                return filtered
        return ["mystic_medal", "covenant_bookmark"]

    def _build_button_images(self) -> Dict[str, str]:
        defaults = {
            "refresh": self.REFRESH_BUTTON,
            "refresh_confirm": self.REFRESH_CONFIRM_BUTTON,
            "purchase": self.PURCHASE_BUTTON,
            "buy": self.BUY_BUTTON,
            "purchase_disabled": self.PURCHASE_BUTTON_DISABLED,
        }
        remote_buttons = self.macro_settings.get("buttons", {})
        if isinstance(remote_buttons, dict):
            defaults.update(remote_buttons)
        return defaults

    def _timing(self, key: str, default: float) -> float:
        try:
            return float(self.timings.get(key, default))
        except (TypeError, ValueError):
            return default

    def _macro_threshold(self, key: str, default_percent: int) -> float:
        try:
            return float(self.macro_thresholds.get(key, default_percent)) / 100.0
        except (TypeError, ValueError):
            return default_percent / 100.0

    def _item_label(self, item_name: str) -> str:
        return self.item_definitions.get(item_name, {}).get("label", item_name)

    def _sleep(self, seconds, category='wait'):
        trace = getattr(self, '_shop_debug', None)
        if trace is None:
            return time.sleep(seconds)
        with trace.span(category):
            return time.sleep(seconds)

    @debug_timed('input')
    def _tap(self, *args, **kwargs):
        return self.adb.tap(*args, **kwargs)

    @debug_timed('input')
    def _swipe(self, *args, **kwargs):
        return self.adb.swipe(*args, **kwargs)

    @debug_timed('capture')
    def _capture_screenshot(self, context: str) -> bool:
        screenshot_path = Path(self.screenshot_path)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.screenshot_path = screenshot_path
        if self.adb.screenshot(str(self.screenshot_path)):
            self._last_capture_info = dict(context=context, captured_at=time.time())
            pending = getattr(self, '_pending_scroll_diagnostic', None)
            if pending is not None:
                pending['after'] = self._cached_scroll_frame()
                self._pending_scroll_diagnostic = None
            return True
        self._last_capture_info = None
        pending = getattr(self, '_pending_scroll_diagnostic', None)
        if pending is not None:
            pending['after_capture_error'] = context
        logger.error("스크린샷 촬영 실패: %s", context)
        return False

    def _reset_scroll_diagnostics(self):
        self.scroll_diagnostics = []
        self._pending_scroll_diagnostic = None
        self._last_capture_info = None
        self._scroll_diagnostic_sequence = 0

    def _cached_scroll_frame(self):
        info = getattr(self, '_last_capture_info', None)
        if info is None:
            return dict(error='재사용할 성공 캡처 없음')
        frame = dict(info)
        try:
            frame['png'] = Path(self.screenshot_path).read_bytes()
        except OSError as exc:
            frame['error'] = str(exc)
            logger.warning('드래그 진단용 기존 캡처 보관 실패: %s', exc)
        return frame

    def _begin_scroll_diagnostic(self, kind, start_y, end_y):
        self._scroll_diagnostic_sequence += 1
        record = dict(sequence=self._scroll_diagnostic_sequence, kind=kind,
                      started_at=time.time(), start=[self.swipe_x, start_y],
                      end=[self.swipe_x, end_y], duration_ms=self.swipe_duration,
                      input_success=None, before=self._cached_scroll_frame(), after=None)
        # Keep at most two drags (four existing PNGs) in memory. Write them
        # only when creating a failure report; never request an extra capture.
        self.scroll_diagnostics.append(record)
        del self.scroll_diagnostics[:-2]
        self._pending_scroll_diagnostic = record
        return record
        
    @debug_run('paid')
    def run(self, max_refresh_count: int, buy_count_per_item: int) -> Dict:
        """
        비밀상점 자동화 실행
        
        Args:
            max_refresh_count: 최대 리프레시 횟수
            buy_count_per_item: 아이템당 구매 횟수
            
        Returns:
            통계 정보 딕셔너리
        """
        import time as time_module
        self._reset_scroll_diagnostics()
        logger.info('최근 드래그 전후 화면은 오류 발생 시 보고서 폴더에 함께 저장합니다.')
        
        # 시작 시간 기록
        self.stats["start_time"] = time_module.time()
        
        logger.info(f"비밀상점 자동화 시작 - 최대 리프레시: {max_refresh_count}회")
        
        for refresh_num in range(max_refresh_count):
            # 중지 요청 확인 (최우선)
            if self.user_action == 'stop':
                logger.info("⛔ 사용자가 중지를 선택했습니다.")
                return self._finish_stats()
            
            logger.info(f"=== 리프레시 {refresh_num + 1}/{max_refresh_count} ===")
            self.stats["completed_runs"] = refresh_num + 1
            self.stats["total_refreshes"] = self.stats["completed_runs"]
            
            # 일시정지 상태 확인
            while self.paused:
                self._sleep(0.1, category='pause')  # 빠른 반응을 위해 0.1초로 감소
                if self.user_action == 'stop':
                    logger.info("⛔ 사용자가 중지를 선택했습니다.")
                    return self._finish_stats()
            
            if self._shop_debug is not None:
                self._shop_debug.begin_cycle(refresh_num + 1, refresh_planned=refresh_num < max_refresh_count - 1)
            # 상점 첫 페이지 스캔
            found_items = self._scan_shop_page(page_num=1)
            
            # 첫 페이지에서 아이템 발견 시 구매
            if found_items:
                logger.info(f"첫 페이지에서 아이템 발견: {list(found_items.keys())}")
                for item_name, item_location in found_items.items():
                    # 중지 요청 확인
                    if self.user_action == 'stop':
                        logger.info("⛔ 사용자가 중지를 선택했습니다.")
                        return self._finish_stats()
                    
                    logger.info(f"⭐ 아이템 발견: {item_name}")
                    if self._purchase_item(item_name, item_location, buy_count_per_item):
                        # 구매 성공 (통계는 _purchase_item 내부에서 업데이트됨)
                        pass
                    else:
                        # 구매 실패 (골드 부족 등) - 중지
                        logger.error("⚠️ 구매 완료를 확인하지 못해 중지합니다. 상품 위치·수량과 실제 구매 결과를 확인하세요.")
                        self.stats.update(status='failed', reason='구매 완료 확인 실패 (상품 위치·수량 또는 구매 결과 확인 필요)')
                        return self._finish_stats()
            
            # 첫 페이지 처리 완료 → 드래그하여 두 번째 페이지로 이동
            logger.debug("두 번째 페이지로 이동")
            self._scroll_down()
            self._sleep(self._timing("after_scroll", 0.5))
            
            # 두 번째 페이지 스캔
            found_items = self._scan_shop_page(page_num=2)
            
            # 두 번째 페이지에서 아이템 발견 시 구매
            if found_items:
                logger.info(f"두 번째 페이지에서 아이템 발견: {list(found_items.keys())}")
                for item_name, item_location in found_items.items():
                    # 중지 요청 확인
                    if self.user_action == 'stop':
                        logger.info("⛔ 사용자가 중지를 선택했습니다.")
                        return self._finish_stats()
                    
                    logger.info(f"⭐ 아이템 발견: {item_name}")
                    if self._purchase_item(item_name, item_location, buy_count_per_item):
                        # 구매 성공 (통계는 _purchase_item 내부에서 업데이트됨)
                        pass
                    else:
                        # 구매 실패 (골드 부족 등) - 중지
                        logger.error("⚠️ 구매 완료를 확인하지 못해 중지합니다. 상품 위치·수량과 실제 구매 결과를 확인하세요.")
                        self.stats.update(status='failed', reason='구매 완료 확인 실패 (상품 위치·수량 또는 구매 결과 확인 필요)')
                        return self._finish_stats()
            else:
                logger.debug("두 번째 페이지에도 아이템 없음")
            
            # 상점 리프레시
            if refresh_num < max_refresh_count - 1:  # 마지막 회차가 아니면
                if self._refresh_shop_with_recovery():
                    self.stats["successful_refreshes"] += 1
                    self._sleep(self._timing("after_refresh", 1.0))  # 리프레시 후 대기
                else:
                    logger.error("Refresh recovery failed; stopping to avoid repeated scroll-only loops.")
                    self.stats.update(status='failed', reason='상점 갱신 복구 실패')
                    return self._finish_stats()
            if self._shop_debug is not None:
                self._shop_debug.end_cycle('completed')
        
        self._finish_stats()
        
        logger.info("비밀상점 자동화 완료")
        logger.info(
            "완료 요약 - 진행: %s회, 갱신 성공: %s회, 신비의 메달: %s개, 성약의 책갈피: %s개, 우정 포인트: %s개, 소요 시간: %s초",
            self.stats["completed_runs"],
            self.stats["successful_refreshes"],
            self.stats["mystic_medal_bought"],
            self.stats["covenant_bookmark_bought"],
            self.stats["friendship_point_bought"],
            self.stats["elapsed_time"],
        )
        
        return self.stats

    @debug_run('natural')
    def run_natural_refresh(self, buy_count_per_item: int) -> Dict:
        """자연 갱신 상품만 15분마다 확인합니다. 유료 갱신은 하지 않습니다."""
        self._reset_scroll_diagnostics()
        logger.info('최근 드래그 전후 화면은 오류 발생 시 보고서 폴더에 함께 저장합니다.')
        self.stats["start_time"] = time.time()
        logger.info("자연 갱신 구매 시작 - 하늘석 사용 없음, 15분 간격, 중지할 때까지 실행")
        while self._wait_natural_refresh(0):
            cycle_started = time.monotonic()
            if self._shop_debug is not None:
                self._shop_debug.begin_cycle(self.stats["completed_runs"] + 1)
            self._scroll_up()
            if not self._wait_natural_refresh(self._timing("after_scroll", 0.5)):
                break
            for page_num in (1, 2):
                if not self._wait_natural_refresh(0):
                    return self._finish_stats()
                if page_num == 2:
                    self._scroll_down()
                    if not self._wait_natural_refresh(self._timing("after_scroll", 0.5)):
                        return self._finish_stats()
                for item_name, location in self._scan_shop_page(page_num=page_num).items():
                    if not self._wait_natural_refresh(0):
                        return self._finish_stats()
                    if not self._purchase_item(item_name, location, buy_count_per_item):
                        logger.error("구매 검증 실패 - 자연 갱신 구매를 중지합니다.")
                        self.stats.update(status='failed', reason='자연 갱신 구매 검증 실패')
                        return self._finish_stats()
            self.stats["completed_runs"] += 1
            logger.info("자연 갱신 상품 확인 완료 (%s회) - 다음 확인까지 대기", self.stats["completed_runs"])
            if self._shop_debug is not None:
                self._shop_debug.end_cycle('completed')
            remaining = max(0, self.NATURAL_REFRESH_INTERVAL - (time.monotonic() - cycle_started))
            if not self._wait_for_next_natural_refresh(remaining):
                break
        return self._finish_stats()

    @debug_timed('natural_idle')
    def _wait_for_next_natural_refresh(self, seconds):
        return self._wait_natural_refresh(seconds)

    def _wait_natural_refresh(self, seconds: float) -> bool:
        """대기 중에는 ADB를 호출하지 않고 일시정지/중지에 응답합니다."""
        deadline = time.monotonic() + seconds
        while self.user_action != "stop":
            remaining = deadline - time.monotonic()
            if not self.paused and remaining <= 0:
                return True
            self._sleep(0.1 if self.paused else min(0.1, remaining), category='pause' if self.paused else 'wait')
        return False

    def _finish_stats(self) -> Dict:
        """종료 시각과 소요 시간을 기록하고 통계를 반환합니다."""
        import time as time_module

        if self.stats.get("start_time") and not self.stats.get("end_time"):
            self.stats["end_time"] = time_module.time()
            self.stats["elapsed_time"] = int(self.stats["end_time"] - self.stats["start_time"])
        return self.stats
    
    def _scan_shop_page(self, page_num: int = 1) -> Dict[str, tuple]:
        """
        현재 상점 페이지 스캠
        
        Returns:
            발견한 아이템 딕셔너리 {아이템명: (x, y, w, h)}
        """
        # 중지 확인
        if self.user_action == 'stop':
            return {}
        
        # 스크린샷 촬영
        if not self._capture_screenshot(f"상점 스캔 {page_num}페이지"):
            return {}
        self._sleep(self._timing("after_screenshot", 0.3))
        
        found_items = {}
        
        for item_name in self.enabled_items:
            item = self.item_definitions.get(item_name, {})
            image_name = item.get("image", f"{item_name}.png")
            image_path = self._find_image_file(self.resource_dir / self.ITEMS_DIR, image_name)
            if not image_path:
                logger.warning(f"⚠️ {self._item_label(item_name)} 이미지 파일을 찾을 수 없음: {image_name} - 이 아이템은 검색하지 않습니다")
                continue

            result = self.matcher.find_image(
                str(self.screenshot_path),
                str(image_path),
                threshold=self.thresholds.get(item_name, 0.92),
            )
            if result:
                found_items[item_name] = result
                similarity = self.matcher.get_similarity_at_location(
                    str(self.screenshot_path),
                    str(image_path),
                    result,
                )
                logger.info(
                    f"⭐ {self._item_label(item_name)} 발견: {result} (매칭률: {similarity * 100:.1f}%)"
                )
        
        if found_items:
            logger.info(f"🔍 스캔 완료 - 발견한 아이템: {list(found_items.keys())}")
        else:
            logger.info(f"🔍 스캔 완료 ({page_num}페이지) - 아이템 없음")
        
        return found_items
    
    @debug_purchase
    def _purchase_item(self, item_name: str, item_location: tuple, verification_count: int) -> bool:
        """
        아이템 구매 (구입 -> 구매 2단계 프로세스) 및 구매 완료 검증
        
        Args:
            item_name: 아이템 이름 (통계 업데이트용)
            item_location: 아이템 위치 (x, y, w, h)
            verification_count: 구매 완료 확인 최대 시도 횟수 (확인되면 즉시 종료)
            
        Returns:
            구매 성공 여부
        """
        # 중지 확인
        if self.user_action == 'stop':
            logger.info("⛔ 중지 요청 - 구매 중단")
            return False
        
        # 1단계: 아이템과 같은 라인의 오른쪽에 있는 구입 버튼 찾기 및 클릭
        purchase_btn = self._find_purchase_button_on_item_line(item_location, item_name)
        if purchase_btn is False:
            # 비활성화된 버튼 (이미 구매한 아이템) - 조용히 건너뛰기
            logger.debug("비활성화된 버튼이므로 구매 건너뜀")
            return True  # 성공으로 처리 (이미 구매했으므로)
        elif purchase_btn is None:
            logger.warning("구입 버튼(1단계)을 찾을 수 없음")
            return False
            
        # 중지 확인
        if self.user_action == 'stop':
            logger.info("⛔ 중지 요청 - 구매 중단")
            return False
        
        # 구입 버튼 클릭
        btn_center_x, btn_center_y = self.matcher.get_center(purchase_btn)
        logger.info(
            "구입 버튼 탭 - 아이템: %s, 아이템 영역: %s, 버튼 영역: %s, 좌표: (%s, %s)",
            item_name,
            item_location,
            purchase_btn,
            btn_center_x,
            btn_center_y,
        )
        self._tap(btn_center_x, btn_center_y, delay=0.5)
        if self._shop_debug is not None:
            self._shop_debug.phase = 'purchase_dialog'
        self._sleep(self._timing("after_purchase_tap", 0.5))  # 구매 팝업이 뜰 때까지 대기
        
        # 중지 확인
        if self.user_action == 'stop':
            logger.info("⛔ 중지 요청 - 구매 중단")
            # 화면 닫기
            self._tap(self.screen_width // 4, self.screen_height // 2, delay=self._timing("close_popup_delay", 0.3))
            return False
        
        # 구매 버튼이 나타날 때까지 대기 (최대 2초)
        buy_button_found = False
        buy_button_wait_attempts = int(self.timings.get("buy_button_wait_attempts", 4))
        wait_interval = self._timing("buy_button_wait_interval", 0.5)
        for wait_attempt in range(buy_button_wait_attempts):
            if not self._capture_screenshot(f"구매 버튼 대기 - {item_name}"):
                return False
            self._sleep(self._timing("after_screenshot", 0.2))
            
            buy_button_path = self._find_image_file(self.resource_dir / self.BUTTONS_DIR, self.button_images["buy"])
            if buy_button_path:
                result = self.matcher.find_image(
                    str(self.screenshot_path),
                    str(buy_button_path),
                    threshold=self.thresholds.get("buy_button", 0.92),
                )
                if result:
                    buy_button_found = True
                    logger.debug(f"구매 버튼 발견 (대기 시간: {wait_attempt * wait_interval}초)")
                    break
            
            if wait_attempt < buy_button_wait_attempts - 1:  # 마지막 시도가 아니면 대기
                self._sleep(wait_interval)
        
        if not buy_button_found:
            logger.warning("⚠️ 구매 버튼이 나타나지 않음 - 구매 팝업 로딩 실패")
            # 화면 닫기
            self._tap(self.screen_width // 4, self.screen_height // 2, delay=self._timing("close_popup_delay", 0.3))
            return False
        
        # 2단계: 구매 버튼 클릭 (최종 구매)
        if self._click_button("buy"):
            self._sleep(self._timing("after_purchase_tap", 0.5))
            # Reuse the pre-click baseline and each existing verification capture.
            # Only an inconclusive result consumes another attempt/capture.
            attempts = max(1, int(verification_count))
            for verify_attempt in range(attempts):
                if self.user_action == 'stop':
                    return False
                if self._shop_debug is not None:
                    self._shop_debug.phase = 'verify'
                    self._shop_debug.count('verification_attempts')
                    self._shop_debug.count('verification_retries', int(verify_attempt > 0))
                    self._shop_debug.record('verification_attempt', attempt=verify_attempt + 1, maximum=attempts)
                if self._verify_purchase_complete():
                    if self._shop_debug is not None:
                        self._shop_debug.count('purchases')
                    stat_key = self.item_definitions.get(item_name, {}).get("stat_key")
                    if stat_key:
                        self.stats[stat_key] = self.stats.get(stat_key, 0) + 1
                    logger.info("✅ %s 구매 완료 (동일 상품 수량 1/1 → 0/1, 확인 %s회)",
                                self._item_label(item_name), verify_attempt + 1)
                    self._tap(self.screen_width // 4, self.screen_height // 2,
                                 delay=self._timing("close_popup_delay", 0.3))
                    return True
                if verify_attempt < attempts - 1:
                    self._sleep(self._timing("verify_interval", 0.3))
            logger.warning("⚠️ 구매 완료를 확인하지 못했습니다. 골드 부족, 화면 전환 또는 수량 인식을 확인하세요.")
            self._tap(self.screen_width // 4, self.screen_height // 2,
                         delay=self._timing("close_popup_delay", 0.3))
            return False
        else:
            logger.warning("구매 버튼(2단계)을 찾을 수 없음")
            # 취소 또는 뒤로가기 처리
            self._tap(self.screen_width // 4, self.screen_height // 2, delay=self._timing("close_popup_delay", 0.3))
            return False
    
    def _get_purchase_observer(self):
        if self._purchase_observer is None:
            templates = []
            for name in ("purchase", "purchase_disabled"):
                path = self._find_image_file(self.resource_dir / self.BUTTONS_DIR, self.button_images[name])
                if path is None:
                    raise ValueError("구입 수량 확인에 필요한 버튼 이미지가 없습니다.")
                template = self.matcher.load_template(path)
                if template is None:
                    raise ValueError("구입 버튼 이미지를 읽을 수 없습니다.")
                templates.append(template)
            self._purchase_observer = ShopPurchaseObserver(*templates, diagnostics=self._shop_debug)
        return self._purchase_observer

    @debug_timed('recognition')
    def _find_purchase_button_on_item_line(self, item_location: tuple, item_name: str):
        """Find the same product row, then read 1/1 or 0/1 without color states."""
        self._purchase_baseline = None
        if not self._capture_screenshot("구입 버튼 탐색"):
            return None
        self._sleep(self._timing("after_screenshot", 0.2))
        screen = read_image(self.screenshot_path)
        if screen is None:
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='screen_unreadable')
            return None
        item = self.item_definitions.get(item_name, {})
        item_path = self._find_image_file(self.resource_dir / self.ITEMS_DIR,
                                          item.get("image", f"{item_name}.png"))
        if item_path is None:
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='item_template_missing')
            return None
        try:
            observer = self._get_purchase_observer()
            template = self.matcher.load_template(item_path)
            if template is None:
                return None
            current_item = observer.locate_item(screen, template, item_location,
                                                self.thresholds.get(item_name, .95), diagnostics=self._shop_debug)
            if current_item is None:
                if self._shop_debug is not None:
                    self._shop_debug.record('purchase_check', result=False, reason='same_item_not_found', same_item=False)
                    x, y, w, h = item_location
                    self._shop_debug.evidence('initial_item_not_found', screen[max(0, y):y+h, max(0, x):x+w])
                logger.debug("구입 전 동일 상품 위치를 재확인하지 못했습니다: %s", item_name)
                return None
            result = observer.find_button(screen, current_item,
                                           self.thresholds.get("purchase_button", .92),
                                           int(self.macro_layout.get("purchase_line_y_tolerance", 50)))
            if result is None:
                if self._shop_debug is not None:
                    self._shop_debug.record('purchase_check', result=False, reason='button_or_quantity_missing', same_item=True)
                    x, y, w, h = current_item
                    self._shop_debug.evidence('button_or_quantity_missing', screen[max(0, y-50):y+h+50, x+w:])
                logger.debug("동일 상품 행의 버튼 또는 수량을 확인하지 못했습니다: %s", item_name)
                return None
            bounds, state = result
            if state == 'sold':
                if self._shop_debug is not None:
                    self._shop_debug.count('skipped_items')
                logger.info("⏭️ 이미 구매한 %s 건너뜀 (수량 0/1)", self._item_label(item_name))
                return False
            self._purchase_baseline = observer.baseline(screen, current_item, bounds)
            return bounds
        except (ValueError, OSError):
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='initial_observation_error')
            logger.warning("구입 버튼 관측 실패", exc_info=True)
            return None

    def _refresh_shop(self) -> bool:
        """상점 리프레시 (갱신 -> 확인 2단계 프로세스)
        
        Returns:
            성공 여부
        """
        logger.debug("상점 갱신 시작")
        
        # 중지 확인
        if self.user_action == 'stop':
            logger.debug("중지 요청으로 갱신 건너뜀")
            return False
        
        # 1단계: 갱신 버튼 찾기 및 클릭
        if self._click_button("refresh"):
            # 2단계: 확인 버튼이 실제로 뜰 때까지 잠시 재시도
            if self._click_button_with_retry(
                "refresh_confirm",
                attempts=int(self.timings.get("refresh_confirm_attempts", 5)),
                initial_delay=self._timing("refresh_confirm_delay", 0.5),
                retry_interval=self._timing("refresh_confirm_retry_interval", 0.3),
            ):
                logger.info("✅ 상점 갱신 성공")
                self._sleep(self._timing("after_refresh", 0.8))
                return True
            else:
                # 중지 요청이면 로그 생략
                if self.user_action != 'stop':
                    logger.warning("⚠️  갱신 확인 버튼을 찾을 수 없음")
                return False
        else:
            # 중지 요청이면 로그 생략
            if self.user_action != 'stop':
                logger.error("❌ 갱신 버튼을 찾을 수 없음")
                if self.debug_mode:
                    logger.error(f"💡 디버깅: 스크린샷이 {self.screenshot_path}에 저장되었습니다.")
                    logger.error(f"💡 버튼 이미지: {self.resource_dir / self.BUTTONS_DIR / self.REFRESH_BUTTON}")
                    logger.error(f"💡 이미지 매칭 정확도를 낮춰보세요 (현재: {int(self.matcher.threshold*100)}%)")
                    
                    # 디버깅용 스크린샷 저장
                    debug_path = self.runtime_dir / "debug_refresh_button.png"
                    debug_path.parent.mkdir(exist_ok=True)
                    import shutil
                    shutil.copy(self.screenshot_path, debug_path)
                    logger.error(f"💡 디버그 스크린샷: {debug_path}")
            return False

    def _refresh_shop_with_recovery(self) -> bool:
        if self._refresh_shop():
            return True

        if self.user_action == "stop":
            return False

        recovery_attempts = max(0, int(getattr(self, "refresh_recovery_attempts", 1)))
        for attempt in range(recovery_attempts):
            logger.warning(
                "Refresh failed after scanning page 2; resetting scroll before retry (%s/%s).",
                attempt + 1,
                recovery_attempts,
            )
            self._scroll_up()
            self._sleep(self._timing("refresh_retry", 2.0))

            if self._refresh_shop():
                logger.info("Refresh succeeded after resetting the scroll position.")
                return True

            if self.user_action == "stop":
                return False

        return False

    def _click_button_with_retry(
        self,
        button_type: str,
        attempts: int = 1,
        initial_delay: float = 0.0,
        retry_interval: float = 0.0,
    ) -> bool:
        attempts = max(1, int(attempts))
        if initial_delay > 0:
            self._sleep(initial_delay)

        for attempt in range(attempts):
            if self.user_action == "stop":
                return False
            if self._click_button(button_type):
                return True
            if attempt < attempts - 1 and retry_interval > 0:
                self._sleep(retry_interval)
        return False
    
    def _click_button(self, button_type: str) -> bool:
        """
        버튼 찾기 및 클릭
        
        Args:
            button_type: 버튼 타입
                - "refresh": 갱신 버튼 (상점 리프레시 시작)
                - "refresh_confirm": 갱신 확인 버튼 (상점 리프레시 확인)
                - "purchase": 구입 버튼 (아이템 구매 1단계)
                - "buy": 구매 버튼 (아이템 구매 2단계, 최종 구매)
            
        Returns:
            클릭 성공 여부
        """
        # 중지 확인
        if self.user_action == 'stop':
            return False
        
        # 스크린샷 촬영
        if not self._capture_screenshot(f"버튼 탐색 - {button_type}"):
            return False
        self._sleep(self._timing("after_screenshot", 0.2))
        
        # 버튼 이미지 경로 선택
        button_filename = self.button_images.get(button_type)
        
        if not button_filename:
            logger.error(f"알 수 없는 버튼 타입: {button_type}")
            return False
        
        button_path = self._find_image_file(self.resource_dir / self.BUTTONS_DIR, button_filename)
        
        if not button_path:
            logger.error(f"버튼 이미지 파일을 찾을 수 없음: {button_filename}")
            return False
        
        # 버튼 찾기
        # 버튼 타입에 따라 임계값 선택
        threshold_key = {
            "refresh": "refresh_button",
            "refresh_confirm": "refresh_button",
            "purchase": "purchase_button",
            "buy": "buy_button",
        }.get(button_type, "buy_button")
        threshold = self.thresholds.get(threshold_key, 0.92)
        result = self.matcher.find_image(str(self.screenshot_path), str(button_path), threshold=threshold)
        
        if result:
            # 버튼 중심 클릭
            center_x, center_y = self.matcher.get_center(result)
            self._tap(center_x, center_y, delay=0.3)
            logger.debug(f"{button_type} 버튼 클릭: ({center_x}, {center_y})")
            return True
        else:
            logger.debug(f"{button_type} 버튼을 찾을 수 없음")
            return False
    
    @debug_timed('verification')
    def _verify_purchase_complete(self) -> bool:
        """Confirm the same product's 1/1 -> 0/1 transition on this capture."""
        if self._purchase_baseline is None or self.user_action == 'stop':
            return False
        if not self._capture_screenshot("구매 완료 검증"):
            return False
        self._sleep(self._timing("after_screenshot", 0.2))
        screen = read_image(self.screenshot_path)
        if screen is None:
            if self._shop_debug is not None:
                self._shop_debug.record('purchase_check', result=False, reason='screen_unreadable')
            return False
        return self._get_purchase_observer().purchase_complete(screen, self._purchase_baseline)

    def _scroll_down(self):
        """화면을 위로 스크롤 (두 번째 페이지로 이동)"""
        diagnostic = self._begin_scroll_diagnostic('normal', self.swipe_start_y, self.swipe_end_y)
        logger.info(
            "화면 스크롤 시도 1/1 - (%s, %s) -> (%s, %s), duration=%sms",
            self.swipe_x,
            self.swipe_start_y,
            self.swipe_x,
            self.swipe_end_y,
            self.swipe_duration,
        )

        success = self._swipe(
            self.swipe_x,
            self.swipe_start_y,
            self.swipe_x,
            self.swipe_end_y,
            duration=self.swipe_duration,
            delay=0.5,
        )
        diagnostic['input_success'] = bool(success)

        if success:
            logger.info("화면 스크롤 시도 1/1 성공")
        else:
            logger.warning("화면 스크롤 시도 1/1 실패")

        logger.info("화면 스크롤 1회 시도 완료")
    
    def _scroll_up(self):
        """Restore the first-page position before retrying a failed refresh."""
        diagnostic = self._begin_scroll_diagnostic('recovery', self.swipe_end_y, self.swipe_start_y)
        logger.info(
            "화면 복구 스크롤 시도 1/1 - (%s, %s) -> (%s, %s), duration=%sms",
            self.swipe_x,
            self.swipe_end_y,
            self.swipe_x,
            self.swipe_start_y,
            self.swipe_duration,
        )

        success = self._swipe(
            self.swipe_x,
            self.swipe_end_y,
            self.swipe_x,
            self.swipe_start_y,
            duration=self.swipe_duration,
            delay=0.5,
        )
        diagnostic['input_success'] = bool(success)

        if success:
            logger.info("화면 복구 스크롤 시도 1/1 성공")
        else:
            logger.warning("화면 복구 스크롤 시도 1/1 실패")

    def set_user_action(self, action: str):
        """
        사용자 액션 설정 (GUI에서 호출)
        
        Args:
            action: 'pause' (일시정지), 'resume' (재개), 'stop' (중지)
        """
        if action == 'pause':
            self.paused = True
            logger.info("⏸️  사용자가 일시정지를 요청했습니다.")
        elif action == 'resume':
            self.paused = False
            self.user_action = None
            logger.info("▶️  사용자가 재개를 요청했습니다.")
        elif action == 'stop':
            self.user_action = 'stop'
            self.paused = False
            logger.info("⛔ 사용자가 중지를 요청했습니다.")
    
    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        return self.stats.copy()
