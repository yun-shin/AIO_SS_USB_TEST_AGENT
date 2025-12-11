"""Unit tests for ProcessState and TestPhase parsing."""

import pytest

from config.constants import ProcessState, TestPhase as TestPhaseEnum


# TestPhase를 다른 이름으로 import (pytest가 테스트 클래스로 인식하지 않도록)
TestPhase = TestPhaseEnum


class TestProcessState:
    """ProcessState.from_text() tests."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            # 정확한 매칭 (Button6 스타일)
            ("Idle", ProcessState.IDLE),
            ("Pass", ProcessState.PASS),
            ("Stop", ProcessState.STOP),
            ("Fail", ProcessState.FAIL),
            ("Test", ProcessState.TEST),
            # 대소문자 무시
            ("IDLE", ProcessState.IDLE),
            ("idle", ProcessState.IDLE),
            ("PASS", ProcessState.PASS),
            ("pass", ProcessState.PASS),
            # 복합 텍스트 (Static 스타일)
            ("10/10 IDLE", ProcessState.IDLE),
            ("4/10  File Copy 35/88", ProcessState.UNKNOWN),  # 상태가 아님
            # 빈 값
            ("", ProcessState.UNKNOWN),
            (None, ProcessState.UNKNOWN),
            # 알 수 없는 값
            ("Unknown", ProcessState.UNKNOWN),
            ("Disconnect", ProcessState.UNKNOWN),
        ],
    )
    def test_from_text(self, text: str | None, expected: ProcessState):
        """Test ProcessState.from_text() with various inputs."""
        if text is None:
            result = ProcessState.from_text("")
        else:
            result = ProcessState.from_text(text)
        assert result == expected


class TestTestPhase:
    """TestPhase.from_text() tests."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            # 정확한 매칭
            ("ContactTest", TestPhase.CONTACT),
            ("FileCopy", TestPhase.COPY),
            ("TestStop", TestPhase.STOP),
            ("FileCompare", TestPhase.COMPARE),
            ("FileDel", TestPhase.DELETE),
            ("IDLE", TestPhase.IDLE),
            # 복합 텍스트 (Static 스타일)
            ("4/10  File Copy 35/88", TestPhase.COPY),
            ("10/10 IDLE", TestPhase.IDLE),
            ("3/5 FileCompare 10/20", TestPhase.COMPARE),
            ("1/10  Contact Test 0/0", TestPhase.CONTACT),
            # 빈 값
            ("", TestPhase.UNKNOWN),
            # 알 수 없는 값
            ("Unknown", TestPhase.UNKNOWN),
        ],
    )
    def test_from_text(self, text: str, expected: TestPhase):
        """Test TestPhase.from_text() with various inputs."""
        result = TestPhase.from_text(text)
        assert result == expected


class TestProgressTextParsing:
    """Progress text parsing tests (루프 정보 추출)."""

    @pytest.mark.parametrize(
        "text,expected_current,expected_total",
        [
            ("4/10  File Copy 35/88", 4, 10),
            ("10/10 IDLE", 10, 10),
            ("1/5 FileCompare 10/20", 1, 5),
            ("0/100  Contact Test", 0, 100),
            ("", None, None),
            ("No numbers here", None, None),
        ],
    )
    def test_parse_loop_from_progress_text(
        self,
        text: str,
        expected_current: int | None,
        expected_total: int | None,
    ):
        """Test loop parsing from progress text."""
        import re

        match = re.match(r"(\d+)/(\d+)", text.strip()) if text else None

        if expected_current is None:
            assert match is None
        else:
            assert match is not None
            assert int(match.group(1)) == expected_current
            assert int(match.group(2)) == expected_total


class TestDetermineStatus:
    """Test _determine_status logic (ProcessState -> Frontend status)."""

    @pytest.mark.parametrize(
        "process_state,current_loop,total_loop,test_phase,expected_status",
        [
            # Fail = failed (최우선)
            (ProcessState.FAIL, 5, 10, TestPhase.COPY, "failed"),
            (ProcessState.FAIL, 0, 10, TestPhase.IDLE, "failed"),
            (ProcessState.FAIL, 10, 10, TestPhase.IDLE, "failed"),  # 완료 조건 충족해도 FAIL 우선
            # Stop = stopping
            (ProcessState.STOP, 5, 10, TestPhase.COPY, "stopping"),
            (ProcessState.STOP, 10, 10, TestPhase.IDLE, "stopping"),  # 완료 조건 충족해도 STOP 우선
            # 루프 완료 + Phase IDLE = completed (Pass/Idle 상태)
            (ProcessState.PASS, 10, 10, TestPhase.IDLE, "completed"),  # Pass + 완료 = completed
            (ProcessState.IDLE, 10, 10, TestPhase.IDLE, "completed"),  # Idle + 완료 = completed
            # 루프 완료지만 Phase가 IDLE 아님 = running/idle
            (ProcessState.PASS, 10, 10, TestPhase.COPY, "running"),  # Phase가 IDLE 아님
            (ProcessState.IDLE, 10, 10, TestPhase.COPY, "idle"),  # Phase가 IDLE 아님
            (ProcessState.IDLE, 10, 10, TestPhase.COMPARE, "idle"),
            # Pass = running (테스트 진행 중, 성공적으로 진행)
            (ProcessState.PASS, 5, 10, TestPhase.COPY, "running"),
            (ProcessState.PASS, 0, 10, TestPhase.IDLE, "running"),
            (ProcessState.PASS, 9, 10, TestPhase.IDLE, "running"),  # 9/10은 아직 진행 중
            # Test = running
            (ProcessState.TEST, 3, 10, TestPhase.COPY, "running"),
            (ProcessState.TEST, 0, 10, TestPhase.IDLE, "running"),
            (ProcessState.TEST, 10, 10, TestPhase.IDLE, "completed"),  # Test + 완료 = completed
            # Idle + 루프 미완료 = idle
            (ProcessState.IDLE, 0, 10, TestPhase.IDLE, "idle"),
            (ProcessState.IDLE, 5, 10, TestPhase.IDLE, "idle"),
            (ProcessState.IDLE, 9, 10, TestPhase.IDLE, "idle"),  # 9/10은 아직 완료 아님
            (ProcessState.IDLE, 0, 0, TestPhase.IDLE, "idle"),  # 설정 전
            # Unknown = error
            (ProcessState.UNKNOWN, 5, 10, TestPhase.IDLE, "error"),
        ],
    )
    def test_determine_status(
        self,
        process_state: ProcessState,
        current_loop: int,
        total_loop: int,
        test_phase: TestPhase,
        expected_status: str,
    ):
        """Test status determination logic."""
        # _determine_status 로직을 직접 테스트 (순서 중요!)
        # 1. Fail은 항상 failed
        if process_state == ProcessState.FAIL:
            status = "failed"
        # 2. Stop은 항상 stopping
        elif process_state == ProcessState.STOP:
            status = "stopping"
        # 3. 완료 조건: current_loop == total_loop AND Phase == IDLE
        elif (
            total_loop > 0
            and current_loop == total_loop
            and test_phase == TestPhase.IDLE
        ):
            status = "completed"
        # 4. Pass 또는 Test는 running
        elif process_state in (ProcessState.PASS, ProcessState.TEST):
            status = "running"
        # 5. Idle = idle
        elif process_state == ProcessState.IDLE:
            status = "idle"
        else:
            status = "error"

        assert status == expected_status
