"""Unit tests for BatchExecutor.

Tests loop_count/loop_step batch calculation, progress callback ordering,
and cancellation state propagation.
"""

import asyncio
import math
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from domain.enums import TestMethod, TestPreset, TestFile, TestCapacity
from domain.models.test_config import TestConfig, PreconditionConfig


class FakeStateMachine:
    """Fake SlotStateMachine for testing."""

    def __init__(self, slot_idx: int = 0):
        self.slot_idx = slot_idx
        self._state = "IDLE"
        self._transitions = []
        self._context = MagicMock()
        self._context.total_loop = 0
        self._context.current_loop = 0
        self._context.loop_step = 1
        self._context.total_batch = 0
        self._context.current_batch = 0
        self._context.is_precondition = False
        self._can_transition = True

    @property
    def state(self):
        return self._state

    @property
    def context(self):
        return self._context

    def can_transition(self, event) -> bool:
        return self._can_transition

    def trigger(self, event, **kwargs):
        self._transitions.append((event, kwargs))


class FakeController:
    """Fake MFCController for testing."""

    def __init__(self):
        self._start_calls = []
        self._continue_calls = []
        self._stop_calls = []
        self._start_success = True
        self._continue_success = True
        self.window_manager = MagicMock()

    async def start_test(self, slot_idx: int, config: TestConfig) -> bool:
        self._start_calls.append((slot_idx, config))
        return self._start_success

    async def continue_batch(self, slot_idx: int) -> bool:
        self._continue_calls.append(slot_idx)
        return self._continue_success

    async def stop_test(self, slot_idx: int) -> bool:
        self._stop_calls.append(slot_idx)
        return True


def create_test_config(
    slot_idx: int = 0,
    loop_count: int = 10,
    loop_step: int = 2,
    precondition_enabled: bool = False,
    test_preset: TestPreset = TestPreset.FULL,
) -> TestConfig:
    """Create test configuration for testing."""
    return TestConfig(
        slot_idx=slot_idx,
        jira_no="TEST-001",
        sample_no="SAMPLE-001",
        drive="E",
        test_preset=test_preset,
        test_file=TestFile.PHOTO,
        method=TestMethod.ZERO_HR,
        capacity=TestCapacity.GB_32,
        loop_count=loop_count,
        loop_step=loop_step,
        test_name="test_001",
        drive_capacity_gb=64.0,
        precondition=PreconditionConfig(
            enabled=precondition_enabled,
            capacity=TestCapacity.GB_64 if precondition_enabled else None,
        ),
    )


class TestBatchCalculation:
    """Test batch count calculation."""

    @pytest.mark.parametrize(
        "loop_count,loop_step,expected_batches",
        [
            (10, 2, 5),  # exact division
            (10, 3, 4),  # 10/3 = 3.33 -> ceil = 4
            (10, 10, 1),  # single batch
            (1, 1, 1),  # minimum
            (100, 7, 15),  # 100/7 = 14.28 -> ceil = 15
            (5, 10, 1),  # loop_step > loop_count
        ],
    )
    def test_batch_count_calculation(
        self, loop_count: int, loop_step: int, expected_batches: int
    ):
        """[TC-BATCH_EXECUTOR-001] Batch count calculation - 테스트 시나리오를 검증한다.

            테스트 목적:
                Batch count calculation 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_batch_count_calculation 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        actual = math.ceil(loop_count / loop_step)
        assert actual == expected_batches


class TestBatchExecutor:
    """Test BatchExecutor functionality."""

    @pytest.fixture
    def fake_controller(self):
        """Create fake controller."""
        return FakeController()

    @pytest.fixture
    def fake_state_machine(self):
        """Create fake state machine."""
        return FakeStateMachine(slot_idx=0)

    @pytest.fixture
    def batch_executor(self, fake_controller, fake_state_machine):
        """Create BatchExecutor with fakes."""
        from services.batch_executor import BatchExecutor

        return BatchExecutor(
            controller=fake_controller,
            state_machine=fake_state_machine,
            poll_interval=0.01,  # Fast polling for tests
            pass_wait_timeout=1.0,
        )

    def test_request_cancel_sets_flag(self, batch_executor):
        """[TC-BATCH_EXECUTOR-002] Request cancel sets flag - 테스트 시나리오를 검증한다.

            테스트 목적:
                Request cancel sets flag 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_request_cancel_sets_flag 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        batch_executor.request_cancel(0)

        assert batch_executor.is_cancel_requested(0) is True

    def test_clear_cancel_clears_flag(self, batch_executor):
        """[TC-BATCH_EXECUTOR-003] Clear cancel clears flag - 테스트 시나리오를 검증한다.

            테스트 목적:
                Clear cancel clears flag 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_clear_cancel_clears_flag 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        batch_executor._cancel_requested[0] = True

        batch_executor.clear_cancel(0)

        assert batch_executor.is_cancel_requested(0) is False

    def test_is_cancel_requested_returns_false_by_default(self, batch_executor):
        """[TC-BATCH_EXECUTOR-004] Is cancel requested returns false by default - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is cancel requested returns false by default 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_cancel_requested_returns_false_by_default 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        assert batch_executor.is_cancel_requested(0) is False

    @pytest.mark.asyncio
    async def test_execute_calls_start_test_for_first_batch(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-005] Execute calls start test for first batch - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute calls start test for first batch 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_calls_start_test_for_first_batch 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=2, loop_step=2)

        # Mock _wait_for_pass to return True immediately
        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            await batch_executor.execute(0, config)

        assert len(fake_controller._start_calls) == 1
        assert fake_controller._start_calls[0][0] == 0

    @pytest.mark.asyncio
    async def test_execute_calls_continue_batch_for_subsequent_batches(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-006] Execute calls continue batch for subsequent batches - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute calls continue batch for subsequent batches 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_calls_continue_batch_for_subsequent_batches 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=4, loop_step=2)  # 2 batches

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            await batch_executor.execute(0, config)

        # First batch uses start_test, second batch uses continue_batch
        assert len(fake_controller._start_calls) == 1
        assert len(fake_controller._continue_calls) == 1

    @pytest.mark.asyncio
    async def test_execute_returns_false_on_cancellation(self, batch_executor):
        """[TC-BATCH_EXECUTOR-007] Execute returns false on cancellation - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute returns false on cancellation 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_returns_false_on_cancellation 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=10, loop_step=2)
        execution_count = {"count": 0}

        async def mock_wait_for_pass(slot_idx):
            execution_count["count"] += 1
            # Cancel after first batch
            if execution_count["count"] >= 1:
                batch_executor.request_cancel(slot_idx)
            return True

        with patch.object(batch_executor, "_wait_for_pass", side_effect=mock_wait_for_pass):
            result = await batch_executor.execute(0, config)

        # Should return False due to cancellation during execution
        assert result is False


class TestBatchProgressCallback:
    """Test progress callback functionality."""

    @pytest.fixture
    def fake_controller(self):
        return FakeController()

    @pytest.fixture
    def fake_state_machine(self):
        return FakeStateMachine(slot_idx=0)

    @pytest.fixture
    def batch_executor(self, fake_controller, fake_state_machine):
        from services.batch_executor import BatchExecutor

        return BatchExecutor(
            controller=fake_controller,
            state_machine=fake_state_machine,
            poll_interval=0.01,
            pass_wait_timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_progress_callback_called_for_each_batch(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-008] Progress callback called for each batch - 테스트 시나리오를 검증한다.

            테스트 목적:
                Progress callback called for each batch 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_progress_callback_called_for_each_batch 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=6, loop_step=2)  # 3 batches
        progress_calls = []

        async def progress_callback(progress):
            progress_calls.append(progress)

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            await batch_executor.execute(0, config, on_progress=progress_callback)

        assert len(progress_calls) == 3

    @pytest.mark.asyncio
    async def test_progress_callback_has_correct_batch_numbers(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-009] Progress callback has correct batch numbers - 테스트 시나리오를 검증한다.

            테스트 목적:
                Progress callback has correct batch numbers 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_progress_callback_has_correct_batch_numbers 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=6, loop_step=2)  # 3 batches
        progress_calls = []

        async def progress_callback(progress):
            progress_calls.append(progress)

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            await batch_executor.execute(0, config, on_progress=progress_callback)

        assert progress_calls[0].current_batch == 1
        assert progress_calls[1].current_batch == 2
        assert progress_calls[2].current_batch == 3
        assert all(p.total_batch == 3 for p in progress_calls)

    @pytest.mark.asyncio
    async def test_progress_callback_has_correct_loop_counts(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-010] Progress callback has correct loop counts - 테스트 시나리오를 검증한다.

            테스트 목적:
                Progress callback has correct loop counts 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_progress_callback_has_correct_loop_counts 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=6, loop_step=2)  # 3 batches
        progress_calls = []

        async def progress_callback(progress):
            progress_calls.append(progress)

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            await batch_executor.execute(0, config, on_progress=progress_callback)

        # current_loop starts at (batch-1) * loop_step
        assert progress_calls[0].current_loop == 0
        assert progress_calls[1].current_loop == 2
        assert progress_calls[2].current_loop == 4
        assert all(p.total_loop == 6 for p in progress_calls)

    @pytest.mark.asyncio
    async def test_progress_callback_has_increasing_progress_percent(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-011] Progress callback has increasing progress percent - 테스트 시나리오를 검증한다.

            테스트 목적:
                Progress callback has increasing progress percent 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_progress_callback_has_increasing_progress_percent 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=10, loop_step=2)  # 5 batches
        progress_calls = []

        async def progress_callback(progress):
            progress_calls.append(progress)

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            await batch_executor.execute(0, config, on_progress=progress_callback)

        # Progress should increase
        for i in range(1, len(progress_calls)):
            assert progress_calls[i].progress_percent > progress_calls[i - 1].progress_percent


class TestBatchCancellation:
    """Test cancellation state propagation."""

    @pytest.fixture
    def fake_controller(self):
        return FakeController()

    @pytest.fixture
    def fake_state_machine(self):
        return FakeStateMachine(slot_idx=0)

    @pytest.fixture
    def batch_executor(self, fake_controller, fake_state_machine):
        from services.batch_executor import BatchExecutor

        return BatchExecutor(
            controller=fake_controller,
            state_machine=fake_state_machine,
            poll_interval=0.01,
            pass_wait_timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_cancel_mid_execution_stops_batches(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-012] Cancel mid execution stops batches - 테스트 시나리오를 검증한다.

            테스트 목적:
                Cancel mid execution stops batches 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_cancel_mid_execution_stops_batches 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=10, loop_step=2)  # 5 batches
        batch_counter = {"count": 0}

        async def mock_wait_for_pass(slot_idx):
            batch_counter["count"] += 1
            # Cancel after 2 batches
            if batch_counter["count"] >= 2:
                batch_executor.request_cancel(slot_idx)
            return True

        with patch.object(batch_executor, "_wait_for_pass", side_effect=mock_wait_for_pass):
            result = await batch_executor.execute(0, config)

        assert result is False
        assert batch_counter["count"] == 2  # Stopped after 2 batches

    @pytest.mark.asyncio
    async def test_cancel_triggers_stop_event(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-013] Cancel triggers stop event - 테스트 시나리오를 검증한다.

            테스트 목적:
                Cancel triggers stop event 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_cancel_triggers_stop_event 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from domain.state_machine import SlotEvent

        config = create_test_config(loop_count=4, loop_step=2)  # 2 batches
        execution_count = {"count": 0}

        async def mock_wait_for_pass(slot_idx):
            execution_count["count"] += 1
            # Cancel during execution
            if execution_count["count"] >= 1:
                batch_executor.request_cancel(slot_idx)
            return True

        with patch.object(batch_executor, "_wait_for_pass", side_effect=mock_wait_for_pass):
            await batch_executor.execute(0, config)

        # Should have triggered STOP
        stop_transitions = [t for t in fake_state_machine._transitions if t[0] == SlotEvent.STOP]
        assert len(stop_transitions) >= 1

    @pytest.mark.asyncio
    async def test_execute_clears_cancel_flag_at_start(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-014] Execute clears cancel flag at start - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute clears cancel flag at start 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_clears_cancel_flag_at_start 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        batch_executor._cancel_requested[0] = True

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            # It will cancel because flag was set initially
            # but clear_cancel is called at start of execute
            await batch_executor.execute(0, create_test_config(loop_count=2, loop_step=2))

        # clear_cancel was called (verified by checking it's false after start)
        assert batch_executor.is_cancel_requested(0) is False


class TestBatchExecutorFailures:
    """Test failure handling."""

    @pytest.fixture
    def fake_controller(self):
        return FakeController()

    @pytest.fixture
    def fake_state_machine(self):
        return FakeStateMachine(slot_idx=0)

    @pytest.fixture
    def batch_executor(self, fake_controller, fake_state_machine):
        from services.batch_executor import BatchExecutor

        return BatchExecutor(
            controller=fake_controller,
            state_machine=fake_state_machine,
            poll_interval=0.01,
            pass_wait_timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_false_on_start_failure(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-015] Execute returns false on start failure - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute returns false on start failure 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_returns_false_on_start_failure 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        fake_controller._start_success = False
        config = create_test_config(loop_count=2, loop_step=2)

        result = await batch_executor.execute(0, config)

        assert result is False

    @pytest.mark.asyncio
    async def test_execute_returns_false_on_continue_failure(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-016] Execute returns false on continue failure - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute returns false on continue failure 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_returns_false_on_continue_failure 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        fake_controller._continue_success = False
        config = create_test_config(loop_count=4, loop_step=2)  # 2 batches

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = True

            result = await batch_executor.execute(0, config)

        assert result is False
        assert len(fake_controller._continue_calls) == 1  # Failed on first continue

    @pytest.mark.asyncio
    async def test_execute_returns_false_on_wait_for_pass_failure(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-017] Execute returns false on wait for pass failure - 테스트 시나리오를 검증한다.

            테스트 목적:
                Execute returns false on wait for pass failure 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_execute_returns_false_on_wait_for_pass_failure 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        config = create_test_config(loop_count=2, loop_step=2)

        with patch.object(
            batch_executor, "_wait_for_pass", new_callable=AsyncMock
        ) as mock_wait:
            mock_wait.return_value = False

            result = await batch_executor.execute(0, config)

        assert result is False

    @pytest.mark.asyncio
    async def test_failure_triggers_fail_event(
        self, batch_executor, fake_controller, fake_state_machine
    ):
        """[TC-BATCH_EXECUTOR-018] Failure triggers fail event - 테스트 시나리오를 검증한다.

            테스트 목적:
                Failure triggers fail event 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_failure_triggers_fail_event 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from domain.state_machine import SlotEvent

        fake_controller._start_success = False
        config = create_test_config(loop_count=2, loop_step=2)

        await batch_executor.execute(0, config)

        fail_transitions = [t for t in fake_state_machine._transitions if t[0] == SlotEvent.FAIL]
        assert len(fail_transitions) >= 1


class TestBatchProgress:
    """Test BatchProgress dataclass."""

    def test_batch_progress_to_dict(self):
        """[TC-BATCH_EXECUTOR-019] Batch progress to dict - 테스트 시나리오를 검증한다.

            테스트 목적:
                Batch progress to dict 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_batch_progress_to_dict 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from services.batch_executor import BatchProgress

        now = datetime.now()
        progress = BatchProgress(
            slot_idx=0,
            current_batch=2,
            total_batch=5,
            current_loop=4,
            total_loop=10,
            loop_step=2,
            progress_percent=40.0,
            started_at=now,
            estimated_remaining=120,
        )

        result = progress.to_dict()

        assert result["slot_idx"] == 0
        assert result["current_batch"] == 2
        assert result["total_batch"] == 5
        assert result["current_loop"] == 4
        assert result["total_loop"] == 10
        assert result["loop_step"] == 2
        assert result["progress_percent"] == 40.0
        assert result["started_at"] == now.isoformat()
        assert result["estimated_remaining"] == 120

    def test_batch_progress_to_dict_with_none_values(self):
        """[TC-BATCH_EXECUTOR-020] Batch progress to dict with none values - 테스트 시나리오를 검증한다.

            테스트 목적:
                Batch progress to dict with none values 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_batch_progress_to_dict_with_none_values 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from services.batch_executor import BatchProgress

        progress = BatchProgress(
            slot_idx=0,
            current_batch=1,
            total_batch=1,
            current_loop=0,
            total_loop=1,
            loop_step=1,
            progress_percent=0.0,
        )

        result = progress.to_dict()

        assert result["started_at"] is None
        assert result["estimated_remaining"] is None


class TestBatchExecutorManager:
    """Test BatchExecutorManager functionality."""

    @pytest.fixture
    def mock_controller(self):
        return FakeController()

    @pytest.fixture
    def mock_state_machines(self):
        return {0: FakeStateMachine(0), 1: FakeStateMachine(1)}

    def test_manager_is_running_returns_false_when_not_started(
        self, mock_controller, mock_state_machines
    ):
        """[TC-BATCH_EXECUTOR-021] Manager is running returns false when not started - 테스트 시나리오를 검증한다.

            테스트 목적:
                Manager is running returns false when not started 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_manager_is_running_returns_false_when_not_started 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from services.batch_executor import BatchExecutorManager

        manager = BatchExecutorManager(mock_controller, mock_state_machines)

        assert manager.is_running(0) is False

    @pytest.mark.asyncio
    async def test_manager_stop_batch_test_requests_cancel(
        self, mock_controller, mock_state_machines
    ):
        """[TC-BATCH_EXECUTOR-022] Manager stop batch test requests cancel - 테스트 시나리오를 검증한다.

            테스트 목적:
                Manager stop batch test requests cancel 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_manager_stop_batch_test_requests_cancel 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from services.batch_executor import BatchExecutorManager

        manager = BatchExecutorManager(mock_controller, mock_state_machines)

        # Create executor for slot 0
        executor = manager._get_or_create_executor(0)

        result = await manager.stop_batch_test(0)

        assert result is True
        assert executor.is_cancel_requested(0) is True

    def test_manager_get_or_create_executor_creates_new(
        self, mock_controller, mock_state_machines
    ):
        """[TC-BATCH_EXECUTOR-023] Manager get or create executor creates new - 테스트 시나리오를 검증한다.

            테스트 목적:
                Manager get or create executor creates new 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_manager_get_or_create_executor_creates_new 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from services.batch_executor import BatchExecutorManager

        manager = BatchExecutorManager(mock_controller, mock_state_machines)

        executor = manager._get_or_create_executor(0)

        assert executor is not None
        assert 0 in manager._executors

    def test_manager_get_or_create_executor_reuses_existing(
        self, mock_controller, mock_state_machines
    ):
        """[TC-BATCH_EXECUTOR-024] Manager get or create executor reuses existing - 테스트 시나리오를 검증한다.

            테스트 목적:
                Manager get or create executor reuses existing 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_manager_get_or_create_executor_reuses_existing 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from services.batch_executor import BatchExecutorManager

        manager = BatchExecutorManager(mock_controller, mock_state_machines)

        executor1 = manager._get_or_create_executor(0)
        executor2 = manager._get_or_create_executor(0)

        assert executor1 is executor2
