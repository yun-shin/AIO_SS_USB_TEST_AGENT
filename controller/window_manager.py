"""Window Manager.

Handles MFC window discovery and management.
Uses pywinauto to find and connect to windows.
Supports per-slot process management with PID mapping.
"""

import asyncio
from typing import Optional

from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError

from config.constants import TimeoutConfig, SlotConfig
from infrastructure.process_manager import SlotProcessManager
from utils.logging import get_logger

logger = get_logger(__name__)


class SlotWindowManager:
    """Per-slot window manager.

    Manages connection to a single USB Test.exe window for one slot.

    Attributes:
        slot_idx: Slot index.
        _app: pywinauto Application instance.
        _main_window: Main window.
        _pid: Process ID.
    """

    def __init__(self, slot_idx: int) -> None:
        """Initialize slot window manager.

        Args:
            slot_idx: Slot index.
        """
        self.slot_idx = slot_idx
        self._app: Optional[Application] = None
        self._main_window = None
        self._pid: Optional[int] = None

    @property
    def is_connected(self) -> bool:
        """Process connection status.

        Returns True only if app, window are set, process is running,
        AND the window is still valid and responsive.
        """
        if self._app is None or self._main_window is None or self._pid is None:
            return False

        # 프로세스가 실제로 살아있는지 확인
        try:
            import psutil
            if not psutil.pid_exists(self._pid):
                # 프로세스가 죽었으면 연결 정보 정리
                self._clear_connection()
                return False

            # 윈도우가 여전히 유효한지 확인 (슬롯 재사용 시 stale 참조 방지)
            if not self._main_window.exists():
                logger.warning(
                    "Window reference is stale, clearing connection",
                    slot_idx=self.slot_idx,
                    pid=self._pid,
                )
                self._clear_connection()
                return False

            return True
        except Exception as e:
            logger.warning(
                "Connection check failed",
                slot_idx=self.slot_idx,
                error=str(e),
            )
            return False

    def _clear_connection(self) -> None:
        """Clear connection info (internal helper)."""
        self._main_window = None
        self._app = None
        self._pid = None

    @property
    def pid(self) -> Optional[int]:
        """Connected process PID."""
        return self._pid

    @property
    def main_window(self):
        """Main window."""
        return self._main_window

    async def connect_to_pid(
        self,
        pid: int,
        timeout: float = TimeoutConfig.PROCESS_START_TIMEOUT,
    ) -> bool:
        """Connect to USB Test.exe by PID.

        Args:
            pid: Process ID to connect.
            timeout: Connection timeout in seconds.

        Returns:
            Connection success status.
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # PID로 프로세스에 연결 (MFC 앱에 win32 백엔드 사용)
                self._app = Application(backend="win32").connect(
                    process=pid,
                    timeout=5,
                )
                self._main_window = self._app.window(title_re=".*USB Test.*")

                if self._main_window.exists():
                    self._pid = pid
                    logger.info(
                        "Connected to USB Test.exe by PID",
                        slot_idx=self.slot_idx,
                        pid=pid,
                        title=self._main_window.window_text(),
                    )
                    return True

            except ElementNotFoundError:
                logger.debug(
                    "Window not found for PID, retrying...",
                    slot_idx=self.slot_idx,
                    pid=pid,
                )
            except Exception as e:
                logger.warning(
                    "Connection attempt failed",
                    slot_idx=self.slot_idx,
                    pid=pid,
                    error=str(e),
                )

            await asyncio.sleep(1)

        logger.error(
            "Failed to connect to USB Test.exe by PID",
            slot_idx=self.slot_idx,
            pid=pid,
            timeout=timeout,
        )
        return False

    def disconnect(self) -> None:
        """Disconnect from process."""
        self._clear_connection()
        logger.info("Disconnected from USB Test.exe", slot_idx=self.slot_idx)

    def find_control(self, **kwargs):
        """Search control by child_window criteria.

        Args:
            **kwargs: pywinauto search criteria (control_id, class_name, etc.).

        Returns:
            Found control or None.
        """
        if not self.is_connected or not self._main_window:
            return None

        try:
            return self._main_window.child_window(**kwargs)
        except ElementNotFoundError:
            return None

    def get_control_by_name(self, name: str):
        """Get control by pywinauto best match name.

        Uses getattr to access controls like 'Button6', 'Static', etc.
        This matches how AIO_USB_TEST_MACRO accesses controls.

        Args:
            name: Best match control name (e.g., 'Button6', 'Static').

        Returns:
            Found control or None.
        """
        if not self.is_connected or not self._main_window:
            return None

        try:
            ctrl = getattr(self._main_window, name, None)
            if ctrl is not None:
                # wrapper_object()를 호출해서 실제 컨트롤 반환
                return ctrl.wrapper_object() if hasattr(ctrl, 'wrapper_object') else ctrl
        except Exception:
            pass

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
            logger.warning(
                "Failed to list controls",
                slot_idx=self.slot_idx,
                error=str(e),
            )

        return controls


class WindowManager:
    """Multi-slot window manager.

    Manages USB Test.exe processes and windows for all slots.
    Each slot has its own dedicated process and window.

    Attributes:
        _exe_path: USB Test.exe path.
        _process_manager: Slot process manager.
        _slot_windows: Per-slot window managers.
    """

    def __init__(
        self,
        exe_path: str = "USB Test.exe",
        max_slots: int = SlotConfig.MAX_SLOTS,
    ) -> None:
        """Initialize window manager.

        Args:
            exe_path: USB Test.exe executable file path.
            max_slots: Maximum number of slots.
        """
        self._exe_path = exe_path
        self._max_slots = max_slots
        self._process_manager = SlotProcessManager(exe_path, max_slots)

        # 슬롯별 윈도우 매니저
        self._slot_windows: dict[int, SlotWindowManager] = {
            idx: SlotWindowManager(idx) for idx in range(max_slots)
        }

    @property
    def process_manager(self) -> SlotProcessManager:
        """Slot process manager."""
        return self._process_manager

    def get_slot_window(self, slot_idx: int) -> Optional[SlotWindowManager]:
        """Get window manager for specific slot.

        Args:
            slot_idx: Slot index.

        Returns:
            SlotWindowManager or None.
        """
        return self._slot_windows.get(slot_idx)

    def is_slot_connected(self, slot_idx: int) -> bool:
        """Check if slot is connected.

        Args:
            slot_idx: Slot index.

        Returns:
            True if slot is connected.
        """
        slot_window = self._slot_windows.get(slot_idx)
        return slot_window.is_connected if slot_window else False

    async def launch_and_connect(
        self,
        slot_idx: int,
        timeout: float = TimeoutConfig.PROCESS_START_TIMEOUT,
    ) -> bool:
        """Launch USB Test.exe for a slot and connect.

        This will:
        1. Launch a new USB Test.exe process
        2. Get its PID
        3. Connect to it via pywinauto

        Args:
            slot_idx: Slot index.
            timeout: Timeout in seconds.

        Returns:
            True if launch and connection succeeded.
        """
        if slot_idx not in self._slot_windows:
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return False

        # 기존 연결 해제
        self._slot_windows[slot_idx].disconnect()

        # 새 프로세스 실행 및 PID 획득
        pid = await self._process_manager.launch_for_slot(slot_idx, timeout)
        if not pid:
            logger.error(
                "Failed to launch process for slot",
                slot_idx=slot_idx,
            )
            return False

        # 프로세스 초기화 대기 (윈도우 생성 시간)
        await asyncio.sleep(2)

        # PID로 연결
        connected = await self._slot_windows[slot_idx].connect_to_pid(pid, timeout)
        if not connected:
            logger.error(
                "Failed to connect to launched process",
                slot_idx=slot_idx,
                pid=pid,
            )
            # 연결 실패 시 프로세스 종료
            await self._process_manager.terminate_for_slot(slot_idx)
            return False

        logger.info(
            "Successfully launched and connected for slot",
            slot_idx=slot_idx,
            pid=pid,
        )
        return True

    async def connect_to_existing(
        self,
        slot_idx: int,
        pid: int,
        timeout: float = TimeoutConfig.PROCESS_START_TIMEOUT,
    ) -> bool:
        """Connect to an existing USB Test.exe process.

        Args:
            slot_idx: Slot index.
            pid: Process ID to connect.
            timeout: Timeout in seconds.

        Returns:
            True if connection succeeded.
        """
        if slot_idx not in self._slot_windows:
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return False

        # PID를 슬롯에 할당
        self._process_manager.assign_pid_to_slot(slot_idx, pid)

        # 연결
        return await self._slot_windows[slot_idx].connect_to_pid(pid, timeout)

    def disconnect_slot(self, slot_idx: int) -> None:
        """Disconnect a slot.

        Args:
            slot_idx: Slot index.
        """
        slot_window = self._slot_windows.get(slot_idx)
        if slot_window:
            slot_window.disconnect()
        self._process_manager.clear_slot(slot_idx)

    async def terminate_slot(self, slot_idx: int) -> bool:
        """Terminate process and disconnect for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            True if terminated successfully.
        """
        # 연결 해제
        slot_window = self._slot_windows.get(slot_idx)
        if slot_window:
            slot_window.disconnect()

        # 프로세스 종료
        return await self._process_manager.terminate_for_slot(slot_idx)

    async def terminate_all(self) -> None:
        """Terminate all slot processes and disconnect."""
        for slot_idx in self._slot_windows:
            await self.terminate_slot(slot_idx)

    def get_slot_pid(self, slot_idx: int) -> Optional[int]:
        """Get PID for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            PID or None.
        """
        return self._process_manager.get_pid(slot_idx)

    def refresh_all_status(self) -> None:
        """Refresh status of all slots."""
        self._process_manager.refresh_status()

        # 프로세스가 종료된 슬롯의 연결도 해제
        for slot_idx, slot_window in self._slot_windows.items():
            if slot_window.is_connected:
                pid = slot_window.pid
                if pid and not self._process_manager.is_active(slot_idx):
                    slot_window.disconnect()

