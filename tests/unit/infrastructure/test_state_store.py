"""Infrastructure State Store Unit Tests.

StateStore 구현체들의 단위 테스트입니다.
"""

import pytest
from datetime import datetime

from src.infrastructure.state_store import (
    InMemoryStateStore,
    FakeStateStore,
    SlotState,
)


class TestSlotState:
    """SlotState 데이터클래스 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        # When
        state = SlotState(slot_idx=0)

        # Then
        assert state.slot_idx == 0
        assert state.status == "idle"
        assert state.progress == 0.0
        assert state.current_phase is None
        assert state.test_id is None
        assert state.error_message is None

    def test_to_dict(self):
        """딕셔너리 변환."""
        # Given
        state = SlotState(
            slot_idx=1,
            status="running",
            progress=50.0,
            current_phase="write",
        )

        # When
        result = state.to_dict()

        # Then
        assert result["slot_idx"] == 1
        assert result["status"] == "running"
        assert result["progress"] == 50.0
        assert result["current_phase"] == "write"
        assert "last_updated" in result


class TestInMemoryStateStore:
    """InMemoryStateStore 테스트."""

    def test_initial_states(self):
        """초기 상태."""
        # When
        store = InMemoryStateStore(max_slots=4)

        # Then
        for i in range(4):
            state = store.get_slot_state(i)
            assert state is not None
            assert state["status"] == "idle"

    def test_set_and_get_slot_state(self):
        """상태 설정 및 조회."""
        # Given
        store = InMemoryStateStore()

        # When
        store.set_slot_state(0, {
            "status": "running",
            "progress": 30.0,
        })

        # Then
        state = store.get_slot_state(0)
        assert state["status"] == "running"
        assert state["progress"] == 30.0

    def test_partial_update(self):
        """부분 업데이트."""
        # Given
        store = InMemoryStateStore()
        store.set_slot_state(0, {"status": "running", "progress": 50.0})

        # When: progress만 업데이트
        store.set_slot_state(0, {"progress": 75.0})

        # Then: status 유지
        state = store.get_slot_state(0)
        assert state["status"] == "running"
        assert state["progress"] == 75.0

    def test_get_all_states(self):
        """모든 상태 조회."""
        # Given
        store = InMemoryStateStore(max_slots=3)
        store.set_slot_state(0, {"status": "running"})
        store.set_slot_state(1, {"status": "idle"})
        store.set_slot_state(2, {"status": "completed"})

        # When
        all_states = store.get_all_states()

        # Then
        assert len(all_states) == 3
        assert all_states[0]["status"] == "running"
        assert all_states[1]["status"] == "idle"
        assert all_states[2]["status"] == "completed"

    def test_reset_slot(self):
        """슬롯 초기화."""
        # Given
        store = InMemoryStateStore()
        store.set_slot_state(0, {"status": "running", "progress": 50.0})

        # When
        store.reset_slot(0)

        # Then
        state = store.get_slot_state(0)
        assert state["status"] == "idle"
        assert state["progress"] == 0.0

    def test_reset_all(self):
        """전체 초기화."""
        # Given
        store = InMemoryStateStore(max_slots=3)
        for i in range(3):
            store.set_slot_state(i, {"status": "running"})

        # When
        store.reset_all()

        # Then
        for i in range(3):
            state = store.get_slot_state(i)
            assert state["status"] == "idle"

    def test_invalid_slot_index_raises(self):
        """잘못된 슬롯 인덱스에서 예외."""
        # Given
        store = InMemoryStateStore(max_slots=4)

        # When/Then
        with pytest.raises(ValueError):
            store.set_slot_state(10, {"status": "running"})

        with pytest.raises(ValueError):
            store.set_slot_state(-1, {"status": "running"})


class TestFakeStateStore:
    """FakeStateStore 테스트."""

    def test_records_get_calls(self):
        """get 호출 기록."""
        # Given
        store = FakeStateStore()
        store.set_slot_state(0, {"status": "running"})

        # When
        store.get_slot_state(0)
        store.get_slot_state(1)
        store.get_slot_state(0)

        # Then
        assert store.get_calls == [0, 1, 0]

    def test_records_set_calls(self):
        """set 호출 기록."""
        # Given
        store = FakeStateStore()

        # When
        store.set_slot_state(0, {"status": "running"})
        store.set_slot_state(1, {"status": "idle"})

        # Then
        assert len(store.set_calls) == 2
        assert store.set_calls[0] == (0, {"status": "running"})
        assert store.set_calls[1] == (1, {"status": "idle"})

    def test_clear_calls(self):
        """호출 기록 초기화."""
        # Given
        store = FakeStateStore()
        store.get_slot_state(0)
        store.set_slot_state(0, {"status": "running"})

        # When
        store.clear_calls()

        # Then
        assert store.get_calls == []
        assert store.set_calls == []

    def test_get_returns_none_for_unset(self):
        """설정되지 않은 슬롯은 None 반환."""
        # Given
        store = FakeStateStore()

        # When
        result = store.get_slot_state(99)

        # Then
        assert result is None
