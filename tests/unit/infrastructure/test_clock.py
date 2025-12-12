"""Infrastructure Clock Unit Tests."""

import pytest
from datetime import datetime, timedelta

from infrastructure.clock import SystemClock, FakeClock


class TestSystemClock:
    """SystemClock 테스트"""

    def test_now_returns_datetime(self) -> None:
        """[TC-CLOCK-001] 현재 시각 반환 - datetime 객체를 돌려준다.

        테스트 목적:
            SystemClock.now가 datetime 인스턴스를 반환하는지 검증한다.

        테스트 시나리오:
            Given: SystemClock 인스턴스가 있고
            When: now()를 호출하면
            Then: 반환값이 datetime 타입이다

        Notes:
            None
        """
        clock = SystemClock()

        result = clock.now()

        assert isinstance(result, datetime)

    def test_monotonic_returns_float(self) -> None:
        """[TC-CLOCK-002] 단조 시계 - float 값을 반환한다.

        테스트 목적:
            SystemClock.monotonic이 float 타입의 단조 증가 값을 반환하는지 확인한다.

        테스트 시나리오:
            Given: SystemClock 인스턴스가 있고
            When: monotonic()을 호출하면
            Then: 반환값이 float 타입이다

        Notes:
            None
        """
        clock = SystemClock()

        result = clock.monotonic()

        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_sleep_awaits(self) -> None:
        """[TC-CLOCK-003] sleep 대기 - await 가능하며 예외가 없다.

        테스트 목적:
            SystemClock.sleep이 await 가능한 코루틴이고 호출 시 예외를 발생시키지 않는지 검증한다.

        테스트 시나리오:
            Given: SystemClock 인스턴스가 있고
            When: sleep(0.01)을 await 하면
            Then: 예외 없이 완료된다

        Notes:
            None
        """
        clock = SystemClock()

        await clock.sleep(0.01)


class TestFakeClock:
    """FakeClock 테스트"""

    def test_initial_time(self) -> None:
        """[TC-CLOCK-004] 초기 시간 설정 - now가 지정한 시간으로 시작한다.

        테스트 목적:
            FakeClock를 초기 시간과 함께 생성하면 now가 해당 값으로 설정되는지 확인한다.

        테스트 시나리오:
            Given: initial_time을 지정해 FakeClock을 생성하고
            When: now()를 호출하면
            Then: 반환값이 initial_time과 동일하다

        Notes:
            None
        """
        initial = datetime(2025, 6, 15, 10, 30, 0)

        clock = FakeClock(initial_time=initial)

        assert clock.now() == initial

    def test_initial_monotonic(self) -> None:
        """[TC-CLOCK-005] 초기 단조 시각 - 지정한 값으로 시작한다.

        테스트 목적:
            FakeClock를 초기 monotonic 값으로 생성했을 때 monotonic이 그 값을 반환하는지 검증한다.

        테스트 시나리오:
            Given: initial_monotonic=100.0으로 FakeClock을 생성하고
            When: monotonic()을 호출하면
            Then: 100.0을 반환한다

        Notes:
            None
        """
        clock = FakeClock(initial_monotonic=100.0)

        assert clock.monotonic() == 100.0

    def test_advance_time(self) -> None:
        """[TC-CLOCK-006] 시간 진행 - now와 monotonic이 함께 증가한다.

        테스트 목적:
            advance 호출 시 now와 monotonic이 지정 초만큼 증가하는지 확인한다.

        테스트 시나리오:
            Given: 초기 시간을 설정한 FakeClock을 만들고
            When: advance(seconds=60)을 호출하면
            Then: now는 60초 후 시각, monotonic은 60.0이 된다

        Notes:
            None
        """
        initial = datetime(2025, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=initial, initial_monotonic=0.0)

        clock.advance(seconds=60)

        expected_time = initial + timedelta(seconds=60)
        assert clock.now() == expected_time
        assert clock.monotonic() == 60.0

    def test_advance_multiple_times(self) -> None:
        """[TC-CLOCK-007] 누적 진행 - 여러 번 advance해도 합산된다.

        테스트 목적:
            advance를 반복 호출할 때 monotonic이 누적 합으로 증가하는지 검증한다.

        테스트 시나리오:
            Given: 초기 monotonic=0인 FakeClock이 있고
            When: 30초씩 세 번 advance하면
            Then: monotonic이 90.0이 된다

        Notes:
            None
        """
        clock = FakeClock(
            initial_time=datetime(2025, 1, 1, 0, 0, 0),
            initial_monotonic=0.0,
        )

        clock.advance(seconds=30)
        clock.advance(seconds=30)
        clock.advance(seconds=30)

        assert clock.monotonic() == 90.0

    def test_set_time(self) -> None:
        """[TC-CLOCK-008] 시간 설정 - now가 새 시각으로 갱신된다.

        테스트 목적:
            set_time 호출로 now가 지정한 datetime으로 설정되는지 확인한다.

        테스트 시나리오:
            Given: 기본 FakeClock을 만들고
            When: set_time(새 datetime)을 호출하면
            Then: now()가 새 시각을 반환한다

        Notes:
            None
        """
        clock = FakeClock()
        new_time = datetime(2030, 12, 31, 23, 59, 59)

        clock.set_time(new_time)

        assert clock.now() == new_time

    @pytest.mark.asyncio
    async def test_sleep_records_calls(self) -> None:
        """[TC-CLOCK-009] sleep 기록 - 호출된 초가 sleep_calls에 저장된다.

        테스트 목적:
            FakeClock.sleep 호출이 실제 대기 없이 기록만 남기는지 검증한다.

        테스트 시나리오:
            Given: FakeClock 인스턴스가 있고
            When: sleep을 여러 번 호출하면
            Then: sleep_calls 리스트에 호출 초가 순서대로 기록된다

        Notes:
            None
        """
        clock = FakeClock()

        await clock.sleep(5)
        await clock.sleep(10)
        await clock.sleep(15)

        assert clock.sleep_calls == [5, 10, 15]

    @pytest.mark.asyncio
    async def test_sleep_does_not_actually_wait(self) -> None:
        """[TC-CLOCK-010] 가짜 대기 - 실제로 기다리지 않고 기록만 남는다.

        테스트 목적:
            FakeClock.sleep이 비동기 대기 없이 즉시 반환하고 기록만 남기는지 확인한다.

        테스트 시나리오:
            Given: FakeClock 인스턴스가 있고
            When: sleep(3600)을 호출하면
            Then: 호출 기록에 3600이 남고 실제 대기는 발생하지 않는다

        Notes:
            None
        """
        clock = FakeClock()

        await clock.sleep(3600)

        assert 3600 in clock.sleep_calls

    def test_clear_sleep_calls(self) -> None:
        """[TC-CLOCK-011] sleep 기록 초기화 - 리스트를 비운다.

        테스트 목적:
            clear_sleep_calls 호출 시 이전 sleep 기록이 모두 삭제되는지 검증한다.

        테스트 시나리오:
            Given: sleep_calls에 값이 있는 FakeClock을 만들고
            When: clear_sleep_calls를 호출하면
            Then: sleep_calls가 빈 리스트가 된다

        Notes:
            None
        """
        clock = FakeClock()
        clock._sleep_calls = [1, 2, 3]

        clock.clear_sleep_calls()

        assert clock.sleep_calls == []
