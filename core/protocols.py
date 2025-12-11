"""Core Interfaces (Protocols).

Defines pytest mock-friendly interfaces.
All external dependencies are abstracted via Protocol.
"""

from abc import abstractmethod
from typing import Protocol, runtime_checkable, Any, Optional
from datetime import datetime


# ============================================================
# MFC Window Control Protocols
# ============================================================


@runtime_checkable
class IWindowFinder(Protocol):
    """Window finder interface.

    Abstracts pywinauto window finding functionality.
    Can be replaced with Mock during testing.
    """

    @abstractmethod
    async def find_window(
        self,
        title_re: str,
        timeout: float = 10.0,
    ) -> Optional["IWindowHandle"]:
        """Find window.

        Args:
            title_re: Window title regex pattern.
            timeout: Search timeout in seconds.

        Returns:
            Window handle or None.
        """
        ...

    @abstractmethod
    async def find_process(
        self,
        process_name: str,
        timeout: float = 10.0,
    ) -> Optional["IProcessHandle"]:
        """Find process.

        Args:
            process_name: Process name.
            timeout: Search timeout in seconds.

        Returns:
            Process handle or None.
        """
        ...


@runtime_checkable
class IWindowHandle(Protocol):
    """Window handle interface."""

    @property
    @abstractmethod
    def exists(self) -> bool:
        """Whether window exists."""
        ...

    @property
    @abstractmethod
    def is_visible(self) -> bool:
        """Window visibility."""
        ...

    @property
    @abstractmethod
    def title(self) -> str:
        """Window title."""
        ...

    @abstractmethod
    async def find_control(
        self,
        **kwargs: Any,
    ) -> Optional["IControlHandle"]:
        """Find control.

        Args:
            **kwargs: Search criteria.

        Returns:
            Control handle or None.
        """
        ...

    @abstractmethod
    async def close(self) -> bool:
        """Close window."""
        ...


@runtime_checkable
class IProcessHandle(Protocol):
    """Process handle interface."""

    @property
    @abstractmethod
    def pid(self) -> int:
        """Process ID."""
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Whether running."""
        ...

    @abstractmethod
    async def terminate(self) -> bool:
        """Terminate process."""
        ...

    @abstractmethod
    async def get_main_window(self) -> Optional[IWindowHandle]:
        """Get main window."""
        ...


@runtime_checkable
class IControlHandle(Protocol):
    """Control handle interface."""

    @property
    @abstractmethod
    def exists(self) -> bool:
        """Whether control exists."""
        ...

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Whether enabled."""
        ...

    @property
    @abstractmethod
    def text(self) -> str:
        """Text content."""
        ...

    @abstractmethod
    async def click(self) -> bool:
        """Click."""
        ...

    @abstractmethod
    async def set_text(self, text: str) -> bool:
        """Set text."""
        ...

    @abstractmethod
    async def select_item(self, item: str | int) -> bool:
        """Select item (ComboBox/ListBox)."""
        ...


# ============================================================
# Communication Protocols
# ============================================================


@runtime_checkable
class IWebSocketClient(Protocol):
    """WebSocket client interface."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether connected."""
        ...

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Agent ID."""
        ...

    @abstractmethod
    async def connect(self) -> bool:
        """Connect."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect."""
        ...

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> bool:
        """Send message."""
        ...

    @abstractmethod
    def register_handler(
        self,
        message_type: str,
        handler: Any,
    ) -> None:
        """Register message handler."""
        ...


@runtime_checkable
class IHttpClient(Protocol):
    """HTTP client interface."""

    @abstractmethod
    async def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> "IHttpResponse":
        """GET request."""
        ...

    @abstractmethod
    async def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> "IHttpResponse":
        """POST request."""
        ...


@runtime_checkable
class IHttpResponse(Protocol):
    """HTTP response interface."""

    @property
    @abstractmethod
    def status_code(self) -> int:
        """Status code."""
        ...

    @abstractmethod
    def json(self) -> dict[str, Any]:
        """Parse JSON."""
        ...


# ============================================================
# State Management Protocols
# ============================================================


@runtime_checkable
class IStateStore(Protocol):
    """State store interface."""

    @abstractmethod
    def get_slot_state(self, slot_idx: int) -> Optional[dict[str, Any]]:
        """Get slot state."""
        ...

    @abstractmethod
    def set_slot_state(self, slot_idx: int, state: dict[str, Any]) -> None:
        """Set slot state."""
        ...

    @abstractmethod
    def get_all_states(self) -> dict[int, dict[str, Any]]:
        """Get all states."""
        ...


# ============================================================
# Notification Protocols
# ============================================================


@runtime_checkable
class INotifier(Protocol):
    """Notification interface."""

    @abstractmethod
    async def notify(
        self,
        title: str,
        message: str,
        level: str = "info",
    ) -> bool:
        """Send notification."""
        ...


# ============================================================
# Logging Protocol
# ============================================================


@runtime_checkable
class ILogger(Protocol):
    """Logging interface."""

    @abstractmethod
    def debug(self, message: str, **kwargs: Any) -> None:
        """Debug log."""
        ...

    @abstractmethod
    def info(self, message: str, **kwargs: Any) -> None:
        """Info log."""
        ...

    @abstractmethod
    def warning(self, message: str, **kwargs: Any) -> None:
        """Warning log."""
        ...

    @abstractmethod
    def error(self, message: str, **kwargs: Any) -> None:
        """Error log."""
        ...


# ============================================================
# Clock Protocol (for time control during testing)
# ============================================================


@runtime_checkable
class IClock(Protocol):
    """Clock interface.

    Abstracts time for controllability during testing.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Current time."""
        ...

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Sleep."""
        ...

    @abstractmethod
    def monotonic(self) -> float:
        """Monotonic timer."""
        ...
