"""Infrastructure Package.

Provides Protocol implementations.
Handles actual external system integrations.
"""

from .clock import SystemClock
from .window_finder import (
    PywinautoWindowFinder,
    FakeProcessHandle,
    FakeWindowFinder,
    FakeWindowHandle,
    FakeControlHandle,
)
from .state_store import InMemoryStateStore
from .process_manager import (
    SlotProcess,
    SlotProcessManager,
)

__all__ = [
    "SystemClock",
    "PywinautoWindowFinder",
    "InMemoryStateStore",
    # Process management
    "SlotProcess",
    "SlotProcessManager",
    # Fake implementations for testing
    "FakeProcessHandle",
    "FakeWindowFinder",
    "FakeWindowHandle",
    "FakeControlHandle",
]
