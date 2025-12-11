"""Exception Unit Tests.

예외 클래스들의 단위 테스트입니다.
"""

import pytest

from src.core.exceptions import (
    AgentError,
    ConnectionError,
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
        """메시지만 있는 예외."""
        # When
        error = AgentError("Test error")

        # Then
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}
        assert error.cause is None

    def test_with_details(self):
        """상세 정보가 있는 예외."""
        # When
        error = AgentError("Test error", details={"key": "value"})

        # Then
        assert "key" in str(error)
        assert error.details == {"key": "value"}

    def test_with_cause(self):
        """원인 예외가 있는 경우."""
        # Given
        original_error = ValueError("Original error")

        # When
        error = AgentError("Wrapped error", cause=original_error)

        # Then
        assert "Original error" in str(error)
        assert error.cause is original_error

    def test_to_dict(self):
        """딕셔너리 변환."""
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
        """WebSocket 연결 예외."""
        # When
        error = WebSocketConnectionError(url="ws://localhost:8000")

        # Then
        assert error.details["url"] == "ws://localhost:8000"
        assert "WebSocket" in error.message

    def test_connection_error_inheritance(self):
        """상속 관계 확인."""
        # Given
        error = WebSocketConnectionError()

        # Then
        assert isinstance(error, ConnectionError)
        assert isinstance(error, AgentError)


class TestWindowErrors:
    """윈도우 관련 예외 테스트."""

    def test_window_not_found_error(self):
        """윈도우 미발견 예외."""
        # When
        error = WindowNotFoundError(
            title_pattern=".*USB Test.*",
            timeout=30.0,
        )

        # Then
        assert error.details["title_pattern"] == ".*USB Test.*"
        assert error.details["timeout"] == 30.0

    def test_control_not_found_error(self):
        """컨트롤 미발견 예외."""
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
        """테스트 시작 실패 예외."""
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
        """테스트 타임아웃 예외."""
        # When
        error = TestTimeoutError(timeout_seconds=3600.0)

        # Then
        assert error.details["timeout_seconds"] == 3600.0

    def test_test_hang_error(self):
        """테스트 Hang 예외."""
        # When
        error = TestHangError(hang_duration_seconds=300.0)

        # Then
        assert error.details["hang_duration_seconds"] == 300.0


class TestConfigurationErrors:
    """설정 관련 예외 테스트."""

    def test_configuration_error(self):
        """설정 오류 예외."""
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
        """잘못된 상태 예외."""
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
        """원인 예외로부터 발생."""
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
