"""Memory Management Module.

Provides memory monitoring, optimization, and garbage collection
for long-running Agent processes (1+ month uptime expected).
"""

import asyncio
import gc
import sys
import ctypes
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, runtime_checkable
from threading import Lock

from core.protocols import IClock


@runtime_checkable
class IMemoryManager(Protocol):
    """Memory manager interface.

    Abstracts memory management for testing.
    """

    def get_memory_usage(self) -> "MemoryStats":
        """Get current memory usage statistics."""
        ...

    async def optimize(self, force: bool = False) -> "OptimizationResult":
        """Perform memory optimization."""
        ...

    def register_cleanup_callback(
        self,
        callback: Callable[[], None],
        name: str,
    ) -> None:
        """Register cleanup callback."""
        ...


@dataclass(frozen=True)
class MemoryStats:
    """Memory usage statistics.

    Attributes:
        rss_mb: Resident Set Size in MB (physical memory).
        vms_mb: Virtual Memory Size in MB.
        gc_objects: Number of tracked objects by GC.
        gc_generations: GC generation stats.
        timestamp: Stats collection time.
    """

    rss_mb: float
    vms_mb: float
    gc_objects: int
    gc_generations: tuple[dict[str, int], dict[str, int], dict[str, int]]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rss_mb": round(self.rss_mb, 2),
            "vms_mb": round(self.vms_mb, 2),
            "gc_objects": self.gc_objects,
            "gc_generations": [
                {"collections": g.get("collections", 0), "collected": g.get("collected", 0)}
                for g in self.gc_generations
            ],
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OptimizationResult:
    """Memory optimization result.

    Attributes:
        before_mb: Memory before optimization in MB.
        after_mb: Memory after optimization in MB.
        freed_mb: Freed memory in MB.
        collected_objects: Number of collected objects.
        duration_ms: Optimization duration in milliseconds.
        callbacks_executed: Number of executed cleanup callbacks.
    """

    before_mb: float
    after_mb: float
    freed_mb: float
    collected_objects: int
    duration_ms: float
    callbacks_executed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "before_mb": round(self.before_mb, 2),
            "after_mb": round(self.after_mb, 2),
            "freed_mb": round(self.freed_mb, 2),
            "collected_objects": self.collected_objects,
            "duration_ms": round(self.duration_ms, 2),
            "callbacks_executed": self.callbacks_executed,
        }


@dataclass
class MemoryThresholds:
    """Memory thresholds for optimization triggers.

    Attributes:
        warning_mb: Warning threshold in MB.
        critical_mb: Critical threshold in MB (force GC).
        gc_interval_seconds: Minimum interval between GC runs.
        max_gc_objects: Trigger GC when object count exceeds this.
    """

    warning_mb: float = 256.0
    critical_mb: float = 512.0
    gc_interval_seconds: float = 300.0  # 5 minutes
    max_gc_objects: int = 100_000


class MemoryManager:
    """Memory manager for long-running processes.

    Provides:
    - Memory usage monitoring
    - Periodic garbage collection
    - Memory threshold alerts
    - Cleanup callback management
    - Windows-specific memory optimizations

    Example:
        ```python
        manager = MemoryManager(clock=SystemClock())

        # Register cleanup callback
        manager.register_cleanup_callback(
            lambda: cache.clear(),
            name="cache_cleanup"
        )

        # Get memory stats
        stats = manager.get_memory_usage()
        print(f"Memory: {stats.rss_mb} MB")

        # Force optimization
        result = await manager.optimize(force=True)
        print(f"Freed: {result.freed_mb} MB")
        ```
    """

    def __init__(
        self,
        clock: IClock,
        thresholds: Optional[MemoryThresholds] = None,
    ) -> None:
        """Initialize memory manager.

        Args:
            clock: Clock instance for time tracking.
            thresholds: Memory thresholds (uses defaults if None).
        """
        self._clock = clock
        self._thresholds = thresholds or MemoryThresholds()
        self._lock = Lock()

        # Cleanup callbacks (name -> weak reference or callable)
        self._cleanup_callbacks: dict[str, Callable[[], None]] = {}

        # Tracking
        self._last_gc_time: Optional[datetime] = None
        self._optimization_count: int = 0
        self._total_freed_mb: float = 0.0

        # Windows psutil alternative (optional)
        self._psutil_available = False
        try:
            import psutil
            self._psutil_available = True
        except ImportError:
            pass

    def get_memory_usage(self) -> MemoryStats:
        """Get current memory usage statistics.

        Returns:
            MemoryStats with current memory information.
        """
        rss_mb = 0.0
        vms_mb = 0.0

        if self._psutil_available:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)
            vms_mb = mem_info.vms / (1024 * 1024)
        else:
            # Fallback: use sys.getsizeof for rough estimation
            # This is less accurate but works without psutil
            rss_mb = self._estimate_memory_usage()
            vms_mb = rss_mb

        # GC statistics
        gc_objects = len(gc.get_objects())
        gc_stats = gc.get_stats()
        gc_generations = tuple(
            {"collections": s.get("collections", 0), "collected": s.get("collected", 0)}
            for s in gc_stats
        )

        return MemoryStats(
            rss_mb=rss_mb,
            vms_mb=vms_mb,
            gc_objects=gc_objects,
            gc_generations=gc_generations,  # type: ignore
            timestamp=self._clock.now(),
        )

    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage without psutil.

        Returns:
            Estimated memory in MB.
        """
        # Use ctypes to get process memory on Windows
        if sys.platform == "win32":
            try:
                # GetProcessMemoryInfo via ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                pmc = PROCESS_MEMORY_COUNTERS()
                pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                psapi = ctypes.windll.psapi
                handle = ctypes.windll.kernel32.GetCurrentProcess()

                if psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(pmc), ctypes.sizeof(pmc)
                ):
                    return pmc.WorkingSetSize / (1024 * 1024)
            except Exception:
                pass

        # Fallback: rough estimate from gc objects
        return len(gc.get_objects()) * 0.001  # Very rough estimate

    async def optimize(self, force: bool = False) -> OptimizationResult:
        """Perform memory optimization.

        Executes cleanup callbacks and runs garbage collection.

        Args:
            force: Force optimization regardless of interval.

        Returns:
            OptimizationResult with optimization details.
        """
        start_time = self._clock.monotonic()
        before_stats = self.get_memory_usage()

        # Check if we should skip (not forced and interval not passed)
        if not force and self._last_gc_time is not None:
            elapsed = (self._clock.now() - self._last_gc_time).total_seconds()
            if elapsed < self._thresholds.gc_interval_seconds:
                return OptimizationResult(
                    before_mb=before_stats.rss_mb,
                    after_mb=before_stats.rss_mb,
                    freed_mb=0.0,
                    collected_objects=0,
                    duration_ms=0.0,
                    callbacks_executed=0,
                )

        callbacks_executed = 0
        collected_objects = 0

        with self._lock:
            # Execute cleanup callbacks
            callbacks_executed = self._execute_cleanup_callbacks()

            # Run garbage collection
            collected_objects = self._run_gc()

            # Windows-specific: Release working set
            self._release_working_set()

            self._last_gc_time = self._clock.now()
            self._optimization_count += 1

        # Allow async operations to complete
        await self._clock.sleep(0.01)

        after_stats = self.get_memory_usage()
        duration_ms = (self._clock.monotonic() - start_time) * 1000
        freed_mb = max(0.0, before_stats.rss_mb - after_stats.rss_mb)

        self._total_freed_mb += freed_mb

        return OptimizationResult(
            before_mb=before_stats.rss_mb,
            after_mb=after_stats.rss_mb,
            freed_mb=freed_mb,
            collected_objects=collected_objects,
            duration_ms=duration_ms,
            callbacks_executed=callbacks_executed,
        )

    def _execute_cleanup_callbacks(self) -> int:
        """Execute all registered cleanup callbacks.

        Returns:
            Number of callbacks executed.
        """
        executed = 0
        failed_callbacks = []

        for name, callback in self._cleanup_callbacks.items():
            try:
                callback()
                executed += 1
            except Exception:
                # Callback failed, mark for removal
                failed_callbacks.append(name)

        # Remove failed callbacks
        for name in failed_callbacks:
            self._cleanup_callbacks.pop(name, None)

        return executed

    def _run_gc(self) -> int:
        """Run garbage collection.

        Returns:
            Number of collected objects.
        """
        # Disable automatic GC during manual collection
        gc_was_enabled = gc.isenabled()
        gc.disable()

        try:
            # Collect all generations
            collected = 0
            for generation in range(3):
                collected += gc.collect(generation)

            return collected
        finally:
            if gc_was_enabled:
                gc.enable()

    def _release_working_set(self) -> None:
        """Release Windows working set memory.

        Signals Windows to trim the working set, potentially
        moving pages to the page file.
        """
        if sys.platform != "win32":
            return

        try:
            # SetProcessWorkingSetSize with -1 tells Windows to trim
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetProcessWorkingSetSize(
                handle,
                ctypes.c_size_t(-1),
                ctypes.c_size_t(-1),
            )
        except Exception:
            pass

    def register_cleanup_callback(
        self,
        callback: Callable[[], None],
        name: str,
    ) -> None:
        """Register a cleanup callback.

        Callbacks are executed during memory optimization.

        Args:
            callback: Cleanup function to call.
            name: Unique name for the callback.
        """
        with self._lock:
            self._cleanup_callbacks[name] = callback

    def unregister_cleanup_callback(self, name: str) -> None:
        """Unregister a cleanup callback.

        Args:
            name: Name of the callback to remove.
        """
        with self._lock:
            self._cleanup_callbacks.pop(name, None)

    def should_optimize(self) -> bool:
        """Check if optimization is recommended.

        Returns:
            True if memory usage exceeds thresholds or interval passed.
        """
        stats = self.get_memory_usage()

        # Critical threshold
        if stats.rss_mb >= self._thresholds.critical_mb:
            return True

        # Too many GC objects
        if stats.gc_objects >= self._thresholds.max_gc_objects:
            return True

        # Interval passed
        if self._last_gc_time is not None:
            elapsed = (self._clock.now() - self._last_gc_time).total_seconds()
            if elapsed >= self._thresholds.gc_interval_seconds:
                return True

        return False

    def is_memory_critical(self) -> bool:
        """Check if memory usage is critical.

        Returns:
            True if memory exceeds critical threshold.
        """
        stats = self.get_memory_usage()
        return stats.rss_mb >= self._thresholds.critical_mb

    def get_statistics(self) -> dict[str, Any]:
        """Get memory management statistics.

        Returns:
            Dictionary with statistics.
        """
        stats = self.get_memory_usage()
        return {
            "current_memory": stats.to_dict(),
            "optimization_count": self._optimization_count,
            "total_freed_mb": round(self._total_freed_mb, 2),
            "last_gc_time": (
                self._last_gc_time.isoformat() if self._last_gc_time else None
            ),
            "cleanup_callbacks": list(self._cleanup_callbacks.keys()),
            "thresholds": {
                "warning_mb": self._thresholds.warning_mb,
                "critical_mb": self._thresholds.critical_mb,
                "gc_interval_seconds": self._thresholds.gc_interval_seconds,
                "max_gc_objects": self._thresholds.max_gc_objects,
            },
        }


class FakeMemoryManager:
    """Fake memory manager for testing.

    Simulates memory management without actual system calls.
    """

    def __init__(
        self,
        initial_memory_mb: float = 100.0,
    ) -> None:
        """Initialize fake manager.

        Args:
            initial_memory_mb: Initial simulated memory usage.
        """
        self._memory_mb = initial_memory_mb
        self._cleanup_callbacks: dict[str, Callable[[], None]] = {}
        self._optimize_calls: list[bool] = []

    def get_memory_usage(self) -> MemoryStats:
        """Get simulated memory stats."""
        return MemoryStats(
            rss_mb=self._memory_mb,
            vms_mb=self._memory_mb * 1.5,
            gc_objects=1000,
            gc_generations=(
                {"collections": 10, "collected": 100},
                {"collections": 5, "collected": 50},
                {"collections": 1, "collected": 10},
            ),
            timestamp=datetime.now(),
        )

    async def optimize(self, force: bool = False) -> OptimizationResult:
        """Simulate optimization."""
        self._optimize_calls.append(force)
        before = self._memory_mb

        # Simulate memory reduction
        freed = self._memory_mb * 0.1
        self._memory_mb -= freed

        return OptimizationResult(
            before_mb=before,
            after_mb=self._memory_mb,
            freed_mb=freed,
            collected_objects=100,
            duration_ms=10.0,
            callbacks_executed=len(self._cleanup_callbacks),
        )

    def register_cleanup_callback(
        self,
        callback: Callable[[], None],
        name: str,
    ) -> None:
        """Register cleanup callback."""
        self._cleanup_callbacks[name] = callback

    def set_memory_mb(self, mb: float) -> None:
        """Set simulated memory usage (for testing)."""
        self._memory_mb = mb
