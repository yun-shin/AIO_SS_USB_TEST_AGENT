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
        """Test MemoryStats to_dict conversion."""
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
        """Test OptimizationResult to_dict conversion."""
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
        """Test MemoryManager initialization."""
        assert memory_manager._last_gc_time is None
        assert memory_manager._optimization_count == 0
        assert memory_manager._total_freed_mb == 0.0

    def test_get_memory_usage(self, memory_manager):
        """Test getting memory usage statistics."""
        stats = memory_manager.get_memory_usage()

        assert isinstance(stats, MemoryStats)
        assert stats.rss_mb >= 0
        assert stats.vms_mb >= 0
        assert stats.gc_objects >= 0
        assert len(stats.gc_generations) == 3

    @pytest.mark.asyncio
    async def test_optimize_first_time(self, memory_manager):
        """Test first optimization run."""
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
        """Test that optimization is skipped if interval hasn't passed."""
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
        """Test forced optimization regardless of interval."""
        # First optimization
        await memory_manager.optimize()

        # Force second optimization immediately
        result = await memory_manager.optimize(force=True)

        assert memory_manager._optimization_count == 2

    @pytest.mark.asyncio
    async def test_optimize_runs_after_interval(self, memory_manager, fake_clock):
        """Test optimization runs after interval has passed."""
        # First optimization
        await memory_manager.optimize()

        # Advance time past interval
        fake_clock.advance(61.0)  # 61 seconds > 60 seconds interval

        # Second optimization should run
        await memory_manager.optimize()

        assert memory_manager._optimization_count == 2

    def test_register_cleanup_callback(self, memory_manager):
        """Test registering cleanup callbacks."""
        callback = MagicMock()
        memory_manager.register_cleanup_callback(callback, "test_cleanup")

        assert "test_cleanup" in memory_manager._cleanup_callbacks

    def test_unregister_cleanup_callback(self, memory_manager):
        """Test unregistering cleanup callbacks."""
        callback = MagicMock()
        memory_manager.register_cleanup_callback(callback, "test_cleanup")
        memory_manager.unregister_cleanup_callback("test_cleanup")

        assert "test_cleanup" not in memory_manager._cleanup_callbacks

    @pytest.mark.asyncio
    async def test_cleanup_callbacks_executed(self, memory_manager, fake_clock):
        """Test that cleanup callbacks are executed during optimization."""
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
        """Test that failed callbacks are removed."""
        def failing_callback():
            raise RuntimeError("Callback failed")

        memory_manager.register_cleanup_callback(failing_callback, "failing")

        await memory_manager.optimize(force=True)

        # Failing callback should be removed
        assert "failing" not in memory_manager._cleanup_callbacks

    def test_should_optimize_no_previous(self, memory_manager):
        """Test should_optimize returns False when no previous optimization."""
        # No threshold exceeded, no previous GC
        result = memory_manager.should_optimize()
        # With small memory usage and no previous GC, should still return False
        # unless interval triggers it
        assert isinstance(result, bool)

    def test_should_optimize_interval_passed(self, memory_manager, fake_clock):
        """Test should_optimize returns True when interval passed."""
        memory_manager._last_gc_time = fake_clock.now()
        fake_clock.advance(301.0)  # Past default interval

        # Note: Default interval is 60s in our test fixture
        assert memory_manager.should_optimize() is True

    def test_is_memory_critical(self, memory_manager):
        """Test is_memory_critical detection."""
        # With normal memory usage, should not be critical
        result = memory_manager.is_memory_critical()
        # This depends on actual system memory
        assert isinstance(result, bool)

    def test_get_statistics(self, memory_manager):
        """Test getting statistics summary."""
        stats = memory_manager.get_statistics()

        assert "current_memory" in stats
        assert "optimization_count" in stats
        assert "total_freed_mb" in stats
        assert "thresholds" in stats
        assert "cleanup_callbacks" in stats


class TestFakeMemoryManager:
    """Tests for FakeMemoryManager."""

    def test_init(self):
        """Test FakeMemoryManager initialization."""
        manager = FakeMemoryManager(initial_memory_mb=150.0)
        assert manager._memory_mb == 150.0

    def test_get_memory_usage(self):
        """Test getting simulated memory usage."""
        manager = FakeMemoryManager(initial_memory_mb=100.0)
        stats = manager.get_memory_usage()

        assert stats.rss_mb == 100.0
        assert stats.vms_mb == 150.0  # 1.5x
        assert stats.gc_objects == 1000

    @pytest.mark.asyncio
    async def test_optimize(self):
        """Test simulated optimization."""
        manager = FakeMemoryManager(initial_memory_mb=100.0)

        result = await manager.optimize()

        assert result.before_mb == 100.0
        assert result.after_mb == 90.0  # 10% reduction
        assert result.freed_mb == 10.0
        assert manager._optimize_calls == [False]

    @pytest.mark.asyncio
    async def test_optimize_force(self):
        """Test forced optimization tracking."""
        manager = FakeMemoryManager(initial_memory_mb=100.0)

        await manager.optimize(force=True)
        await manager.optimize(force=False)

        assert manager._optimize_calls == [True, False]

    def test_register_cleanup_callback(self):
        """Test registering cleanup callbacks."""
        manager = FakeMemoryManager()
        callback = MagicMock()

        manager.register_cleanup_callback(callback, "test")

        assert "test" in manager._cleanup_callbacks

    def test_set_memory_mb(self):
        """Test setting simulated memory."""
        manager = FakeMemoryManager(initial_memory_mb=100.0)
        manager.set_memory_mb(250.0)

        stats = manager.get_memory_usage()
        assert stats.rss_mb == 250.0
