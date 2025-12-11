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
    TestMethod,
    TestType,
    ProcessState,
    SlotConfig,
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
            self._slot_states[slot_idx].error_message = (
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
            capacity=config.capacity,
            method=config.method,
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

            # TODO: 실제 MFC 컨트롤 조작 구현
            # 1. 용량 설정
            # 2. 테스트 방식 설정
            # 3. 시작 버튼 클릭

            await self._set_capacity(slot_window, config.capacity)
            await self._set_method(slot_window, config.method)
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
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(callback, interval)
        )
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
                    self._slot_states[slot_idx].error_message = "프로세스 연결이 끊어졌습니다."
                continue

            # TODO: 실제 MFC UI에서 상태 읽기 구현
            # 각 슬롯의 진행률, 상태 등을 읽어 업데이트
            pass

    # ===== Private Helper Methods =====
    # These methods should be implemented according to actual USB Test.exe UI structure.

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
        # TODO: 실제 UI 구조에 맞게 구현
        logger.debug("Setting capacity", capacity=capacity)
        await asyncio.sleep(0.1)

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
        # TODO: 실제 UI 구조에 맞게 구현
        logger.debug("Setting method", method=method)
        await asyncio.sleep(0.1)

    async def _click_start_button(self, slot_window: SlotWindowManager) -> None:
        """Click start button on slot window.

        Args:
            slot_window: Slot window manager.
        """
        # TODO: Implement according to actual UI structure
        logger.debug("Clicking start button")
        await asyncio.sleep(0.1)

    async def _click_stop_button(self, slot_window: SlotWindowManager) -> None:
        """Click stop button on slot window.

        Args:
            slot_window: Slot window manager.
        """
        # TODO: Implement according to actual UI structure
        logger.debug("Clicking stop button")
        await asyncio.sleep(0.1)

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
