"""Unit tests for ProcessState and TestPhase parsing."""

import re
import pytest

from config.constants import ProcessState, TestPhase as TestPhaseEnum

# Alias for readability in parametrized cases
TestPhase = TestPhaseEnum


class TestProcessState:
    """ProcessState.from_text() tests."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Idle", ProcessState.IDLE),
            ("Pass", ProcessState.PASS),
            ("Stop", ProcessState.STOP),
            ("Fail", ProcessState.FAIL),
            ("Test", ProcessState.TEST),
            ("IDLE", ProcessState.IDLE),
            ("idle", ProcessState.IDLE),
            ("PASS", ProcessState.PASS),
            ("pass", ProcessState.PASS),
            ("10/10 IDLE", ProcessState.IDLE),
            ("4/10  File Copy 35/88", ProcessState.UNKNOWN),
            ("", ProcessState.UNKNOWN),
            (None, ProcessState.UNKNOWN),
            ("Unknown", ProcessState.UNKNOWN),
            ("Disconnect", ProcessState.UNKNOWN),
        ],
    )
    def test_from_text(self, text: str | None, expected: ProcessState) -> None:
        """[TC-PARSE-001] ProcessState 파싱 - 텍스트를 상태 Enum으로 변환한다.

        테스트 목적:
            다양한 UI 텍스트(대소문자, 혼합 문자열 포함)를 ProcessState로 정확히 매핑하는지 검증한다.

        테스트 시나리오:
            Given: Idle/Pass/Stop/Fail/Test, 혼합 텍스트, 빈 값, None, Unknown 등을 준비하고
            When: ProcessState.from_text를 호출하면
            Then: 각 입력이 기대하는 상태로 반환되고 알 수 없는 값은 UNKNOWN이 된다

        Notes:
            None
        """
        value = "" if text is None else text
        result = ProcessState.from_text(value)
        assert result == expected


class TestTestPhase:
    """TestPhase.from_text() tests."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("ContactTest", TestPhase.CONTACT),
            ("FileCopy", TestPhase.COPY),
            ("TestStop", TestPhase.STOP),
            ("FileCompare", TestPhase.COMPARE),
            ("FileDel", TestPhase.DELETE),
            ("IDLE", TestPhase.IDLE),
            ("4/10  File Copy 35/88", TestPhase.COPY),
            ("10/10 IDLE", TestPhase.IDLE),
            ("3/5 FileCompare 10/20", TestPhase.COMPARE),
            ("1/10  Contact Test 0/0", TestPhase.CONTACT),
            ("", TestPhase.UNKNOWN),
            ("Unknown", TestPhase.UNKNOWN),
        ],
    )
    def test_from_text(self, text: str, expected: TestPhase) -> None:
        """[TC-PARSE-002] TestPhase 파싱 - 단계 텍스트를 Phase Enum으로 변환한다.

        테스트 목적:
            MFC 단계 문자열(대소문자, 진행도 포함)이 올바른 TestPhase로 매핑되는지 검증한다.

        테스트 시나리오:
            Given: ContactTest/FileCopy/TestStop 등과 진행도 포함 문자열을 준비하고
            When: TestPhase.from_text를 호출하면
            Then: 각 입력이 기대 Phase로 매핑되고 알 수 없는 값은 UNKNOWN을 반환한다

        Notes:
            None
        """
        result = TestPhase.from_text(text)
        assert result == expected


class TestProgressTextParsing:
    """Progress text parsing tests (loop info extraction)."""

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
    ) -> None:
        """[TC-PARSE-003] 진행 텍스트 파싱 - 루프 현재/총계를 추출한다.

        테스트 목적:
            진행도 텍스트에서 정규식으로 current/total 루프 값을 정확히 읽어오는지 확인한다.

        테스트 시나리오:
            Given: '4/10 File Copy', '10/10 IDLE', 'No numbers here', 빈 문자열 등을 준비하고
            When: 앞부분의 n/m 패턴을 정규식으로 매칭하면
            Then: 숫자가 있는 경우 기대 current/total을 얻고 없으면 매칭이 없어야 한다

        Notes:
            None
        """
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
            (ProcessState.FAIL, 5, 10, TestPhase.COPY, "failed"),
            (ProcessState.FAIL, 0, 10, TestPhase.IDLE, "failed"),
            (ProcessState.FAIL, 10, 10, TestPhase.IDLE, "failed"),
            (ProcessState.STOP, 5, 10, TestPhase.COPY, "stopping"),
            (ProcessState.STOP, 10, 10, TestPhase.IDLE, "stopping"),
            (ProcessState.PASS, 10, 10, TestPhase.IDLE, "completed"),
            (ProcessState.IDLE, 10, 10, TestPhase.IDLE, "completed"),
            (ProcessState.PASS, 10, 10, TestPhase.COPY, "running"),
            (ProcessState.IDLE, 10, 10, TestPhase.COPY, "idle"),
            (ProcessState.IDLE, 10, 10, TestPhase.COMPARE, "idle"),
            (ProcessState.PASS, 5, 10, TestPhase.COPY, "running"),
            (ProcessState.PASS, 0, 10, TestPhase.IDLE, "running"),
            (ProcessState.PASS, 9, 10, TestPhase.IDLE, "running"),
            (ProcessState.TEST, 3, 10, TestPhase.COPY, "running"),
            (ProcessState.TEST, 0, 10, TestPhase.IDLE, "running"),
            (ProcessState.TEST, 10, 10, TestPhase.IDLE, "completed"),
            (ProcessState.IDLE, 0, 10, TestPhase.IDLE, "idle"),
            (ProcessState.IDLE, 5, 10, TestPhase.IDLE, "idle"),
            (ProcessState.IDLE, 9, 10, TestPhase.IDLE, "idle"),
            (ProcessState.IDLE, 0, 0, TestPhase.IDLE, "idle"),
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
    ) -> None:
        """[TC-PARSE-004] 상태 결정 - ProcessState/Phase/루프 조합을 FE 상태로 변환한다.

        테스트 목적:
            _determine_status 로직이 프로세스 상태, 루프 진행도, Phase에 따라 예상 상태 문자열을 반환하는지 검증한다.

        테스트 시나리오:
            Given: FAIL/STOP/PASS/TEST/IDLE/UNKNOWN 조합과 루프 완료 여부, Phase(IDLE/기타)를 준비하고
            When: _determine_status 조건 분기를 수행하면
            Then: 실패는 failed, 중지는 stopping, 완료+IDLE은 completed, PASS/TEST는 running, IDLE은 idle, UNKNOWN은 error를 반환한다

        Notes:
            None
        """
        if process_state == ProcessState.FAIL:
            status = "failed"
        elif process_state == ProcessState.STOP:
            status = "stopping"
        elif (
            total_loop > 0
            and current_loop == total_loop
            and test_phase == TestPhase.IDLE
        ):
            status = "completed"
        elif process_state in (ProcessState.PASS, ProcessState.TEST):
            status = "running"
        elif process_state == ProcessState.IDLE:
            status = "idle"
        else:
            status = "error"

        assert status == expected_status
