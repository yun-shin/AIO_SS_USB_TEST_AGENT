"""Custom Exceptions.

Defines hierarchical exception classes.
Each exception includes specific error context.
"""

from typing import Any, Optional


class AgentError(Exception):
    """Base Agent exception.

    Base class for all Agent-related exceptions.

    Attributes:
        message: Error message.
        details: Additional detail information.
        cause: Cause exception.
    """

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        base = self.message
        if self.details:
            base += f" | Details: {self.details}"
        if self.cause:
            base += f" | Caused by: {self.cause}"
        return base

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


# ============================================================
# Connection Errors
# ============================================================


class AgentConnectionError(AgentError):
    """Connection related exception.

    Note:
        Uses Agent prefix to distinguish from Python built-in ConnectionError.
    """

    pass


class WebSocketConnectionError(AgentConnectionError):
    """WebSocket connection exception."""

    def __init__(
        self,
        message: str = "WebSocket connection failed",
        url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if url:
            details["url"] = url
        super().__init__(message, details=details, **kwargs)


class BackendUnreachableError(AgentConnectionError):
    """Backend unreachable exception."""

    def __init__(
        self,
        message: str = "Backend server is unreachable",
        url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if url:
            details["url"] = url
        super().__init__(message, details=details, **kwargs)


# ============================================================
# Window/Control Errors
# ============================================================


class WindowNotFoundError(AgentError):
    """Window not found exception."""

    def __init__(
        self,
        message: str = "Window not found",
        title_pattern: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if title_pattern:
            details["title_pattern"] = title_pattern
        if timeout:
            details["timeout"] = timeout
        super().__init__(message, details=details, **kwargs)


class ControlNotFoundError(AgentError):
    """Control not found exception."""

    def __init__(
        self,
        message: str = "Control not found",
        control_id: Optional[str] = None,
        control_type: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if control_id:
            details["control_id"] = control_id
        if control_type:
            details["control_type"] = control_type
        super().__init__(message, details=details, **kwargs)


class ControlNotEnabledError(AgentError):
    """Control not enabled exception."""

    def __init__(
        self,
        message: str = "Control is not enabled",
        control_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if control_id:
            details["control_id"] = control_id
        super().__init__(message, details=details, **kwargs)


class ProcessNotFoundError(AgentError):
    """Process not found exception."""

    def __init__(
        self,
        message: str = "Process not found",
        process_name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if process_name:
            details["process_name"] = process_name
        super().__init__(message, details=details, **kwargs)


# ============================================================
# Test Execution Errors
# ============================================================


class TestExecutionError(AgentError):
    """Test execution exception."""

    def __init__(
        self,
        message: str = "Test execution failed",
        slot_idx: Optional[int] = None,
        phase: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if slot_idx is not None:
            details["slot_idx"] = slot_idx
        if phase:
            details["phase"] = phase
        super().__init__(message, details=details, **kwargs)


class TestStartError(TestExecutionError):
    """Test start failure."""

    pass


class TestStopError(TestExecutionError):
    """Test stop failure."""

    pass


class TestTimeoutError(TestExecutionError):
    """Test timeout exception."""

    def __init__(
        self,
        message: str = "Test timed out",
        timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, details=details, **kwargs)


class TestHangError(TestExecutionError):
    """Test hang state exception."""

    def __init__(
        self,
        message: str = "Test appears to be hanging",
        hang_duration_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if hang_duration_seconds:
            details["hang_duration_seconds"] = hang_duration_seconds
        super().__init__(message, details=details, **kwargs)


# ============================================================
# General Errors
# ============================================================


class AgentTimeoutError(AgentError):
    """General timeout exception.

    Note:
        Uses Agent prefix to distinguish from Python built-in TimeoutError.
    """

    def __init__(
        self,
        message: str = "Operation timed out",
        operation: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if operation:
            details["operation"] = operation
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(message, details=details, **kwargs)


class ConfigurationError(AgentError):
    """Configuration error."""

    def __init__(
        self,
        message: str = "Configuration error",
        config_key: Optional[str] = None,
        expected: Optional[str] = None,
        actual: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if config_key:
            details["config_key"] = config_key
        if expected:
            details["expected"] = expected
        if actual:
            details["actual"] = actual
        super().__init__(message, details=details, **kwargs)


class InvalidStateError(AgentError):
    """Invalid state exception."""

    def __init__(
        self,
        message: str = "Invalid state",
        current_state: Optional[str] = None,
        expected_states: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {})
        if current_state:
            details["current_state"] = current_state
        if expected_states:
            details["expected_states"] = expected_states
        super().__init__(message, details=details, **kwargs)
