"""Pywinauto Window Finder Implementation.

Pywinauto-based implementation of the IWindowFinder protocol.
"""

import asyncio
import warnings
from typing import Any, Optional

try:  # pragma: no cover - optional dependency
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.controls.uiawrapper import UIAWrapper
except ImportError:  # pragma: no cover - allow tests without pywinauto
    Application = None
    UIAWrapper = Any  # type: ignore

    class ElementNotFoundError(Exception):
        """Fallback when pywinauto is not installed."""


from core.protocols import (
    IWindowFinder,
    IWindowHandle,
    IProcessHandle,
    IControlHandle,
)
from core.exceptions import (
    WindowNotFoundError,
    ProcessNotFoundError,
    ControlNotFoundError,
)

_PYWINAUTO_32BIT_WARNING_REGEX = (
    r"32-bit application should be automated using 32-bit Python.*"
)
warnings.filterwarnings(
    "ignore",
    message=_PYWINAUTO_32BIT_WARNING_REGEX,
    category=UserWarning,
    module=r"pywinauto\.application",
)

class PywinautoControlHandle(IControlHandle):
    """Pywinauto control handle.

    Wraps UIAWrapper to implement the IControlHandle protocol.
    """

    def __init__(self, control: UIAWrapper, name: str = "") -> None:
        """Initialize.

        Args:
            control: pywinauto control.
            name: Control identifier name.
        """
        self._control = control
        self._name = name

    @property
    def exists(self) -> bool:
        """Control existence."""
        try:
            return self._control.exists()
        except Exception:
            return False

    @property
    def is_enabled(self) -> bool:
        """Enabled status."""
        try:
            return self._control.is_enabled()
        except Exception:
            return False

    @property
    def text(self) -> str:
        """Text content."""
        try:
            return self._control.window_text()
        except Exception:
            return ""

    async def click(self) -> bool:
        """Click."""
        if not self.exists:
            return False

        try:
            self._control.click_input()
            await asyncio.sleep(0.1)
            return True
        except Exception:
            return False

    async def set_text(self, text: str) -> bool:
        """Set text."""
        if not self.exists:
            return False

        try:
            self._control.set_edit_text("")
            self._control.type_keys(text, with_spaces=True)
            return True
        except Exception:
            return False

    async def select_item(self, item: str | int) -> bool:
        """Select item."""
        if not self.exists:
            return False

        try:
            self._control.select(item)
            await asyncio.sleep(0.1)
            return True
        except Exception:
            return False


class PywinautoWindowHandle(IWindowHandle):
    """Pywinauto window handle.

    Wraps pywinauto window to implement the IWindowHandle protocol.
    """

    def __init__(self, window: Any) -> None:
        """Initialize.

        Args:
            window: pywinauto window object.
        """
        self._window = window

    @property
    def exists(self) -> bool:
        """Window existence."""
        try:
            return self._window.exists()
        except Exception:
            return False

    @property
    def is_visible(self) -> bool:
        """Visibility status."""
        try:
            return self._window.is_visible()
        except Exception:
            return False

    @property
    def title(self) -> str:
        """Window title."""
        try:
            return self._window.window_text()
        except Exception:
            return ""

    async def find_control(
        self,
        **kwargs: Any,
    ) -> Optional[IControlHandle]:
        """Find control.

        Args:
            **kwargs: pywinauto child_window arguments.

        Returns:
            Control handle or None.
        """
        if not self.exists:
            return None

        try:
            control = self._window.child_window(**kwargs)
            if control.exists():
                name = kwargs.get("title", "") or kwargs.get("auto_id", "")
                return PywinautoControlHandle(control, name)
        except ElementNotFoundError:
            pass
        except Exception:
            pass

        return None

    async def close(self) -> bool:
        """Close window."""
        if not self.exists:
            return False

        try:
            self._window.close()
            return True
        except Exception:
            return False


class PywinautoProcessHandle(IProcessHandle):
    """Pywinauto process handle.

    Wraps pywinauto Application to implement the IProcessHandle protocol.
    """

    def __init__(self, app: Application, pid: int) -> None:
        """Initialize.

        Args:
            app: pywinauto Application.
            pid: Process ID.
        """
        self._app = app
        self._pid = pid

    @property
    def pid(self) -> int:
        """Process ID."""
        return self._pid

    @property
    def is_running(self) -> bool:
        """Running status."""
        try:
            return self._app.is_process_running()
        except Exception:
            return False

    async def terminate(self) -> bool:
        """Terminate process."""
        try:
            self._app.kill()
            return True
        except Exception:
            return False

    async def get_main_window(self) -> Optional[IWindowHandle]:
        """Get main window."""
        try:
            windows = self._app.windows()
            if windows:
                return PywinautoWindowHandle(windows[0])
        except Exception:
            pass
        return None


class PywinautoWindowFinder(IWindowFinder):
    """Pywinauto window finder.

    Pywinauto-based implementation of the IWindowFinder protocol.
    """

    def __init__(self, backend: str = "uia") -> None:
        """Initialize.

        Args:
            backend: pywinauto backend ("uia" or "win32").
        """
        self._backend = backend
        self._available = Application is not None

    async def find_window(
        self,
        title_re: str,
        timeout: float = 10.0,
    ) -> Optional[IWindowHandle]:
        """Find window.

        Args:
            title_re: Window title regex pattern.
            timeout: Search timeout in seconds.

        Returns:
            Window handle or None.
        """
        if not self._available:
            return None

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                app = Application(backend=self._backend).connect(
                    title_re=title_re,
                    timeout=1,
                )
                window = app.window(title_re=title_re)
                if window.exists():
                    return PywinautoWindowHandle(window)
            except ElementNotFoundError:
                pass
            except Exception:
                pass

            await asyncio.sleep(0.5)

        return None

    async def find_process(
        self,
        process_name: str,
        timeout: float = 10.0,
    ) -> Optional[IProcessHandle]:
        """Find process.

        Args:
            process_name: Process name or path.
            timeout: Search timeout in seconds.

        Returns:
            Process handle or None.
        """
        if not self._available:
            return None

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                app = Application(backend=self._backend).connect(
                    path=process_name,
                    timeout=1,
                )
                return PywinautoProcessHandle(app, app.process)
            except ElementNotFoundError:
                pass
            except Exception:
                pass

            await asyncio.sleep(0.5)

        return None

    async def start_process(
        self,
        exe_path: str,
        timeout: float = 30.0,
    ) -> Optional[IProcessHandle]:
        """Start process.

        Args:
            exe_path: Executable file path.
            timeout: Start timeout in seconds.

        Returns:
            Process handle or None.
        """
        if not self._available:
            return None

        try:
            app = Application(backend=self._backend).start(exe_path)

            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < timeout:
                if app.is_process_running():
                    return PywinautoProcessHandle(app, app.process)
                await asyncio.sleep(0.5)

        except Exception:
            pass

        return None


class FakeProcessHandle(IProcessHandle):
    """Fake process handle for testing.

    Simulates a process in tests.
    """

    def __init__(self, pid: int = 12345, running: bool = True) -> None:
        """Initialize.

        Args:
            pid: Fake process ID.
            running: Whether the process is running.
        """
        self._pid = pid
        self._running = running
        self._main_window: Optional[IWindowHandle] = None

    @property
    def pid(self) -> int:
        """Process ID."""
        return self._pid

    @property
    def is_running(self) -> bool:
        """Running status."""
        return self._running

    def set_main_window(self, window: IWindowHandle) -> None:
        """Set main window for testing."""
        self._main_window = window

    async def terminate(self) -> bool:
        """Terminate process."""
        self._running = False
        return True

    async def get_main_window(self) -> Optional[IWindowHandle]:
        """Get main window."""
        return self._main_window


class FakeWindowFinder(IWindowFinder):
    """Fake window finder for testing.

    Simulates window/process search in tests.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._windows: dict[str, IWindowHandle] = {}
        self._processes: dict[str, IProcessHandle] = {}
        self._find_window_calls: list[tuple[str, float]] = []
        self._find_process_calls: list[tuple[str, float]] = []
        self._start_process_calls: list[tuple[str, float]] = []
        # start_process 호출 시 자동으로 윈도우를 찾을 수 있도록 하는 플래그
        self._auto_create_window_on_start: bool = True

    def add_window(self, title_pattern: str, window: IWindowHandle) -> None:
        """Register fake window."""
        self._windows[title_pattern] = window

    def add_process(self, process_name: str, process: IProcessHandle) -> None:
        """Register fake process."""
        self._processes[process_name] = process

    async def find_window(
        self,
        title_re: str,
        timeout: float = 10.0,
    ) -> Optional[IWindowHandle]:
        """Find window."""
        self._find_window_calls.append((title_re, timeout))
        return self._windows.get(title_re)

    async def find_process(
        self,
        process_name: str,
        timeout: float = 10.0,
    ) -> Optional[IProcessHandle]:
        """Find process."""
        self._find_process_calls.append((process_name, timeout))
        return self._processes.get(process_name)

    async def start_process(
        self,
        exe_path: str,
        timeout: float = 30.0,
    ) -> Optional[IProcessHandle]:
        """Start process (fake implementation).

        Args:
            exe_path: Executable file path.
            timeout: Start timeout in seconds.

        Returns:
            Fake process handle or None.
        """
        self._start_process_calls.append((exe_path, timeout))

        # 이미 등록된 프로세스가 있으면 반환
        if exe_path in self._processes:
            return self._processes[exe_path]

        # 기본적으로 fake process 생성 및 반환
        fake_process = FakeProcessHandle(pid=12345, running=True)
        self._processes[exe_path] = fake_process
        return fake_process

    @property
    def find_window_calls(self) -> list[tuple[str, float]]:
        """find_window call history."""
        return self._find_window_calls

    @property
    def find_process_calls(self) -> list[tuple[str, float]]:
        """find_process call history."""
        return self._find_process_calls

    @property
    def start_process_calls(self) -> list[tuple[str, float]]:
        """start_process call history."""
        return self._start_process_calls


class FakeWindowHandle(IWindowHandle):
    """Fake window handle for testing."""

    def __init__(
        self,
        title: str = "Test Window",
        exists: bool = True,
        visible: bool = True,
    ) -> None:
        """Initialize."""
        self._title = title
        self._exists = exists
        self._visible = visible
        self._controls: dict[str, IControlHandle] = {}
        self._closed = False

    @property
    def exists(self) -> bool:
        return self._exists and not self._closed

    @property
    def is_visible(self) -> bool:
        return self._visible and not self._closed

    @property
    def title(self) -> str:
        return self._title

    def add_control(self, key: str, control: IControlHandle) -> None:
        """Register fake control."""
        self._controls[key] = control

    async def find_control(self, **kwargs: Any) -> Optional[IControlHandle]:
        """Find control."""
        # Simply find by first matching key
        for key in kwargs.values():
            if isinstance(key, str) and key in self._controls:
                return self._controls[key]
        return None

    async def close(self) -> bool:
        """Close window."""
        self._closed = True
        return True


class FakeControlHandle(IControlHandle):
    """Fake control handle for testing."""

    def __init__(
        self,
        text: str = "",
        exists: bool = True,
        enabled: bool = True,
    ) -> None:
        """Initialize."""
        self._text = text
        self._exists = exists
        self._enabled = enabled
        self._click_count = 0
        self._selected_items: list[str | int] = []

    @property
    def exists(self) -> bool:
        return self._exists

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def text(self) -> str:
        return self._text

    async def click(self) -> bool:
        if self._exists and self._enabled:
            self._click_count += 1
            return True
        return False

    async def set_text(self, text: str) -> bool:
        if self._exists and self._enabled:
            self._text = text
            return True
        return False

    async def select_item(self, item: str | int) -> bool:
        if self._exists and self._enabled:
            self._selected_items.append(item)
            return True
        return False

    @property
    def click_count(self) -> int:
        """Click count."""
        return self._click_count

    @property
    def selected_items(self) -> list[str | int]:
        """List of selected items."""
        return self._selected_items
