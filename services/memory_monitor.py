"""Memory Monitor Service.

Periodic memory monitoring and automatic optimization service
for long-running Agent processes.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, Awaitable

from core.memory import (
    MemoryManager,
    MemoryStats,
    MemoryThresholds,
    OptimizationResult,
)
from core.protocols import IClock, ILogger


@dataclass
class MemoryMonitorConfig:
    """Memory monitor configuration.

    Attributes:
        check_interval_seconds: Interval between memory checks.
        auto_optimize: Enable automatic optimization.
        log_stats_interval_seconds: Interval for logging memory stats.
        alert_on_warning: Enable alerts on warning threshold.
        alert_on_critical: Enable alerts on critical threshold.
    """

    check_interval_seconds: float = 60.0  # 1 minute
    auto_optimize: bool = True
    log_stats_interval_seconds: float = 3600.0  # 1 hour
    alert_on_warning: bool = True
    alert_on_critical: bool = True


class MemoryMonitor:
    """Memory monitoring service.

    Periodically monitors memory usage and performs automatic
    optimization when thresholds are exceeded.

    Features:
    - Periodic memory usage logging
    - Automatic garbage collection
    - Threshold-based alerts
    - Statistics collection

    Example:
        ```python
        monitor = MemoryMonitor(
            memory_manager=MemoryManager(clock=SystemClock()),
            clock=SystemClock(),
            logger=get_logger(__name__),
        )

        # Set alert callback
        monitor.on_memory_alert = async_alert_callback

        # Start monitoring
        await monitor.start()

        # ... agent runs ...

        # Stop monitoring
        await monitor.stop()
        ```
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        clock: IClock,
        logger: ILogger,
        config: Optional[MemoryMonitorConfig] = None,
        thresholds: Optional[MemoryThresholds] = None,
    ) -> None:
        """Initialize memory monitor.

        Args:
            memory_manager: Memory manager instance.
            clock: Clock instance.
            logger: Logger instance.
            config: Monitor configuration.
            thresholds: Memory thresholds.
        """
        self._memory_manager = memory_manager
        self._clock = clock
        self._logger = logger
        self._config = config or MemoryMonitorConfig()
        self._thresholds = thresholds or MemoryThresholds()

        # State
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_log_time: Optional[datetime] = None
        self._last_alert_time: Optional[datetime] = None

        # Statistics
        self._stats_history: list[MemoryStats] = []
        self._max_history_size = 1000  # Keep last 1000 samples
        self._optimization_history: list[OptimizationResult] = []
        self._max_optimization_history = 100

        # Callbacks
        self.on_memory_alert: Optional[
            Callable[[str, MemoryStats], Awaitable[None]]
        ] = None
        self.on_optimization_complete: Optional[
            Callable[[OptimizationResult], Awaitable[None]]
        ] = None

    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._is_running

    async def start(self) -> None:
        """Start memory monitoring."""
        if self._is_running:
            self._logger.warning("Memory monitor already running")
            return

        self._is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        self._logger.info(
            "Memory monitor started",
            check_interval=self._config.check_interval_seconds,
            auto_optimize=self._config.auto_optimize,
        )

    async def stop(self) -> None:
        """Stop memory monitoring."""
        self._is_running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        self._monitor_task = None
        self._logger.info("Memory monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._is_running:
            try:
                await self._check_memory()
                await self._clock.sleep(self._config.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Memory monitor error", error=str(e))
                await self._clock.sleep(self._config.check_interval_seconds)

    async def _check_memory(self) -> None:
        """Check memory usage and take action if needed."""
        stats = self._memory_manager.get_memory_usage()

        # Add to history (with size limit)
        self._stats_history.append(stats)
        if len(self._stats_history) > self._max_history_size:
            self._stats_history = self._stats_history[-self._max_history_size :]

        # Log stats periodically
        await self._maybe_log_stats(stats)

        # Check thresholds and alert
        await self._check_thresholds(stats)

        # Auto-optimize if enabled
        if self._config.auto_optimize and self._memory_manager.should_optimize():
            await self._perform_optimization()

    async def _maybe_log_stats(self, stats: MemoryStats) -> None:
        """Log memory stats if interval has passed.

        Args:
            stats: Current memory stats.
        """
        should_log = (
            self._last_log_time is None
            or (self._clock.now() - self._last_log_time).total_seconds()
            >= self._config.log_stats_interval_seconds
        )

        if should_log:
            self._logger.info(
                "Memory stats",
                rss_mb=round(stats.rss_mb, 2),
                vms_mb=round(stats.vms_mb, 2),
                gc_objects=stats.gc_objects,
            )
            self._last_log_time = self._clock.now()

    async def _check_thresholds(self, stats: MemoryStats) -> None:
        """Check memory thresholds and trigger alerts.

        Args:
            stats: Current memory stats.
        """
        # Rate limit alerts (at most once per 5 minutes)
        if self._last_alert_time is not None:
            elapsed = (self._clock.now() - self._last_alert_time).total_seconds()
            if elapsed < 300:  # 5 minutes
                return

        alert_level: Optional[str] = None

        if (
            self._config.alert_on_critical
            and stats.rss_mb >= self._thresholds.critical_mb
        ):
            alert_level = "critical"
            self._logger.error(
                "CRITICAL: Memory usage exceeded critical threshold",
                current_mb=round(stats.rss_mb, 2),
                threshold_mb=self._thresholds.critical_mb,
            )
        elif (
            self._config.alert_on_warning
            and stats.rss_mb >= self._thresholds.warning_mb
        ):
            alert_level = "warning"
            self._logger.warning(
                "WARNING: Memory usage exceeded warning threshold",
                current_mb=round(stats.rss_mb, 2),
                threshold_mb=self._thresholds.warning_mb,
            )

        if alert_level and self.on_memory_alert:
            try:
                await self.on_memory_alert(alert_level, stats)
                self._last_alert_time = self._clock.now()
            except Exception as e:
                self._logger.error("Memory alert callback failed", error=str(e))

    async def _perform_optimization(self) -> None:
        """Perform memory optimization."""
        self._logger.info("Starting memory optimization")

        try:
            result = await self._memory_manager.optimize()

            # Add to history
            self._optimization_history.append(result)
            if len(self._optimization_history) > self._max_optimization_history:
                self._optimization_history = self._optimization_history[
                    -self._max_optimization_history :
                ]

            self._logger.info(
                "Memory optimization complete",
                before_mb=round(result.before_mb, 2),
                after_mb=round(result.after_mb, 2),
                freed_mb=round(result.freed_mb, 2),
                collected_objects=result.collected_objects,
                duration_ms=round(result.duration_ms, 2),
            )

            if self.on_optimization_complete:
                try:
                    await self.on_optimization_complete(result)
                except Exception as e:
                    self._logger.error(
                        "Optimization callback failed",
                        error=str(e),
                    )

        except Exception as e:
            self._logger.error("Memory optimization failed", error=str(e))

    async def force_optimize(self) -> OptimizationResult:
        """Force immediate memory optimization.

        Returns:
            Optimization result.
        """
        self._logger.info("Force optimization requested")
        result = await self._memory_manager.optimize(force=True)

        self._optimization_history.append(result)
        if len(self._optimization_history) > self._max_optimization_history:
            self._optimization_history = self._optimization_history[
                -self._max_optimization_history :
            ]

        # Call optimization complete callback
        if self.on_optimization_complete:
            try:
                await self.on_optimization_complete(result)
            except Exception as e:
                self._logger.error(
                    "Optimization callback failed",
                    error=str(e),
                )

        return result

    def get_current_stats(self) -> MemoryStats:
        """Get current memory stats.

        Returns:
            Current memory statistics.
        """
        return self._memory_manager.get_memory_usage()

    def get_statistics_summary(self) -> dict[str, Any]:
        """Get comprehensive statistics summary.

        Returns:
            Dictionary with memory statistics summary.
        """
        current = self._memory_manager.get_memory_usage()
        manager_stats = self._memory_manager.get_statistics()

        # Calculate averages from history
        avg_rss = 0.0
        max_rss = 0.0
        min_rss = float("inf")

        if self._stats_history:
            rss_values = [s.rss_mb for s in self._stats_history]
            avg_rss = sum(rss_values) / len(rss_values)
            max_rss = max(rss_values)
            min_rss = min(rss_values)

        # Calculate optimization stats
        total_optimizations = len(self._optimization_history)
        total_freed = sum(r.freed_mb for r in self._optimization_history)
        avg_freed = total_freed / total_optimizations if total_optimizations > 0 else 0

        return {
            "current": current.to_dict(),
            "history": {
                "samples": len(self._stats_history),
                "avg_rss_mb": round(avg_rss, 2),
                "max_rss_mb": round(max_rss, 2),
                "min_rss_mb": round(min_rss, 2) if min_rss != float("inf") else 0,
            },
            "optimizations": {
                "total_count": total_optimizations,
                "total_freed_mb": round(total_freed, 2),
                "avg_freed_mb": round(avg_freed, 2),
            },
            "manager": manager_stats,
            "config": {
                "check_interval_seconds": self._config.check_interval_seconds,
                "auto_optimize": self._config.auto_optimize,
                "log_stats_interval_seconds": self._config.log_stats_interval_seconds,
            },
        }

    def register_cleanup(
        self,
        callback: Callable[[], None],
        name: str,
    ) -> None:
        """Register a cleanup callback.

        Args:
            callback: Cleanup function.
            name: Callback name.
        """
        self._memory_manager.register_cleanup_callback(callback, name)

    def unregister_cleanup(self, name: str) -> None:
        """Unregister a cleanup callback.

        Args:
            name: Callback name.
        """
        self._memory_manager.unregister_cleanup_callback(name)

    def clear_history(self) -> None:
        """Clear statistics history.

        Useful for resetting statistics after a period.
        """
        self._stats_history.clear()
        self._optimization_history.clear()
        self._logger.info("Memory statistics history cleared")
