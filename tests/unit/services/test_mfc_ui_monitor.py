"""Unit tests for MFCUIMonitor service."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.constants import ProcessState, MFCControlId
from services.mfc_ui_monitor import (
    MFCUIMonitor,
    MFCUIState,
    UIStateChange,
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


class FakeSlotWindowManager:
    """Fake slot window manager for testing."""

    def __init__(self, slot_idx: int, connected: bool = True):
        self.slot_idx = slot_idx
        self.is_connected = connected
        self._controls: dict[int, MagicMock] = {}

    def set_control(self, control_id: int, text: str, enabled: bool = True):
        """Set a fake control."""
        ctrl = MagicMock()
        ctrl.window_text.return_value = text
        ctrl.is_enabled.return_value = enabled
        self._controls[control_id] = ctrl

    def find_control(self, control_id: int, class_name: str = None):
        """Find a control by ID."""
        return self._controls.get(control_id)


class FakeWindowManager:
    """Fake window manager for testing."""

    def __init__(self):
        self._slot_windows: dict[int, FakeSlotWindowManager] = {}

    def add_slot(self, slot_idx: int, connected: bool = True) -> FakeSlotWindowManager:
        """Add a fake slot."""
        window = FakeSlotWindowManager(slot_idx, connected)
        self._slot_windows[slot_idx] = window
        return window

    def get_slot_window(self, slot_idx: int):
        """Get slot window manager."""
        return self._slot_windows.get(slot_idx)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_logger() -> FakeLogger:
    return FakeLogger()


@pytest.fixture
def fake_window_manager() -> FakeWindowManager:
    return FakeWindowManager()


@pytest.fixture
def mfc_ui_monitor(
    fake_window_manager: FakeWindowManager,
    fake_clock: FakeClock,
    fake_logger: FakeLogger,
) -> MFCUIMonitor:
    return MFCUIMonitor(
        window_manager=fake_window_manager,
        clock=fake_clock,
        logger=fake_logger,
        max_slots=4,
    )


class TestMFCUIState:
    """Tests for MFCUIState dataclass."""

    def test_init_defaults(self):
        """Test default initialization."""
        state = MFCUIState(slot_idx=0)
        assert state.slot_idx == 0
        assert state.process_state == ProcessState.IDLE
        assert state.current_loop == 0
        assert state.total_loop == 0
        assert state.timestamp is not None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = MFCUIState(
            slot_idx=0,
            process_state=ProcessState.TEST,
            current_loop=5,
            total_loop=10,
            status_text="Test",
        )
        d = state.to_dict()
        assert d["slot_idx"] == 0
        assert d["process_state"] == ProcessState.TEST.value
        assert d["process_state_name"] == "TEST"
        assert d["current_loop"] == 5
        assert d["total_loop"] == 10


class TestMFCUIMonitor:
    """Tests for MFCUIMonitor."""

    def test_init(self, mfc_ui_monitor: MFCUIMonitor):
        """Test initialization."""
        assert not mfc_ui_monitor.is_running

    def test_add_remove_monitored_slot(self, mfc_ui_monitor: MFCUIMonitor):
        """Test adding and removing monitored slots."""
        mfc_ui_monitor.add_monitored_slot(0)
        mfc_ui_monitor.add_monitored_slot(1)
        mfc_ui_monitor.remove_monitored_slot(0)
        # We can't directly check the set, but we can verify no errors

    @pytest.mark.asyncio
    async def test_start_stop(self, mfc_ui_monitor: MFCUIMonitor):
        """Test start and stop."""
        await mfc_ui_monitor.start(interval=0.1)
        assert mfc_ui_monitor.is_running

        await mfc_ui_monitor.stop()
        assert not mfc_ui_monitor.is_running

    @pytest.mark.asyncio
    async def test_poll_slot_once(
        self,
        mfc_ui_monitor: MFCUIMonitor,
        fake_window_manager: FakeWindowManager,
    ):
        """Test polling a slot once."""
        slot_window = fake_window_manager.add_slot(0, connected=True)
        slot_window.set_control(MFCControlId.TXT_STATUS, "Test")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "5")
        slot_window.set_control(MFCControlId.EDT_LOOP, "10")
        slot_window.set_control(MFCControlId.BTN_TEST, "", enabled=False)
        slot_window.set_control(MFCControlId.BTN_STOP, "", enabled=True)

        state = await mfc_ui_monitor.poll_slot_once(0)

        assert state is not None
        assert state.slot_idx == 0
        assert state.process_state == ProcessState.TEST
        assert state.current_loop == 5
        assert state.total_loop == 10
        assert not state.is_test_button_enabled
        assert state.is_stop_button_enabled

    @pytest.mark.asyncio
    async def test_poll_disconnected_slot(
        self,
        mfc_ui_monitor: MFCUIMonitor,
        fake_window_manager: FakeWindowManager,
    ):
        """Test polling a disconnected slot returns None."""
        fake_window_manager.add_slot(0, connected=False)

        state = await mfc_ui_monitor.poll_slot_once(0)
        assert state is None

    @pytest.mark.asyncio
    async def test_change_callback(
        self,
        mfc_ui_monitor: MFCUIMonitor,
        fake_window_manager: FakeWindowManager,
    ):
        """Test change callback is called on state change."""
        callback = AsyncMock()
        mfc_ui_monitor.set_change_callback(callback)
        mfc_ui_monitor.add_monitored_slot(0)

        slot_window = fake_window_manager.add_slot(0, connected=True)

        # First poll - sets initial state
        slot_window.set_control(MFCControlId.TXT_STATUS, "Idle")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "0")
        slot_window.set_control(MFCControlId.EDT_LOOP, "10")
        await mfc_ui_monitor._poll_all_slots()

        # Second poll - state changed
        slot_window.set_control(MFCControlId.TXT_STATUS, "Test")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "1")
        await mfc_ui_monitor._poll_all_slots()

        callback.assert_called_once()
        change = callback.call_args[0][0]
        assert isinstance(change, UIStateChange)
        assert change.slot_idx == 0
        assert "process_state" in change.changed_fields
        assert "current_loop" in change.changed_fields

    @pytest.mark.asyncio
    async def test_test_completed_callback(
        self,
        mfc_ui_monitor: MFCUIMonitor,
        fake_window_manager: FakeWindowManager,
    ):
        """Test completion callback is called when test transitions to PASS."""
        completed_callback = AsyncMock()
        change_callback = AsyncMock()
        mfc_ui_monitor.set_test_completed_callback(completed_callback)
        mfc_ui_monitor.set_change_callback(change_callback)
        mfc_ui_monitor.add_monitored_slot(0)

        slot_window = fake_window_manager.add_slot(0, connected=True)

        # First poll - TEST state
        slot_window.set_control(MFCControlId.TXT_STATUS, "Test")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "5")
        slot_window.set_control(MFCControlId.EDT_LOOP, "10")
        await mfc_ui_monitor._poll_all_slots()

        # Second poll - PASS state
        slot_window.set_control(MFCControlId.TXT_STATUS, "Pass")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "10")
        await mfc_ui_monitor._poll_all_slots()

        completed_callback.assert_called_once()
        args = completed_callback.call_args[0]
        assert args[0] == 0  # slot_idx
        assert args[1] == ProcessState.PASS  # final_state

    @pytest.mark.asyncio
    async def test_user_intervention_callback(
        self,
        mfc_ui_monitor: MFCUIMonitor,
        fake_window_manager: FakeWindowManager,
    ):
        """Test user intervention callback."""
        intervention_callback = AsyncMock()
        change_callback = AsyncMock()
        mfc_ui_monitor.set_user_intervention_callback(intervention_callback)
        mfc_ui_monitor.set_change_callback(change_callback)
        mfc_ui_monitor.add_monitored_slot(0)

        slot_window = fake_window_manager.add_slot(0, connected=True)

        # First poll - TEST state
        slot_window.set_control(MFCControlId.TXT_STATUS, "Test")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "5")
        slot_window.set_control(MFCControlId.EDT_LOOP, "10")
        await mfc_ui_monitor._poll_all_slots()

        # Second poll - suddenly IDLE (user stopped)
        slot_window.set_control(MFCControlId.TXT_STATUS, "Idle")
        slot_window.set_control(MFCControlId.EDT_LOOP_CURRENT, "0")
        await mfc_ui_monitor._poll_all_slots()

        intervention_callback.assert_called_once()
        args = intervention_callback.call_args[0]
        assert args[0] == 0  # slot_idx
        assert "manually" in args[1].lower() or "stopped" in args[1].lower()

    def test_detect_changes(self, mfc_ui_monitor: MFCUIMonitor):
        """Test change detection between states."""
        previous = MFCUIState(
            slot_idx=0,
            process_state=ProcessState.IDLE,
            current_loop=0,
            total_loop=10,
        )
        current = MFCUIState(
            slot_idx=0,
            process_state=ProcessState.TEST,
            current_loop=1,
            total_loop=10,
        )

        changes = mfc_ui_monitor._detect_changes(previous, current)
        assert "process_state" in changes
        assert "current_loop" in changes
        assert "total_loop" not in changes

    def test_detect_changes_no_previous(self, mfc_ui_monitor: MFCUIMonitor):
        """Test no changes detected on first poll."""
        current = MFCUIState(slot_idx=0, process_state=ProcessState.IDLE)
        changes = mfc_ui_monitor._detect_changes(None, current)
        assert changes == []

    def test_get_last_state(
        self,
        mfc_ui_monitor: MFCUIMonitor,
    ):
        """Test getting last polled state."""
        # No state yet
        assert mfc_ui_monitor.get_last_state(0) is None

        # Set a state manually (simulating poll)
        mfc_ui_monitor._previous_states[0] = MFCUIState(
            slot_idx=0,
            process_state=ProcessState.TEST,
        )

        state = mfc_ui_monitor.get_last_state(0)
        assert state is not None
        assert state.process_state == ProcessState.TEST
