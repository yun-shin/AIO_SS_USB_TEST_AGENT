"""Tests for TestState Model."""

import pytest
from datetime import datetime
from src.domain.models import TestState
from src.config.constants import ProcessState, TestPhase


class TestTestState:
    """TestState 모델 테스트."""

    def test_create_default_state(self) -> None:
        """기본 상태 생성 테스트."""
        state = TestState(slot_idx=0)
        assert state.slot_idx == 0
        assert state.process_state == ProcessState.UNKNOWN
        assert state.test_phase == TestPhase.UNKNOWN
        assert state.current_loop == 0
        assert state.is_active is False

    def test_update_immutability(self, sample_test_state: TestState) -> None:
        """상태 업데이트 불변성 테스트."""
        original_loop = sample_test_state.current_loop
        new_state = sample_test_state.update(current_loop=5)

        assert sample_test_state.current_loop == original_loop  # 원본 불변
        assert new_state.current_loop == 5  # 새 인스턴스에 반영

    def test_increment_loop(self, sample_test_state: TestState) -> None:
        """루프 증가 테스트."""
        new_state = sample_test_state.increment_loop()
        assert new_state.current_loop == sample_test_state.current_loop + 1

    def test_set_error(self, sample_test_state: TestState) -> None:
        """에러 설정 테스트."""
        error_msg = "Test error occurred"
        new_state = sample_test_state.set_error(error_msg)

        assert new_state.error_count == 1
        assert new_state.last_error == error_msg
        assert sample_test_state.error_count == 0  # 원본 불변

    def test_clear_error(self, sample_test_state: TestState) -> None:
        """에러 클리어 테스트."""
        state_with_error = sample_test_state.set_error("Error")
        cleared_state = state_with_error.clear_error()

        assert cleared_state.error_count == 0
        assert cleared_state.last_error is None

    def test_is_completed(self) -> None:
        """완료 상태 확인 테스트."""
        state = TestState(slot_idx=0, current_loop=10, total_loop=10)
        assert state.is_completed()

        state_not_done = TestState(slot_idx=0, current_loop=5, total_loop=10)
        assert not state_not_done.is_completed()

    def test_is_failed(self) -> None:
        """실패 상태 확인 테스트."""
        state = TestState(slot_idx=0, process_state=ProcessState.FAIL)
        assert state.is_failed()

        state_pass = TestState(slot_idx=0, process_state=ProcessState.PASS)
        assert not state_pass.is_failed()

    def test_is_running(self) -> None:
        """실행 중 상태 확인 테스트."""
        state = TestState(
            slot_idx=0,
            process_state=ProcessState.TEST,
            is_active=True,
        )
        assert state.is_running()

        state_inactive = TestState(
            slot_idx=0,
            process_state=ProcessState.TEST,
            is_active=False,
        )
        assert not state_inactive.is_running()

    def test_get_progress_percent(self) -> None:
        """진행률 계산 테스트."""
        state = TestState(slot_idx=0, current_loop=5, total_loop=10)
        assert state.get_progress_percent() == 50.0

        state_zero = TestState(slot_idx=0, current_loop=0, total_loop=0)
        assert state_zero.get_progress_percent() == 0.0

    def test_to_dict_and_from_dict(self, sample_test_state: TestState) -> None:
        """딕셔너리 변환 테스트."""
        state_dict = sample_test_state.to_dict()
        restored = TestState.from_dict(state_dict)

        assert restored.slot_idx == sample_test_state.slot_idx
        assert restored.current_loop == sample_test_state.current_loop
        assert restored.total_loop == sample_test_state.total_loop
        assert restored.is_active == sample_test_state.is_active
