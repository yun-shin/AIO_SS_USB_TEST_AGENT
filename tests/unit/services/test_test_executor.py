"""TestExecutor Unit Tests."""

from datetime import datetime
import pytest

from services.test_executor import TestExecutor, TestRequest, TestPhase
from core.exceptions import WindowNotFoundError, TestStartError
from infrastructure.clock import FakeClock
from infrastructure.state_store import FakeStateStore
from infrastructure.window_finder import (
    FakeWindowFinder,
    FakeWindowHandle,
    FakeControlHandle,
)

from tests.conftest import FakeLogger


class TestTestExecutorConnection:
    """TestExecutor 연결 테스트"""

    @pytest.mark.asyncio
    async def test_connect_success(
        self,
        test_executor: TestExecutor,
        fake_logger: FakeLogger,
    ) -> None:
        """[TC-EXEC-001] 연결 성공 - 창을 찾으면 연결 상태로 전환된다.

        테스트 목적:
            connect 호출 시 창 검색이 성공하면 is_connected가 True로 설정되는지 확인한다.

        테스트 시나리오:
            Given: 정상 FakeWindowFinder/FakeStateStore가 주입된 TestExecutor가 있고
            When: connect를 호출하면
            Then: True를 반환하고 is_connected가 True이며 info 로그에 Connected 메시지가 기록된다

        Notes:
            None
        """
        result = await test_executor.connect()

        assert result is True
        assert test_executor.is_connected is True
        info_logs = fake_logger.get_logs("info")
        assert any("Connected" in log["message"] for log in info_logs)

    @pytest.mark.asyncio
    async def test_connect_failure_window_not_found(
        self,
        fake_window_finder: FakeWindowFinder,
        fake_state_store: FakeStateStore,
        fake_clock: FakeClock,
        fake_logger: FakeLogger,
    ) -> None:
        """[TC-EXEC-002] 연결 실패 - 창을 찾지 못하면 False를 반환한다.

        테스트 목적:
            connect 시 대상 창을 찾지 못하면 연결 플래그가 False로 유지되는지 검증한다.

        테스트 시나리오:
            Given: 창 패턴이 매칭되지 않는 FakeWindowFinder로 TestExecutor를 만들고
            When: connect(timeout=1.0)을 호출하면
            Then: False를 반환하며 is_connected는 False다

        Notes:
            None
        """
        executor = TestExecutor(
            window_finder=fake_window_finder,
            state_store=fake_state_store,
            clock=fake_clock,
            logger=fake_logger,
        )

        result = await executor.connect(timeout=1.0)

        assert result is False
        assert executor.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, test_executor: TestExecutor) -> None:
        """[TC-EXEC-003] 연결 해제 - 연결 후 disconnect하면 플래그가 내려간다.

        테스트 목적:
            connect 이후 disconnect 호출 시 is_connected가 False로 변경되는지 확인한다.

        테스트 시나리오:
            Given: connect를 완료해 is_connected가 True인 상태에서
            When: disconnect를 호출하면
            Then: is_connected가 False로 바뀐다

        Notes:
            None
        """
        await test_executor.connect()
        assert test_executor.is_connected is True

        await test_executor.disconnect()

        assert test_executor.is_connected is False


class TestTestExecutorStartTest:
    """TestExecutor start_test 테스트"""

    @pytest.mark.asyncio
    async def test_start_test_success(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
        fake_state_store: FakeStateStore,
    ) -> None:
        """[TC-EXEC-004] 테스트 시작 성공 - 실행 결과와 상태 저장을 확인한다.

        테스트 목적:
            연결된 상태에서 start_test 호출 시 성공 결과와 상태 저장소 업데이트를 검증한다.

        테스트 시나리오:
            Given: connect가 완료된 TestExecutor와 샘플 요청이 있고
            When: start_test를 호출하면
            Then: 결과가 success=True이고 phase가 RUNNING이며 state_store에 RUNNING 상태가 기록된다

        Notes:
            None
        """
        await test_executor.connect()

        result = await test_executor.start_test(sample_test_request)

        assert result.success is True
        assert result.slot_idx == sample_test_request.slot_idx
        assert result.phase == TestPhase.RUNNING
        assert result.test_id is not None

        state = fake_state_store.get_slot_state(sample_test_request.slot_idx)
        assert state is not None
        assert state["status"] == TestPhase.RUNNING.value

    @pytest.mark.asyncio
    async def test_start_test_not_connected(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
    ) -> None:
        """[TC-EXEC-005] 미연결 상태 - start_test 호출 시 예외를 발생시킨다.

        테스트 목적:
            연결되지 않은 상태에서 start_test 호출 시 WindowNotFoundError가 발생하는지 확인한다.

        테스트 시나리오:
            Given: connect를 수행하지 않은 TestExecutor가 있고
            When: start_test를 호출하면
            Then: WindowNotFoundError가 발생한다

        Notes:
            None
        """
        with pytest.raises(WindowNotFoundError):
            await test_executor.start_test(sample_test_request)

    @pytest.mark.asyncio
    async def test_start_test_state_transitions(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
        fake_state_store: FakeStateStore,
    ) -> None:
        """[TC-EXEC-006] 상태 전이 콜백 - PREPARING/CONFIGURING/RUNNING 순서로 호출된다.

        테스트 목적:
            start_test 실행 중 등록된 콜백이 예상 Phase 순서로 호출되는지 검증한다.

        테스트 시나리오:
            Given: state_change 콜백을 등록한 후 connect를 완료하고
            When: start_test를 호출하면
            Then: 콜백이 PREPARING → CONFIGURING → RUNNING 순서로 실행된다

        Notes:
            None
        """
        await test_executor.connect()
        state_changes: list[tuple[int, TestPhase]] = []

        async def capture_state_change(slot_idx: int, phase: TestPhase) -> None:
            state_changes.append((slot_idx, phase))

        test_executor.set_state_change_callback(capture_state_change)

        await test_executor.start_test(sample_test_request)

        assert len(state_changes) == 3
        assert state_changes[0] == (0, TestPhase.PREPARING)
        assert state_changes[1] == (0, TestPhase.CONFIGURING)
        assert state_changes[2] == (0, TestPhase.RUNNING)


class TestTestExecutorStopTest:
    """TestExecutor stop_test 테스트"""

    @pytest.mark.asyncio
    async def test_stop_test_success(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
    ) -> None:
        """[TC-EXEC-007] 테스트 중지 성공 - stop_test 결과가 STOPPED로 반환된다.

        테스트 목적:
            연결 및 start_test 후 stop_test 호출 시 성공 여부와 Phase 변경을 검증한다.

        테스트 시나리오:
            Given: connect와 start_test가 완료된 상태에서
            When: stop_test를 호출하면
            Then: 결과가 success=True이고 phase가 STOPPED다

        Notes:
            None
        """
        await test_executor.connect()
        await test_executor.start_test(sample_test_request)

        result = await test_executor.stop_test(sample_test_request.slot_idx)

        assert result.success is True
        assert result.phase == TestPhase.STOPPED

    @pytest.mark.asyncio
    async def test_stop_test_not_connected(self, test_executor: TestExecutor) -> None:
        """[TC-EXEC-008] 미연결 상태 중지 - stop_test가 예외를 발생시킨다.

        테스트 목적:
            연결되지 않은 상태에서 stop_test 호출 시 WindowNotFoundError가 발생하는지 확인한다.

        테스트 시나리오:
            Given: connect를 수행하지 않은 TestExecutor가 있고
            When: stop_test를 호출하면
            Then: WindowNotFoundError가 발생한다

        Notes:
            None
        """
        with pytest.raises(WindowNotFoundError):
            await test_executor.stop_test(0)


class TestTestExecutorWithMockTime:
    """시간 Mock을 사용하는 테스트"""

    @pytest.mark.asyncio
    async def test_execution_duration_tracking(
        self,
        test_executor: TestExecutor,
        sample_test_request: TestRequest,
        fake_clock: FakeClock,
    ) -> None:
        """[TC-EXEC-009] 실행 시간 기록 - duration과 sleep 호출이 기록된다.

        테스트 목적:
            start_test 실행 시 duration_seconds가 설정되고 FakeClock에 sleep 기록이 남는지 확인한다.

        테스트 시나리오:
            Given: FakeClock이 주입된 TestExecutor를 connect한 뒤
            When: start_test를 호출하면
            Then: 반환 결과의 duration_seconds가 0 이상이며 fake_clock.sleep_calls가 비어 있지 않다

        Notes:
            None
        """
        await test_executor.connect()

        result = await test_executor.start_test(sample_test_request)

        assert result.duration_seconds >= 0
        assert len(fake_clock.sleep_calls) > 0
