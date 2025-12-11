"""Unit tests for Slot State Machine."""

import pytest
from datetime import datetime

from domain.state_machine import (
    SlotState,
    SlotEvent,
    SlotContext,
    SlotStateMachine,
    SlotStateMachineManager,
    InvalidTransitionError,
)
from domain.enums import ProcessState, TestPhase


class TestSlotContext:
    """Tests for SlotContext."""

    def test_init_default_values(self):
        """Test default initialization."""
        ctx = SlotContext(slot_idx=0)

        assert ctx.slot_idx == 0
        assert ctx.test_id is None
        assert ctx.test_name is None
        assert ctx.process_state == ProcessState.IDLE
        assert ctx.test_phase == TestPhase.IDLE
        assert ctx.current_loop == 0
        assert ctx.total_loop == 0
        assert ctx.error_message is None

    def test_update_creates_new_instance(self):
        """Test update creates new instance."""
        ctx1 = SlotContext(slot_idx=0)
        ctx2 = ctx1.update(test_id="test-123", current_loop=5)

        assert ctx1.test_id is None
        assert ctx1.current_loop == 0
        assert ctx2.test_id == "test-123"
        assert ctx2.current_loop == 5
        assert ctx1 is not ctx2

    def test_reset_clears_values(self):
        """Test reset clears all values."""
        ctx = SlotContext(
            slot_idx=0,
            test_id="test-123",
            current_loop=5,
            error_message="some error",
        )
        reset_ctx = ctx.reset()

        assert reset_ctx.slot_idx == 0
        assert reset_ctx.test_id is None
        assert reset_ctx.current_loop == 0
        assert reset_ctx.error_message is None

    def test_progress_percent(self):
        """Test progress percentage calculation."""
        ctx = SlotContext(slot_idx=0, current_loop=5, total_loop=10)
        assert ctx.get_progress_percent() == 50.0

        ctx_zero = SlotContext(slot_idx=0, current_loop=0, total_loop=0)
        assert ctx_zero.get_progress_percent() == 0.0

    def test_to_dict(self):
        """Test to_dict conversion."""
        ctx = SlotContext(
            slot_idx=0,
            test_id="test-123",
            current_loop=5,
            total_loop=10,
        )
        data = ctx.to_dict()

        assert data["slot_idx"] == 0
        assert data["test_id"] == "test-123"
        assert data["current_loop"] == 5
        assert data["total_loop"] == 10
        assert data["progress_percent"] == 50.0


class TestSlotStateMachine:
    """Tests for SlotStateMachine."""

    def test_initial_state_is_idle(self):
        """Test initial state is IDLE."""
        machine = SlotStateMachine(slot_idx=0)
        assert machine.state == SlotState.IDLE

    def test_custom_initial_state(self):
        """Test custom initial state."""
        machine = SlotStateMachine(slot_idx=0, initial_state=SlotState.READY)
        assert machine.state == SlotState.READY

    def test_valid_transition_idle_to_preparing(self):
        """Test valid transition from IDLE to PREPARING."""
        machine = SlotStateMachine(slot_idx=0)

        new_state = machine.trigger(SlotEvent.START_TEST)

        assert new_state == SlotState.PREPARING
        assert machine.state == SlotState.PREPARING

    def test_valid_transition_sequence(self):
        """Test valid transition sequence: IDLE -> PREPARING -> CONFIGURING -> RUNNING."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        assert machine.state == SlotState.PREPARING

        machine.trigger(SlotEvent.CONFIGURE)
        assert machine.state == SlotState.CONFIGURING

        machine.trigger(SlotEvent.RUN)
        assert machine.state == SlotState.RUNNING

    def test_invalid_transition_raises_error(self):
        """Test invalid transition raises InvalidTransitionError."""
        machine = SlotStateMachine(slot_idx=0)

        with pytest.raises(InvalidTransitionError) as exc_info:
            machine.trigger(SlotEvent.RUN)  # Cannot RUN from IDLE

        assert exc_info.value.current_state == SlotState.IDLE
        assert exc_info.value.event == SlotEvent.RUN
        assert exc_info.value.slot_idx == 0

    def test_can_transition(self):
        """Test can_transition method."""
        machine = SlotStateMachine(slot_idx=0)

        assert machine.can_transition(SlotEvent.START_TEST) is True
        assert machine.can_transition(SlotEvent.CONNECT) is True
        assert machine.can_transition(SlotEvent.RUN) is False
        assert machine.can_transition(SlotEvent.COMPLETE) is False

    def test_get_valid_events(self):
        """Test get_valid_events method."""
        machine = SlotStateMachine(slot_idx=0)

        valid_events = machine.get_valid_events()

        assert SlotEvent.START_TEST in valid_events
        assert SlotEvent.CONNECT in valid_events
        assert SlotEvent.RESET in valid_events
        assert SlotEvent.RUN not in valid_events

    def test_context_update_on_transition(self):
        """Test context is updated on transition."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(
            SlotEvent.START_TEST,
            context_update={"test_name": "Test 1"},
        )

        assert machine.context.test_name == "Test 1"
        assert machine.context.started_at is not None

    def test_error_message_on_error_transition(self):
        """Test error message is set on error transition."""
        machine = SlotStateMachine(slot_idx=0)
        machine.trigger(SlotEvent.START_TEST)

        machine.trigger(
            SlotEvent.ERROR,
            error_message="Connection failed",
        )

        assert machine.state == SlotState.ERROR
        assert machine.context.error_message == "Connection failed"
        assert machine.context.error_count == 1

    def test_reset_clears_context(self):
        """Test RESET clears context."""
        machine = SlotStateMachine(slot_idx=0)
        machine.trigger(
            SlotEvent.START_TEST,
            context_update={"test_name": "Test 1"},
        )
        machine.trigger(SlotEvent.ERROR, error_message="Error")
        machine.trigger(SlotEvent.RESET)

        assert machine.state == SlotState.IDLE
        assert machine.context.test_name is None
        assert machine.context.error_message is None

    def test_history_is_recorded(self):
        """Test transition history is recorded."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)

        assert len(machine.history) == 2

        # First transition
        _, old_state1, event1, new_state1 = machine.history[0]
        assert old_state1 == SlotState.IDLE
        assert event1 == SlotEvent.START_TEST
        assert new_state1 == SlotState.PREPARING

        # Second transition
        _, old_state2, event2, new_state2 = machine.history[1]
        assert old_state2 == SlotState.PREPARING
        assert event2 == SlotEvent.CONFIGURE
        assert new_state2 == SlotState.CONFIGURING

    def test_state_change_callback(self):
        """Test state change callback is invoked."""
        callback_calls = []

        def callback(slot_idx, old_state, new_state):
            callback_calls.append((slot_idx, old_state, new_state))

        machine = SlotStateMachine(slot_idx=0, on_state_change=callback)
        machine.trigger(SlotEvent.START_TEST)

        assert len(callback_calls) == 1
        assert callback_calls[0] == (0, SlotState.IDLE, SlotState.PREPARING)

    def test_is_idle(self):
        """Test is_idle method."""
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_idle() is True

        machine.trigger(SlotEvent.START_TEST)
        assert machine.is_idle() is False

    def test_is_busy(self):
        """Test is_busy method."""
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_busy() is False

        machine.trigger(SlotEvent.START_TEST)
        assert machine.is_busy() is True

        machine.trigger(SlotEvent.ERROR)
        assert machine.is_busy() is False

    def test_is_running(self):
        """Test is_running method."""
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_running() is False

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        assert machine.is_running() is True

    def test_is_terminal(self):
        """Test is_terminal method."""
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_terminal() is False

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.COMPLETE)
        assert machine.is_terminal() is True

    def test_force_state(self):
        """Test force_state method."""
        machine = SlotStateMachine(slot_idx=0)
        machine.trigger(SlotEvent.START_TEST)

        machine.force_state(SlotState.IDLE, "Recovery")

        assert machine.state == SlotState.IDLE

    def test_to_dict(self):
        """Test to_dict method."""
        machine = SlotStateMachine(slot_idx=0)
        machine.trigger(SlotEvent.START_TEST)

        data = machine.to_dict()

        assert data["slot_idx"] == 0
        assert data["state"] == "preparing"
        assert data["is_busy"] is True
        assert data["is_running"] is False
        assert "context" in data


class TestSlotStateMachineManager:
    """Tests for SlotStateMachineManager."""

    def test_init_creates_machines_for_all_slots(self):
        """Test initialization creates machines for all slots."""
        manager = SlotStateMachineManager(max_slots=8)

        assert manager.max_slots == 8
        for i in range(8):
            assert manager.get(i) is not None
            assert manager.get(i).slot_idx == i

    def test_getitem(self):
        """Test __getitem__ access."""
        manager = SlotStateMachineManager(max_slots=4)

        machine = manager[0]
        assert machine.slot_idx == 0

    def test_getitem_invalid_raises_keyerror(self):
        """Test invalid slot index raises KeyError."""
        manager = SlotStateMachineManager(max_slots=4)

        with pytest.raises(KeyError):
            _ = manager[10]

    def test_trigger(self):
        """Test trigger on specific slot."""
        manager = SlotStateMachineManager(max_slots=4)

        new_state = manager.trigger(0, SlotEvent.START_TEST)

        assert new_state == SlotState.PREPARING
        assert manager[0].state == SlotState.PREPARING

    def test_get_all_states(self):
        """Test get_all_states."""
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        states = manager.get_all_states()

        assert states[0] == SlotState.PREPARING
        assert states[1] == SlotState.CONNECTING
        assert states[2] == SlotState.IDLE
        assert states[3] == SlotState.IDLE

    def test_get_busy_slots(self):
        """Test get_busy_slots."""
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        busy = manager.get_busy_slots()

        assert 0 in busy
        assert 1 in busy
        assert 2 not in busy

    def test_get_running_slots(self):
        """Test get_running_slots."""
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(0, SlotEvent.CONFIGURE)
        manager.trigger(0, SlotEvent.RUN)

        running = manager.get_running_slots()

        assert 0 in running
        assert 1 not in running

    def test_get_idle_slots(self):
        """Test get_idle_slots."""
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)

        idle = manager.get_idle_slots()

        assert 0 not in idle
        assert 1 in idle
        assert 2 in idle
        assert 3 in idle

    def test_reset_all(self):
        """Test reset_all."""
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        manager.reset_all()

        assert manager[0].state == SlotState.IDLE
        assert manager[1].state == SlotState.IDLE

    def test_to_dict(self):
        """Test to_dict."""
        manager = SlotStateMachineManager(max_slots=2)
        manager.trigger(0, SlotEvent.START_TEST)

        data = manager.to_dict()

        assert data["max_slots"] == 2
        assert 0 in data["busy_slots"]
        assert 1 in data["idle_slots"]
        assert "slots" in data
        assert len(data["slots"]) == 2

    def test_callback_propagation(self):
        """Test callback is propagated to all machines."""
        callback_calls = []

        def callback(slot_idx, old_state, new_state):
            callback_calls.append((slot_idx, old_state, new_state))

        manager = SlotStateMachineManager(max_slots=2, on_state_change=callback)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        assert len(callback_calls) == 2
        assert callback_calls[0][0] == 0
        assert callback_calls[1][0] == 1


class TestTransitionPaths:
    """Tests for specific transition paths."""

    def test_full_success_path(self):
        """Test full success path: IDLE -> PREPARING -> CONFIGURING -> RUNNING -> COMPLETED."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        assert machine.state == SlotState.PREPARING

        machine.trigger(SlotEvent.CONFIGURE)
        assert machine.state == SlotState.CONFIGURING

        machine.trigger(SlotEvent.RUN)
        assert machine.state == SlotState.RUNNING

        machine.trigger(SlotEvent.COMPLETE)
        assert machine.state == SlotState.COMPLETED
        assert machine.is_terminal()

    def test_fail_during_running(self):
        """Test failure during running."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.FAIL, error_message="Test failed")

        assert machine.state == SlotState.FAILED
        assert machine.context.error_message == "Test failed"

    def test_stop_during_running(self):
        """Test stop during running."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.STOP)

        assert machine.state == SlotState.STOPPING

        machine.trigger(SlotEvent.STOPPED)
        assert machine.state == SlotState.IDLE

    def test_retry_after_failure(self):
        """Test retry after failure."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.FAIL)
        assert machine.state == SlotState.FAILED

        machine.trigger(SlotEvent.RETRY)
        assert machine.state == SlotState.PREPARING

    def test_reset_after_error(self):
        """Test reset after error."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.ERROR)
        assert machine.state == SlotState.ERROR

        machine.trigger(SlotEvent.RESET)
        assert machine.state == SlotState.IDLE

    def test_pause_and_resume(self):
        """Test pause and resume during running."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.PAUSE)

        assert machine.state == SlotState.PAUSED

        machine.trigger(SlotEvent.RESUME)
        assert machine.state == SlotState.RUNNING

    def test_start_test_after_error(self):
        """Test START_TEST after error state (recovery scenario).

        When a slot enters ERROR state and user takes corrective action,
        they should be able to restart the test without calling RESET first.
        """
        machine = SlotStateMachine(slot_idx=0)

        # 테스트 시작 -> 에러 발생
        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.ERROR, error_message="Connection lost")

        assert machine.state == SlotState.ERROR
        assert machine.context.error_message == "Connection lost"
        assert machine.context.error_count == 1

        # 에러 상태에서 바로 START_TEST 가능해야 함
        machine.trigger(
            SlotEvent.START_TEST,
            context_update={"test_name": "Retry Test"},
        )

        assert machine.state == SlotState.PREPARING
        # 에러 정보가 초기화되어야 함
        assert machine.context.error_message is None
        assert machine.context.error_count == 0
        assert machine.context.test_name == "Retry Test"
        assert machine.context.started_at is not None

    def test_start_test_after_failed(self):
        """Test START_TEST after failed state."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.FAIL, error_message="Test failed")

        assert machine.state == SlotState.FAILED
        assert machine.context.error_message == "Test failed"

        # FAILED 상태에서 바로 START_TEST 가능
        machine.trigger(SlotEvent.START_TEST)

        assert machine.state == SlotState.PREPARING
        assert machine.context.error_message is None

    def test_start_test_after_completed(self):
        """Test START_TEST after completed state."""
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.COMPLETE)

        assert machine.state == SlotState.COMPLETED

        # COMPLETED 상태에서 바로 START_TEST 가능
        machine.trigger(SlotEvent.START_TEST)

        assert machine.state == SlotState.PREPARING
        assert machine.context.current_loop == 0
