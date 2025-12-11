"""Window Manager.

Handles MFC window discovery and management.
Uses pywinauto to find and connect to windows.
"""

import asyncio
from typing import Optional

from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError

from config.constants import TimeoutConfig
from utils.logging import get_logger

logger = get_logger(__name__)


class WindowManager:
    """MFC window manager.

    Connects to USB Test.exe process and manages windows.

    Attributes:
        _app: pywinauto Application instance.
        _main_window: Main window.
        _exe_path: USB Test.exe path.
    """

    def __init__(self, exe_path: str = "USB Test.exe") -> None:
        """Initialize window manager.

        Args:
            exe_path: USB Test.exe executable file path.
        """
        self._exe_path = exe_path
        self._app: Optional[Application] = None
        self._main_window = None

    @property
    def is_connected(self) -> bool:
        """Process connection status."""
        return self._app is not None and self._main_window is not None

    @property
    def main_window(self):
        """Main window."""
        return self._main_window

    async def connect(self, timeout: float = TimeoutConfig.PROCESS_START) -> bool:
        """Connect to USB Test.exe process.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            Connection success status.
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # 실행 중인 프로세스에 연결 시도
                self._app = Application(backend="uia").connect(
                    path=self._exe_path,
                    timeout=5,
                )
                self._main_window = self._app.window(title_re=".*USB Test.*")

                if self._main_window.exists():
                    logger.info(
                        "Connected to USB Test.exe",
                        title=self._main_window.window_text(),
                    )
                    return True

            except ElementNotFoundError:
                logger.debug("USB Test.exe not found, retrying...")
            except Exception as e:
                logger.warning("Connection attempt failed", error=str(e))

            await asyncio.sleep(1)

        logger.error("Failed to connect to USB Test.exe", timeout=timeout)
        return False

    async def start_and_connect(
        self,
        timeout: float = TimeoutConfig.PROCESS_START,
    ) -> bool:
        """Start USB Test.exe and connect.

        Args:
            timeout: Timeout in seconds.

        Returns:
            Connection success status.
        """
        try:
            # 프로세스 시작
            self._app = Application(backend="uia").start(self._exe_path)

            # 윈도우 대기
            start_time = asyncio.get_event_loop().time()

            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    self._main_window = self._app.window(title_re=".*USB Test.*")
                    if self._main_window.exists():
                        logger.info(
                            "Started and connected to USB Test.exe",
                            title=self._main_window.window_text(),
                        )
                        return True
                except ElementNotFoundError:
                    pass

                await asyncio.sleep(0.5)

            logger.error("Failed to start USB Test.exe", timeout=timeout)
            return False

        except Exception as e:
            logger.error("Failed to start process", error=str(e))
            return False

    def disconnect(self) -> None:
        """Disconnect."""
        self._main_window = None
        self._app = None
        logger.info("Disconnected from USB Test.exe")

    def get_slot_window(self, slot_idx: int):
        """Get window/control area for specific slot.

        Args:
            slot_idx: Slot index (0-15).

        Returns:
            Slot window or None.
        """
        if not self.is_connected:
            return None

        # TODO: 실제 USB Test.exe UI 구조에 맞게 구현
        # 예: 탭 컨트롤, 패널 등의 구조 분석 필요
        return None

    def find_control(self, **kwargs):
        """Search control.

        Args:
            **kwargs: pywinauto search criteria.

        Returns:
            Found control or None.
        """
        if not self.is_connected or not self._main_window:
            return None

        try:
            return self._main_window.child_window(**kwargs)
        except ElementNotFoundError:
            return None

    def list_controls(self) -> list[dict]:
        """Get all controls list.

        For debugging and UI analysis.

        Returns:
            List of control information.
        """
        if not self.is_connected or not self._main_window:
            return []

        controls = []
        try:
            for ctrl in self._main_window.descendants():
                controls.append(
                    {
                        "control_type": ctrl.element_info.control_type,
                        "class_name": ctrl.element_info.class_name,
                        "name": ctrl.element_info.name,
                        "automation_id": ctrl.element_info.automation_id,
                        "rectangle": str(ctrl.element_info.rectangle),
                    }
                )
        except Exception as e:
            logger.warning("Failed to list controls", error=str(e))

        return controls
