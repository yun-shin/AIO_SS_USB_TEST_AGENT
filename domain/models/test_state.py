"""Test State Model.

Domain model tracking state during test execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from domain.enums import ProcessState, TestPhase


@dataclass
class TestState:
    """Test state model.

    Tracks current state during test execution.
    Creates new instances via update() method to maintain immutability.

    Attributes:
        slot_idx: Test slot index.
        process_state: USB Test process state.
        test_phase: Current test phase.
        current_loop: Current loop number (overall, across all batches).
        total_loop: Total loop count (overall target).
        loop_step: Loops per batch execution (MFC Client setting).
        current_batch: Current batch iteration (1-based).
        total_batch: Total batch iterations (loop_count / loop_step).
        pid: USB Test process PID.
        is_active: Test active state.
        started_at: Test start time.
        updated_at: Last state update time.
        estimated_remaining: Estimated remaining time in seconds.
        avg_loop_time: Average loop time in seconds.
        error_count: Error occurrence count.
        last_error: Last error message.
    """

    slot_idx: int
    process_state: ProcessState = ProcessState.UNKNOWN
    test_phase: TestPhase = TestPhase.UNKNOWN
    current_loop: int = 0
    total_loop: int = 0
    loop_step: int = 1  # MFC Client에 설정되는 1회 실행 루프 횟수
    current_batch: int = 0  # 현재 배치 반복 횟수 (1-based)
    total_batch: int = 1  # 총 배치 반복 횟수
    pid: Optional[int] = None
    is_active: bool = False

    # Time information
    started_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    estimated_remaining: Optional[int] = None  # in seconds
    avg_loop_time: Optional[float] = None  # in seconds

    # Error information
    error_count: int = 0
    last_error: Optional[str] = None

    def update(self, **kwargs) -> "TestState":
        """Update state (maintains immutability).

        Creates a new TestState instance with the given keyword arguments.
        updated_at is automatically set to current time.

        Args:
            **kwargs: Fields and values to update.

        Returns:
            New TestState instance.
        """
        return TestState(
            slot_idx=kwargs.get("slot_idx", self.slot_idx),
            process_state=kwargs.get("process_state", self.process_state),
            test_phase=kwargs.get("test_phase", self.test_phase),
            current_loop=kwargs.get("current_loop", self.current_loop),
            total_loop=kwargs.get("total_loop", self.total_loop),
            loop_step=kwargs.get("loop_step", self.loop_step),
            current_batch=kwargs.get("current_batch", self.current_batch),
            total_batch=kwargs.get("total_batch", self.total_batch),
            pid=kwargs.get("pid", self.pid),
            is_active=kwargs.get("is_active", self.is_active),
            started_at=kwargs.get("started_at", self.started_at),
            updated_at=datetime.now(),
            estimated_remaining=kwargs.get("estimated_remaining", self.estimated_remaining),
            avg_loop_time=kwargs.get("avg_loop_time", self.avg_loop_time),
            error_count=kwargs.get("error_count", self.error_count),
            last_error=kwargs.get("last_error", self.last_error),
        )

    def increment_loop(self) -> "TestState":
        """Increment loop count.

        Returns:
            New TestState with incremented loop.
        """
        new_loop = self.current_loop + 1
        remaining = self._calculate_remaining(new_loop)
        return self.update(
            current_loop=new_loop,
            estimated_remaining=remaining,
        )

    def increment_batch(self) -> "TestState":
        """Increment batch count and update current_loop.

        Each batch completion adds loop_step to current_loop.

        Returns:
            New TestState with incremented batch.
        """
        new_batch = self.current_batch + 1
        new_loop = min(new_batch * self.loop_step, self.total_loop)
        remaining = self._calculate_remaining(new_loop)
        return self.update(
            current_batch=new_batch,
            current_loop=new_loop,
            estimated_remaining=remaining,
        )

    def is_batch_completed(self) -> bool:
        """Check if all batches are completed.

        Returns:
            True if all batches completed.
        """
        return self.current_batch >= self.total_batch

    def set_error(self, error_message: str) -> "TestState":
        """Set error.

        Args:
            error_message: Error message.

        Returns:
            New TestState with error set.
        """
        return self.update(
            error_count=self.error_count + 1,
            last_error=error_message,
        )

    def clear_error(self) -> "TestState":
        """Clear error.

        Returns:
            New TestState with error cleared.
        """
        return self.update(
            error_count=0,
            last_error=None,
        )

    def is_completed(self) -> bool:
        """Check if test is completed.

        Returns:
            True if completed.
        """
        return self.current_loop >= self.total_loop

    def is_failed(self) -> bool:
        """Check if test failed.

        Returns:
            True if failed.
        """
        return self.process_state == ProcessState.FAIL

    def is_running(self) -> bool:
        """Check if test is running.

        Returns:
            True if running.
        """
        return self.is_active and self.process_state == ProcessState.TEST

    def get_progress_percent(self) -> float:
        """Calculate progress percentage.

        Returns:
            Progress percentage (0.0 ~ 100.0).
        """
        if self.total_loop == 0:
            return 0.0
        return (self.current_loop / self.total_loop) * 100.0

    def _calculate_remaining(self, current_loop: int) -> Optional[int]:
        """Calculate estimated remaining time.

        Args:
            current_loop: Current loop number.

        Returns:
            Estimated remaining time in seconds, None if cannot calculate.
        """
        if self.avg_loop_time is None or self.total_loop == 0:
            return None
        remaining_loops = self.total_loop - current_loop
        return int(remaining_loops * self.avg_loop_time)

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            State dictionary.
        """
        return {
            "slot_idx": self.slot_idx,
            "process_state": self.process_state.value,
            "process_state_name": self.process_state.name,
            "test_phase": self.test_phase.value,
            "test_phase_name": self.test_phase.name,
            "current_loop": self.current_loop,
            "total_loop": self.total_loop,
            "loop_step": self.loop_step,
            "current_batch": self.current_batch,
            "total_batch": self.total_batch,
            "pid": self.pid,
            "is_active": self.is_active,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat(),
            "estimated_remaining": self.estimated_remaining,
            "avg_loop_time": self.avg_loop_time,
            "progress_percent": self.get_progress_percent(),
            "error_count": self.error_count,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestState":
        """Create TestState from dictionary.

        Args:
            data: State dictionary.

        Returns:
            TestState instance.
        """
        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])

        return cls(
            slot_idx=data["slot_idx"],
            process_state=ProcessState(data.get("process_state", ProcessState.UNKNOWN)),
            test_phase=TestPhase(data.get("test_phase", TestPhase.UNKNOWN)),
            current_loop=data.get("current_loop", 0),
            total_loop=data.get("total_loop", 0),
            loop_step=data.get("loop_step", 1),
            current_batch=data.get("current_batch", 0),
            total_batch=data.get("total_batch", 1),
            pid=data.get("pid"),
            is_active=data.get("is_active", False),
            started_at=started_at,
            estimated_remaining=data.get("estimated_remaining"),
            avg_loop_time=data.get("avg_loop_time"),
            error_count=data.get("error_count", 0),
            last_error=data.get("last_error"),
        )
