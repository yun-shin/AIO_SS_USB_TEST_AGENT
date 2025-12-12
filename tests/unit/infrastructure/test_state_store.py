"""Infrastructure State Store Unit Tests."""

import pytest
from datetime import datetime

from infrastructure.state_store import (
    InMemoryStateStore,
    FakeStateStore,
    SlotState,
)


class TestSlotState:
    """SlotState 데이터 클래스 테스트"""

    def test_default_values(self) -> None:
        """[TC-STATESTORE-001] 기본값 초기화 - 슬롯 상태가 idle로 시작된다.

        테스트 목적:
            SlotState 생성 시 기본 필드 값이 올바르게 설정되는지 확인한다.

        테스트 시나리오:
            Given: slot_idx만 지정해 SlotState를 생성하고
            When: 필드를 조회하면
            Then: status=idle, progress=0.0, current_phase/test_id/error_message가 None이다

        Notes:
            None
        """
        state = SlotState(slot_idx=0)

        assert state.slot_idx == 0
        assert state.status == "idle"
        assert state.progress == 0.0
        assert state.current_phase is None
        assert state.test_id is None
        assert state.error_message is None

    def test_to_dict(self) -> None:
        """[TC-STATESTORE-002] dict 변환 - 필드가 직렬화된다.

        테스트 목적:
            SlotState.to_dict 호출 시 주요 필드와 timestamp가 포함되는지 검증한다.

        테스트 시나리오:
            Given: status/progress/current_phase를 지정한 SlotState가 있고
            When: to_dict를 호출하면
            Then: 필드 값과 slot_idx가 동일하게 포함되며 last_updated 키가 존재한다

        Notes:
            None
        """
        state = SlotState(
            slot_idx=1,
            status="running",
            progress=50.0,
            current_phase="write",
        )

        result = state.to_dict()

        assert result["slot_idx"] == 1
        assert result["status"] == "running"
        assert result["progress"] == 50.0
        assert result["current_phase"] == "write"
        assert "last_updated" in result


class TestInMemoryStateStore:
    """InMemoryStateStore 테스트"""

    def test_initial_states(self) -> None:
        """[TC-STATESTORE-003] 초기 상태 - 모든 슬롯이 idle로 채워진다.

        테스트 목적:
            생성 시 각 슬롯의 초기 상태가 idle인지 확인한다.

        테스트 시나리오:
            Given: max_slots=4로 InMemoryStateStore를 생성하고
            When: 각 슬롯 상태를 조회하면
            Then: status가 모두 idle이다

        Notes:
            None
        """
        store = InMemoryStateStore(max_slots=4)

        for i in range(4):
            state = store.get_slot_state(i)
            assert state is not None
            assert state["status"] == "idle"

    def test_set_and_get_slot_state(self) -> None:
        """[TC-STATESTORE-004] 상태 설정/조회 - 저장한 값이 그대로 반환된다.

        테스트 목적:
            set_slot_state로 기록한 상태가 get_slot_state로 동일하게 읽히는지 검증한다.

        테스트 시나리오:
            Given: 슬롯 0에 status/progress를 설정하고
            When: get_slot_state(0)를 호출하면
            Then: 저장된 status와 progress 값이 반환된다

        Notes:
            None
        """
        store = InMemoryStateStore()

        store.set_slot_state(
            0,
            {
                "status": "running",
                "progress": 30.0,
            },
        )

        state = store.get_slot_state(0)
        assert state["status"] == "running"
        assert state["progress"] == 30.0

    def test_partial_update(self) -> None:
        """[TC-STATESTORE-005] 부분 업데이트 - 기존 필드는 유지된다.

        테스트 목적:
            일부 필드만 업데이트해도 다른 필드가 유지되는지 확인한다.

        테스트 시나리오:
            Given: status=running, progress=50.0인 상태를 저장하고
            When: progress만 75.0으로 업데이트하면
            Then: status는 running 그대로이고 progress만 75.0으로 변경된다

        Notes:
            None
        """
        store = InMemoryStateStore()
        store.set_slot_state(0, {"status": "running", "progress": 50.0})

        store.set_slot_state(0, {"progress": 75.0})

        state = store.get_slot_state(0)
        assert state["status"] == "running"
        assert state["progress"] == 75.0

    def test_get_all_states(self) -> None:
        """[TC-STATESTORE-006] 전체 상태 조회 - 모든 슬롯 상태를 리스트로 반환한다.

        테스트 목적:
            get_all_states가 슬롯 수만큼의 상태 딕셔너리를 반환하는지 검증한다.

        테스트 시나리오:
            Given: 3개 슬롯에 서로 다른 status를 설정하고
            When: get_all_states를 호출하면
            Then: 길이가 3인 리스트가 반환되고 각 status가 설정값과 동일하다

        Notes:
            None
        """
        store = InMemoryStateStore(max_slots=3)
        store.set_slot_state(0, {"status": "running"})
        store.set_slot_state(1, {"status": "idle"})
        store.set_slot_state(2, {"status": "completed"})

        all_states = store.get_all_states()

        assert len(all_states) == 3
        assert all_states[0]["status"] == "running"
        assert all_states[1]["status"] == "idle"
        assert all_states[2]["status"] == "completed"

    def test_reset_slot(self) -> None:
        """[TC-STATESTORE-007] 슬롯 리셋 - 상태/진행도가 초기화된다.

        테스트 목적:
            reset_slot 호출 시 해당 슬롯이 idle, progress=0.0으로 초기화되는지 확인한다.

        테스트 시나리오:
            Given: 슬롯 0에 running 상태를 기록하고
            When: reset_slot(0)을 호출하면
            Then: status는 idle, progress는 0.0으로 설정된다

        Notes:
            None
        """
        store = InMemoryStateStore()
        store.set_slot_state(0, {"status": "running", "progress": 50.0})

        store.reset_slot(0)

        state = store.get_slot_state(0)
        assert state["status"] == "idle"
        assert state["progress"] == 0.0

    def test_reset_all(self) -> None:
        """[TC-STATESTORE-008] 전체 리셋 - 모든 슬롯이 idle로 초기화된다.

        테스트 목적:
            reset_all이 모든 슬롯의 상태를 idle로 되돌리는지 검증한다.

        테스트 시나리오:
            Given: 3개 슬롯을 running으로 설정한 뒤
            When: reset_all을 호출하면
            Then: 모든 슬롯의 status가 idle이 된다

        Notes:
            None
        """
        store = InMemoryStateStore(max_slots=3)
        for i in range(3):
            store.set_slot_state(i, {"status": "running"})

        store.reset_all()

        for i in range(3):
            state = store.get_slot_state(i)
            assert state["status"] == "idle"

    def test_invalid_slot_index_raises(self) -> None:
        """[TC-STATESTORE-009] 잘못된 슬롯 인덱스 - ValueError를 발생시킨다.

        테스트 목적:
            인덱스 범위를 벗어난 set_slot_state 호출 시 ValueError가 발생하는지 확인한다.

        테스트 시나리오:
            Given: max_slots=4인 스토어에서
            When: 10 또는 -1 슬롯에 set_slot_state를 호출하면
            Then: ValueError가 발생한다

        Notes:
            None
        """
        store = InMemoryStateStore(max_slots=4)

        with pytest.raises(ValueError):
            store.set_slot_state(10, {"status": "running"})

        with pytest.raises(ValueError):
            store.set_slot_state(-1, {"status": "running"})


class TestFakeStateStore:
    """FakeStateStore 테스트"""

    def test_records_get_calls(self) -> None:
        """[TC-STATESTORE-010] get 호출 기록 - 호출 슬롯 인덱스를 저장한다.

        테스트 목적:
            FakeStateStore가 get_slot_state 호출 시 인덱스를 기록하는지 검증한다.

        테스트 시나리오:
            Given: 슬롯 0에 상태를 설정한 뒤
            When: 여러 번 get_slot_state를 호출하면
            Then: get_calls 리스트에 호출 순서대로 인덱스가 기록된다

        Notes:
            None
        """
        store = FakeStateStore()
        store.set_slot_state(0, {"status": "running"})

        store.get_slot_state(0)
        store.get_slot_state(1)
        store.get_slot_state(0)

        assert store.get_calls == [0, 1, 0]

    def test_records_set_calls(self) -> None:
        """[TC-STATESTORE-011] set 호출 기록 - 인덱스와 데이터가 저장된다.

        테스트 목적:
            set_slot_state 호출 시 인덱스와 전달 데이터가 기록되는지 확인한다.

        테스트 시나리오:
            Given: FakeStateStore 인스턴스가 있고
            When: set_slot_state를 두 번 호출하면
            Then: set_calls에 (인덱스, 데이터) 튜플이 순서대로 기록된다

        Notes:
            None
        """
        store = FakeStateStore()

        store.set_slot_state(0, {"status": "running"})
        store.set_slot_state(1, {"status": "idle"})

        assert len(store.set_calls) == 2
        assert store.set_calls[0] == (0, {"status": "running"})
        assert store.set_calls[1] == (1, {"status": "idle"})

    def test_clear_calls(self) -> None:
        """[TC-STATESTORE-012] 호출 기록 초기화 - get/set 기록을 모두 비운다.

        테스트 목적:
            clear_calls 호출 시 get_calls와 set_calls가 모두 초기화되는지 검증한다.

        테스트 시나리오:
            Given: get과 set을 호출해 기록을 남긴 뒤
            When: clear_calls를 호출하면
            Then: get_calls와 set_calls가 빈 리스트가 된다

        Notes:
            None
        """
        store = FakeStateStore()
        store.get_slot_state(0)
        store.set_slot_state(0, {"status": "running"})

        store.clear_calls()

        assert store.get_calls == []
        assert store.set_calls == []

    def test_get_returns_none_for_unset(self) -> None:
        """[TC-STATESTORE-013] 미설정 슬롯 조회 - None을 반환한다.

        테스트 목적:
            설정되지 않은 슬롯을 조회하면 None을 반환하는지 확인한다.

        테스트 시나리오:
            Given: FakeStateStore에 특정 슬롯을 설정하지 않고
            When: get_slot_state(99)를 호출하면
            Then: None을 반환한다

        Notes:
            None
        """
        store = FakeStateStore()

        result = store.get_slot_state(99)

        assert result is None
