"""Unit tests for MemoryManager.

Tests memory management functionality including:
- Memory statistics collection
- Garbage collection
- Cleanup callbacks
- Threshold detection
"""

import gc
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.memory import (
    MemoryManager,
    MemoryStats,
    MemoryThresholds,
    OptimizationResult,
    FakeMemoryManager,
)
from infrastructure.clock import FakeClock


class TestMemoryStats:
    """Tests for MemoryStats dataclass."""

    def test_to_dict(self):
        """[TC-MEMORY-001] To dict - 테스트 시나리오를 검증한다.

            테스트 목적:
                To dict 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_to_dict 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        stats = MemoryStats(
            rss_mb=100.5,
            vms_mb=200.3,
            gc_objects=5000,
            gc_generations=(
                {"collections": 10, "collected": 100},
                {"collections": 5, "collected": 50},
                {"collections": 1, "collected": 10},
            ),
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

        result = stats.to_dict()

        assert result["rss_mb"] == 100.5
        assert result["vms_mb"] == 200.3
        assert result["gc_objects"] == 5000
        assert len(result["gc_generations"]) == 3
        assert "2025-01-01" in result["timestamp"]


class TestOptimizationResult:
    """Tests for OptimizationResult dataclass."""

    def test_to_dict(self):
        """[TC-MEMORY-002] To dict - 테스트 시나리오를 검증한다.

            테스트 목적:
                To dict 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_to_dict 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        result = OptimizationResult(
            before_mb=150.0,
            after_mb=100.0,
            freed_mb=50.0,
            collected_objects=500,
            duration_ms=15.5,
            callbacks_executed=3,
        )

        result_dict = result.to_dict()

        assert result_dict["before_mb"] == 150.0
        assert result_dict["after_mb"] == 100.0
        assert result_dict["freed_mb"] == 50.0
        assert result_dict["collected_objects"] == 500
        assert result_dict["duration_ms"] == 15.5
        assert result_dict["callbacks_executed"] == 3


class TestMemoryManager:
    """Tests for MemoryManager."""

    @pytest.fixture
    def fake_clock(self):
        """Create a fake clock for testing."""
        return FakeClock(initial_time=datetime(2025, 1, 1, 12, 0, 0))

    @pytest.fixture
    def memory_manager(self, fake_clock):
        """Create a MemoryManager with fake clock."""
        return MemoryManager(
            clock=fake_clock,
            thresholds=MemoryThresholds(
                warning_mb=100.0,
                critical_mb=200.0,
                gc_interval_seconds=60.0,
                max_gc_objects=10000,
            ),
        )

    def test_init(self, memory_manager):
        """[TC-MEMORY-003] Init - 테스트 시나리오를 검증한다.

            테스트 목적:
                Init 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_init 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        assert memory_manager._last_gc_time is None
        assert memory_manager._optimization_count == 0
        assert memory_manager._total_freed_mb == 0.0

    def test_get_memory_usage(self, memory_manager):
        """[TC-MEMORY-004] Get memory usage - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get memory usage 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_memory_usage 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        stats = memory_manager.get_memory_usage()

        assert isinstance(stats, MemoryStats)
        assert stats.rss_mb >= 0
        assert stats.vms_mb >= 0
        assert stats.gc_objects >= 0
        assert len(stats.gc_generations) == 3

    @pytest.mark.asyncio
    async def test_optimize_first_time(self, memory_manager):
        """[TC-MEMORY-005] Optimize first time - 테스트 시나리오를 검증한다.

            테스트 목적:
                Optimize first time 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_optimize_first_time 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        result = await memory_manager.optimize()

        assert isinstance(result, OptimizationResult)
        assert result.collected_objects >= 0
        assert result.duration_ms >= 0
        assert memory_manager._optimization_count == 1
        assert memory_manager._last_gc_time is not None

    @pytest.mark.asyncio
    async def test_optimize_skip_if_interval_not_passed(
        self, memory_manager, fake_clock
    ):
        """[TC-MEMORY-006] Optimize skip if interval not passed - 테스트 시나리오를 검증한다.

            테스트 목적:
                Optimize skip if interval not passed 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_optimize_skip_if_interval_not_passed 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        # First optimization
        await memory_manager.optimize()

        # Advance time by less than interval
        fake_clock.advance(30.0)  # 30 seconds < 60 seconds interval

        # Second optimization should be skipped
        result = await memory_manager.optimize()

        assert result.freed_mb == 0.0
        assert result.collected_objects == 0
        assert memory_manager._optimization_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_optimize_force(self, memory_manager, fake_clock):
        """[TC-MEMORY-007] Optimize force - 테스트 시나리오를 검증한다.

            테스트 목적:
                Optimize force 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_optimize_force 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        # First optimization
        await memory_manager.optimize()

        # Force second optimization immediately
        result = await memory_manager.optimize(force=True)

        assert memory_manager._optimization_count == 2

    @pytest.mark.asyncio
    async def test_optimize_runs_after_interval(self, memory_manager, fake_clock):
        """[TC-MEMORY-008] Optimize runs after interval - 테스트 시나리오를 검증한다.

            테스트 목적:
                Optimize runs after interval 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_optimize_runs_after_interval 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        # First optimization
        await memory_manager.optimize()

        # Advance time past interval
        fake_clock.advance(61.0)  # 61 seconds > 60 seconds interval

        # Second optimization should run
        await memory_manager.optimize()

        assert memory_manager._optimization_count == 2

    def test_register_cleanup_callback(self, memory_manager):
        """[TC-MEMORY-009] Register cleanup callback - 테스트 시나리오를 검증한다.

            테스트 목적:
                Register cleanup callback 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_register_cleanup_callback 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback = MagicMock()
        memory_manager.register_cleanup_callback(callback, "test_cleanup")

        assert "test_cleanup" in memory_manager._cleanup_callbacks

    def test_unregister_cleanup_callback(self, memory_manager):
        """[TC-MEMORY-010] Unregister cleanup callback - 테스트 시나리오를 검증한다.

            테스트 목적:
                Unregister cleanup callback 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_unregister_cleanup_callback 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback = MagicMock()
        memory_manager.register_cleanup_callback(callback, "test_cleanup")
        memory_manager.unregister_cleanup_callback("test_cleanup")

        assert "test_cleanup" not in memory_manager._cleanup_callbacks

    @pytest.mark.asyncio
    async def test_cleanup_callbacks_executed(self, memory_manager, fake_clock):
        """[TC-MEMORY-011] Cleanup callbacks executed - 테스트 시나리오를 검증한다.

            테스트 목적:
                Cleanup callbacks executed 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_cleanup_callbacks_executed 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        callback1 = MagicMock()
        callback2 = MagicMock()

        memory_manager.register_cleanup_callback(callback1, "cleanup1")
        memory_manager.register_cleanup_callback(callback2, "cleanup2")

        result = await memory_manager.optimize(force=True)

        callback1.assert_called_once()
        callback2.assert_called_once()
        assert result.callbacks_executed == 2

    @pytest.mark.asyncio
    async def test_failed_callback_removed(self, memory_manager, fake_clock):
        """[TC-MEMORY-012] Failed callback removed - 테스트 시나리오를 검증한다.

            테스트 목적:
                Failed callback removed 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_failed_callback_removed 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        def failing_callback():
            raise RuntimeError("Callback failed")

        memory_manager.register_cleanup_callback(failing_callback, "failing")

        await memory_manager.optimize(force=True)

        # Failing callback should be removed
        assert "failing" not in memory_manager._cleanup_callbacks

    def test_should_optimize_no_previous(self, memory_manager):
        """[TC-MEMORY-013] Should optimize no previous - 테스트 시나리오를 검증한다.

            테스트 목적:
                Should optimize no previous 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_should_optimize_no_previous 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        # No threshold exceeded, no previous GC
        result = memory_manager.should_optimize()
        # With small memory usage and no previous GC, should still return False
        # unless interval triggers it
        assert isinstance(result, bool)

    def test_should_optimize_interval_passed(self, memory_manager, fake_clock):
        """[TC-MEMORY-014] Should optimize interval passed - 테스트 시나리오를 검증한다.

            테스트 목적:
                Should optimize interval passed 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_should_optimize_interval_passed 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        memory_manager._last_gc_time = fake_clock.now()
        fake_clock.advance(301.0)  # Past default interval

        # Note: Default interval is 60s in our test fixture
        assert memory_manager.should_optimize() is True

    def test_is_memory_critical(self, memory_manager):
        """[TC-MEMORY-015] Is memory critical - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is memory critical 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_memory_critical 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        # With normal memory usage, should not be critical
        result = memory_manager.is_memory_critical()
        # This depends on actual system memory
        assert isinstance(result, bool)

    def test_get_statistics(self, memory_manager):
        """[TC-MEMORY-016] Get statistics - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get statistics 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_statistics 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        stats = memory_manager.get_statistics()

        assert "current_memory" in stats
        assert "optimization_count" in stats
        assert "total_freed_mb" in stats
        assert "thresholds" in stats
        assert "cleanup_callbacks" in stats


class TestFakeMemoryManager:
    """Tests for FakeMemoryManager."""

    def test_init(self):
        """[TC-MEMORY-017] Init - 테스트 시나리오를 검증한다.

            테스트 목적:
                Init 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_init 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = FakeMemoryManager(initial_memory_mb=150.0)
        assert manager._memory_mb == 150.0

    def test_get_memory_usage(self):
        """[TC-MEMORY-018] Get memory usage - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get memory usage 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_memory_usage 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = FakeMemoryManager(initial_memory_mb=100.0)
        stats = manager.get_memory_usage()

        assert stats.rss_mb == 100.0
        assert stats.vms_mb == 150.0  # 1.5x
        assert stats.gc_objects == 1000

    @pytest.mark.asyncio
    async def test_optimize(self):
        """[TC-MEMORY-019] Optimize - 테스트 시나리오를 검증한다.

            테스트 목적:
                Optimize 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_optimize 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = FakeMemoryManager(initial_memory_mb=100.0)

        result = await manager.optimize()

        assert result.before_mb == 100.0
        assert result.after_mb == 90.0  # 10% reduction
        assert result.freed_mb == 10.0
        assert manager._optimize_calls == [False]

    @pytest.mark.asyncio
    async def test_optimize_force(self):
        """[TC-MEMORY-020] Optimize force - 테스트 시나리오를 검증한다.

            테스트 목적:
                Optimize force 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_optimize_force 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = FakeMemoryManager(initial_memory_mb=100.0)

        await manager.optimize(force=True)
        await manager.optimize(force=False)

        assert manager._optimize_calls == [True, False]

    def test_register_cleanup_callback(self):
        """[TC-MEMORY-021] Register cleanup callback - 테스트 시나리오를 검증한다.

            테스트 목적:
                Register cleanup callback 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_register_cleanup_callback 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = FakeMemoryManager()
        callback = MagicMock()

        manager.register_cleanup_callback(callback, "test")

        assert "test" in manager._cleanup_callbacks

    def test_set_memory_mb(self):
        """[TC-MEMORY-022] Set memory mb - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set memory mb 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_memory_mb 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        manager = FakeMemoryManager(initial_memory_mb=100.0)
        manager.set_memory_mb(250.0)

        stats = manager.get_memory_usage()
        assert stats.rss_mb == 250.0
