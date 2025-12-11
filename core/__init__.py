"""Core Package.

Provides core interfaces, exceptions, and DI container.
"""

from .protocols import (
    IWindowFinder,
    IWindowHandle,
    IProcessHandle,
    IControlHandle,
    IWebSocketClient,
    IHttpClient,
    IHttpResponse,
    IStateStore,
    INotifier,
    ILogger,
    IClock,
)
from .exceptions import (
    AgentError,
    AgentConnectionError,
    WindowNotFoundError,
    ControlNotFoundError,
    TestExecutionError,
    AgentTimeoutError,
    ConfigurationError,
)
from .container import Container, get_container

__all__ = [
    # Protocols
    "IWindowFinder",
    "IWindowHandle",
    "IProcessHandle",
    "IControlHandle",
    "IWebSocketClient",
    "IHttpClient",
    "IHttpResponse",
    "IStateStore",
    "INotifier",
    "ILogger",
    "IClock",
    # Exceptions
    "AgentError",
    "AgentConnectionError",
    "WindowNotFoundError",
    "ControlNotFoundError",
    "TestExecutionError",
    "AgentTimeoutError",
    "ConfigurationError",
    # Container
    "Container",
    "get_container",
]
