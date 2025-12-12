"""Unit tests for WindowManager and ProcessManager.

Tests slot PID mapping, reconnection failure, and cleanup paths
using monkeypatched psutil and pywinauto.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest


class FakePsutilProcess:
    """Fake psutil.Process for testing."""

    def __init__(self, pid: int, name: str = "USB Test.exe", exists: bool = True):
        self._pid = pid
        self._name = name
        self._exists = exists
        self._terminated = False
        self._killed = False

    def terminate(self):
        self._terminated = True

    def kill(self):
        self._killed = True

    def wait(self, timeout=None):
        if not self._terminated:
            import psutil

            raise psutil.TimeoutExpired(timeout)

    @property
    def pid(self):
        return self._pid


class TestSlotProcessManager:
    """Test SlotProcessManager functionality."""

    @pytest.fixture
    def mock_psutil(self, monkeypatch):
        """Mock psutil module."""
        mock_module = MagicMock()
        mock_module.pid_exists = MagicMock(return_value=True)
        mock_module.NoSuchProcess = Exception
        mock_module.AccessDenied = Exception
        mock_module.ZombieProcess = Exception
        mock_module.TimeoutExpired = Exception
        mock_module.process_iter = MagicMock(return_value=[])
        monkeypatch.setattr("infrastructure.process_manager.psutil", mock_module)
        return mock_module

    def test_slot_process_manager_init(self, mock_psutil):
        """[TC-WINDOW_MANAGER-001] Slot process manager init - 테스트 시나리오를 검증한다.

            테스트 목적:
                Slot process manager init 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_slot_process_manager_init 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        manager = SlotProcessManager(exe_path="C:/USB Test.exe", max_slots=4)

        assert manager.exe_path == "C:/USB Test.exe"
        assert manager._max_slots == 4
        assert len(manager._slots) == 4
        for idx in range(4):
            assert idx in manager._slots
            assert manager._slots[idx].slot_idx == idx
            assert manager._slots[idx].pid is None

    def test_get_slot_returns_slot_process(self, mock_psutil):
        """[TC-WINDOW_MANAGER-002] Get slot returns slot process - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get slot returns slot process 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_slot_returns_slot_process 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        slot = manager.get_slot(0)

        assert slot is not None
        assert slot.slot_idx == 0

    def test_get_slot_returns_none_for_invalid_index(self, mock_psutil):
        """[TC-WINDOW_MANAGER-003] Get slot returns none for invalid index - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get slot returns none for invalid index 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_slot_returns_none_for_invalid_index 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        slot = manager.get_slot(10)

        assert slot is None

    def test_get_pid_returns_none_when_not_running(self, mock_psutil):
        """[TC-WINDOW_MANAGER-004] Get pid returns none when not running - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get pid returns none when not running 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_pid_returns_none_when_not_running 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        pid = manager.get_pid(0)

        assert pid is None

    def test_is_active_returns_false_when_no_pid(self, mock_psutil):
        """[TC-WINDOW_MANAGER-005] Is active returns false when no pid - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is active returns false when no pid 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_active_returns_false_when_no_pid 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        assert manager.is_active(0) is False

    def test_is_active_checks_psutil_pid_exists(self, mock_psutil):
        """[TC-WINDOW_MANAGER-006] Is active checks psutil pid exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is active checks psutil pid exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_active_checks_psutil_pid_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)
        mock_psutil.pid_exists.return_value = True

        assert manager.is_active(0) is True
        mock_psutil.pid_exists.assert_called_with(1234)

    def test_is_active_returns_false_when_pid_not_exists(self, mock_psutil):
        """[TC-WINDOW_MANAGER-007] Is active returns false when pid not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is active returns false when pid not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_active_returns_false_when_pid_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)
        mock_psutil.pid_exists.return_value = False

        assert manager.is_active(0) is False

    def test_get_all_active_pids(self, mock_psutil):
        """[TC-WINDOW_MANAGER-008] Get all active pids - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get all active pids 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_all_active_pids 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        mock_psutil.pid_exists.return_value = True

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)
        manager._slots[2] = SlotProcess(slot_idx=2, pid=5678, is_active=True)

        pids = manager.get_all_active_pids()

        assert 1234 in pids
        assert 5678 in pids

    def test_assign_pid_to_slot_success(self, mock_psutil):
        """[TC-WINDOW_MANAGER-009] Assign pid to slot success - 테스트 시나리오를 검증한다.

            테스트 목적:
                Assign pid to slot success 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_assign_pid_to_slot_success 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        mock_psutil.pid_exists.return_value = True

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        result = manager.assign_pid_to_slot(0, 1234)

        assert result is True
        assert manager.get_pid(0) == 1234

    def test_assign_pid_to_slot_fails_for_invalid_slot(self, mock_psutil):
        """[TC-WINDOW_MANAGER-010] Assign pid to slot fails for invalid slot - 테스트 시나리오를 검증한다.

            테스트 목적:
                Assign pid to slot fails for invalid slot 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_assign_pid_to_slot_fails_for_invalid_slot 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        result = manager.assign_pid_to_slot(10, 1234)

        assert result is False

    def test_assign_pid_to_slot_fails_when_pid_not_exists(self, mock_psutil):
        """[TC-WINDOW_MANAGER-011] Assign pid to slot fails when pid not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Assign pid to slot fails when pid not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_assign_pid_to_slot_fails_when_pid_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager

        mock_psutil.pid_exists.return_value = False

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)

        result = manager.assign_pid_to_slot(0, 1234)

        assert result is False

    def test_clear_slot_clears_slot_info(self, mock_psutil):
        """[TC-WINDOW_MANAGER-012] Clear slot clears slot info - 테스트 시나리오를 검증한다.

            테스트 목적:
                Clear slot clears slot info 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_clear_slot_clears_slot_info 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)

        manager.clear_slot(0)

        assert manager._slots[0].pid is None
        assert manager._slots[0].is_active is False

    def test_refresh_status_clears_dead_processes(self, mock_psutil):
        """[TC-WINDOW_MANAGER-013] Refresh status clears dead processes - 테스트 시나리오를 검증한다.

            테스트 목적:
                Refresh status clears dead processes 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_refresh_status_clears_dead_processes 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)
        manager._slots[1] = SlotProcess(slot_idx=1, pid=5678, is_active=True)

        # PID 1234 exists, PID 5678 doesn't
        mock_psutil.pid_exists.side_effect = lambda pid: pid == 1234

        manager.refresh_status()

        assert manager._slots[0].pid == 1234  # still active
        assert manager._slots[1].pid is None  # cleared

    @pytest.mark.asyncio
    async def test_terminate_for_slot_success(self, mock_psutil):
        """[TC-WINDOW_MANAGER-014] Terminate for slot success - 테스트 시나리오를 검증한다.

            테스트 목적:
                Terminate for slot success 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_terminate_for_slot_success 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        fake_proc = MagicMock()
        fake_proc.terminate = MagicMock()
        fake_proc.wait = MagicMock()

        mock_psutil.Process = MagicMock(return_value=fake_proc)

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)

        result = await manager.terminate_for_slot(0)

        assert result is True
        fake_proc.terminate.assert_called_once()
        assert manager._slots[0].pid is None

    @pytest.mark.asyncio
    async def test_terminate_for_slot_kills_on_timeout(self, mock_psutil):
        """[TC-WINDOW_MANAGER-015] Terminate for slot kills on timeout - 테스트 시나리오를 검증한다.

            테스트 목적:
                Terminate for slot kills on timeout 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_terminate_for_slot_kills_on_timeout 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        fake_proc = MagicMock()
        fake_proc.terminate = MagicMock()
        fake_proc.kill = MagicMock()
        fake_proc.wait = MagicMock(side_effect=mock_psutil.TimeoutExpired)

        mock_psutil.Process = MagicMock(return_value=fake_proc)
        mock_psutil.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
        fake_proc.wait = MagicMock(side_effect=mock_psutil.TimeoutExpired())

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)

        result = await manager.terminate_for_slot(0)

        assert result is True
        fake_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_for_slot_handles_no_such_process(self, mock_psutil):
        """[TC-WINDOW_MANAGER-016] Terminate for slot handles no such process - 테스트 시나리오를 검증한다.

            테스트 목적:
                Terminate for slot handles no such process 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_terminate_for_slot_handles_no_such_process 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.Process = MagicMock(
            side_effect=mock_psutil.NoSuchProcess("Process not found")
        )

        manager = SlotProcessManager(exe_path="test.exe", max_slots=4)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)

        result = await manager.terminate_for_slot(0)

        assert result is True  # Should succeed (process already gone)

    @pytest.mark.asyncio
    async def test_terminate_all_terminates_all_slots(self, mock_psutil):
        """[TC-WINDOW_MANAGER-017] Terminate all terminates all slots - 테스트 시나리오를 검증한다.

            테스트 목적:
                Terminate all terminates all slots 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_terminate_all_terminates_all_slots 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from infrastructure.process_manager import SlotProcessManager, SlotProcess

        fake_proc = MagicMock()
        fake_proc.terminate = MagicMock()
        fake_proc.wait = MagicMock()
        mock_psutil.Process = MagicMock(return_value=fake_proc)

        manager = SlotProcessManager(exe_path="test.exe", max_slots=2)
        manager._slots[0] = SlotProcess(slot_idx=0, pid=1234, is_active=True)
        manager._slots[1] = SlotProcess(slot_idx=1, pid=5678, is_active=True)

        await manager.terminate_all()

        assert manager._slots[0].pid is None
        assert manager._slots[1].pid is None


class TestSlotWindowManager:
    """Test SlotWindowManager functionality."""

    @pytest.fixture
    def mock_application(self, monkeypatch):
        """Mock pywinauto Application."""
        mock_app_class = MagicMock()
        mock_app_instance = MagicMock()
        mock_app_class.return_value = mock_app_instance
        monkeypatch.setattr(
            "controller.window_manager.Application", mock_app_class
        )
        return mock_app_class, mock_app_instance

    def test_slot_window_manager_init(self):
        """[TC-WINDOW_MANAGER-018] Slot window manager init - 테스트 시나리오를 검증한다.

            테스트 목적:
                Slot window manager init 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_slot_window_manager_init 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        manager = SlotWindowManager(slot_idx=0)

        assert manager.slot_idx == 0
        assert manager._app is None
        assert manager._main_window is None
        assert manager._pid is None

    def test_is_connected_false_when_not_connected(self):
        """[TC-WINDOW_MANAGER-019] Is connected false when not connected - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is connected false when not connected 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_connected_false_when_not_connected 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        manager = SlotWindowManager(slot_idx=0)

        assert manager.is_connected is False

    def test_is_connected_checks_psutil_and_window(self, mock_application):
        """[TC-WINDOW_MANAGER-020] Is connected checks psutil and window - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is connected checks psutil and window 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_connected_checks_psutil_and_window 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        mock_app_class, mock_app_instance = mock_application

        manager = SlotWindowManager(slot_idx=0)
        manager._app = mock_app_instance
        manager._pid = 1234

        # Create mock window
        mock_window = MagicMock()
        mock_window.exists.return_value = True
        manager._main_window = mock_window

        with patch("psutil.pid_exists", return_value=True):
            assert manager.is_connected is True

    def test_is_connected_clears_when_pid_not_exists(self, mock_application):
        """[TC-WINDOW_MANAGER-021] Is connected clears when pid not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is connected clears when pid not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_connected_clears_when_pid_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        mock_app_class, mock_app_instance = mock_application

        manager = SlotWindowManager(slot_idx=0)
        manager._app = mock_app_instance
        manager._pid = 1234
        manager._main_window = MagicMock()

        with patch("psutil.pid_exists", return_value=False):
            assert manager.is_connected is False
        assert manager._pid is None  # Connection cleared

    def test_is_connected_clears_when_window_stale(self, mock_application):
        """[TC-WINDOW_MANAGER-022] Is connected clears when window stale - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is connected clears when window stale 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_connected_clears_when_window_stale 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        mock_app_class, mock_app_instance = mock_application

        manager = SlotWindowManager(slot_idx=0)
        manager._app = mock_app_instance
        manager._pid = 1234

        mock_window = MagicMock()
        mock_window.exists.return_value = False  # Stale window
        manager._main_window = mock_window

        with patch("psutil.pid_exists", return_value=True):
            with patch("controller.window_manager.logger"):
                assert manager.is_connected is False
        assert manager._pid is None  # Connection cleared

    def test_disconnect_clears_connection(self, mock_application):
        """[TC-WINDOW_MANAGER-023] Disconnect clears connection - 테스트 시나리오를 검증한다.

            테스트 목적:
                Disconnect clears connection 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_disconnect_clears_connection 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        mock_app_class, mock_app_instance = mock_application

        manager = SlotWindowManager(slot_idx=0)
        manager._app = mock_app_instance
        manager._pid = 1234
        manager._main_window = MagicMock()

        with patch("controller.window_manager.logger"):
            manager.disconnect()

        assert manager._app is None
        assert manager._pid is None
        assert manager._main_window is None

    def test_find_control_returns_none_when_not_connected(self):
        """[TC-WINDOW_MANAGER-024] Find control returns none when not connected - 테스트 시나리오를 검증한다.

            테스트 목적:
                Find control returns none when not connected 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_find_control_returns_none_when_not_connected 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        manager = SlotWindowManager(slot_idx=0)

        result = manager.find_control(control_id=123)

        assert result is None

    def test_get_control_by_name_returns_none_when_not_connected(self):
        """[TC-WINDOW_MANAGER-025] Get control by name returns none when not connected - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get control by name returns none when not connected 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_control_by_name_returns_none_when_not_connected 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        manager = SlotWindowManager(slot_idx=0)

        result = manager.get_control_by_name("Button6")

        assert result is None

    def test_list_controls_returns_empty_when_not_connected(self):
        """[TC-WINDOW_MANAGER-026] List controls returns empty when not connected - 테스트 시나리오를 검증한다.

            테스트 목적:
                List controls returns empty when not connected 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_list_controls_returns_empty_when_not_connected 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager

        manager = SlotWindowManager(slot_idx=0)

        result = manager.list_controls()

        assert result == []

    @pytest.mark.asyncio
    async def test_connect_to_pid_timeout(self, mock_application):
        """[TC-WINDOW_MANAGER-027] Connect to pid timeout - 테스트 시나리오를 검증한다.

            테스트 목적:
                Connect to pid timeout 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_connect_to_pid_timeout 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import SlotWindowManager
        from pywinauto.findwindows import ElementNotFoundError

        mock_app_class, mock_app_instance = mock_application

        # Simulate connect() raising ElementNotFoundError every time
        mock_app_class.return_value.connect.side_effect = ElementNotFoundError()

        manager = SlotWindowManager(slot_idx=0)

        with patch("controller.window_manager.logger"):
            result = await manager.connect_to_pid(1234, timeout=0.1)

        assert result is False


class TestWindowManager:
    """Test WindowManager functionality."""

    @pytest.fixture
    def mock_process_manager(self, monkeypatch):
        """Mock SlotProcessManager."""
        mock_pm = MagicMock()
        mock_pm.assign_pid_to_slot = MagicMock(return_value=True)
        mock_pm.clear_slot = MagicMock()
        mock_pm.terminate_for_slot = AsyncMock(return_value=True)
        mock_pm.launch_for_slot = AsyncMock(return_value=1234)
        mock_pm.get_pid = MagicMock(return_value=None)
        mock_pm.is_active = MagicMock(return_value=False)

        monkeypatch.setattr(
            "controller.window_manager.SlotProcessManager",
            MagicMock(return_value=mock_pm),
        )
        return mock_pm

    def test_window_manager_init(self, mock_process_manager):
        """[TC-WINDOW_MANAGER-028] Window manager init - 테스트 시나리오를 검증한다.

            테스트 목적:
                Window manager init 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_window_manager_init 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        assert manager._exe_path == "USB Test.exe"
        assert manager._max_slots == 4
        assert len(manager._slot_windows) == 4

    def test_get_slot_window_returns_slot_window_manager(self, mock_process_manager):
        """[TC-WINDOW_MANAGER-029] Get slot window returns slot window manager - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get slot window returns slot window manager 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_slot_window_returns_slot_window_manager 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        slot_window = manager.get_slot_window(0)

        assert slot_window is not None
        assert slot_window.slot_idx == 0

    def test_get_slot_window_returns_none_for_invalid_index(
        self, mock_process_manager
    ):
        """[TC-WINDOW_MANAGER-030] Get slot window returns none for invalid index - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get slot window returns none for invalid index 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_slot_window_returns_none_for_invalid_index 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        slot_window = manager.get_slot_window(10)

        assert slot_window is None

    def test_is_slot_connected_returns_false_when_not_connected(
        self, mock_process_manager
    ):
        """[TC-WINDOW_MANAGER-031] Is slot connected returns false when not connected - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is slot connected returns false when not connected 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_slot_connected_returns_false_when_not_connected 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        assert manager.is_slot_connected(0) is False

    def test_disconnect_slot_clears_connection(self, mock_process_manager):
        """[TC-WINDOW_MANAGER-032] Disconnect slot clears connection - 테스트 시나리오를 검증한다.

            테스트 목적:
                Disconnect slot clears connection 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_disconnect_slot_clears_connection 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        manager.disconnect_slot(0)

        mock_process_manager.clear_slot.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_terminate_slot_terminates_and_disconnects(
        self, mock_process_manager
    ):
        """[TC-WINDOW_MANAGER-033] Terminate slot terminates and disconnects - 테스트 시나리오를 검증한다.

            테스트 목적:
                Terminate slot terminates and disconnects 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_terminate_slot_terminates_and_disconnects 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        result = await manager.terminate_slot(0)

        assert result is True
        mock_process_manager.terminate_for_slot.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_terminate_all_terminates_all_slots(self, mock_process_manager):
        """[TC-WINDOW_MANAGER-034] Terminate all terminates all slots - 테스트 시나리오를 검증한다.

            테스트 목적:
                Terminate all terminates all slots 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_terminate_all_terminates_all_slots 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=2)

        await manager.terminate_all()

        assert mock_process_manager.terminate_for_slot.call_count == 2

    def test_refresh_all_status_refreshes_process_manager(self, mock_process_manager):
        """[TC-WINDOW_MANAGER-035] Refresh all status refreshes process manager - 테스트 시나리오를 검증한다.

            테스트 목적:
                Refresh all status refreshes process manager 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_refresh_all_status_refreshes_process_manager 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        manager.refresh_all_status()

        mock_process_manager.refresh_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_and_connect_failure_terminates_process(
        self, mock_process_manager
    ):
        """[TC-WINDOW_MANAGER-036] Launch and connect failure terminates process - 테스트 시나리오를 검증한다.

            테스트 목적:
                Launch and connect failure terminates process 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_launch_and_connect_failure_terminates_process 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        # Launch succeeds but connect fails
        mock_process_manager.launch_for_slot = AsyncMock(return_value=1234)

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        # Mock the slot window manager's connect_to_pid to fail
        with patch.object(
            manager._slot_windows[0], "connect_to_pid", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = False

            result = await manager.launch_and_connect(0, timeout=1.0)

        assert result is False
        mock_process_manager.terminate_for_slot.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_connect_to_existing_assigns_and_connects(
        self, mock_process_manager
    ):
        """[TC-WINDOW_MANAGER-037] Connect to existing assigns and connects - 테스트 시나리오를 검증한다.

            테스트 목적:
                Connect to existing assigns and connects 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_connect_to_existing_assigns_and_connects 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.window_manager import WindowManager

        manager = WindowManager(exe_path="USB Test.exe", max_slots=4)

        with patch.object(
            manager._slot_windows[0], "connect_to_pid", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = True

            result = await manager.connect_to_existing(0, pid=5678, timeout=1.0)

        assert result is True
        mock_process_manager.assign_pid_to_slot.assert_called_with(0, 5678)
