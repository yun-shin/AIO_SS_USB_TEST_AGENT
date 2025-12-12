"""MFC Controller.

Main controller responsible for overall USB Test.exe control.
Handles test start, stop, state monitoring, etc.
Each slot has its own dedicated USB Test.exe process.
"""

import asyncio
from typing import Optional

from config.settings import get_settings
from config.constants import (
    TestCapacity,
    TestFile,
    TestMethod,
    TestPreset,
    ProcessState,
    SlotConfig,
    MFCControlId,
    RetryConfig,
    TimeoutConfig,
)
from domain.models.test_config import TestConfig
from domain.models.test_state import TestState
from domain.enums import SlotStatus
from utils.logging import get_logger
from controller.window_manager import WindowManager, SlotWindowManager
from controller.control_wrapper import ControlWrapper

logger = get_logger(__name__)


class MFCController:
    """USB Test.exe MFC controller.

    Interacts with MFC application to control tests.
    Each slot has its own dedicated USB Test.exe process.

    Attributes:
        _window_manager: Window manager for all slots.
        _slot_states: State per slot.
        _is_monitoring: State monitoring activation status.
    """

    def __init__(self, exe_path: Optional[str] = None) -> None:
        """Initialize controller.

        Args:
            exe_path: USB Test.exe path (uses settings if None).
        """
        settings = get_settings()
        self._exe_path = exe_path or settings.usb_test_path
        self._window_manager = WindowManager(self._exe_path)
        self._slot_states: dict[int, TestState] = {}
        self._is_monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

        # 슬롯 상태 초기화
        for slot_idx in range(SlotConfig.MAX_SLOTS):
            self._slot_states[slot_idx] = TestState(slot_idx=slot_idx)

    @property
    def window_manager(self) -> WindowManager:
        """Window manager."""
        return self._window_manager

    def is_slot_connected(self, slot_idx: int) -> bool:
        """Check if a specific slot is connected.

        Args:
            slot_idx: Slot index.

        Returns:
            True if slot is connected.
        """
        return self._window_manager.is_slot_connected(slot_idx)

    def get_slot_pid(self, slot_idx: int) -> Optional[int]:
        """Get PID for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            PID or None.
        """
        return self._window_manager.get_slot_pid(slot_idx)

    @property
    def slot_states(self) -> dict[int, TestState]:
        """All slot states."""
        return self._slot_states

    def get_slot_state(self, slot_idx: int) -> Optional[TestState]:
        """Get specific slot state.

        Args:
            slot_idx: Slot index.

        Returns:
            Slot state or None.
        """
        return self._slot_states.get(slot_idx)

    async def connect_slot(self, slot_idx: int) -> bool:
        """Launch and connect USB Test.exe for a specific slot.

        This will:
        1. Launch a new USB Test.exe process
        2. Get its PID
        3. Connect to it via pywinauto

        Args:
            slot_idx: Slot index.

        Returns:
            Connection success status.
        """
        if not (0 <= slot_idx < SlotConfig.MAX_SLOTS):
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return False

        logger.info(
            "Connecting slot to USB Test.exe",
            slot_idx=slot_idx,
            exe_path=self._exe_path,
        )

        connected = await self._window_manager.launch_and_connect(slot_idx)

        if connected:
            pid = self._window_manager.get_slot_pid(slot_idx)
            logger.info(
                "Slot connected",
                slot_idx=slot_idx,
                pid=pid,
            )
            # 슬롯 상태 업데이트
            self._slot_states[slot_idx].status = SlotStatus.IDLE
            self._slot_states[slot_idx].error_message = None
        else:
            self._slot_states[slot_idx].status = SlotStatus.ERROR
            self._slot_states[
                slot_idx
            ].error_message = (
                "USB Test.exe에 연결할 수 없습니다. 프로그램 경로를 확인하세요."
            )

        return connected

    async def disconnect_slot(self, slot_idx: int) -> None:
        """Disconnect a specific slot (without terminating process).

        Args:
            slot_idx: Slot index.
        """
        self._window_manager.disconnect_slot(slot_idx)
        logger.info("Slot disconnected", slot_idx=slot_idx)

    async def terminate_slot(self, slot_idx: int) -> bool:
        """Terminate process and disconnect for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            True if terminated successfully.
        """
        result = await self._window_manager.terminate_slot(slot_idx)
        if result:
            self._slot_states[slot_idx].status = SlotStatus.IDLE
            logger.info("Slot process terminated", slot_idx=slot_idx)
        return result

    async def terminate_all(self) -> None:
        """Terminate all slot processes."""
        self.stop_monitoring()
        await self._window_manager.terminate_all()
        logger.info("All slot processes terminated")

    async def start_test(
        self,
        slot_idx: int,
        config: TestConfig,
    ) -> bool:
        """Start test on a specific slot.

        MFC Client의 Loop 필드에는 loop_step 값을 설정합니다.
        총 테스트 횟수(loop_count)를 loop_step으로 나눈 만큼 반복 실행해야 합니다.
        반복 실행은 호출하는 쪽(Agent)에서 처리해야 합니다.

        Args:
            slot_idx: Slot index.
            config: Test configuration.

        Returns:
            Start success status.
        """
        if not self.is_slot_connected(slot_idx):
            logger.error("Slot not connected", slot_idx=slot_idx)
            return False

        if not (0 <= slot_idx < SlotConfig.MAX_SLOTS):
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return False

        logger.info(
            "Starting test",
            slot_idx=slot_idx,
            test_name=config.test_name,
            capacity=config.capacity.value,
            method=config.method.value,
            loop_step=config.loop_step,
        )

        # 슬롯 상태 업데이트
        state = self._slot_states[slot_idx]
        state.status = SlotStatus.PREPARING
        state.current_config = config

        try:
            # 슬롯의 윈도우 매니저 가져오기
            slot_window = self._window_manager.get_slot_window(slot_idx)
            if not slot_window or not slot_window.is_connected:
                raise RuntimeError("Slot window not available")

            # MFC 상태 리셋 (Pass/Idle 상태에서 Contact 클릭 → 컨트롤 활성화)
            # 기존 AIO_USB_TEST_MACRO의 wait_until_ready 로직 참조
            await self._reset_mfc_state(slot_window)

            # MFC 컨트롤 조작 (순서 중요!)
            # 0. Ignore Fail 체크 해제 (항상 먼저 실행)
            await self._uncheck_ignore_fail(slot_window)

            # 1. 드라이브 설정
            await self._set_drive(slot_window, config.drive)

            # 2. 용량 설정
            await self._set_capacity(slot_window, config.capacity)

            # 3. 테스트 방식 설정
            await self._set_method(slot_window, config.method)

            # 4. 루프 카운트 설정 (loop_step 값을 MFC에 설정)
            await self._set_loop_count(slot_window, config.loop_step)

            # 5. 테스트 파일 타입 설정 (Photo 또는 MP3)
            await self._set_test_file(slot_window, config.test_file)

            # 6. Contact 버튼 클릭 (환경 변수 및 드라이브 인식)
            await self._click_contact_button(slot_window)

            # Contact 완료 대기 및 Test 버튼 활성화 대기
            await self._wait_for_test_button_enabled(slot_window)

            # 7. Test 버튼 클릭 (테스트 시작)
            await self._click_start_button(slot_window)

            state.status = SlotStatus.RUNNING
            state.current_phase = "Initializing"
            logger.info("Test started", slot_idx=slot_idx)

            return True

        except Exception as e:
            state.status = SlotStatus.ERROR
            state.error_message = str(e)
            logger.error("Failed to start test", slot_idx=slot_idx, error=str(e))
            return False

    async def continue_batch(self, slot_idx: int) -> bool:
        """Continue to next batch iteration (Contact → Test only).

        Used for batch mode where configuration is already set.
        Only clicks Contact and Test buttons without reconfiguring.

        Args:
            slot_idx: Slot index.

        Returns:
            True if batch continuation started successfully.
        """
        if not self.is_slot_connected(slot_idx):
            logger.error("Slot not connected", slot_idx=slot_idx)
            return False

        logger.info("Continuing batch", slot_idx=slot_idx)

        state = self._slot_states.get(slot_idx)
        if not state:
            logger.error("Slot state not found", slot_idx=slot_idx)
            return False

        try:
            slot_window = self._window_manager.get_slot_window(slot_idx)
            if not slot_window or not slot_window.is_connected:
                raise RuntimeError("Slot window not available")

            # Batch 계속: Contact → Test만 실행 (설정은 이미 됨)
            # 0. Contact 버튼이 활성화될 때까지 대기 (이전 배치 완료 확인)
            await self._wait_for_contact_button_enabled(slot_window)

            # 1. Contact 버튼 클릭
            await self._click_contact_button(slot_window)

            # Contact 완료 대기 및 Test 버튼 활성화 대기 (기본 타임아웃 사용)
            await self._wait_for_test_button_enabled(slot_window)

            # 2. Test 버튼 클릭
            await self._click_start_button(slot_window)

            state.status = SlotStatus.RUNNING
            state.current_phase = "Batch Continue"
            logger.info("Batch continued", slot_idx=slot_idx)

            return True

        except Exception as e:
            state.status = SlotStatus.ERROR
            state.error_message = str(e)
            logger.error("Failed to continue batch", slot_idx=slot_idx, error=str(e))
            return False

    async def stop_test(self, slot_idx: int) -> bool:
        """Stop test on a specific slot.

        Args:
            slot_idx: Slot index.

        Returns:
            Stop success status.
        """
        if not self.is_slot_connected(slot_idx):
            logger.error("Slot not connected", slot_idx=slot_idx)
            return False

        logger.info("Stopping test", slot_idx=slot_idx)

        state = self._slot_states.get(slot_idx)
        if not state:
            return False

        try:
            slot_window = self._window_manager.get_slot_window(slot_idx)
            if not slot_window or not slot_window.is_connected:
                raise RuntimeError("Slot window not available")

            await self._click_stop_button(slot_window)

            state.status = SlotStatus.STOPPED
            logger.info("Test stopped", slot_idx=slot_idx)

            return True

        except Exception as e:
            state.status = SlotStatus.ERROR
            state.error_message = str(e)
            logger.error("Failed to stop test", slot_idx=slot_idx, error=str(e))
            return False

    def start_monitoring(
        self,
        callback: Optional[callable] = None,
        interval: float = 1.0,
    ) -> None:
        """Start state monitoring.

        Args:
            callback: Callback to call on state change.
            interval: Monitoring interval in seconds.
        """
        if self._is_monitoring:
            return

        self._is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(callback, interval))
        logger.info("State monitoring started", interval=interval)

    def stop_monitoring(self) -> None:
        """Stop state monitoring."""
        self._is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("State monitoring stopped")

    async def _monitor_loop(
        self,
        callback: Optional[callable],
        interval: float,
    ) -> None:
        """State monitoring loop.

        Args:
            callback: State change callback.
            interval: Interval.
        """
        while self._is_monitoring:
            try:
                # 프로세스 상태 갱신
                self._window_manager.refresh_all_status()

                await self._update_all_slot_states()

                if callback:
                    for slot_idx, state in self._slot_states.items():
                        await callback(slot_idx, state)

            except Exception as e:
                logger.error("Monitoring error", error=str(e))

            await asyncio.sleep(interval)

    async def _update_all_slot_states(self) -> None:
        """Update all slot states."""
        for slot_idx in range(SlotConfig.MAX_SLOTS):
            if not self.is_slot_connected(slot_idx):
                # 연결되지 않은 슬롯은 IDLE로 설정
                if self._slot_states[slot_idx].status == SlotStatus.RUNNING:
                    self._slot_states[slot_idx].status = SlotStatus.ERROR
                    self._slot_states[
                        slot_idx
                    ].error_message = "프로세스 연결이 끊어졌습니다."
                continue

            # TODO: 실제 MFC UI에서 상태 읽기 구현
            # 각 슬롯의 진행률, 상태 등을 읽어 업데이트
            pass

    # ===== Private Helper Methods =====
    # These methods should be implemented according to actual USB Test.exe UI structure.

    async def _select_combobox_item(
        self,
        slot_window: SlotWindowManager,
        control_id: int,
        value: str,
    ) -> bool:
        """Select item in combobox by value.

        Args:
            slot_window: Slot window manager.
            control_id: Control ID (integer for win32 backend).
            value: Value to select.

        Returns:
            Success status.
        """
        try:
            combo = slot_window.find_control(
                control_id=control_id, class_name="ComboBox"
            )
            if combo is None:
                logger.error("ComboBox not found", control_id=control_id)
                return False

            # 콤보박스 아이템 목록 가져오기
            items = combo.item_texts()
            logger.debug("ComboBox items", control_id=control_id, items=items)

            # 정상화를 통해 대소문자/공백 차이 최소화
            def _normalize(text: str) -> str:
                return text.strip().lower()

            target = _normalize(value)
            normalized_items = [
                (idx, item, _normalize(item)) for idx, item in enumerate(items)
            ]

            # 1순위: 정확히 동일한 값 매칭
            for idx, item, normalized in normalized_items:
                if normalized == target:
                    combo.select(idx)
                    await asyncio.sleep(0.1)
                    logger.debug("ComboBox selected", control_id=control_id, value=item)
                    return True

            # 2순위: 대상 값이 포함된 아이템 매칭 (예: "E" in "E:\\")
            for idx, item, normalized in normalized_items:
                if target and target in normalized:
                    combo.select(idx)
                    await asyncio.sleep(0.1)
                    logger.debug(
                        "ComboBox selected (partial)",
                        control_id=control_id,
                        value=item,
                    )
                    return True

            logger.warning(
                "Item not found in combobox",
                control_id=control_id,
                value=value,
                available=items,
            )
            return False

        except Exception as e:
            logger.error(
                "Failed to select combobox item",
                control_id=control_id,
                value=value,
                error=str(e),
            )
            return False

    async def _set_edit_text(
        self,
        slot_window: SlotWindowManager,
        control_id: int,
        value: str,
    ) -> bool:
        """Set text in edit control.

        Args:
            slot_window: Slot window manager.
            control_id: Control ID (integer for win32 backend).
            value: Text value to set.

        Returns:
            Success status.
        """
        try:
            edit = slot_window.find_control(control_id=control_id, class_name="Edit")
            if edit is None:
                logger.error("Edit control not found", control_id=control_id)
                return False

            edit.set_edit_text(value)
            await asyncio.sleep(0.1)
            logger.debug("Edit text set", control_id=control_id, value=value)
            return True

        except Exception as e:
            logger.error(
                "Failed to set edit text",
                control_id=control_id,
                value=value,
                error=str(e),
            )
            return False

    async def _click_button(
        self,
        slot_window: SlotWindowManager,
        control_id: int,
    ) -> bool:
        """Click button by control ID.

        Uses pywinauto's click() method which matches AIO_USB_TEST_MACRO behavior.

        Args:
            slot_window: Slot window manager.
            control_id: Control ID (integer for win32 backend).

        Returns:
            Success status.
        """
        try:
            button = slot_window.find_control(
                control_id=control_id, class_name="Button"
            )
            if button is None:
                logger.error("Button not found", control_id=control_id)
                return False

            # 버튼 활성화 상태 확인
            if not button.is_enabled():
                logger.error(
                    "Button is disabled",
                    control_id=control_id,
                    button_text=button.window_text()
                    if hasattr(button, "window_text")
                    else "unknown",
                )
                return False

            button.click()
            await asyncio.sleep(0.3)
            logger.debug("Button clicked", control_id=control_id)
            return True

        except Exception as e:
            logger.error(
                "Failed to click button",
                control_id=control_id,
                error=str(e) if str(e) else type(e).__name__,
            )
            return False

    async def _get_status_text(self, slot_window: SlotWindowManager) -> str:
        """Get current status text from UI.

        Args:
            slot_window: Slot window manager.

        Returns:
            Status text (e.g., "IDLE", "Test", "Pass", "Fail").
        """
        try:
            status = slot_window.find_control(
                control_id=MFCControlId.TXT_STATUS, class_name="Static"
            )
            if status is None:
                return "UNKNOWN"
            return status.window_text()
        except Exception:
            return "UNKNOWN"

    async def _uncheck_ignore_fail(self, slot_window: SlotWindowManager) -> None:
        """Uncheck 'Ignore Fail' checkbox if checked.

        This must be called before every test to ensure proper failure detection.
        Matching AIO_USB_TEST_MACRO behavior (ignore_fail_uncheck).

        Args:
            slot_window: Slot window manager.
        """
        try:
            # Control ID 방식으로 시도
            checkbox = slot_window.find_control(
                control_id=MFCControlId.CHK_IGNORE_FAIL,
                class_name="Button",
            )

            # Control ID로 못 찾으면 Best Match 이름으로 시도
            if checkbox is None:
                checkbox = slot_window.get_control_by_name("Ignore FailCheckBox")

            if checkbox is None:
                checkbox = slot_window.get_control_by_name("CheckBox2")

            if checkbox is None:
                logger.warning("Ignore Fail checkbox not found")
                return

            # 체크박스가 체크되어 있으면 해제
            try:
                # pywinauto CheckBox 컨트롤 - get_check_state() 메서드 사용
                check_state = checkbox.get_check_state()
                if check_state == 1:  # 1 = Checked
                    checkbox.uncheck()
                    logger.info("Ignore Fail checkbox unchecked")
                else:
                    logger.debug("Ignore Fail checkbox already unchecked")
            except AttributeError:
                # get_check_state가 없으면 uncheck() 직접 호출
                checkbox.uncheck()
                logger.info("Ignore Fail checkbox unchecked (direct)")

        except Exception as e:
            logger.warning(
                "Failed to uncheck Ignore Fail checkbox",
                error=str(e),
            )
            # 실패해도 테스트는 계속 진행 (경고만 로그)

    async def _set_capacity(
        self,
        slot_window: SlotWindowManager,
        capacity: TestCapacity,
    ) -> None:
        """Set capacity on slot window.

        Args:
            slot_window: Slot window manager.
            capacity: Test capacity.
        """
        logger.debug("Setting capacity", capacity=str(capacity))
        success = await self._select_combobox_item(
            slot_window,
            MFCControlId.CMB_CAPACITY,
            str(capacity),
        )
        if not success:
            raise RuntimeError(f"Failed to set capacity: {capacity}")

    async def _set_method(
        self,
        slot_window: SlotWindowManager,
        method: TestMethod,
    ) -> None:
        """Set test method on slot window.

        Args:
            slot_window: Slot window manager.
            method: Test method.
        """
        logger.debug("Setting method", method=str(method))
        success = await self._select_combobox_item(
            slot_window,
            MFCControlId.CMB_METHOD,
            str(method),
        )
        if not success:
            raise RuntimeError(f"Failed to set method: {method}")

    async def _set_test_file(
        self,
        slot_window: SlotWindowManager,
        test_file: TestFile,
    ) -> None:
        """Set test file type on slot window.

        Args:
            slot_window: Slot window manager.
            test_file: Test file type (Photo or MP3).
        """
        test_file_value = str(test_file)
        logger.debug("Setting test file", test_file=test_file_value)
        success = await self._select_combobox_item(
            slot_window,
            MFCControlId.CMB_TEST_TYPE,
            test_file_value,
        )
        if not success:
            raise RuntimeError(f"Failed to set test file: {test_file}")

    async def _set_drive(
        self,
        slot_window: SlotWindowManager,
        drive: str,
    ) -> None:
        """Set test drive on slot window.

        Args:
            slot_window: Slot window manager.
            drive: Drive letter (e.g., "E", "E:", "E:\\", "D: - 119.1GB").
        """
        logger.debug("Setting drive", drive=drive)

        # 드라이브 문자만 추출
        # "D: - 119.1GB" -> "D"
        # "E:" -> "E"
        # "E:\\" -> "E"
        # "E" -> "E"
        drive_letter = drive.split(":")[0].split("-")[0].strip().upper()
        if len(drive_letter) > 1:
            drive_letter = drive_letter[0]

        logger.debug("Extracted drive letter", drive_letter=drive_letter)

        # USB Test.exe는 "D:\\" 형식으로 드라이브를 표시
        # 드라이브 문자로 시작하는 항목을 찾아 선택
        success = await self._select_drive_by_letter(
            slot_window,
            drive_letter,
        )
        if not success:
            raise RuntimeError(f"Failed to set drive: {drive}")

    async def _select_drive_by_letter(
        self,
        slot_window: SlotWindowManager,
        drive_letter: str,
    ) -> bool:
        """Select drive in combobox by drive letter.

        Args:
            slot_window: Slot window manager.
            drive_letter: Drive letter (e.g., "D", "E").

        Returns:
            Success status.
        """
        try:
            combo = slot_window.find_control(
                control_id=MFCControlId.CMB_DRIVE,
                class_name="ComboBox",
            )
            if combo is None:
                logger.error("Drive ComboBox not found")
                return False

            items = combo.item_texts()
            logger.debug("Drive ComboBox items", items=items)

            # 드라이브 문자로 시작하는 항목 찾기 (예: "D:\\" 에서 "D" 매칭)
            for idx, item in enumerate(items):
                item_letter = item.rstrip(":\\").upper()
                if item_letter == drive_letter or item.upper().startswith(drive_letter):
                    combo.select(idx)
                    await asyncio.sleep(0.1)
                    logger.debug("Drive selected", drive_letter=drive_letter, item=item)
                    return True

            logger.warning(
                "Drive not found in combobox",
                drive_letter=drive_letter,
                available=items,
            )
            return False

        except Exception as e:
            logger.error(
                "Failed to select drive",
                drive_letter=drive_letter,
                error=str(e),
            )
            return False

    async def _set_loop_count(
        self,
        slot_window: SlotWindowManager,
        loop_count: int,
    ) -> None:
        """Set loop count on slot window.

        Args:
            slot_window: Slot window manager.
            loop_count: Number of loops.
        """
        logger.debug("Setting loop count", loop_count=loop_count)
        success = await self._set_edit_text(
            slot_window,
            MFCControlId.EDT_LOOP,
            str(loop_count),
        )
        if not success:
            raise RuntimeError(f"Failed to set loop count: {loop_count}")

    async def _set_foreground(self, slot_window: SlotWindowManager) -> bool:
        """Set slot window to foreground with retry.

        Multiple USB Test.exe processes may compete for focus.
        Uses retry logic with double-click + set_focus (AIO_USB_TEST_MACRO pattern).

        Args:
            slot_window: Slot window manager.

        Returns:
            True if focus was set successfully.
        """
        max_retries = RetryConfig.FOCUS_MAX_RETRIES
        retry_delay = RetryConfig.FOCUS_RETRY_DELAY

        for attempt in range(max_retries):
            try:
                main_window = slot_window.main_window
                if main_window:
                    # AIO_USB_TEST_MACRO 패턴: click_input(double=True) + set_focus()
                    try:
                        main_window.click_input(double=True)
                    except Exception:
                        pass  # 클릭 실패해도 set_focus 시도

                    main_window.set_focus()
                    await asyncio.sleep(RetryConfig.FOCUS_SETTLE_DELAY)

                    logger.debug(
                        "Window focus set",
                        attempt=attempt + 1,
                        pid=slot_window.pid,
                    )
                    return True
            except Exception as e:
                logger.warning(
                    "Failed to set focus",
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        logger.error("Failed to set window focus after retries")
        return False

    async def _click_button_with_focus(
        self,
        slot_window: SlotWindowManager,
        control_id: int,
        button_name: str = "button",
        max_retries: int = RetryConfig.BUTTON_CLICK_MAX_RETRIES,
        retry_delay: float = RetryConfig.BUTTON_CLICK_RETRY_DELAY,
    ) -> bool:
        """Click button with focus setting and retry logic.

        Ensures window is focused before clicking, with retry on failure.

        Args:
            slot_window: Slot window manager.
            control_id: Control ID of the button.
            button_name: Button name for logging.
            max_retries: Maximum retry attempts.
            retry_delay: Delay between retries in seconds.

        Returns:
            True if button was clicked successfully.
        """
        for attempt in range(max_retries):
            try:
                # 1. 포커스 설정
                await self._set_foreground(slot_window)
                await asyncio.sleep(0.1)

                # 2. 버튼 클릭
                success = await self._click_button(slot_window, control_id)
                if success:
                    logger.debug(
                        f"{button_name} clicked successfully",
                        attempt=attempt + 1,
                    )
                    return True

            except Exception as e:
                logger.warning(
                    f"Failed to click {button_name}",
                    attempt=attempt + 1,
                    error=str(e),
                )

            if attempt < max_retries - 1:
                logger.debug(
                    f"Retrying {button_name} click",
                    next_attempt=attempt + 2,
                    delay=retry_delay,
                )
                await asyncio.sleep(retry_delay)

        return False

    async def _click_start_button(self, slot_window: SlotWindowManager) -> None:
        """Click start button on slot window with retry.

        Tries control_id first, then falls back to attribute access (AIO_USB_TEST_MACRO style).

        Args:
            slot_window: Slot window manager.
        """
        logger.debug("Clicking start button")

        # control_id로 시도
        success = await self._click_button_with_focus(
            slot_window,
            MFCControlId.BTN_TEST,
            button_name="Test",
            # 기본값 사용 (RetryConfig에서 정의)
        )

        if success:
            return

        # 속성 접근 방식 (AIO_USB_TEST_MACRO 방식): dialog.TestButton.click()
        logger.info("Trying Test button by attribute access")
        try:
            await self._set_foreground(slot_window)
            await asyncio.sleep(RetryConfig.FOCUS_SETTLE_DELAY)

            main_window = slot_window.main_window
            if main_window:
                test_btn = getattr(main_window, "TestButton", None)
                if test_btn is not None:
                    test_btn.click()
                    await asyncio.sleep(RetryConfig.CLICK_SETTLE_DELAY)
                    logger.info("Test button clicked via attribute access")
                    return
        except Exception as e:
            logger.warning("Attribute access click failed", error=str(e))

        raise RuntimeError("Failed to click start button after all attempts")

    async def _reset_mfc_state(self, slot_window: SlotWindowManager) -> None:
        """Reset MFC state to enable controls (only when in Pass state).

        When MFC is in Pass state, ComboBox controls are disabled.
        Clicking Contact button resets the state and enables controls.

        IMPORTANT: Only reset when in Pass state!
        - Initial run: Settings → Contact → Test (no reset needed)
        - After Pass: Contact (reset) → Settings → Contact → Test

        Drive must be set BEFORE clicking Contact, so we only reset
        when MFC is already in Pass state (previous test completed).

        Args:
            slot_window: Slot window manager.
        """
        try:
            # MFC 상태 확인 (Button6 = Pass/Idle/Test/Fail/Stop)
            state_btn = slot_window.get_control_by_name("Button6")
            if not state_btn:
                logger.debug("State button not found, skipping reset")
                return

            status_text = state_btn.window_text()
            logger.debug("Current MFC state", status_text=status_text)

            # Pass 상태일 때만 Contact 눌러서 리셋
            # (초기 Idle 상태에서는 드라이브 설정 전에 Contact 누르면 안 됨)
            if status_text and "Pass" in status_text:
                button = slot_window.find_control(
                    control_id=MFCControlId.BTN_CONTACT,
                    class_name="Button",
                )

                if button is not None and button.is_enabled():
                    await self._set_foreground(slot_window)
                    await asyncio.sleep(RetryConfig.FOCUS_SETTLE_DELAY)
                    button.click()
                    await asyncio.sleep(0.5)  # 상태 변경 대기
                    logger.info("MFC state reset via Contact button (was Pass state)")
                else:
                    logger.debug("Contact button not enabled in Pass state")
            else:
                logger.debug(
                    "MFC not in Pass state, skipping reset",
                    status_text=status_text,
                )

        except Exception as e:
            logger.warning("MFC state reset failed (non-fatal)", error=str(e))
            # 실패해도 계속 진행 (컨트롤이 이미 활성화 상태일 수 있음)

    async def _click_contact_button(self, slot_window: SlotWindowManager) -> None:
        """Click contact button on slot window with retry.

        Contact button initializes environment variables and drive recognition.
        Must be clicked before Test button.

        Args:
            slot_window: Slot window manager.
        """
        logger.debug("Clicking contact button")

        # control_id로 시도
        success = await self._click_button_with_focus(
            slot_window,
            MFCControlId.BTN_CONTACT,
            button_name="Contact",
            # 기본값 사용 (RetryConfig에서 정의)
        )

        if success:
            return

        # 속성 접근 방식 (AIO_USB_TEST_MACRO 방식): dialog.ContactButton.click()
        logger.info("Trying Contact button by attribute access")
        try:
            await self._set_foreground(slot_window)
            await asyncio.sleep(RetryConfig.FOCUS_SETTLE_DELAY)

            main_window = slot_window.main_window
            if main_window:
                contact_btn = getattr(main_window, "ContactButton", None)
                if contact_btn is not None:
                    contact_btn.click()
                    await asyncio.sleep(RetryConfig.CLICK_SETTLE_DELAY)
                    logger.info("Contact button clicked via attribute access")
                    return
        except Exception as e:
            logger.warning("Attribute access click failed", error=str(e))

        raise RuntimeError("Failed to click contact button after all attempts")

    async def _wait_for_contact_button_enabled(
        self,
        slot_window: SlotWindowManager,
        timeout: float = TimeoutConfig.CONTACT_BUTTON_TIMEOUT,
    ) -> None:
        """Wait for Contact button to become enabled.

        Used in batch continuation to ensure previous test is fully complete.
        Sets foreground focus only when button becomes enabled (경합 방지).

        Args:
            slot_window: Slot window manager.
            timeout: Maximum wait time in seconds.

        Raises:
            RuntimeError: If Contact button is not enabled within timeout.
        """
        logger.debug("Waiting for Contact button to be enabled", timeout=timeout)
        start_time = asyncio.get_event_loop().time()
        check_interval = TimeoutConfig.BUTTON_CHECK_INTERVAL

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # 포커스 설정 없이 버튼 상태만 확인 (경합 방지)
                button = slot_window.find_control(
                    control_id=MFCControlId.BTN_CONTACT,
                    class_name="Button",
                )
                if button is not None and button.is_enabled():
                    # 버튼이 활성화되면 포커스 설정 후 반환
                    await self._set_foreground(slot_window)
                    logger.debug(
                        "Contact button is enabled",
                        elapsed=f"{asyncio.get_event_loop().time() - start_time:.1f}s",
                    )
                    return
            except Exception as e:
                logger.debug("Error checking Contact button", error=str(e))

            await asyncio.sleep(check_interval)

        raise RuntimeError(
            f"Contact button not enabled within {timeout} seconds. "
            "Previous test may not have completed."
        )

    async def _wait_for_test_button_enabled(
        self,
        slot_window: SlotWindowManager,
        timeout: float = TimeoutConfig.TEST_BUTTON_TIMEOUT,
    ) -> None:
        """Wait for Test button to become enabled after Contact.

        Args:
            slot_window: Slot window manager.
            timeout: Maximum wait time in seconds.

        Raises:
            RuntimeError: If Test button is not enabled within timeout.
        """
        logger.debug("Waiting for Test button to be enabled", timeout=timeout)
        start_time = asyncio.get_event_loop().time()
        check_interval = TimeoutConfig.BUTTON_CHECK_INTERVAL

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # 포커스 설정 없이 버튼 상태만 확인 (경합 방지)
                button = slot_window.find_control(
                    control_id=MFCControlId.BTN_TEST,
                    class_name="Button",
                )
                if button is not None and button.is_enabled():
                    logger.debug(
                        "Test button is now enabled",
                        elapsed=f"{asyncio.get_event_loop().time() - start_time:.1f}s",
                    )
                    return
            except Exception as e:
                logger.debug("Error checking Test button", error=str(e))

            await asyncio.sleep(check_interval)

        raise RuntimeError(
            f"Test button not enabled within {timeout} seconds. "
            "Contact test may have failed or drive not recognized."
        )

    async def _click_stop_button(self, slot_window: SlotWindowManager) -> None:
        """Click stop button on slot window.

        Args:
            slot_window: Slot window manager.
        """
        logger.debug("Clicking stop button")
        success = await self._click_button(slot_window, MFCControlId.BTN_STOP)
        if not success:
            raise RuntimeError("Failed to click stop button")

    def list_controls(self, slot_idx: int) -> list[dict]:
        """Get UI control list for a slot (for debugging).

        Args:
            slot_idx: Slot index.

        Returns:
            List of control information.
        """
        slot_window = self._window_manager.get_slot_window(slot_idx)
        if slot_window:
            return slot_window.list_controls()
        return []
