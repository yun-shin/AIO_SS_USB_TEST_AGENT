"""MFC Controller.

Main controller responsible for overall USB Test.exe control.
Handles test start, stop, state monitoring, etc.
"""

import asyncio
from typing import Optional

from ..config.settings import get_settings
from ..config.constants import (
    TestCapacity,
    TestMethod,
    TestType,
    ProcessState,
    SlotConfig,
)
from ..domain.models.test_config import TestConfig
from ..domain.models.test_state import SlotStatus, TestState
from ..utils.logging import get_logger
from .window_manager import WindowManager
from .control_wrapper import ControlWrapper

logger = get_logger(__name__)


class MFCController:
    """USB Test.exe MFC controller.

    Interacts with MFC application to control tests.

    Attributes:
        _window_manager: Window manager.
        _slot_states: State per slot.
        _is_monitoring: State monitoring activation status.
    """

    def __init__(self, exe_path: Optional[str] = None) -> None:
        """Initialize controller.

        Args:
            exe_path: USB Test.exe path (uses settings if None).
        """
        settings = get_settings()
        self._exe_path = exe_path or settings.usb_test_exe_path
        self._window_manager = WindowManager(self._exe_path)
        self._slot_states: dict[int, TestState] = {}
        self._is_monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

        # 슬롯 상태 초기화
        for slot_idx in range(SlotConfig.MAX_SLOTS):
            self._slot_states[slot_idx] = TestState(slot_idx=slot_idx)

    @property
    def is_connected(self) -> bool:
        """USB Test.exe connection status."""
        return self._window_manager.is_connected

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

    async def connect(self) -> bool:
        """Connect to USB Test.exe.

        Returns:
            Connection success status.
        """
        logger.info("Connecting to USB Test.exe", exe_path=self._exe_path)
        return await self._window_manager.connect()

    async def start(self) -> bool:
        """Start and connect to USB Test.exe.

        Returns:
            Connection success status.
        """
        logger.info("Starting USB Test.exe", exe_path=self._exe_path)
        return await self._window_manager.start_and_connect()

    def disconnect(self) -> None:
        """Disconnect."""
        self.stop_monitoring()
        self._window_manager.disconnect()
        logger.info("Disconnected from USB Test.exe")

    async def start_test(
        self,
        slot_idx: int,
        config: TestConfig,
    ) -> bool:
        """Start test.

        Args:
            slot_idx: Slot index.
            config: Test configuration.

        Returns:
            Start success status.
        """
        if not self.is_connected:
            logger.error("Not connected to USB Test.exe")
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
            # TODO: 실제 MFC 컨트롤 조작 구현
            # 1. 슬롯 선택
            # 2. 용량 설정
            # 3. 테스트 방식 설정
            # 4. 시작 버튼 클릭

            # 임시 로직 (실제 UI 구조 분석 후 대체)
            await self._select_slot(slot_idx)
            await self._set_capacity(config.capacity)
            await self._set_method(config.method)
            await self._click_start_button()

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
        """Stop test.

        Args:
            slot_idx: Slot index.

        Returns:
            Stop success status.
        """
        if not self.is_connected:
            logger.error("Not connected to USB Test.exe")
            return False

        logger.info("Stopping test", slot_idx=slot_idx)

        state = self._slot_states.get(slot_idx)
        if not state:
            return False

        try:
            # TODO: 실제 MFC 컨트롤 조작 구현
            # 1. 슬롯 선택
            # 2. 중지 버튼 클릭

            await self._select_slot(slot_idx)
            await self._click_stop_button()

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
                await self._update_all_slot_states()

                if callback:
                    for slot_idx, state in self._slot_states.items():
                        await callback(slot_idx, state)

            except Exception as e:
                logger.error("Monitoring error", error=str(e))

            await asyncio.sleep(interval)

    async def _update_all_slot_states(self) -> None:
        """Update all slot states."""
        if not self.is_connected:
            return

        # TODO: 실제 MFC UI에서 상태 읽기 구현
        # 각 슬롯의 진행률, 상태 등을 읽어 업데이트
        pass

    # ===== Private Helper Methods =====
    # These methods should be implemented according to actual USB Test.exe UI structure.

    async def _select_slot(self, slot_idx: int) -> None:
        """Select slot.

        Args:
            slot_idx: Slot index.
        """
        # TODO: 실제 UI 구조에 맞게 구현
        logger.debug("Selecting slot", slot_idx=slot_idx)
        await asyncio.sleep(0.1)

    async def _set_capacity(self, capacity: TestCapacity) -> None:
        """Set capacity.

        Args:
            capacity: Test capacity.
        """
        # TODO: 실제 UI 구조에 맞게 구현
        logger.debug("Setting capacity", capacity=capacity)
        await asyncio.sleep(0.1)

    async def _set_method(self, method: TestMethod) -> None:
        """Set test method.

        Args:
            method: Test method.
        """
        # TODO: 실제 UI 구조에 맞게 구현
        logger.debug("Setting method", method=method)
        await asyncio.sleep(0.1)

    async def _click_start_button(self) -> None:
        """Click start button."""
        # TODO: Implement according to actual UI structure
        logger.debug("Clicking start button")
        await asyncio.sleep(0.1)

    async def _click_stop_button(self) -> None:
        """Click stop button."""
        # TODO: Implement according to actual UI structure
        logger.debug("Clicking stop button")
        await asyncio.sleep(0.1)

    def list_controls(self) -> list[dict]:
        """Get UI control list (for debugging).

        Returns:
            List of control information.
        """
        return self._window_manager.list_controls()
