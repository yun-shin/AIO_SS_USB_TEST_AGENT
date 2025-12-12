"""Tests for TestState Model."""

import pytest
from datetime import datetime
from domain.models import TestState
from config.constants import ProcessState, TestPhase


class TestTestState:
    """TestState 모델 테스트."""

    def test_create_default_state(self) -> None:
        """[TC-STATE-001] 기본 상태 생성 - 필수 기본값이 설정된다.

        테스트 목적:
            최소 입력으로 생성한 TestState의 기본 필드 값이 올바른지 검증한다.

        테스트 시나리오:
            Given: slot_idx만 전달해 TestState를 생성하고
            When: 생성된 객체의 초기 필드를 조회하면
            Then: process_state/test_phase는 UNKNOWN이고 loop 값은 0, is_active는 False다

        Notes:
            없음
        """
        state = TestState(slot_idx=0)
        assert state.slot_idx == 0
        assert state.process_state == ProcessState.UNKNOWN
        assert state.test_phase == TestPhase.UNKNOWN
        assert state.current_loop == 0
        assert state.is_active is False

    def test_update_immutability(self, sample_test_state: TestState) -> None:
        """[TC-STATE-002] 업데이트 불변성 - 기존 인스턴스는 유지된다.

        테스트 목적:
            update 호출 시 새로운 객체를 반환하며 원본 상태가 변경되지 않는지 확인한다.

        테스트 시나리오:
            Given: current_loop가 설정된 기존 TestState가 있고
            When: update(current_loop=5)를 호출하면
            Then: 반환 객체만 loop 값이 5로 변경되고 원본의 loop 값은 그대로다

        Notes:
            없음
        """
        original_loop = sample_test_state.current_loop
        new_state = sample_test_state.update(current_loop=5)

        assert sample_test_state.current_loop == original_loop  # 원본 불변
        assert new_state.current_loop == 5  # 새 인스턴스에 반영

    def test_increment_loop(self, sample_test_state: TestState) -> None:
        """[TC-STATE-003] 루프 증가 - 카운터가 1 증가한다.

        테스트 목적:
            increment_loop 호출 시 current_loop가 1 증가한 새 상태가 반환되는지 검증한다.

        테스트 시나리오:
            Given: current_loop가 설정된 TestState가 있고
            When: increment_loop를 호출하면
            Then: 반환된 상태의 current_loop가 원본 값 +1로 설정된다

        Notes:
            없음
        """
        new_state = sample_test_state.increment_loop()
        assert new_state.current_loop == sample_test_state.current_loop + 1

    def test_set_error(self, sample_test_state: TestState) -> None:
        """[TC-STATE-004] 오류 기록 - 카운트와 메시지가 누적된다.

        테스트 목적:
            set_error 호출 시 error_count가 증가하고 last_error가 설정되는지 확인한다.

        테스트 시나리오:
            Given: 오류 없는 TestState가 있고
            When: set_error(\"Test error occurred\")를 호출하면
            Then: 반환된 상태의 error_count는 1, last_error는 전달한 메시지로 설정된다

        Notes:
            없음
        """
        error_msg = "Test error occurred"
        new_state = sample_test_state.set_error(error_msg)

        assert new_state.error_count == 1
        assert new_state.last_error == error_msg
        assert sample_test_state.error_count == 0  # 원본 불변

    def test_clear_error(self, sample_test_state: TestState) -> None:
        """[TC-STATE-005] 오류 초기화 - 카운트와 메시지가 리셋된다.

        테스트 목적:
            clear_error가 error_count와 last_error를 초기화하는지 검증한다.

        테스트 시나리오:
            Given: set_error로 오류가 기록된 TestState가 있고
            When: clear_error를 호출하면
            Then: 반환된 상태에서 error_count는 0, last_error는 None으로 초기화된다

        Notes:
            없음
        """
        state_with_error = sample_test_state.set_error("Error")
        cleared_state = state_with_error.clear_error()

        assert cleared_state.error_count == 0
        assert cleared_state.last_error is None

    def test_is_completed(self) -> None:
        """[TC-STATE-006] 완료 판정 - current_loop가 total_loop에 도달하면 True.

        테스트 목적:
            루프 진행도가 총 루프 수에 도달했을 때 is_completed가 True를 반환하는지 확인한다.

        테스트 시나리오:
            Given: current_loop와 total_loop가 동일한 상태와 다른 상태를 준비하고
            When: 각 상태에서 is_completed를 호출하면
            Then: 동일한 경우 True, 진행 중인 경우 False를 반환한다

        Notes:
            없음
        """
        state = TestState(slot_idx=0, current_loop=10, total_loop=10)
        assert state.is_completed()

        state_not_done = TestState(slot_idx=0, current_loop=5, total_loop=10)
        assert not state_not_done.is_completed()

    def test_is_failed(self) -> None:
        """[TC-STATE-007] 실패 판정 - process_state FAIL일 때만 True.

        테스트 목적:
            process_state 값에 따라 is_failed 결과가 달라지는지 검증한다.

        테스트 시나리오:
            Given: process_state가 FAIL인 상태와 PASS인 상태를 준비하고
            When: 각 상태에서 is_failed를 호출하면
            Then: FAIL은 True, PASS는 False를 반환한다

        Notes:
            없음
        """
        state = TestState(slot_idx=0, process_state=ProcessState.FAIL)
        assert state.is_failed()

        state_pass = TestState(slot_idx=0, process_state=ProcessState.PASS)
        assert not state_pass.is_failed()

    def test_is_running(self) -> None:
        """[TC-STATE-008] 실행 중 판정 - TEST 상태이면서 활성일 때만 True.

        테스트 목적:
            process_state와 is_active 조합에 따라 is_running 반환값이 달라지는지 확인한다.

        테스트 시나리오:
            Given: process_state가 TEST이면서 is_active가 True/False인 상태를 준비하고
            When: is_running을 호출하면
            Then: 활성인 경우에만 True, 비활성인 경우 False를 반환한다

        Notes:
            없음
        """
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
        """[TC-STATE-009] 진행률 계산 - 루프 비율을 백분율로 계산한다.

        테스트 목적:
            current_loop/total_loop 비율이 올바른 백분율로 계산되는지 검증한다.

        테스트 시나리오:
            Given: total_loop가 10인 상태와 0인 상태를 준비하고
            When: get_progress_percent를 호출하면
            Then: 5/10은 50.0을, 0/0은 0.0을 반환한다

        Notes:
            없음
        """
        state = TestState(slot_idx=0, current_loop=5, total_loop=10)
        assert state.get_progress_percent() == 50.0

        state_zero = TestState(slot_idx=0, current_loop=0, total_loop=0)
        assert state_zero.get_progress_percent() == 0.0

    def test_to_dict_and_from_dict(self, sample_test_state: TestState) -> None:
        """[TC-STATE-010] 직렬화 왕복 - dict 변환 후 복원 시 값이 유지된다.

        테스트 목적:
            to_dict와 from_dict를 거쳐도 모든 필드가 손실 없이 복원되는지 검증한다.

        테스트 시나리오:
            Given: 필드가 채워진 TestState 인스턴스가 있고
            When: to_dict 후 from_dict로 복원하면
            Then: slot_idx, loop, is_active 등 모든 값이 원본과 동일하다

        Notes:
            없음
        """
        state_dict = sample_test_state.to_dict()
        restored = TestState.from_dict(state_dict)

        assert restored.slot_idx == sample_test_state.slot_idx
        assert restored.current_loop == sample_test_state.current_loop
        assert restored.total_loop == sample_test_state.total_loop
        assert restored.is_active == sample_test_state.is_active
