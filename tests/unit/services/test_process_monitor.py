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
        """Test initialization."""
        assert not process_monitor.is_running
        assert process_monitor.get_watched_slots() == {}

    def test_watch_slot(self, process_monitor: ProcessMonitor):
        """Test watching a slot."""
        process_monitor.watch_slot(0, 1234, is_running=True)
        assert process_monitor.get_watched_slots() == {0: 1234}

    def test_unwatch_slot(self, process_monitor: ProcessMonitor):
        """Test unwatching a slot."""
        process_monitor.watch_slot(0, 1234)
        process_monitor.unwatch_slot(0)
        assert process_monitor.get_watched_slots() == {}

    def test_update_slot_running_state(self, process_monitor: ProcessMonitor):
        """Test updating slot running state."""
        process_monitor.watch_slot(0, 1234, is_running=False)
        process_monitor.update_slot_running_state(0, True)
        # State is internal, but we can verify the slot is still watched
        assert 0 in process_monitor.get_watched_slots()

    @pytest.mark.asyncio
    async def test_start_stop(self, process_monitor: ProcessMonitor):
        """Test start and stop."""
        await process_monitor.start(interval=0.1)
        assert process_monitor.is_running

        await process_monitor.stop()
        assert not process_monitor.is_running

    @pytest.mark.asyncio
    async def test_termination_callback(
        self,
        process_monitor: ProcessMonitor,
    ):
        """Test termination callback is called when process terminates."""
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
        """Test zombie process is detected."""
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
        """Test slot is removed from watch list after termination."""
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
        """Test monitoring multiple slots."""
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
