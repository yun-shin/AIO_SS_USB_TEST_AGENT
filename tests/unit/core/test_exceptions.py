"""Exception Unit Tests.

예외 클래스들의 단위 테스트입니다.
"""

import pytest

from core.exceptions import (
    AgentError,
    AgentConnectionError,
    WebSocketConnectionError,
    WindowNotFoundError,
    ControlNotFoundError,
    TestExecutionError,
    TestStartError,
    TestTimeoutError,
    TestHangError,
    ConfigurationError,
    InvalidStateError,
)


class TestAgentError:
    """AgentError 기본 테스트."""

    def test_message_only(self):
        """[TC-EXC-001] 기본 메시지 - 전달한 메시지가 저장된다.

        테스트 목적:
            AgentError가 메시지만 전달했을 때 message/str이 그대로 유지되는지 확인한다.

        테스트 시나리오:
            Given: 메시지 문자열만 넣어 AgentError를 생성하고
            When: str(error)와 error.message를 조회하면
            Then: 동일한 메시지를 반환하고 details는 빈 dict, cause는 None이다

        Notes:
            없음
        """
        # When
        error = AgentError("Test error")

        # Then
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}
        assert error.cause is None

    def test_with_details(self):
        """[TC-EXC-002] 부가 정보 포함 - details가 메시지에 반영된다.

        테스트 목적:
            details를 전달하면 에러 객체와 문자열 표현에 키가 포함되는지 검증한다.

        테스트 시나리오:
            Given: details={'key': 'value'}로 AgentError를 생성하고
            When: str(error)와 error.details를 확인하면
            Then: 문자열에 key가 포함되고 details는 전달한 dict와 동일하다

        Notes:
            없음
        """
        # When
        error = AgentError("Test error", details={"key": "value"})

        # Then
        assert "key" in str(error)
        assert error.details == {"key": "value"}

    def test_with_cause(self):
        """[TC-EXC-003] 원인 예외 포함 - cause가 유지된다.

        테스트 목적:
            cause를 전달했을 때 내부 속성과 문자열에 원인 메시지가 포함되는지 확인한다.

        테스트 시나리오:
            Given: ValueError를 cause로 전달해 AgentError를 생성하고
            When: str(error)를 확인하고 error.cause를 조회하면
            Then: 문자열에 원인 메시지가 포함되고 cause는 전달한 예외 객체다

        Notes:
            없음
        """
        # Given
        original_error = ValueError("Original error")

        # When
        error = AgentError("Wrapped error", cause=original_error)

        # Then
        assert "Original error" in str(error)
        assert error.cause is original_error

    def test_to_dict(self):
        """[TC-EXC-004] dict 변환 - 타입/메시지/세부정보가 포함된다.

        테스트 목적:
            to_dict 결과에 error_type, message, details, cause 문자열이 포함되는지 검증한다.

        테스트 시나리오:
            Given: details와 cause가 있는 AgentError를 생성하고
            When: to_dict를 호출하면
            Then: error_type은 클래스명, message와 details가 그대로 포함되고 cause 키도 존재한다

        Notes:
            없음
        """
        # Given
        error = AgentError(
            "Test error",
            details={"slot_idx": 0},
            cause=ValueError("cause"),
        )

        # When
        result = error.to_dict()

        # Then
        assert result["error_type"] == "AgentError"
        assert result["message"] == "Test error"
        assert result["details"] == {"slot_idx": 0}
        assert "cause" in result["cause"]


class TestConnectionErrors:
    """연결 관련 예외 테스트."""

    def test_websocket_connection_error(self):
        """[TC-EXC-005] WebSocket 연결 오류 - URL 정보가 세부정보에 담긴다.

        테스트 목적:
            WebSocketConnectionError 생성 시 url이 details에 저장되고 메시지에 포함되는지 확인한다.

        테스트 시나리오:
            Given: url 값을 전달해 WebSocketConnectionError를 생성하고
            When: error.details와 error.message를 확인하면
            Then: details['url']이 전달값과 같고 메시지에 WebSocket 문자열이 포함된다

        Notes:
            없음
        """
        # When
        error = WebSocketConnectionError(url="ws://localhost:8000")

        # Then
        assert error.details["url"] == "ws://localhost:8000"
        assert "WebSocket" in error.message

    def test_connection_error_inheritance(self):
        """[TC-EXC-006] 연결 오류 계층 - 상위 예외 타입을 상속한다.

        테스트 목적:
            WebSocketConnectionError가 AgentConnectionError 및 AgentError를 상속하는지 검증한다.

        테스트 시나리오:
            Given: WebSocketConnectionError 인스턴스를 만들고
            When: isinstance로 상위 클래스 여부를 확인하면
            Then: AgentConnectionError와 AgentError 모두 True를 반환한다

        Notes:
            없음
        """
        # Given
        error = WebSocketConnectionError()

        # Then
        assert isinstance(error, AgentConnectionError)
        assert isinstance(error, AgentError)


class TestWindowErrors:
    """윈도우 관련 예외 테스트."""

    def test_window_not_found_error(self):
        """[TC-EXC-007] 창 미발견 오류 - 패턴과 타임아웃을 기록한다.

        테스트 목적:
            WindowNotFoundError가 title_pattern과 timeout 값을 details에 저장하는지 확인한다.

        테스트 시나리오:
            Given: title_pattern과 timeout을 전달해 WindowNotFoundError를 생성하고
            When: error.details를 조회하면
            Then: 전달한 패턴과 타임아웃 값이 동일하게 저장되어 있다

        Notes:
            없음
        """
        # When
        error = WindowNotFoundError(
            title_pattern=".*USB Test.*",
            timeout=30.0,
        )

        # Then
        assert error.details["title_pattern"] == ".*USB Test.*"
        assert error.details["timeout"] == 30.0

    def test_control_not_found_error(self):
        """[TC-EXC-008] 컨트롤 미발견 오류 - 컨트롤 식별자를 기록한다.

        테스트 목적:
            ControlNotFoundError가 control_id와 control_type을 details에 저장하는지 검증한다.

        테스트 시나리오:
            Given: control_id와 control_type을 전달해 ControlNotFoundError를 생성하고
            When: error.details를 조회하면
            Then: 두 값이 그대로 저장되어 있다

        Notes:
            없음
        """
        # When
        error = ControlNotFoundError(
            control_id="start_button",
            control_type="Button",
        )

        # Then
        assert error.details["control_id"] == "start_button"
        assert error.details["control_type"] == "Button"


class TestTestExecutionErrors:
    """테스트 실행 관련 예외 테스트."""

    def test_test_start_error(self):
        """[TC-EXC-009] 테스트 시작 오류 - 슬롯/단계를 세부정보로 남긴다.

        테스트 목적:
            TestStartError가 slot_idx와 phase 정보를 details에 기록하고 TestExecutionError를 상속하는지 검증한다.

        테스트 시나리오:
            Given: slot_idx와 phase를 전달해 TestStartError를 생성하고
            When: error.details를 확인하고 isinstance를 검사하면
            Then: details에 slot_idx/phase가 저장되고 TestExecutionError 하위임을 확인한다

        Notes:
            없음
        """
        # When
        error = TestStartError(
            message="Failed to start test",
            slot_idx=2,
            phase="configuring",
        )

        # Then
        assert error.details["slot_idx"] == 2
        assert error.details["phase"] == "configuring"
        assert isinstance(error, TestExecutionError)

    def test_test_timeout_error(self):
        """[TC-EXC-010] 테스트 타임아웃 - 제한 시간 초가 기록된다.

        테스트 목적:
            TestTimeoutError가 timeout_seconds 값을 details에 저장하는지 검증한다.

        테스트 시나리오:
            Given: timeout_seconds를 전달해 TestTimeoutError를 생성하고
            When: error.details를 확인하면
            Then: timeout_seconds 키가 전달한 값과 동일하다

        Notes:
            없음
        """
        # When
        error = TestTimeoutError(timeout_seconds=3600.0)

        # Then
        assert error.details["timeout_seconds"] == 3600.0

    def test_test_hang_error(self):
        """[TC-EXC-011] 테스트 행 정지 - 정지 시간 정보가 저장된다.

        테스트 목적:
            TestHangError가 hang_duration_seconds 값을 details에 기록하는지 확인한다.

        테스트 시나리오:
            Given: hang_duration_seconds를 전달해 TestHangError를 생성하고
            When: error.details를 확인하면
            Then: 해당 키가 전달한 값과 동일하다

        Notes:
            없음
        """
        # When
        error = TestHangError(hang_duration_seconds=300.0)

        # Then
        assert error.details["hang_duration_seconds"] == 300.0


class TestConfigurationErrors:
    """설정 관련 예외 테스트."""

    def test_configuration_error(self):
        """[TC-EXC-012] 설정 오류 - 기대/실제 값이 세부정보에 담긴다.

        테스트 목적:
            ConfigurationError가 config_key, expected, actual 정보를 details에 담는지 검증한다.

        테스트 시나리오:
            Given: key/expected/actual 값을 전달해 ConfigurationError를 생성하고
            When: error.details를 확인하면
            Then: 세 필드가 전달한 값과 동일하게 기록되어 있다

        Notes:
            없음
        """
        # When
        error = ConfigurationError(
            config_key="max_slots",
            expected="1-16",
            actual="100",
        )

        # Then
        assert error.details["config_key"] == "max_slots"
        assert error.details["expected"] == "1-16"
        assert error.details["actual"] == "100"


class TestInvalidStateError:
    """잘못된 상태 예외 테스트."""

    def test_invalid_state_error(self):
        """[TC-EXC-013] 잘못된 상태 - 현재/기대 상태를 기록한다.

        테스트 목적:
            InvalidStateError가 current_state와 expected_states를 details에 저장하는지 확인한다.

        테스트 시나리오:
            Given: current_state와 expected_states를 전달해 InvalidStateError를 생성하고
            When: error.details를 확인하면
            Then: 두 값이 그대로 저장되어 있다

        Notes:
            없음
        """
        # When
        error = InvalidStateError(
            current_state="running",
            expected_states=["idle", "stopped"],
        )

        # Then
        assert error.details["current_state"] == "running"
        assert error.details["expected_states"] == ["idle", "stopped"]


class TestExceptionChaining:
    """예외 체이닝 테스트."""

    def test_raise_from_original(self):
        """[TC-EXC-014] 예외 체이닝 - cause가 원본 예외를 유지한다.

        테스트 목적:
            from 구문으로 래핑할 때 TestStartError가 원본 예외를 cause로 유지하는지 검증한다.

        테스트 시나리오:
            Given: ValueError를 발생시키고 TestStartError로 다시 raise from 처리한 후
            When: pytest.raises 컨텍스트로 잡힌 예외의 cause와 메시지를 확인하면
            Then: cause는 원본 예외 객체이고 문자열에 원본 메시지가 포함된다

        Notes:
            없음
        """
        # Given
        original = ValueError("Invalid value")

        # When
        with pytest.raises(TestStartError) as exc_info:
            try:
                raise original
            except ValueError as e:
                raise TestStartError(
                    "Test failed",
                    slot_idx=0,
                    cause=e,
                ) from e

        # Then
        error = exc_info.value
        assert error.cause is original
        assert "Invalid value" in str(error)
