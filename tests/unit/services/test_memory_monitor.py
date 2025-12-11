"""Unit tests for MemoryMonitor service.

Tests periodic memory monitoring, automatic optimization,
and threshold-based alerting.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory import (
    MemoryManager,
    MemoryStats,
    MemoryThresholds,
    OptimizationResult,
    FakeMemoryManager,
)
from services.memory_monitor import MemoryMonitor, MemoryMonitorConfig
from infrastructure.clock import FakeClock


class FakeLogger:
    """Fake logger for testing."""

    def __init__(self):
        self.logs: list[tuple[str, str, dict]] = []

    def info(self, msg: str, **kwargs):
        self.logs.append(("info", msg, kwargs))

    def warning(self, msg: str, **kwargs):
        self.logs.append(("warning", msg, kwargs))

    def error(self, msg: str, **kwargs):
        self.logs.append(("error", msg, kwargs))

    def debug(self, msg: str, **kwargs):
        self.logs.append(("debug", msg, kwargs))


class TestMemoryMonitorConfig:
    """Tests for MemoryMonitorConfig."""

    def test_defaults(self):
        """Test default configuration values."""
        config = MemoryMonitorConfig()

        assert config.check_interval_seconds == 60.0
        assert config.auto_optimize is True
        assert config.log_stats_interval_seconds == 3600.0
        assert config.alert_on_warning is True
        assert config.alert_on_critical is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = MemoryMonitorConfig(
            check_interval_seconds=30.0,
            auto_optimize=False,
            log_stats_interval_seconds=1800.0,
        )

        assert config.check_interval_seconds == 30.0
        assert config.auto_optimize is False
        assert config.log_stats_interval_seconds == 1800.0


class TestMemoryMonitor:
    """Tests for MemoryMonitor service."""

    @pytest.fixture
    def fake_clock(self):
        """Create a fake clock."""
        return FakeClock(initial_time=datetime(2025, 1, 1, 12, 0, 0))

    @pytest.fixture
    def fake_logger(self):
        """Create a fake logger."""
        return FakeLogger()

    @pytest.fixture
    def fake_memory_manager(self):
        """Create a fake memory manager."""
        return FakeMemoryManager(initial_memory_mb=100.0)

    @pytest.fixture
    def memory_monitor(self, fake_memory_manager, fake_clock, fake_logger):
        """Create a MemoryMonitor with fake dependencies."""
        return MemoryMonitor(
            memory_manager=fake_memory_manager,
            clock=fake_clock,
            logger=fake_logger,
            config=MemoryMonitorConfig(
                check_interval_seconds=1.0,  # Fast for testing
                auto_optimize=True,
                log_stats_interval_seconds=10.0,
            ),
            thresholds=MemoryThresholds(
                warning_mb=150.0,
                critical_mb=250.0,
            ),
        )

    def test_init(self, memory_monitor):
        """Test MemoryMonitor initialization."""
        assert memory_monitor.is_running is False
        assert memory_monitor._monitor_task is None

    @pytest.mark.asyncio
    async def test_start_stop(self, memory_monitor):
        """Test starting and stopping the monitor."""
        # Start
        await memory_monitor.start()
        assert memory_monitor.is_running is True
        assert memory_monitor._monitor_task is not None

        # Give task time to run
        await asyncio.sleep(0.1)

        # Stop
        await memory_monitor.stop()
        assert memory_monitor.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_warning(self, memory_monitor, fake_logger):
        """Test that double start logs warning."""
        await memory_monitor.start()
        await memory_monitor.start()  # Second start

        # Check warning was logged
        warnings = [log for log in fake_logger.logs if log[0] == "warning"]
        assert any("already running" in log[1] for log in warnings)

        await memory_monitor.stop()

    @pytest.mark.asyncio
    async def test_get_current_stats(self, memory_monitor, fake_memory_manager):
        """Test getting current memory stats."""
        fake_memory_manager.set_memory_mb(120.0)

        stats = memory_monitor.get_current_stats()

        assert stats.rss_mb == 120.0

    @pytest.mark.asyncio
    async def test_force_optimize(self, memory_monitor, fake_memory_manager):
        """Test forced optimization."""
        fake_memory_manager.set_memory_mb(100.0)

        result = await memory_monitor.force_optimize()

        assert isinstance(result, OptimizationResult)
        assert result.before_mb == 100.0
        # Optimization history should be updated
        assert len(memory_monitor._optimization_history) == 1

    @pytest.mark.asyncio
    async def test_memory_alert_callback(self, fake_memory_manager, fake_clock, fake_logger):
        """Test memory alert callback on threshold exceeded."""
        alert_callback = AsyncMock()

        monitor = MemoryMonitor(
            memory_manager=fake_memory_manager,
            clock=fake_clock,
            logger=fake_logger,
            config=MemoryMonitorConfig(
                check_interval_seconds=0.1,
                auto_optimize=False,  # Disable auto-optimize for this test
            ),
            thresholds=MemoryThresholds(
                warning_mb=80.0,  # Set low threshold
                critical_mb=120.0,
            ),
        )
        monitor.on_memory_alert = alert_callback

        # Set memory above warning threshold
        fake_memory_manager.set_memory_mb(90.0)

        # Manually check memory (simulate one iteration)
        await monitor._check_memory()

        # Alert callback should have been called
        alert_callback.assert_called_once()
        call_args = alert_callback.call_args
        assert call_args[0][0] == "warning"

    @pytest.mark.asyncio
    async def test_critical_alert(self, fake_memory_manager, fake_clock, fake_logger):
        """Test critical memory alert."""
        alert_callback = AsyncMock()

        monitor = MemoryMonitor(
            memory_manager=fake_memory_manager,
            clock=fake_clock,
            logger=fake_logger,
            config=MemoryMonitorConfig(
                check_interval_seconds=0.1,
                auto_optimize=False,
            ),
            thresholds=MemoryThresholds(
                warning_mb=80.0,
                critical_mb=100.0,  # Set critical threshold
            ),
        )
        monitor.on_memory_alert = alert_callback

        # Set memory above critical threshold
        fake_memory_manager.set_memory_mb(110.0)

        await monitor._check_memory()

        alert_callback.assert_called_once()
        call_args = alert_callback.call_args
        assert call_args[0][0] == "critical"

    @pytest.mark.asyncio
    async def test_stats_history_limit(self, memory_monitor, fake_memory_manager):
        """Test that stats history respects size limit."""
        memory_monitor._max_history_size = 5

        # Add more than max history size
        for i in range(10):
            fake_memory_manager.set_memory_mb(100.0 + i)
            await memory_monitor._check_memory()

        assert len(memory_monitor._stats_history) == 5

    @pytest.mark.asyncio
    async def test_optimization_callback(self, memory_monitor, fake_memory_manager):
        """Test optimization complete callback."""
        opt_callback = AsyncMock()
        memory_monitor.on_optimization_complete = opt_callback

        # Make should_optimize return True by setting up conditions
        fake_memory_manager._memory_mb = 100.0

        # Force optimization
        await memory_monitor.force_optimize()

        opt_callback.assert_called_once()

    def test_get_statistics_summary(self, memory_monitor, fake_memory_manager):
        """Test getting statistics summary."""
        summary = memory_monitor.get_statistics_summary()

        assert "current" in summary
        assert "history" in summary
        assert "optimizations" in summary
        assert "manager" in summary
        assert "config" in summary

    def test_register_cleanup(self, memory_monitor):
        """Test registering cleanup callbacks."""
        callback = MagicMock()
        memory_monitor.register_cleanup(callback, "test_cleanup")

        # Verify it was passed to memory manager
        assert "test_cleanup" in memory_monitor._memory_manager._cleanup_callbacks

    def test_clear_history(self, memory_monitor, fake_logger):
        """Test clearing history."""
        # Add some history
        memory_monitor._stats_history.append(
            MemoryStats(
                rss_mb=100.0,
                vms_mb=150.0,
                gc_objects=1000,
                gc_generations=(
                    {"collections": 1, "collected": 10},
                    {"collections": 1, "collected": 10},
                    {"collections": 1, "collected": 10},
                ),
            )
        )
        memory_monitor._optimization_history.append(
            OptimizationResult(
                before_mb=100.0,
                after_mb=90.0,
                freed_mb=10.0,
                collected_objects=100,
                duration_ms=10.0,
            )
        )

        memory_monitor.clear_history()

        assert len(memory_monitor._stats_history) == 0
        assert len(memory_monitor._optimization_history) == 0

    @pytest.mark.asyncio
    async def test_monitor_loop_error_handling(
        self, fake_memory_manager, fake_clock, fake_logger
    ):
        """Test that monitor loop handles errors gracefully."""
        # Create a memory manager that raises an error
        class ErrorMemoryManager(FakeMemoryManager):
            def __init__(self):
                super().__init__()
                self._error_count = 0

            def get_memory_usage(self):
                self._error_count += 1
                if self._error_count == 1:
                    raise RuntimeError("Simulated error")
                return super().get_memory_usage()

        error_manager = ErrorMemoryManager()

        monitor = MemoryMonitor(
            memory_manager=error_manager,
            clock=fake_clock,
            logger=fake_logger,
            config=MemoryMonitorConfig(check_interval_seconds=0.05),
        )

        await monitor.start()
        await asyncio.sleep(0.2)  # Let a few iterations run
        await monitor.stop()

        # Should have logged error but continued
        errors = [log for log in fake_logger.logs if log[0] == "error"]
        assert len(errors) >= 1
