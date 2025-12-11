"""Infrastructure Clock Unit Tests.

Clock 구현체들의 단위 테스트입니다.
"""

import pytest
from datetime import datetime, timedelta

from src.infrastructure.clock import SystemClock, FakeClock


class TestSystemClock:
    """SystemClock 테스트."""

    def test_now_returns_datetime(self):
        """now()가 datetime 반환."""
        # Given
        clock = SystemClock()

        # When
        result = clock.now()

        # Then
        assert isinstance(result, datetime)

    def test_monotonic_returns_float(self):
        """monotonic()이 float 반환."""
        # Given
        clock = SystemClock()

        # When
        result = clock.monotonic()

        # Then
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_sleep_awaits(self):
        """sleep()이 대기."""
        # Given
        clock = SystemClock()

        # When/Then: 예외 없이 완료
        await clock.sleep(0.01)


class TestFakeClock:
    """FakeClock 테스트."""

    def test_initial_time(self):
        """초기 시간 설정."""
        # Given
        initial = datetime(2025, 6, 15, 10, 30, 0)

        # When
        clock = FakeClock(initial_time=initial)

        # Then
        assert clock.now() == initial

    def test_initial_monotonic(self):
        """초기 모노토닉 값 설정."""
        # When
        clock = FakeClock(initial_monotonic=100.0)

        # Then
        assert clock.monotonic() == 100.0

    def test_advance_time(self):
        """시간 진행."""
        # Given
        initial = datetime(2025, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=initial, initial_monotonic=0.0)

        # When
        clock.advance(seconds=60)

        # Then
        expected_time = initial + timedelta(seconds=60)
        assert clock.now() == expected_time
        assert clock.monotonic() == 60.0

    def test_advance_multiple_times(self):
        """여러 번 시간 진행."""
        # Given
        clock = FakeClock(
            initial_time=datetime(2025, 1, 1, 0, 0, 0),
            initial_monotonic=0.0,
        )

        # When
        clock.advance(seconds=30)
        clock.advance(seconds=30)
        clock.advance(seconds=30)

        # Then
        assert clock.monotonic() == 90.0

    def test_set_time(self):
        """시간 직접 설정."""
        # Given
        clock = FakeClock()
        new_time = datetime(2030, 12, 31, 23, 59, 59)

        # When
        clock.set_time(new_time)

        # Then
        assert clock.now() == new_time

    @pytest.mark.asyncio
    async def test_sleep_records_calls(self):
        """sleep 호출 기록."""
        # Given
        clock = FakeClock()

        # When
        await clock.sleep(5)
        await clock.sleep(10)
        await clock.sleep(15)

        # Then
        assert clock.sleep_calls == [5, 10, 15]

    @pytest.mark.asyncio
    async def test_sleep_does_not_actually_wait(self):
        """sleep이 실제로 대기하지 않음."""
        # Given
        clock = FakeClock()

        # When: 1시간 sleep (실제로 기다리면 테스트 실패)
        await clock.sleep(3600)

        # Then: 즉시 완료
        assert 3600 in clock.sleep_calls

    def test_clear_sleep_calls(self):
        """sleep 호출 기록 초기화."""
        # Given
        clock = FakeClock()
        clock._sleep_calls = [1, 2, 3]

        # When
        clock.clear_sleep_calls()

        # Then
        assert clock.sleep_calls == []
