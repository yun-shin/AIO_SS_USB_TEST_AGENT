"""Process Monitor Service.

Service that monitors USB Test.exe processes for unexpected termination.
Detects when running tests lose their process (user force quit, crash, etc.)
and notifies the system.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import psutil

from config.constants import SlotConfig
from core.protocols import IClock, ILogger


class ProcessTerminationReason(str, Enum):
    """Reason for process termination."""

    USER_TERMINATED = "user_terminated"  # 사용자가 직접 종료
    PROCESS_CRASHED = "process_crashed"  # 프로세스 크래시
    ACCESS_DENIED = "access_denied"  # 접근 권한 없음
    UNKNOWN = "unknown"


@dataclass
class ProcessTerminationEvent:
    """Process termination event.

    Attributes:
        slot_idx: Slot index.
        pid: Terminated process PID.
        reason: Termination reason.
        timestamp: Event timestamp.
        was_running: Whether test was running when terminated.
    """

    slot_idx: int
    pid: int
    reason: ProcessTerminationReason
    timestamp: datetime
    was_running: bool = False


class ProcessMonitor:
    """Process monitoring service.

    Monitors USB Test.exe processes and detects unexpected terminations.
    Runs at a configurable interval (default: 5 seconds).

    Example:
        ```python
        monitor = ProcessMonitor(
            clock=system_clock,
            logger=logger,
        )

        async def on_terminated(event: ProcessTerminationEvent) -> None:
            print(f"Process terminated: slot {event.slot_idx}, reason: {event.reason}")

        monitor.set_termination_callback(on_terminated)
        await monitor.start(interval=5.0)
        ```
    """

    def __init__(
        self,
        clock: IClock,
        logger: ILogger,
        max_slots: int = SlotConfig.MAX_SLOTS,
    ) -> None:
        """Initialize process monitor.

        Args:
            clock: Clock interface.
            logger: Logger interface.
            max_slots: Maximum number of slots.
        """
        self._clock = clock
        self._logger = logger
        self._max_slots = max_slots

        # 상태
        self._is_running = False
        self._monitor_task: asyncio.Task | None = None

        # 슬롯별 모니터링 대상 PID
        self._watched_pids: dict[int, int] = {}  # slot_idx -> pid

        # 슬롯별 실행 중 플래그
        self._slot_running: dict[int, bool] = {}

        # 콜백
        self._on_termination: (
            Callable[[ProcessTerminationEvent], Awaitable[None]] | None
        ) = None

    def set_termination_callback(
        self,
        callback: Callable[[ProcessTerminationEvent], Awaitable[None]],
    ) -> None:
        """Set termination callback.

        Args:
            callback: Callback function.
        """
        self._on_termination = callback

    def watch_slot(self, slot_idx: int, pid: int, is_running: bool = False) -> None:
        """Register a slot's process for monitoring.

        Args:
            slot_idx: Slot index.
            pid: Process ID to watch.
            is_running: Whether test is currently running.
        """
        self._watched_pids[slot_idx] = pid
        self._slot_running[slot_idx] = is_running
        self._logger.info(
            "Started watching process",
            slot_idx=slot_idx,
            pid=pid,
            is_running=is_running,
        )

    def unwatch_slot(self, slot_idx: int) -> None:
        """Stop monitoring a slot's process.

        Args:
            slot_idx: Slot index.
        """
        if slot_idx in self._watched_pids:
            pid = self._watched_pids.pop(slot_idx, None)
            self._slot_running.pop(slot_idx, None)
            self._logger.info(
                "Stopped watching process",
                slot_idx=slot_idx,
                pid=pid,
            )

    def update_slot_running_state(self, slot_idx: int, is_running: bool) -> None:
        """Update slot's running state.

        Args:
            slot_idx: Slot index.
            is_running: Whether test is currently running.
        """
        self._slot_running[slot_idx] = is_running

    @property
    def is_running(self) -> bool:
        """Monitoring running status."""
        return self._is_running

    async def start(self, interval: float = 5.0) -> None:
        """Start monitoring.

        Args:
            interval: Check interval in seconds.
        """
        if self._is_running:
            self._logger.warning("Process monitor already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        self._logger.info("Process monitor started", interval=interval)

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

        self._logger.info("Process monitor stopped")

    async def _monitor_loop(self, interval: float) -> None:
        """Monitoring loop.

        Args:
            interval: Check interval in seconds.
        """
        while self._is_running:
            try:
                await self._check_processes()
            except Exception as e:
                self._logger.error("Process monitor error", error=str(e))

            await self._clock.sleep(interval)

    async def _check_processes(self) -> None:
        """Check all watched processes."""
        terminated_slots: list[tuple[int, int, ProcessTerminationReason]] = []

        for slot_idx, pid in list(self._watched_pids.items()):
            try:
                if not psutil.pid_exists(pid):
                    # PID가 더 이상 존재하지 않음
                    terminated_slots.append(
                        (slot_idx, pid, ProcessTerminationReason.USER_TERMINATED)
                    )
                    continue

                # 프로세스가 존재하는 경우, 상태 확인
                try:
                    proc = psutil.Process(pid)
                    status = proc.status()

                    if status == psutil.STATUS_ZOMBIE:
                        terminated_slots.append(
                            (slot_idx, pid, ProcessTerminationReason.PROCESS_CRASHED)
                        )

                except psutil.AccessDenied:
                    # 접근 권한이 없는 경우 - 프로세스는 아직 실행 중일 수 있음
                    self._logger.warning(
                        "Access denied to process",
                        slot_idx=slot_idx,
                        pid=pid,
                    )

                except psutil.NoSuchProcess:
                    terminated_slots.append(
                        (slot_idx, pid, ProcessTerminationReason.USER_TERMINATED)
                    )

            except Exception as e:
                self._logger.error(
                    "Error checking process",
                    slot_idx=slot_idx,
                    pid=pid,
                    error=str(e),
                )

        # 종료된 프로세스 처리
        for slot_idx, pid, reason in terminated_slots:
            was_running = self._slot_running.get(slot_idx, False)

            # 감시 목록에서 제거
            self._watched_pids.pop(slot_idx, None)
            self._slot_running.pop(slot_idx, None)

            # 콜백 호출
            if self._on_termination:
                event = ProcessTerminationEvent(
                    slot_idx=slot_idx,
                    pid=pid,
                    reason=reason,
                    timestamp=self._clock.now(),
                    was_running=was_running,
                )
                try:
                    await self._on_termination(event)
                except Exception as e:
                    self._logger.error(
                        "Termination callback error",
                        slot_idx=slot_idx,
                        error=str(e),
                    )

            self._logger.warning(
                "Process terminated unexpectedly",
                slot_idx=slot_idx,
                pid=pid,
                reason=reason.value,
                was_running=was_running,
            )

    def get_watched_slots(self) -> dict[int, int]:
        """Get all watched slots and their PIDs.

        Returns:
            Dictionary of slot_idx -> pid.
        """
        return dict(self._watched_pids)
