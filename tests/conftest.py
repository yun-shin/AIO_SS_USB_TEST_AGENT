"""Pytest Configuration and Fixtures.

Defines common fixtures used in pytest.
Provides mock objects, test containers, etc.
"""

from datetime import datetime
from typing import Generator, Any

import pytest

# Config
from config.settings import AgentSettings
from domain.models import TestConfig, TestState
from config.constants import (
    TestCapacity,
    TestFile,
    TestMethod,
    TestPreset,
    VendorId,
)

# Core
from core.container import Container, set_container, reset_container
from core.protocols import (
    IWindowFinder,
    IStateStore,
    IClock,
    ILogger,
)

# Infrastructure (Fake implementations)
from infrastructure.clock import FakeClock
from infrastructure.state_store import FakeStateStore
from infrastructure.window_finder import (
    FakeWindowFinder,
    FakeWindowHandle,
    FakeControlHandle,
)

# Services
from services.test_executor import TestExecutor, TestRequest
from services.state_monitor import StateMonitor


# ============================================================
# Fake Logger
# ============================================================


class FakeLogger(ILogger):
    """Fake logger for testing.

    Stores log messages in memory.
    """

    def __init__(self) -> None:
        self.logs: list[dict[str, Any]] = []

    def debug(self, message: str, **kwargs: Any) -> None:
        self.logs.append({"level": "debug", "message": message, **kwargs})

    def info(self, message: str, **kwargs: Any) -> None:
        self.logs.append({"level": "info", "message": message, **kwargs})

    def warning(self, message: str, **kwargs: Any) -> None:
        self.logs.append({"level": "warning", "message": message, **kwargs})

    def error(self, message: str, **kwargs: Any) -> None:
        self.logs.append({"level": "error", "message": message, **kwargs})

    def clear(self) -> None:
        self.logs.clear()

    def get_logs(self, level: str | None = None) -> list[dict[str, Any]]:
        if level is None:
            return self.logs
        return [log for log in self.logs if log["level"] == level]


# ============================================================
# Legacy Fixtures (maintained for backward compatibility)
# ============================================================


@pytest.fixture
def agent_settings() -> AgentSettings:
    """Return AgentSettings for testing."""
    return AgentSettings(
        name="test-agent",
        debug=True,
        usb_test_path="C:/Test/USB Test.exe",
        health_report_path="C:/Test/HealthReport.exe",
        max_slots=4,
        backend_url="http://localhost:8000",
        backend_ws_url="ws://localhost:8000/api/agent/ws",
    )


@pytest.fixture
def sample_test_config() -> TestConfig:
    """Return TestConfig for testing."""
    return TestConfig(
        slot_idx=0,
        jira_no="TEST-123",
        sample_no="SAMPLE_001",
        drive="E",
        test_preset=TestPreset.FULL,
        test_file=TestFile.PHOTO,
        method=TestMethod.ZERO_HR,
        capacity=TestCapacity.GB_32,
        loop_count=10,
        loop_step=1,
        hr_enabled=True,
        die_count=1,
        vendor_id=VendorId.SS,
    )


@pytest.fixture
def sample_test_state() -> TestState:
    """Return TestState for testing."""
    return TestState(
        slot_idx=0,
        current_loop=0,
        total_loop=10,
        is_active=True,
    )


# ============================================================
# Core Fixtures (새 아키텍처)
# ============================================================


@pytest.fixture
def fake_clock() -> FakeClock:
    """Fake clock fixture.

    Allows time control in tests.

    Example:
        ```python
        def test_timeout(fake_clock):
            fake_clock.advance(seconds=60)
            assert fake_clock.monotonic() == 60
        ```
    """
    return FakeClock(
        initial_time=datetime(2025, 1, 1, 12, 0, 0),
        initial_monotonic=0.0,
    )


@pytest.fixture
def fake_logger() -> FakeLogger:
    """Fake logger fixture.

    Allows verification of log messages.
    """
    return FakeLogger()


@pytest.fixture
def fake_state_store() -> FakeStateStore:
    """Fake state store fixture."""
    return FakeStateStore()


@pytest.fixture
def fake_window_finder() -> FakeWindowFinder:
    """Fake window finder fixture."""
    return FakeWindowFinder()


@pytest.fixture
def fake_window() -> FakeWindowHandle:
    """Fake window handle fixture."""
    window = FakeWindowHandle(title="USB Test")
    window.add_control("start_button", FakeControlHandle(text="Start"))
    window.add_control("stop_button", FakeControlHandle(text="Stop"))
    window.add_control("capacity_combo", FakeControlHandle(text="1TB"))
    return window


# ============================================================
# Service Fixtures
# ============================================================


@pytest.fixture
def test_executor(
    fake_window_finder: FakeWindowFinder,
    fake_state_store: FakeStateStore,
    fake_clock: FakeClock,
    fake_logger: FakeLogger,
    fake_window: FakeWindowHandle,
) -> TestExecutor:
    """TestExecutor fixture with mocked dependencies."""
    fake_window_finder.add_window(".*USB Test.*", fake_window)

    return TestExecutor(
        window_finder=fake_window_finder,
        state_store=fake_state_store,
        clock=fake_clock,
        logger=fake_logger,
    )


@pytest.fixture
def state_monitor(
    fake_window_finder: FakeWindowFinder,
    fake_state_store: FakeStateStore,
    fake_clock: FakeClock,
    fake_logger: FakeLogger,
) -> StateMonitor:
    """StateMonitor fixture."""
    return StateMonitor(
        window_finder=fake_window_finder,
        state_store=fake_state_store,
        clock=fake_clock,
        logger=fake_logger,
        max_slots=4,
    )


# ============================================================
# Container Fixtures
# ============================================================


@pytest.fixture
def test_container(
    fake_window_finder: FakeWindowFinder,
    fake_state_store: FakeStateStore,
    fake_clock: FakeClock,
    fake_logger: FakeLogger,
) -> Generator[Container, None, None]:
    """DI container fixture for testing."""
    container = Container()

    container.register_instance(IWindowFinder, fake_window_finder)
    container.register_instance(IStateStore, fake_state_store)
    container.register_instance(IClock, fake_clock)
    container.register_instance(ILogger, fake_logger)

    set_container(container)

    yield container

    reset_container()


# ============================================================
# Test Data Fixtures
# ============================================================


@pytest.fixture
def sample_test_request() -> TestRequest:
    """Sample test request fixture."""
    return TestRequest(
        slot_idx=0,
        test_name="SampleTest",
        capacity="1TB",
        method="AUTO",
        test_type="NORMAL",
    )


@pytest.fixture
def sample_slot_states() -> dict[int, dict[str, Any]]:
    """Sample slot states fixture."""
    return {
        0: {"status": "running", "progress": 50.0, "current_phase": "write"},
        1: {"status": "idle", "progress": 0.0, "current_phase": None},
        2: {"status": "completed", "progress": 100.0, "current_phase": "done"},
        3: {"status": "error", "progress": 25.0, "error_message": "Timeout"},
    }
