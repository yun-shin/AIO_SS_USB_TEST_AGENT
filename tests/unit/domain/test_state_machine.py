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
        """[TC-STATE_MACHINE-001] Init default values - 테스트 시나리오를 검증한다.

            테스트 목적:
                Init default values 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_init_default_values 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-002] Update creates new instance - 테스트 시나리오를 검증한다.

            테스트 목적:
                Update creates new instance 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_update_creates_new_instance 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        ctx1 = SlotContext(slot_idx=0)
        ctx2 = ctx1.update(test_id="test-123", current_loop=5)

        assert ctx1.test_id is None
        assert ctx1.current_loop == 0
        assert ctx2.test_id == "test-123"
        assert ctx2.current_loop == 5
        assert ctx1 is not ctx2

    def test_reset_clears_values(self):
        """[TC-STATE_MACHINE-003] Reset clears values - 테스트 시나리오를 검증한다.

            테스트 목적:
                Reset clears values 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_reset_clears_values 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-004] Progress percent - 테스트 시나리오를 검증한다.

            테스트 목적:
                Progress percent 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_progress_percent 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        ctx = SlotContext(slot_idx=0, current_loop=5, total_loop=10)
        assert ctx.get_progress_percent() == 50.0

        ctx_zero = SlotContext(slot_idx=0, current_loop=0, total_loop=0)
        assert ctx_zero.get_progress_percent() == 0.0

    def test_to_dict(self):
        """[TC-STATE_MACHINE-005] To dict - 테스트 시나리오를 검증한다.

            테스트 목적:
                To dict 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_to_dict 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-006] Initial state is idle - 테스트 시나리오를 검증한다.

            테스트 목적:
                Initial state is idle 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_initial_state_is_idle 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)
        assert machine.state == SlotState.IDLE

    def test_custom_initial_state(self):
        """[TC-STATE_MACHINE-007] Custom initial state - 테스트 시나리오를 검증한다.

            테스트 목적:
                Custom initial state 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_custom_initial_state 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0, initial_state=SlotState.READY)
        assert machine.state == SlotState.READY

    def test_valid_transition_idle_to_preparing(self):
        """[TC-STATE_MACHINE-008] Valid transition idle to preparing - 테스트 시나리오를 검증한다.

            테스트 목적:
                Valid transition idle to preparing 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_valid_transition_idle_to_preparing 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        new_state = machine.trigger(SlotEvent.START_TEST)

        assert new_state == SlotState.PREPARING
        assert machine.state == SlotState.PREPARING

    def test_valid_transition_sequence(self):
        """[TC-STATE_MACHINE-009] Valid transition sequence - 테스트 시나리오를 검증한다.

            테스트 목적:
                Valid transition sequence 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_valid_transition_sequence 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        assert machine.state == SlotState.PREPARING

        machine.trigger(SlotEvent.CONFIGURE)
        assert machine.state == SlotState.CONFIGURING

        machine.trigger(SlotEvent.RUN)
        assert machine.state == SlotState.RUNNING

    def test_invalid_transition_raises_error(self):
        """[TC-STATE_MACHINE-010] Invalid transition raises error - 테스트 시나리오를 검증한다.

            테스트 목적:
                Invalid transition raises error 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_invalid_transition_raises_error 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        with pytest.raises(InvalidTransitionError) as exc_info:
            machine.trigger(SlotEvent.RUN)  # Cannot RUN from IDLE

        assert exc_info.value.current_state == SlotState.IDLE
        assert exc_info.value.event == SlotEvent.RUN
        assert exc_info.value.slot_idx == 0

    def test_can_transition(self):
        """[TC-STATE_MACHINE-011] Can transition - 테스트 시나리오를 검증한다.

            테스트 목적:
                Can transition 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_can_transition 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        assert machine.can_transition(SlotEvent.START_TEST) is True
        assert machine.can_transition(SlotEvent.CONNECT) is True
        assert machine.can_transition(SlotEvent.RUN) is False
        assert machine.can_transition(SlotEvent.COMPLETE) is False

    def test_get_valid_events(self):
        """[TC-STATE_MACHINE-012] Get valid events - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get valid events 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_valid_events 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        valid_events = machine.get_valid_events()

        assert SlotEvent.START_TEST in valid_events
        assert SlotEvent.CONNECT in valid_events
        assert SlotEvent.RESET in valid_events
        assert SlotEvent.RUN not in valid_events

    def test_context_update_on_transition(self):
        """[TC-STATE_MACHINE-013] Context update on transition - 테스트 시나리오를 검증한다.

            테스트 목적:
                Context update on transition 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_context_update_on_transition 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(
            SlotEvent.START_TEST,
            context_update={"test_name": "Test 1"},
        )

        assert machine.context.test_name == "Test 1"
        assert machine.context.started_at is not None

    def test_error_message_on_error_transition(self):
        """[TC-STATE_MACHINE-014] Error message on error transition - 테스트 시나리오를 검증한다.

            테스트 목적:
                Error message on error transition 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_error_message_on_error_transition 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-015] Reset clears context - 테스트 시나리오를 검증한다.

            테스트 목적:
                Reset clears context 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_reset_clears_context 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-016] History is recorded - 테스트 시나리오를 검증한다.

            테스트 목적:
                History is recorded 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_history_is_recorded 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-017] State change callback - 테스트 시나리오를 검증한다.

            테스트 목적:
                State change callback 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_state_change_callback 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback_calls = []

        def callback(slot_idx, old_state, new_state):
            callback_calls.append((slot_idx, old_state, new_state))

        machine = SlotStateMachine(slot_idx=0, on_state_change=callback)
        machine.trigger(SlotEvent.START_TEST)

        assert len(callback_calls) == 1
        assert callback_calls[0] == (0, SlotState.IDLE, SlotState.PREPARING)

    def test_is_idle(self):
        """[TC-STATE_MACHINE-018] Is idle - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is idle 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_idle 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_idle() is True

        machine.trigger(SlotEvent.START_TEST)
        assert machine.is_idle() is False

    def test_is_busy(self):
        """[TC-STATE_MACHINE-019] Is busy - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is busy 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_busy 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_busy() is False

        machine.trigger(SlotEvent.START_TEST)
        assert machine.is_busy() is True

        machine.trigger(SlotEvent.ERROR)
        assert machine.is_busy() is False

    def test_is_running(self):
        """[TC-STATE_MACHINE-020] Is running - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is running 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_running 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_running() is False

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        assert machine.is_running() is True

    def test_is_terminal(self):
        """[TC-STATE_MACHINE-021] Is terminal - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is terminal 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_terminal 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)
        assert machine.is_terminal() is False

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.COMPLETE)
        assert machine.is_terminal() is True

    def test_force_state(self):
        """[TC-STATE_MACHINE-022] Force state - 테스트 시나리오를 검증한다.

            테스트 목적:
                Force state 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_force_state 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)
        machine.trigger(SlotEvent.START_TEST)

        machine.force_state(SlotState.IDLE, "Recovery")

        assert machine.state == SlotState.IDLE

    def test_to_dict(self):
        """[TC-STATE_MACHINE-023] To dict - 테스트 시나리오를 검증한다.

            테스트 목적:
                To dict 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_to_dict 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-024] Init creates machines for all slots - 테스트 시나리오를 검증한다.

            테스트 목적:
                Init creates machines for all slots 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_init_creates_machines_for_all_slots 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=8)

        assert manager.max_slots == 8
        for i in range(8):
            assert manager.get(i) is not None
            assert manager.get(i).slot_idx == i

    def test_getitem(self):
        """[TC-STATE_MACHINE-025] Getitem - 테스트 시나리오를 검증한다.

            테스트 목적:
                Getitem 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_getitem 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)

        machine = manager[0]
        assert machine.slot_idx == 0

    def test_getitem_invalid_raises_keyerror(self):
        """[TC-STATE_MACHINE-026] Getitem invalid raises keyerror - 테스트 시나리오를 검증한다.

            테스트 목적:
                Getitem invalid raises keyerror 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_getitem_invalid_raises_keyerror 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)

        with pytest.raises(KeyError):
            _ = manager[10]

    def test_trigger(self):
        """[TC-STATE_MACHINE-027] Trigger - 테스트 시나리오를 검증한다.

            테스트 목적:
                Trigger 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_trigger 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)

        new_state = manager.trigger(0, SlotEvent.START_TEST)

        assert new_state == SlotState.PREPARING
        assert manager[0].state == SlotState.PREPARING

    def test_get_all_states(self):
        """[TC-STATE_MACHINE-028] Get all states - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get all states 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_all_states 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        states = manager.get_all_states()

        assert states[0] == SlotState.PREPARING
        assert states[1] == SlotState.CONNECTING
        assert states[2] == SlotState.IDLE
        assert states[3] == SlotState.IDLE

    def test_get_busy_slots(self):
        """[TC-STATE_MACHINE-029] Get busy slots - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get busy slots 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_busy_slots 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        busy = manager.get_busy_slots()

        assert 0 in busy
        assert 1 in busy
        assert 2 not in busy

    def test_get_running_slots(self):
        """[TC-STATE_MACHINE-030] Get running slots - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get running slots 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_running_slots 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(0, SlotEvent.CONFIGURE)
        manager.trigger(0, SlotEvent.RUN)

        running = manager.get_running_slots()

        assert 0 in running
        assert 1 not in running

    def test_get_idle_slots(self):
        """[TC-STATE_MACHINE-031] Get idle slots - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get idle slots 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_idle_slots 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)

        idle = manager.get_idle_slots()

        assert 0 not in idle
        assert 1 in idle
        assert 2 in idle
        assert 3 in idle

    def test_reset_all(self):
        """[TC-STATE_MACHINE-032] Reset all - 테스트 시나리오를 검증한다.

            테스트 목적:
                Reset all 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_reset_all 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=4)
        manager.trigger(0, SlotEvent.START_TEST)
        manager.trigger(1, SlotEvent.CONNECT)

        manager.reset_all()

        assert manager[0].state == SlotState.IDLE
        assert manager[1].state == SlotState.IDLE

    def test_to_dict(self):
        """[TC-STATE_MACHINE-033] To dict - 테스트 시나리오를 검증한다.

            테스트 목적:
                To dict 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_to_dict 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = SlotStateMachineManager(max_slots=2)
        manager.trigger(0, SlotEvent.START_TEST)

        data = manager.to_dict()

        assert data["max_slots"] == 2
        assert 0 in data["busy_slots"]
        assert 1 in data["idle_slots"]
        assert "slots" in data
        assert len(data["slots"]) == 2

    def test_callback_propagation(self):
        """[TC-STATE_MACHINE-034] Callback propagation - 테스트 시나리오를 검증한다.

            테스트 목적:
                Callback propagation 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_callback_propagation 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-035] Full success path - 테스트 시나리오를 검증한다.

            테스트 목적:
                Full success path 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_full_success_path 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-036] Fail during running - 테스트 시나리오를 검증한다.

            테스트 목적:
                Fail during running 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_fail_during_running 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.FAIL, error_message="Test failed")

        assert machine.state == SlotState.FAILED
        assert machine.context.error_message == "Test failed"

    def test_stop_during_running(self):
        """[TC-STATE_MACHINE-037] Stop during running - 테스트 시나리오를 검증한다.

            테스트 목적:
                Stop during running 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_stop_during_running 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.STOP)

        assert machine.state == SlotState.STOPPING

        machine.trigger(SlotEvent.STOPPED)
        assert machine.state == SlotState.IDLE

    def test_retry_after_failure(self):
        """[TC-STATE_MACHINE-038] Retry after failure - 테스트 시나리오를 검증한다.

            테스트 목적:
                Retry after failure 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_retry_after_failure 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.FAIL)
        assert machine.state == SlotState.FAILED

        machine.trigger(SlotEvent.RETRY)
        assert machine.state == SlotState.PREPARING

    def test_reset_after_error(self):
        """[TC-STATE_MACHINE-039] Reset after error - 테스트 시나리오를 검증한다.

            테스트 목적:
                Reset after error 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_reset_after_error 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.ERROR)
        assert machine.state == SlotState.ERROR

        machine.trigger(SlotEvent.RESET)
        assert machine.state == SlotState.IDLE

    def test_pause_and_resume(self):
        """[TC-STATE_MACHINE-040] Pause and resume - 테스트 시나리오를 검증한다.

            테스트 목적:
                Pause and resume 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_pause_and_resume 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        machine = SlotStateMachine(slot_idx=0)

        machine.trigger(SlotEvent.START_TEST)
        machine.trigger(SlotEvent.CONFIGURE)
        machine.trigger(SlotEvent.RUN)
        machine.trigger(SlotEvent.PAUSE)

        assert machine.state == SlotState.PAUSED

        machine.trigger(SlotEvent.RESUME)
        assert machine.state == SlotState.RUNNING

    def test_start_test_after_error(self):
        """[TC-STATE_MACHINE-041] Start test after error - 테스트 시나리오를 검증한다.

            테스트 목적:
                Start test after error 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_start_test_after_error 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
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
        """[TC-STATE_MACHINE-042] Start test after failed - 테스트 시나리오를 검증한다.

            테스트 목적:
                Start test after failed 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_start_test_after_failed 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
        """[TC-STATE_MACHINE-043] Start test after completed - 테스트 시나리오를 검증한다.

            테스트 목적:
                Start test after completed 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_start_test_after_completed 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
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
