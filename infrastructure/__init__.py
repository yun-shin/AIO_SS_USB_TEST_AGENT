"""Infrastructure Package.

Provides Protocol implementations.
Handles actual external system integrations.
"""

from .clock import SystemClock
from .window_finder import PywinautoWindowFinder
from .state_store import InMemoryStateStore

__all__ = [
    "SystemClock",
    "PywinautoWindowFinder",
    "InMemoryStateStore",
]
