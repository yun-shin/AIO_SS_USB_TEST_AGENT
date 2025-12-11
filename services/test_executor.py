"""Test Executor Service.

Service responsible for executing USB tests.
All external dependencies are injected via Protocol.
"""

import uuid
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable
from enum import Enum

from core.protocols import (
    IWindowFinder,
    IWindowHandle,
    IControlHandle,
    IStateStore,
    IClock,
    ILogger,
)
from core.exceptions import (
    WindowNotFoundError,
    ControlNotFoundError,
    TestStartError,
    TestStopError,
    TestExecutionError,
)


class TestPhase(str, Enum):
    """Test phase."""

    IDLE = "idle"
    PREPARING = "preparing"
    CONFIGURING = "configuring"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class TestRequest:
    """Test execution request.

    Attributes:
        slot_idx: Slot index.
        test_name: Test name.
        capacity: Capacity (e.g., "1TB").
        method: Test method (e.g., "AUTO").
        test_type: Test type (e.g., "NORMAL").
    """

    slot_idx: int
    test_name: str
    capacity: str = "1TB"
    method: str = "AUTO"
    test_type: str = "NORMAL"


@dataclass
class TestResult:
    """Test result.

    Attributes:
        test_id: Test ID.
        slot_idx: Slot index.
        success: Success status.
        phase: Final phase.
        error_message: Error message.
        duration_seconds: Execution time in seconds.
    """

    test_id: str
    slot_idx: int
    success: bool
    phase: TestPhase
    error_message: Optional[str] = None
    duration_seconds: float = 0.0


class TestExecutor:
    """Test execution service.

    Controls USB Test.exe to execute tests.
    All dependencies are injected via constructor.

    Example:
        ```python
        # Production
        executor = TestExecutor(
            window_finder=PywinautoWindowFinder(),
            state_store=InMemoryStateStore(),
            clock=SystemClock(),
            logger=get_logger(__name__),
        )

        # Test
        executor = TestExecutor(
            window_finder=FakeWindowFinder(),
            state_store=FakeStateStore(),
            clock=FakeClock(),
            logger=NullLogger(),
        )
        ```
    """

    def __init__(
        self,
        window_finder: IWindowFinder,
        state_store: IStateStore,
        clock: IClock,
        logger: ILogger,
        exe_path: str = "USB Test.exe",
        window_title_pattern: str = ".*USB Test.*",
    ) -> None:
        """Initialize service.

        Args:
            window_finder: Window finder.
            state_store: State store.
            clock: Clock.
            logger: Logger.
            exe_path: USB Test.exe path.
            window_title_pattern: Window title pattern.
        """
        self._window_finder = window_finder
        self._state_store = state_store
        self._clock = clock
        self._logger = logger
        self._exe_path = exe_path
        self._window_title_pattern = window_title_pattern

        # 상태
        self._main_window: Optional[IWindowHandle] = None
        self._running_tests: dict[int, str] = {}  # slot_idx -> test_id

        # 콜백
        self._on_state_change: Optional[
            Callable[[int, TestPhase], Awaitable[None]]
        ] = None

    def set_state_change_callback(
        self,
        callback: Callable[[int, TestPhase], Awaitable[None]],
    ) -> None:
        """Set state change callback.

        Args:
            callback: Callback function (slot_idx, phase).
        """
        self._on_state_change = callback

    async def connect(self, timeout: float = 30.0) -> bool:
        """Connect to USB Test.exe.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            Connection success status.
        """
        self._logger.info("Connecting to USB Test.exe", exe_path=self._exe_path)

        window = await self._window_finder.find_window(
            title_re=self._window_title_pattern,
            timeout=timeout,
        )

        if window is None:
            self._logger.error(
                "Window not found",
                pattern=self._window_title_pattern,
                timeout=timeout,
            )
            return False

        self._main_window = window
        self._logger.info("Connected to USB Test.exe", title=window.title)
        return True

    async def disconnect(self) -> None:
        """Disconnect."""
        self._main_window = None
        self._logger.info("Disconnected from USB Test.exe")

    @property
    def is_connected(self) -> bool:
        """Connection status."""
        return self._main_window is not None and self._main_window.exists

    async def start_test(self, request: TestRequest) -> TestResult:
        """Start test.

        Args:
            request: Test request.

        Returns:
            Test result.

        Raises:
            WindowNotFoundError: Window not connected.
            TestStartError: Test start failed.
        """
        test_id = str(uuid.uuid4())
        slot_idx = request.slot_idx
        start_time = self._clock.monotonic()

        self._logger.info(
            "Starting test",
            test_id=test_id,
            slot_idx=slot_idx,
            test_name=request.test_name,
        )

        if not self.is_connected:
            raise WindowNotFoundError(
                "Not connected to USB Test.exe",
                title_pattern=self._window_title_pattern,
            )

        try:
            # 상태 업데이트: PREPARING
            await self._update_state(slot_idx, TestPhase.PREPARING, test_id)

            # 슬롯 선택
            await self._select_slot(slot_idx)

            # 상태 업데이트: CONFIGURING
            await self._update_state(slot_idx, TestPhase.CONFIGURING, test_id)

            # 설정 적용
            await self._configure_test(request)

            # 상태 업데이트: RUNNING
            await self._update_state(slot_idx, TestPhase.RUNNING, test_id)

            # 시작 버튼 클릭
            await self._click_start_button()

            self._running_tests[slot_idx] = test_id

            duration = self._clock.monotonic() - start_time
            self._logger.info(
                "Test started successfully",
                test_id=test_id,
                slot_idx=slot_idx,
                duration=duration,
            )

            return TestResult(
                test_id=test_id,
                slot_idx=slot_idx,
                success=True,
                phase=TestPhase.RUNNING,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = self._clock.monotonic() - start_time
            await self._update_state(slot_idx, TestPhase.FAILED, test_id, str(e))

            self._logger.error(
                "Test start failed",
                test_id=test_id,
                slot_idx=slot_idx,
                error=str(e),
            )

            raise TestStartError(
                f"Failed to start test: {e}",
                slot_idx=slot_idx,
                phase="start",
                cause=e if isinstance(e, Exception) else None,
            )

    async def stop_test(self, slot_idx: int) -> TestResult:
        """Stop test.

        Args:
            slot_idx: Slot index.

        Returns:
            Test result.
        """
        test_id = self._running_tests.get(slot_idx, "unknown")
        start_time = self._clock.monotonic()

        self._logger.info("Stopping test", test_id=test_id, slot_idx=slot_idx)

        if not self.is_connected:
            raise WindowNotFoundError(
                "Not connected to USB Test.exe",
                title_pattern=self._window_title_pattern,
            )

        try:
            # 슬롯 선택
            await self._select_slot(slot_idx)

            # 중지 버튼 클릭
            await self._click_stop_button()

            # 상태 업데이트
            await self._update_state(slot_idx, TestPhase.STOPPED, test_id)

            self._running_tests.pop(slot_idx, None)

            duration = self._clock.monotonic() - start_time
            self._logger.info(
                "Test stopped",
                test_id=test_id,
                slot_idx=slot_idx,
                duration=duration,
            )

            return TestResult(
                test_id=test_id,
                slot_idx=slot_idx,
                success=True,
                phase=TestPhase.STOPPED,
                duration_seconds=duration,
            )

        except Exception as e:
            self._logger.error(
                "Test stop failed",
                test_id=test_id,
                slot_idx=slot_idx,
                error=str(e),
            )

            raise TestStopError(
                f"Failed to stop test: {e}",
                slot_idx=slot_idx,
                cause=e if isinstance(e, Exception) else None,
            )

    async def _update_state(
        self,
        slot_idx: int,
        phase: TestPhase,
        test_id: str,
        error: Optional[str] = None,
    ) -> None:
        """Update state.

        Args:
            slot_idx: Slot index.
            phase: Test phase.
            test_id: Test ID.
            error: Error message.
        """
        state = {
            "status": phase.value,
            "test_id": test_id,
            "current_phase": phase.value,
            "error_message": error,
        }
        self._state_store.set_slot_state(slot_idx, state)

        if self._on_state_change:
            await self._on_state_change(slot_idx, phase)

    # ===== Private Control Methods =====
    # These methods should be implemented according to actual UI.

    async def _select_slot(self, slot_idx: int) -> None:
        """Select slot.

        Args:
            slot_idx: Slot index.
        """
        self._logger.debug("Selecting slot", slot_idx=slot_idx)
        # TODO: 실제 구현
        await self._clock.sleep(0.1)

    async def _configure_test(self, request: TestRequest) -> None:
        """Configure test.

        Args:
            request: Test request.
        """
        self._logger.debug(
            "Configuring test",
            capacity=request.capacity,
            method=request.method,
        )
        # TODO: 실제 구현
        await self._clock.sleep(0.1)

    async def _click_start_button(self) -> None:
        """Click start button."""
        self._logger.debug("Clicking start button")
        # TODO: 실제 구현
        await self._clock.sleep(0.1)

    async def _click_stop_button(self) -> None:
        """Click stop button."""
        self._logger.debug("Clicking stop button")
        # TODO: 실제 구현
        await self._clock.sleep(0.1)
