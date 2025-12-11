"""System Clock Implementation.

Actual implementation of the IClock protocol.
"""

import asyncio
import time
from datetime import datetime

from core.protocols import IClock


class SystemClock(IClock):
    """System Clock.

    IClock implementation using actual system time.
    Used in production environment.
    """

    def now(self) -> datetime:
        """Return current time."""
        return datetime.now()

    async def sleep(self, seconds: float) -> None:
        """Async sleep.

        Args:
            seconds: Sleep duration in seconds.
        """
        await asyncio.sleep(seconds)

    def monotonic(self) -> float:
        """Return monotonic timer value.

        A timer not affected by system clock changes.
        """
        return time.monotonic()


class FakeClock(IClock):
    """Fake clock for testing.

    Allows time control in tests.

    Example:
        ```python
        clock = FakeClock(datetime(2025, 1, 1, 12, 0, 0))

        # Check current time
        assert clock.now() == datetime(2025, 1, 1, 12, 0, 0)

        # Advance time
        clock.advance(seconds=60)
        assert clock.now() == datetime(2025, 1, 1, 12, 1, 0)

        # sleep returns immediately (no actual wait)
        await clock.sleep(10)  # Completes immediately
        ```
    """

    def __init__(
        self,
        initial_time: datetime | None = None,
        initial_monotonic: float = 0.0,
    ) -> None:
        """Initialize fake clock.

        Args:
            initial_time: Initial time (default: current time).
            initial_monotonic: Initial monotonic value.
        """
        self._current_time = initial_time or datetime.now()
        self._monotonic = initial_monotonic
        self._sleep_calls: list[float] = []

    def now(self) -> datetime:
        """Return current (fake) time."""
        return self._current_time

    async def sleep(self, seconds: float) -> None:
        """Fake sleep (returns immediately).

        Does not actually wait, only records the call.

        Args:
            seconds: Sleep duration in seconds.
        """
        self._sleep_calls.append(seconds)
        # 실제로 대기하지 않음

    def monotonic(self) -> float:
        """Return monotonic timer value."""
        return self._monotonic

    def advance(self, seconds: float) -> None:
        """Advance time.

        Args:
            seconds: Time to advance in seconds.
        """
        from datetime import timedelta

        self._current_time += timedelta(seconds=seconds)
        self._monotonic += seconds

    def set_time(self, time: datetime) -> None:
        """Set time.

        Args:
            time: Time to set.
        """
        self._current_time = time

    @property
    def sleep_calls(self) -> list[float]:
        """Sleep call history."""
        return self._sleep_calls

    def clear_sleep_calls(self) -> None:
        """Clear sleep call history."""
        self._sleep_calls.clear()
