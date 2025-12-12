"""Unit tests for ProcessMonitor service."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.process_monitor import (
    ProcessMonitor,
    ProcessTerminationEvent,
    ProcessTerminationReason,
)


class FakeClock:
    """Fake clock for testing."""

    def __init__(self, initial_time: datetime = None):
        self._time = initial_time or datetime(2025, 1, 1, 12, 0, 0)

    def now(self) -> datetime:
        return self._time

    def monotonic(self) -> float:
        return self._time.timestamp()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(0)  # Yield control without actual delay


class FakeLogger:
    """Fake logger for testing."""

    def __init__(self):
        self.messages: list[dict] = []

    def info(self, msg: str, **kwargs) -> None:
        self.messages.append({"level": "info", "msg": msg, **kwargs})

    def warning(self, msg: str, **kwargs) -> None:
        self.messages.append({"level": "warning", "msg": msg, **kwargs})

    def error(self, msg: str, **kwargs) -> None:
        self.messages.append({"level": "error", "msg": msg, **kwargs})

    def debug(self, msg: str, **kwargs) -> None:
        self.messages.append({"level": "debug", "msg": msg, **kwargs})


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_logger() -> FakeLogger:
    return FakeLogger()


@pytest.fixture
def process_monitor(fake_clock: FakeClock, fake_logger: FakeLogger) -> ProcessMonitor:
    return ProcessMonitor(
        clock=fake_clock,
        logger=fake_logger,
        max_slots=4,
    )


class TestProcessMonitor:
    """Tests for ProcessMonitor."""

    def test_init(self, process_monitor: ProcessMonitor):
        """[TC-PROCESS_MONITOR-001] Init - 테스트 시나리오를 검증한다.

            테스트 목적:
                Init 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_init 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        assert not process_monitor.is_running
        assert process_monitor.get_watched_slots() == {}

    def test_watch_slot(self, process_monitor: ProcessMonitor):
        """[TC-PROCESS_MONITOR-002] Watch slot - 테스트 시나리오를 검증한다.

            테스트 목적:
                Watch slot 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_watch_slot 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        process_monitor.watch_slot(0, 1234, is_running=True)
        assert process_monitor.get_watched_slots() == {0: 1234}

    def test_unwatch_slot(self, process_monitor: ProcessMonitor):
        """[TC-PROCESS_MONITOR-003] Unwatch slot - 테스트 시나리오를 검증한다.

            테스트 목적:
                Unwatch slot 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_unwatch_slot 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        process_monitor.watch_slot(0, 1234)
        process_monitor.unwatch_slot(0)
        assert process_monitor.get_watched_slots() == {}

    def test_update_slot_running_state(self, process_monitor: ProcessMonitor):
        """[TC-PROCESS_MONITOR-004] Update slot running state - 테스트 시나리오를 검증한다.

            테스트 목적:
                Update slot running state 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_update_slot_running_state 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        process_monitor.watch_slot(0, 1234, is_running=False)
        process_monitor.update_slot_running_state(0, True)
        # State is internal, but we can verify the slot is still watched
        assert 0 in process_monitor.get_watched_slots()

    @pytest.mark.asyncio
    async def test_start_stop(self, process_monitor: ProcessMonitor):
        """[TC-PROCESS_MONITOR-005] Start stop - 테스트 시나리오를 검증한다.

            테스트 목적:
                Start stop 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_start_stop 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        await process_monitor.start(interval=0.1)
        assert process_monitor.is_running

        await process_monitor.stop()
        assert not process_monitor.is_running

    @pytest.mark.asyncio
    async def test_termination_callback(
        self,
        process_monitor: ProcessMonitor,
    ):
        """[TC-PROCESS_MONITOR-006] Termination callback - 테스트 시나리오를 검증한다.

            테스트 목적:
                Termination callback 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_termination_callback 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback = AsyncMock()
        process_monitor.set_termination_callback(callback)

        process_monitor.watch_slot(0, 99999, is_running=True)  # Non-existent PID

        with patch("psutil.pid_exists", return_value=False):
            await process_monitor._check_processes()

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert isinstance(event, ProcessTerminationEvent)
        assert event.slot_idx == 0
        assert event.pid == 99999
        assert event.reason == ProcessTerminationReason.USER_TERMINATED
        assert event.was_running is True

    @pytest.mark.asyncio
    async def test_zombie_process_detected(
        self,
        process_monitor: ProcessMonitor,
    ):
        """[TC-PROCESS_MONITOR-007] Zombie process detected - 테스트 시나리오를 검증한다.

            테스트 목적:
                Zombie process detected 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_zombie_process_detected 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback = AsyncMock()
        process_monitor.set_termination_callback(callback)

        process_monitor.watch_slot(0, 1234, is_running=True)

        mock_process = MagicMock()
        mock_process.status.return_value = "zombie"

        with patch("psutil.pid_exists", return_value=True):
            with patch("psutil.Process", return_value=mock_process):
                with patch("psutil.STATUS_ZOMBIE", "zombie"):
                    await process_monitor._check_processes()

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.reason == ProcessTerminationReason.PROCESS_CRASHED

    @pytest.mark.asyncio
    async def test_slot_removed_after_termination(
        self,
        process_monitor: ProcessMonitor,
    ):
        """[TC-PROCESS_MONITOR-008] Slot removed after termination - 테스트 시나리오를 검증한다.

            테스트 목적:
                Slot removed after termination 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_slot_removed_after_termination 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback = AsyncMock()
        process_monitor.set_termination_callback(callback)

        process_monitor.watch_slot(0, 99999, is_running=True)
        assert 0 in process_monitor.get_watched_slots()

        with patch("psutil.pid_exists", return_value=False):
            await process_monitor._check_processes()

        assert 0 not in process_monitor.get_watched_slots()

    @pytest.mark.asyncio
    async def test_multiple_slots_monitoring(
        self,
        process_monitor: ProcessMonitor,
    ):
        """[TC-PROCESS_MONITOR-009] Multiple slots monitoring - 테스트 시나리오를 검증한다.

            테스트 목적:
                Multiple slots monitoring 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_multiple_slots_monitoring 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback = AsyncMock()
        process_monitor.set_termination_callback(callback)

        process_monitor.watch_slot(0, 1001, is_running=True)
        process_monitor.watch_slot(1, 1002, is_running=True)

        # Simulate: all processes terminated
        with patch("psutil.pid_exists", return_value=False):
            await process_monitor._check_processes()

        # Both slots should be removed
        assert 0 not in process_monitor.get_watched_slots()
        assert 1 not in process_monitor.get_watched_slots()
        # Callback should be called for each terminated slot
        assert callback.call_count == 2
