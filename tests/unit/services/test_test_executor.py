"""TestExecutor Unit Tests.

TestExecutor 서비스의 단위 테스트입니다.
모든 외부 의존성은 Mock으로 대체됩니다.
"""

import pytest
from datetime import datetime

from src.services.test_executor import TestExecutor, TestRequest, TestPhase
from src.core.exceptions import WindowNotFoundError, TestStartError
from src.infrastructure.clock import FakeClock
from src.infrastructure.state_store import FakeStateStore
from src.infrastructure.window_finder import (
    FakeWindowFinder,
    FakeWindowHandle,
    FakeControlHandle,
)

from tests.conftest import FakeLogger


class TestTestExecutorConnection:
    """TestExecutor 연결 테스트."""

    @pytest.mark.asyncio
    async def test_connect_success(
        self,
        test_executor: TestExecutor,
        fake_logger: FakeLogger,
    ):
        """연결 성공 테스트."""
        # When
        result = await test_executor.connect()

        # Then
        assert result is True
        assert test_executor.is_connected is True

        # 로그 검증
        info_logs = fake_logger.get_logs("info")
        assert any("Connected" in log["message"] for log in info_logs)

    @pytest.mark.asyncio
    async def test_connect_failure_window_not_found(
        self,
        fake_window_finder: FakeWindowFinder,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
        fake_logger: FakeLogger,
    ):
        """윈도우 없을 때 연결 실패 테스트."""
        # Given: 윈도우가 등록되지 않은 상태
        executor = TestExecutor(
            window_finder=fake_window_finder,
            state_store=fake_state_store,
            clock=fake_clock,
            logger=fake_logger,
        )

        # When
        result = await executor.connect(timeout=1.0)

        # Then
        assert result is False
        assert executor.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, test_executor: TestExecutor):
        """연결 해제 테스트."""
        # Given
        await test_executor.connect()
        assert test_executor.is_connected is True

        # When
        await test_executor.disconnect()

        # Then
        assert test_executor.is_connected is False


class TestTestExecutorStartTest:
    """TestExecutor 테스트 시작 테스트."""

    @pytest.mark.asyncio
    async def test_start_test_success(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
        fake_state_store: FakeStateStore,
    ):
        """테스트 시작 성공."""
        # Given
        await test_executor.connect()

        # When
        result = await test_executor.start_test(sample_test_request)

        # Then
        assert result.success is True
        assert result.slot_idx == sample_test_request.slot_idx
        assert result.phase == TestPhase.RUNNING
        assert result.test_id is not None

        # 상태 저장소 검증
        state = fake_state_store.get_slot_state(sample_test_request.slot_idx)
        assert state is not None
        assert state["status"] == TestPhase.RUNNING.value

    @pytest.mark.asyncio
    async def test_start_test_not_connected(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
    ):
        """연결되지 않은 상태에서 테스트 시작 시 예외."""
        # Given: 연결하지 않음

        # When/Then
        with pytest.raises(WindowNotFoundError):
            await test_executor.start_test(sample_test_request)

    @pytest.mark.asyncio
    async def test_start_test_state_transitions(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
        fake_state_store: FakeStateStore,
    ):
        """테스트 시작 시 상태 전이 검증."""
        # Given
        await test_executor.connect()
        state_changes: list[tuple[int, TestPhase]] = []

        async def capture_state_change(slot_idx: int, phase: TestPhase):
            state_changes.append((slot_idx, phase))

        test_executor.set_state_change_callback(capture_state_change)

        # When
        await test_executor.start_test(sample_test_request)

        # Then: 상태 전이 순서 검증
        assert len(state_changes) == 3
        assert state_changes[0] == (0, TestPhase.PREPARING)
        assert state_changes[1] == (0, TestPhase.CONFIGURING)
        assert state_changes[2] == (0, TestPhase.RUNNING)


class TestTestExecutorStopTest:
    """TestExecutor 테스트 중지 테스트."""

    @pytest.mark.asyncio
    async def test_stop_test_success(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
    ):
        """테스트 중지 성공."""
        # Given
        await test_executor.connect()
        await test_executor.start_test(sample_test_request)

        # When
        result = await test_executor.stop_test(sample_test_request.slot_idx)

        # Then
        assert result.success is True
        assert result.phase == TestPhase.STOPPED

    @pytest.mark.asyncio
    async def test_stop_test_not_connected(self, test_executor: TestExecutor):
        """연결되지 않은 상태에서 중지 시 예외."""
        # When/Then
        with pytest.raises(WindowNotFoundError):
            await test_executor.stop_test(0)


class TestTestExecutorWithMockTime:
    """시간 Mock을 활용한 테스트."""

    @pytest.mark.asyncio
    async def test_execution_duration_tracking(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
        fake_clock: FakeClock,
    ):
        """실행 시간 추적 테스트."""
        # Given
        await test_executor.connect()

        # When
        result = await test_executor.start_test(sample_test_request)

        # Then: duration이 기록됨
        assert result.duration_seconds >= 0

        # FakeClock의 sleep 호출 확인
        assert len(fake_clock.sleep_calls) > 0
