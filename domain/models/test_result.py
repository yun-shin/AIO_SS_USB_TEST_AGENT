"""Test Result Model.

Domain model representing test execution results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..enums import ErrorCode


@dataclass
class TestResult:
    """Test result model.

    Represents execution results of use cases/service methods.
    Applies Result pattern to explicitly convey success/failure.

    Attributes:
        success: Whether successful.
        error_code: Error code (on failure).
        error_message: Error message (on failure).
        data: Additional data.
        timestamp: Result creation time.
    """

    success: bool
    error_code: ErrorCode = ErrorCode.NO_ERROR
    error_message: Optional[str] = None
    data: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def ok(cls, data: Optional[dict] = None) -> "TestResult":
        """Create success result.

        Args:
            data: Additional data.

        Returns:
            Success TestResult.
        """
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls,
        error_code: ErrorCode,
        error_message: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> "TestResult":
        """Create failure result.

        Args:
            error_code: Error code.
            error_message: Error message.
            data: Additional data.

        Returns:
            Failure TestResult.
        """
        return cls(
            success=False,
            error_code=error_code,
            error_message=error_message or f"Error: {error_code.name}",
            data=data,
        )

    @classmethod
    def completed(cls, data: Optional[dict] = None) -> "TestResult":
        """Create test completed result.

        Args:
            data: Additional data.

        Returns:
            Completed TestResult.
        """
        return cls(
            success=True,
            error_code=ErrorCode.TEST_COMPLETED,
            data=data,
        )

    def is_completed(self) -> bool:
        """Check if test is completed.

        Returns:
            True if completed.
        """
        return self.error_code == ErrorCode.TEST_COMPLETED

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Result dictionary.
        """
        return {
            "success": self.success,
            "error_code": self.error_code.value,
            "error_code_name": self.error_code.name,
            "error_message": self.error_message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestResult":
        """Create TestResult from dictionary.

        Args:
            data: Result dictionary.

        Returns:
            TestResult instance.
        """
        return cls(
            success=data["success"],
            error_code=ErrorCode(data.get("error_code", 0)),
            error_message=data.get("error_message"),
            data=data.get("data"),
        )


@dataclass
class OperationResult:
    """General operation result model.

    Simplified version of TestResult for representing simple operation results.

    Attributes:
        success: Whether successful.
        message: Result message.
        data: Additional data.
    """

    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None

    @classmethod
    def ok(cls, message: Optional[str] = None, data: Optional[dict] = None) -> "OperationResult":
        """Create success result.

        Args:
            message: Result message.
            data: Additional data.

        Returns:
            Success OperationResult.
        """
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, data: Optional[dict] = None) -> "OperationResult":
        """Create failure result.

        Args:
            message: Error message.
            data: Additional data.

        Returns:
            Failure OperationResult.
        """
        return cls(success=False, message=message, data=data)
