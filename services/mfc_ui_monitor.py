"""MFC UI Monitor Service.

Service that monitors USB Test.exe MFC UI state.
Periodically polls the UI to detect state changes made by user or test progress.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config.constants import (
    MFCControlId,
    ProcessState,
    SlotConfig,
    TestPhase,
)
from controller.window_manager import SlotWindowManager, WindowManager
from core.protocols import IClock, ILogger


@dataclass
class MFCUIState:
    """MFC UI state snapshot.

    Attributes:
        slot_idx: Slot index.
        process_state: USB Test process state (IDLE, TEST, PASS, FAIL, etc.).
        test_phase: Current test phase.
        current_loop: Current loop number.
        total_loop: Total loop count.
        status_text: Raw status text from UI.
        progress_text: Raw progress text from UI.
        is_test_button_enabled: Test button enabled state.
        is_stop_button_enabled: Stop button enabled state.
        timestamp: Snapshot timestamp.
    """

    slot_idx: int
    process_state: ProcessState = ProcessState.IDLE
    test_phase: TestPhase = TestPhase.IDLE
    current_loop: int = 0
    total_loop: int = 0
    status_text: str = ""
    progress_text: str = ""
    is_test_button_enabled: bool = False
    is_stop_button_enabled: bool = False
    timestamp: datetime = None

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage.

        Returns:
            Progress percentage (0.0 ~ 100.0).
        """
        if self.total_loop <= 0:
            return 0.0
        return min(100.0, (self.current_loop / self.total_loop) * 100.0)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "slot_idx": self.slot_idx,
            "process_state": self.process_state.value,
            "process_state_name": self.process_state.name,
            "test_phase": self.test_phase.value,
            "test_phase_name": self.test_phase.name,
            "current_loop": self.current_loop,
            "total_loop": self.total_loop,
            "progress_percent": self.progress_percent,
            "status_text": self.status_text,
            "progress_text": self.progress_text,
            "is_test_button_enabled": self.is_test_button_enabled,
            "is_stop_button_enabled": self.is_stop_button_enabled,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class UIStateChange:
    """UI state change event.

    Attributes:
        slot_idx: Slot index.
        previous_state: Previous UI state.
        current_state: Current UI state.
        changed_fields: List of changed field names.
    """

    slot_idx: int
    previous_state: MFCUIState | None
    current_state: MFCUIState
    changed_fields: list[str]


class MFCUIMonitor:
    """MFC UI monitoring service.

    Monitors USB Test.exe UI state by polling at regular intervals.
    Detects changes in process state, loop progress, and button states.
    Uses lazy polling (longer interval) to reduce resource usage.

    Example:
        ```python
        monitor = MFCUIMonitor(
            window_manager=window_manager,
            clock=system_clock,
            logger=logger,
        )

        async def on_change(change: UIStateChange) -> None:
            print(f"UI changed: {change.changed_fields}")

        monitor.set_change_callback(on_change)
        await monitor.start(interval=10.0)  # Lazy polling every 10 seconds
        ```
    """

    def __init__(
        self,
        window_manager: WindowManager,
        clock: IClock,
        logger: ILogger,
        max_slots: int = SlotConfig.MAX_SLOTS,
    ) -> None:
        """Initialize MFC UI monitor.

        Args:
            window_manager: Window manager.
            clock: Clock interface.
            logger: Logger interface.
            max_slots: Maximum number of slots.
        """
        self._window_manager = window_manager
        self._clock = clock
        self._logger = logger
        self._max_slots = max_slots

        # 상태
        self._is_running = False
        self._monitor_task: asyncio.Task | None = None

        # 이전 상태 저장
        self._previous_states: dict[int, MFCUIState] = {}

        # 모니터링 대상 슬롯
        self._monitored_slots: set[int] = set()

        # 콜백
        self._on_change: Callable[[UIStateChange], Awaitable[None]] | None = None
        self._on_poll: Callable[[MFCUIState], Awaitable[None]] | None = None
        self._on_test_completed: Callable[[int, ProcessState], Awaitable[None]] | None = None
        self._on_user_intervention: Callable[[int, str], Awaitable[None]] | None = None

    def set_change_callback(
        self,
        callback: Callable[[UIStateChange], Awaitable[None]],
    ) -> None:
        """Set state change callback.

        Args:
            callback: Callback function.
        """
        self._on_change = callback

    def set_poll_callback(
        self,
        callback: Callable[[MFCUIState], Awaitable[None]],
    ) -> None:
        """Set periodic poll callback.

        Called on every poll regardless of state change.
        Use this for real-time status updates.

        Args:
            callback: Callback function (state).
        """
        self._on_poll = callback

    def set_test_completed_callback(
        self,
        callback: Callable[[int, ProcessState], Awaitable[None]],
    ) -> None:
        """Set test completed callback.

        Called when test transitions to PASS, FAIL, or STOP state.

        Args:
            callback: Callback function (slot_idx, final_state).
        """
        self._on_test_completed = callback

    def set_user_intervention_callback(
        self,
        callback: Callable[[int, str], Awaitable[None]],
    ) -> None:
        """Set user intervention callback.

        Called when user appears to have manually interacted with the UI.

        Args:
            callback: Callback function (slot_idx, description).
        """
        self._on_user_intervention = callback

    def add_monitored_slot(self, slot_idx: int) -> None:
        """Add slot to monitoring.

        Args:
            slot_idx: Slot index.
        """
        self._monitored_slots.add(slot_idx)
        self._logger.info("Added slot to UI monitoring", slot_idx=slot_idx)

    def remove_monitored_slot(self, slot_idx: int) -> None:
        """Remove slot from monitoring.

        Args:
            slot_idx: Slot index.
        """
        self._monitored_slots.discard(slot_idx)
        self._previous_states.pop(slot_idx, None)
        self._logger.info("Removed slot from UI monitoring", slot_idx=slot_idx)

    @property
    def is_running(self) -> bool:
        """Monitoring running status."""
        return self._is_running

    async def start(self, interval: float = 10.0) -> None:
        """Start monitoring.

        Args:
            interval: Polling interval in seconds (default: 10s for lazy polling).
        """
        if self._is_running:
            self._logger.warning("MFC UI monitor already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        self._logger.info("MFC UI monitor started", interval=interval)

    async def stop(self) -> None:
        """Stop monitoring."""
        self._is_running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        self._logger.info("MFC UI monitor stopped")

    async def _monitor_loop(self, interval: float) -> None:
        """Monitoring loop.

        Args:
            interval: Polling interval in seconds.
        """
        while self._is_running:
            try:
                await self._poll_all_slots()
            except Exception as e:
                self._logger.error("MFC UI monitor error", error=str(e))

            await self._clock.sleep(interval)

    async def _poll_all_slots(self) -> None:
        """Poll all monitored slots."""
        for slot_idx in list(self._monitored_slots):
            try:
                await self._poll_slot(slot_idx)
            except Exception as e:
                self._logger.error(
                    "Failed to poll slot UI",
                    slot_idx=slot_idx,
                    error=str(e),
                )

    async def _poll_slot(self, slot_idx: int) -> None:
        """Poll single slot UI state.

        Args:
            slot_idx: Slot index.
        """
        slot_window = self._window_manager.get_slot_window(slot_idx)
        if not slot_window or not slot_window.is_connected:
            return

        # 현재 UI 상태 읽기
        current_state = await self._read_ui_state(slot_idx, slot_window)

        # 매 폴링마다 상태 전송 (변경 여부와 무관)
        if self._on_poll:
            await self._on_poll(current_state)

        # 이전 상태와 비교
        previous_state = self._previous_states.get(slot_idx)
        changed_fields = self._detect_changes(previous_state, current_state)

        if changed_fields:
            # 변경 이벤트 발생
            change = UIStateChange(
                slot_idx=slot_idx,
                previous_state=previous_state,
                current_state=current_state,
                changed_fields=changed_fields,
            )

            # 콜백 호출
            if self._on_change:
                await self._on_change(change)

            # 테스트 완료 감지 (두 가지 조건)
            # 1. Fail 상태로 전환 (실패)
            # 2. Stop 상태로 전환 (중지)
            # 3. 루프 완료 (current_loop >= total_loop이고 Idle 상태)
            await self._check_test_completion(
                slot_idx,
                previous_state,
                current_state,
                changed_fields,
            )

            # 사용자 개입 감지
            await self._check_user_intervention(
                slot_idx,
                previous_state,
                current_state,
                changed_fields,
            )

        # 상태 저장
        self._previous_states[slot_idx] = current_state

    async def _read_ui_state(
        self,
        slot_idx: int,
        slot_window: SlotWindowManager,
    ) -> MFCUIState:
        """Read current UI state from MFC window.

        Args:
            slot_idx: Slot index.
            slot_window: Slot window manager.

        Returns:
            Current MFC UI state.
        """
        state = MFCUIState(slot_idx=slot_idx)

        try:
            # 상태 버튼에서 상태 텍스트 읽기 (Button6 = Pass/Idle/Test/Fail/Stop)
            # AIO_USB_TEST_MACRO와 동일한 방식 (best match 이름 사용)
            state_btn = slot_window.get_control_by_name("Button6")
            if state_btn:
                state.status_text = state_btn.window_text()
                state.process_state = ProcessState.from_text(state.status_text)
            else:
                # Fallback: Static 컨트롤에서 복합 텍스트 읽기 (예: '10/10 IDLE')
                status_ctrl = slot_window.find_control(
                    control_id=MFCControlId.TXT_STATUS,
                    class_name="Static",
                )
                if status_ctrl:
                    state.status_text = status_ctrl.window_text()
                    state.process_state = ProcessState.from_text(state.status_text)

            # 진행 상황 텍스트 읽기 (Static = '4/10  File Copy 35/88' 형식)
            # 형식: '현재루프/총루프  테스트단계 파일진행'
            progress_ctrl = slot_window.get_control_by_name("Static")
            if progress_ctrl:
                state.progress_text = progress_ctrl.window_text()
                state.test_phase = TestPhase.from_text(state.progress_text)

                # 진행 텍스트에서 루프 정보 파싱 (예: '4/10  File Copy 35/88')
                self._parse_progress_text(state)

            # 전체 루프 읽기 (Loop Edit 필드)
            total_loop_ctrl = slot_window.find_control(
                control_id=MFCControlId.EDT_LOOP,
                class_name="Edit",
            )
            if total_loop_ctrl:
                try:
                    state.total_loop = int(total_loop_ctrl.window_text() or "0")
                except ValueError:
                    state.total_loop = 0

            # Test 버튼 상태
            test_btn = slot_window.find_control(
                control_id=MFCControlId.BTN_TEST,
                class_name="Button",
            )
            if test_btn:
                state.is_test_button_enabled = test_btn.is_enabled()

            # Stop 버튼 상태
            stop_btn = slot_window.find_control(
                control_id=MFCControlId.BTN_STOP,
                class_name="Button",
            )
            if stop_btn:
                state.is_stop_button_enabled = stop_btn.is_enabled()

        except Exception as e:
            self._logger.warning(
                "Error reading UI state",
                slot_idx=slot_idx,
                error=str(e),
            )

        state.timestamp = self._clock.now()
        return state

    def _parse_progress_text(self, state: MFCUIState) -> None:
        """Parse progress text to extract loop information.

        Format: '현재루프/총루프  테스트단계 파일진행'
        Examples:
            - '4/10  File Copy 35/88' -> current_loop=4
            - '10/10 IDLE' -> current_loop=10

        Args:
            state: MFCUIState to update with parsed values.
        """
        if not state.progress_text:
            return

        import re

        # 패턴: '숫자/숫자' (예: '4/10')
        match = re.match(r"(\d+)/(\d+)", state.progress_text.strip())
        if match:
            try:
                state.current_loop = int(match.group(1))
                # total_loop는 EDT_LOOP에서 읽으므로 여기서는 설정하지 않음
                # 단, EDT_LOOP가 없으면 여기서 설정
                if state.total_loop == 0:
                    state.total_loop = int(match.group(2))
            except ValueError:
                pass

    def _detect_changes(
        self,
        previous: MFCUIState | None,
        current: MFCUIState,
    ) -> list[str]:
        """Detect changed fields between states.

        Args:
            previous: Previous state.
            current: Current state.

        Returns:
            List of changed field names.
        """
        if previous is None:
            return []  # 최초 폴링은 변경으로 처리하지 않음

        changed = []

        if previous.process_state != current.process_state:
            changed.append("process_state")

        if previous.current_loop != current.current_loop:
            changed.append("current_loop")

        if previous.total_loop != current.total_loop:
            changed.append("total_loop")

        if previous.status_text != current.status_text:
            changed.append("status_text")

        if previous.is_test_button_enabled != current.is_test_button_enabled:
            changed.append("is_test_button_enabled")

        if previous.is_stop_button_enabled != current.is_stop_button_enabled:
            changed.append("is_stop_button_enabled")

        return changed

    async def _check_test_completion(
        self,
        slot_idx: int,
        previous_state: MFCUIState | None,
        current_state: MFCUIState,
        changed_fields: list[str],
    ) -> None:
        """Check if test has completed.

        Test completion conditions:
        1. Fail 상태로 전환 -> 테스트 실패
        2. Stop 상태로 전환 -> 테스트 중지
        3. 루프 완료: current_loop >= total_loop이고 Idle 상태 -> 테스트 성공

        Note: Pass 상태는 "테스트 진행 중 (성공적으로 진행)"을 의미하며,
              완료가 아닙니다.

        Args:
            slot_idx: Slot index.
            previous_state: Previous MFC UI state.
            current_state: Current MFC UI state.
            changed_fields: List of changed fields.
        """
        if not previous_state:
            return

        prev_process = previous_state.process_state
        curr_process = current_state.process_state

        # 1. Fail 상태로 전환 -> 테스트 실패
        if curr_process == ProcessState.FAIL and prev_process != ProcessState.FAIL:
            self._logger.info(
                "Test FAILED detected via UI",
                slot_idx=slot_idx,
                final_state=curr_process.name,
            )
            if self._on_test_completed:
                await self._on_test_completed(slot_idx, ProcessState.FAIL)
            return

        # 2. Stop 상태로 전환 -> 테스트 중지
        if curr_process == ProcessState.STOP and prev_process != ProcessState.STOP:
            self._logger.info(
                "Test STOPPED detected via UI",
                slot_idx=slot_idx,
                final_state=curr_process.name,
            )
            if self._on_test_completed:
                await self._on_test_completed(slot_idx, ProcessState.STOP)
            return

        # 3. 루프 완료 감지: Idle 상태이고 current_loop == total_loop 이고 Phase가 IDLE
        # (Pass/Test에서 Idle로 전환되고 루프가 완료된 경우)
        if curr_process == ProcessState.IDLE:
            if (
                current_state.total_loop > 0
                and current_state.current_loop == current_state.total_loop
                and current_state.test_phase == TestPhase.IDLE
            ):
                # 이전에 테스트 중이었는지 확인 (Pass 또는 Test 상태)
                if prev_process in (ProcessState.PASS, ProcessState.TEST):
                    self._logger.info(
                        "Test COMPLETED (loop finished) detected via UI",
                        slot_idx=slot_idx,
                        current_loop=current_state.current_loop,
                        total_loop=current_state.total_loop,
                    )
                    if self._on_test_completed:
                        await self._on_test_completed(slot_idx, ProcessState.PASS)

    async def _check_user_intervention(
        self,
        slot_idx: int,
        previous: MFCUIState | None,
        current: MFCUIState,
        changed_fields: list[str],
    ) -> None:
        """Check for user intervention.

        Args:
            slot_idx: Slot index.
            previous: Previous state.
            current: Current state.
            changed_fields: List of changed fields.
        """
        if not previous or not self._on_user_intervention:
            return

        # 사용자 개입 패턴 감지

        # 1. 테스트 중인데 갑자기 IDLE로 변경 (사용자가 Stop 클릭 후 새로 시작 준비)
        if (
            previous.process_state == ProcessState.TEST
            and current.process_state == ProcessState.IDLE
        ):
            await self._on_user_intervention(
                slot_idx,
                "User may have stopped the test manually",
            )

        # 2. 루프 카운트가 예상치 않게 변경
        if "total_loop" in changed_fields and previous.total_loop != current.total_loop:
            await self._on_user_intervention(
                slot_idx,
                f"Loop count changed: {previous.total_loop} -> {current.total_loop}",
            )

    async def poll_slot_once(self, slot_idx: int) -> MFCUIState | None:
        """Poll a slot once (on-demand).

        Args:
            slot_idx: Slot index.

        Returns:
            Current UI state or None if not connected.
        """
        slot_window = self._window_manager.get_slot_window(slot_idx)
        if not slot_window or not slot_window.is_connected:
            return None

        return await self._read_ui_state(slot_idx, slot_window)

    def get_last_state(self, slot_idx: int) -> MFCUIState | None:
        """Get last polled state for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            Last polled UI state or None.
        """
        return self._previous_states.get(slot_idx)
