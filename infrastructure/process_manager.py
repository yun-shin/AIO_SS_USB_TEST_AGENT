"""Process Manager.

Manages USB Test.exe processes per slot.
Each slot has its own dedicated process.
"""

import asyncio
import ctypes
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

import psutil

from config.constants import SlotConfig, TimeoutConfig
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SlotProcess:
    """Slot process information.

    Attributes:
        slot_idx: Slot index.
        pid: Process ID (None if not running).
        is_active: Whether the process is active.
        started_at: Process start time.
        exe_path: Path to the executable.
    """

    slot_idx: int
    pid: Optional[int] = None
    is_active: bool = False
    started_at: Optional[datetime] = None
    exe_path: Optional[str] = None


def _launch_exe_get_pid(exe_path: str, timeout: float = 10.0) -> Optional[int]:
    """Launch executable and get its PID.

    Args:
        exe_path: Path to the executable.
        timeout: Timeout in seconds to find the new process.

    Returns:
        PID of the launched process, or None if failed.
    """
    path = Path(exe_path)
    if not path.exists():
        logger.error("Executable not found", exe_path=exe_path)
        return None

    exe_name = path.name
    working_dir = str(path.parent)

    # 실행 전 기존 프로세스 PID 목록 저장
    existing_pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and exe_name.lower() in proc.info["name"].lower():
                existing_pids.add(proc.info["pid"])
        except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
            pass

    logger.debug(
        "Existing PIDs before launch",
        exe_name=exe_name,
        existing_pids=list(existing_pids),
    )

    # ShellExecuteW로 실행 (GUI 프로세스에 적합)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,  # hwnd
        "open",  # operation
        str(path),  # file
        None,  # parameters
        working_dir,  # directory
        1,  # SW_SHOWNORMAL
    )

    if result <= 32:
        logger.error(
            "Failed to launch executable",
            exe_path=exe_path,
            error_code=result,
        )
        return None

    logger.info("Launched executable, searching for new PID", exe_path=exe_path)

    # 새로 생성된 프로세스 PID 찾기
    start_time = (
        asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
    )
    poll_interval = 0.5
    elapsed = 0.0

    while elapsed < timeout:
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                proc_name = proc.info.get("name", "")
                proc_pid = proc.info.get("pid")

                if (
                    proc_name
                    and exe_name.lower() in proc_name.lower()
                    and proc_pid not in existing_pids
                ):
                    logger.info(
                        "Found new process PID",
                        exe_name=exe_name,
                        pid=proc_pid,
                    )
                    return proc_pid

            except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
                pass

        # 동기적으로 대기 (asyncio가 아닌 환경에서도 동작)
        import time

        time.sleep(poll_interval)
        elapsed += poll_interval

    logger.error(
        "Failed to find new process PID",
        exe_name=exe_name,
        timeout=timeout,
    )
    return None


async def _launch_exe_get_pid_async(
    exe_path: str,
    timeout: float = 10.0,
) -> Optional[int]:
    """Launch executable and get its PID (async version).

    Args:
        exe_path: Path to the executable.
        timeout: Timeout in seconds to find the new process.

    Returns:
        PID of the launched process, or None if failed.
    """
    path = Path(exe_path)
    if not path.exists():
        logger.error("Executable not found", exe_path=exe_path)
        return None

    exe_name = path.name
    working_dir = str(path.parent)

    # 실행 전 기존 프로세스 PID 목록 저장
    existing_pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and exe_name.lower() in proc.info["name"].lower():
                existing_pids.add(proc.info["pid"])
        except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
            pass

    logger.debug(
        "Existing PIDs before launch",
        exe_name=exe_name,
        existing_pids=list(existing_pids),
    )

    # ShellExecuteW로 실행 (GUI 프로세스에 적합)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,  # hwnd
        "open",  # operation
        str(path),  # file
        None,  # parameters
        working_dir,  # directory
        1,  # SW_SHOWNORMAL
    )

    if result <= 32:
        logger.error(
            "Failed to launch executable",
            exe_path=exe_path,
            error_code=result,
        )
        return None

    logger.info("Launched executable, searching for new PID", exe_path=exe_path)

    # 새로 생성된 프로세스 PID 찾기
    start_time = asyncio.get_event_loop().time()
    poll_interval = 0.5

    while asyncio.get_event_loop().time() - start_time < timeout:
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                proc_name = proc.info.get("name", "")
                proc_pid = proc.info.get("pid")

                if (
                    proc_name
                    and exe_name.lower() in proc_name.lower()
                    and proc_pid not in existing_pids
                ):
                    logger.info(
                        "Found new process PID",
                        exe_name=exe_name,
                        pid=proc_pid,
                    )
                    return proc_pid

            except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
                pass

        await asyncio.sleep(poll_interval)

    logger.error(
        "Failed to find new process PID",
        exe_name=exe_name,
        timeout=timeout,
    )
    return None


class SlotProcessManager:
    """Manages USB Test.exe processes per slot.

    Each slot has its own dedicated USB Test.exe process.
    This class handles launching, tracking, and terminating processes.

    Attributes:
        _exe_path: Path to USB Test.exe.
        _slots: Dictionary of slot processes.
        _lock: Thread lock for concurrent access.
    """

    def __init__(
        self,
        exe_path: str,
        max_slots: int = SlotConfig.MAX_SLOTS,
    ) -> None:
        """Initialize process manager.

        Args:
            exe_path: Path to USB Test.exe.
            max_slots: Maximum number of slots.
        """
        self._exe_path = exe_path
        self._max_slots = max_slots
        self._lock = Lock()

        # 슬롯별 프로세스 정보 초기화
        self._slots: dict[int, SlotProcess] = {
            idx: SlotProcess(slot_idx=idx) for idx in range(max_slots)
        }

    @property
    def exe_path(self) -> str:
        """USB Test.exe path."""
        return self._exe_path

    def get_slot(self, slot_idx: int) -> Optional[SlotProcess]:
        """Get slot process information.

        Args:
            slot_idx: Slot index.

        Returns:
            SlotProcess or None if invalid index.
        """
        return self._slots.get(slot_idx)

    def get_pid(self, slot_idx: int) -> Optional[int]:
        """Get PID for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            PID or None if not running.
        """
        slot = self._slots.get(slot_idx)
        return slot.pid if slot else None

    def is_active(self, slot_idx: int) -> bool:
        """Check if slot process is active.

        Args:
            slot_idx: Slot index.

        Returns:
            True if process is active.
        """
        slot = self._slots.get(slot_idx)
        if not slot or not slot.pid:
            return False

        # 실제 프로세스가 실행 중인지 확인
        try:
            return psutil.pid_exists(slot.pid)
        except Exception:
            return False

    def get_all_active_pids(self) -> list[int]:
        """Get all active PIDs.

        Returns:
            List of active PIDs.
        """
        return [
            slot.pid
            for slot in self._slots.values()
            if slot.pid and self.is_active(slot.slot_idx)
        ]

    async def launch_for_slot(
        self,
        slot_idx: int,
        timeout: float = TimeoutConfig.PROCESS_START_TIMEOUT,
    ) -> Optional[int]:
        """Launch USB Test.exe for a specific slot.

        Args:
            slot_idx: Slot index.
            timeout: Timeout in seconds.

        Returns:
            PID of the launched process, or None if failed.
        """
        if slot_idx not in self._slots:
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return None

        # 이미 실행 중인 프로세스가 있으면 종료
        if self.is_active(slot_idx):
            logger.warning(
                "Terminating existing process for slot",
                slot_idx=slot_idx,
                pid=self._slots[slot_idx].pid,
            )
            await self.terminate_for_slot(slot_idx)

        logger.info(
            "Launching USB Test.exe for slot",
            slot_idx=slot_idx,
            exe_path=self._exe_path,
        )

        # 새 프로세스 실행 및 PID 획득
        pid = await _launch_exe_get_pid_async(self._exe_path, timeout)

        if pid:
            with self._lock:
                self._slots[slot_idx] = SlotProcess(
                    slot_idx=slot_idx,
                    pid=pid,
                    is_active=True,
                    started_at=datetime.now(),
                    exe_path=self._exe_path,
                )

            logger.info(
                "Process launched for slot",
                slot_idx=slot_idx,
                pid=pid,
            )
            return pid

        logger.error(
            "Failed to launch process for slot",
            slot_idx=slot_idx,
        )
        return None

    async def terminate_for_slot(self, slot_idx: int) -> bool:
        """Terminate USB Test.exe for a specific slot.

        Args:
            slot_idx: Slot index.

        Returns:
            True if terminated successfully.
        """
        slot = self._slots.get(slot_idx)
        if not slot or not slot.pid:
            return True

        try:
            proc = psutil.Process(slot.pid)
            proc.terminate()

            # 종료 대기
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()

            logger.info(
                "Process terminated for slot",
                slot_idx=slot_idx,
                pid=slot.pid,
            )

        except psutil.NoSuchProcess:
            logger.debug("Process already terminated", slot_idx=slot_idx)
        except Exception as e:
            logger.error(
                "Failed to terminate process",
                slot_idx=slot_idx,
                error=str(e),
            )
            return False

        # 슬롯 정보 초기화
        with self._lock:
            self._slots[slot_idx] = SlotProcess(slot_idx=slot_idx)

        return True

    async def terminate_all(self) -> None:
        """Terminate all slot processes."""
        for slot_idx in self._slots:
            await self.terminate_for_slot(slot_idx)

    def clear_slot(self, slot_idx: int) -> None:
        """Clear slot information without terminating process.

        Args:
            slot_idx: Slot index.
        """
        with self._lock:
            if slot_idx in self._slots:
                self._slots[slot_idx] = SlotProcess(slot_idx=slot_idx)

    def refresh_status(self) -> None:
        """Refresh status of all slots by checking if processes are still running."""
        with self._lock:
            for slot_idx, slot in self._slots.items():
                if slot.pid:
                    if not psutil.pid_exists(slot.pid):
                        logger.info(
                            "Process no longer running",
                            slot_idx=slot_idx,
                            pid=slot.pid,
                        )
                        self._slots[slot_idx] = SlotProcess(slot_idx=slot_idx)

    def find_unassigned_process(self, exe_name: str = "USB Test.exe") -> Optional[int]:
        """Find a running USB Test.exe process that is not assigned to any slot.

        Args:
            exe_name: Name of the executable.

        Returns:
            PID of unassigned process, or None.
        """
        assigned_pids = set(self.get_all_active_pids())

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc_name = proc.info.get("name", "")
                proc_pid = proc.info.get("pid")

                if (
                    proc_name
                    and exe_name.lower() in proc_name.lower()
                    and proc_pid not in assigned_pids
                ):
                    return proc_pid

            except (psutil.AccessDenied, psutil.ZombieProcess, psutil.NoSuchProcess):
                pass

        return None

    def assign_pid_to_slot(self, slot_idx: int, pid: int) -> bool:
        """Assign an existing PID to a slot.

        Args:
            slot_idx: Slot index.
            pid: Process ID to assign.

        Returns:
            True if assigned successfully.
        """
        if slot_idx not in self._slots:
            return False

        if not psutil.pid_exists(pid):
            logger.error("PID does not exist", pid=pid)
            return False

        with self._lock:
            self._slots[slot_idx] = SlotProcess(
                slot_idx=slot_idx,
                pid=pid,
                is_active=True,
                started_at=datetime.now(),
                exe_path=self._exe_path,
            )

        logger.info(
            "PID assigned to slot",
            slot_idx=slot_idx,
            pid=pid,
        )
        return True
