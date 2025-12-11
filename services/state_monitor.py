"""State Monitor Service.

Service that monitors test states.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, Any

from ..core.protocols import (
    IWindowFinder,
    IWindowHandle,
    IStateStore,
    IClock,
    ILogger,
)


@dataclass
class SlotSnapshot:
    """Slot state snapshot.

    Attributes:
        slot_idx: Slot index.
        status: Status.
        progress: Progress percentage.
        current_phase: Current phase.
        is_changed: Whether changed from previous state.
    """

    slot_idx: int
    status: str
    progress: float = 0.0
    current_phase: Optional[str] = None
    is_changed: bool = False


class StateMonitor:
    """State monitoring service.

    Periodically polls test progress status and detects changes.

    Example:
        ```python
        monitor = StateMonitor(
            window_finder=window_finder,
            state_store=state_store,
            clock=clock,
            logger=logger,
        )

        async def on_change(snapshot: SlotSnapshot) -> None:
            print(f"Slot {snapshot.slot_idx}: {snapshot.status}")

        monitor.set_change_callback(on_change)
        await monitor.start(interval=1.0)
        ```
    """

    def __init__(
        self,
        window_finder: IWindowFinder,
        state_store: IStateStore,
        clock: IClock,
        logger: ILogger,
        max_slots: int = 16,
    ) -> None:
        """Initialize service.

        Args:
            window_finder: Window finder.
            state_store: State store.
            clock: Clock.
            logger: Logger.
            max_slots: Maximum number of slots.
        """
        self._window_finder = window_finder
        self._state_store = state_store
        self._clock = clock
        self._logger = logger
        self._max_slots = max_slots

        # 상태
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._previous_states: dict[int, dict[str, Any]] = {}

        # 콜백
        self._on_change: Optional[Callable[[SlotSnapshot], Awaitable[None]]] = None
        self._on_hang_detected: Optional[
            Callable[[int, float], Awaitable[None]]
        ] = None

        # Hang 감지
        self._last_progress_change: dict[int, float] = {}
        self._hang_threshold_seconds = 300.0

    def set_change_callback(
        self,
        callback: Callable[[SlotSnapshot], Awaitable[None]],
    ) -> None:
        """Set state change callback.

        Args:
            callback: Callback function.
        """
        self._on_change = callback

    def set_hang_callback(
        self,
        callback: Callable[[int, float], Awaitable[None]],
        threshold_seconds: float = 300.0,
    ) -> None:
        """Set hang detection callback.

        Args:
            callback: Callback function (slot_idx, duration).
            threshold_seconds: Hang detection threshold in seconds.
        """
        self._on_hang_detected = callback
        self._hang_threshold_seconds = threshold_seconds

    @property
    def is_running(self) -> bool:
        """Monitoring running status."""
        return self._is_running

    async def start(self, interval: float = 1.0) -> None:
        """Start monitoring.

        Args:
            interval: Polling interval in seconds.
        """
        if self._is_running:
            self._logger.warning("Monitor already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        self._logger.info("State monitor started", interval=interval)

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

        self._logger.info("State monitor stopped")

    async def _monitor_loop(self, interval: float) -> None:
        """Monitoring loop.

        Args:
            interval: Polling interval in seconds.
        """
        while self._is_running:
            try:
                await self._poll_states()
            except Exception as e:
                self._logger.error("Monitor poll error", error=str(e))

            await self._clock.sleep(interval)

    async def _poll_states(self) -> None:
        """Poll states."""
        current_time = self._clock.monotonic()

        for slot_idx in range(self._max_slots):
            try:
                await self._poll_slot_state(slot_idx, current_time)
            except Exception as e:
                self._logger.error(
                    "Slot poll error",
                    slot_idx=slot_idx,
                    error=str(e),
                )

    async def _poll_slot_state(self, slot_idx: int, current_time: float) -> None:
        """Poll single slot state.

        Args:
            slot_idx: Slot index.
            current_time: Current time.
        """
        current_state = self._state_store.get_slot_state(slot_idx)
        if not current_state:
            return

        previous_state = self._previous_states.get(slot_idx, {})

        # 변경 감지
        is_changed = self._detect_change(current_state, previous_state)

        if is_changed:
            snapshot = SlotSnapshot(
                slot_idx=slot_idx,
                status=current_state.get("status", "unknown"),
                progress=current_state.get("progress", 0.0),
                current_phase=current_state.get("current_phase"),
                is_changed=True,
            )

            if self._on_change:
                await self._on_change(snapshot)

            # 진행률 변경 시간 업데이트
            if current_state.get("progress") != previous_state.get("progress"):
                self._last_progress_change[slot_idx] = current_time

        # Hang 감지
        await self._check_hang(slot_idx, current_state, current_time)

        # 이전 상태 저장
        self._previous_states[slot_idx] = current_state.copy()

    def _detect_change(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
    ) -> bool:
        """Detect state change.

        Args:
            current: Current state.
            previous: Previous state.

        Returns:
            Whether changed.
        """
        watch_keys = ["status", "progress", "current_phase", "error_message"]

        for key in watch_keys:
            if current.get(key) != previous.get(key):
                return True

        return False

    async def _check_hang(
        self,
        slot_idx: int,
        state: dict[str, Any],
        current_time: float,
    ) -> None:
        """Detect hang state.

        Args:
            slot_idx: Slot index.
            state: Current state.
            current_time: Current time.
        """
        status = state.get("status", "")

        # 실행 중이 아니면 스킵
        if status not in ("running", "processing"):
            self._last_progress_change.pop(slot_idx, None)
            return

        last_change = self._last_progress_change.get(slot_idx)
        if last_change is None:
            self._last_progress_change[slot_idx] = current_time
            return

        duration = current_time - last_change

        if duration >= self._hang_threshold_seconds:
            self._logger.warning(
                "Hang detected",
                slot_idx=slot_idx,
                duration=duration,
            )

            if self._on_hang_detected:
                await self._on_hang_detected(slot_idx, duration)

            # 시간 리셋 (반복 알림 방지)
            self._last_progress_change[slot_idx] = current_time

    def get_snapshot(self, slot_idx: int) -> Optional[SlotSnapshot]:
        """Get slot snapshot.

        Args:
            slot_idx: Slot index.

        Returns:
            Slot snapshot or None.
        """
        state = self._state_store.get_slot_state(slot_idx)
        if not state:
            return None

        return SlotSnapshot(
            slot_idx=slot_idx,
            status=state.get("status", "unknown"),
            progress=state.get("progress", 0.0),
            current_phase=state.get("current_phase"),
            is_changed=False,
        )

    def get_all_snapshots(self) -> list[SlotSnapshot]:
        """Get all slot snapshots.

        Returns:
            List of snapshots.
        """
        snapshots = []
        for slot_idx in range(self._max_slots):
            snapshot = self.get_snapshot(slot_idx)
            if snapshot:
                snapshots.append(snapshot)
        return snapshots
