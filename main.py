"""Agent Entry Point.

Main entry point for SS USB Test Agent.
All dependencies are injected via DI Container.
"""

import asyncio
import signal
from typing import Optional

from config.settings import get_settings
from config.constants import BackendMessageType
from interface.websocket.client import WebSocketClient
from utils.logging import setup_logging, get_logger, bind_context, get_ilogger

# Core - DI Container & Protocols
from core import (
    Container,
    get_container,
    IWindowFinder,
    IStateStore,
    IClock,
    MemoryManager,
    MemoryThresholds,
)

# Infrastructure - 실제 구현체
from infrastructure import (
    SystemClock,
    PywinautoWindowFinder,
    InMemoryStateStore,
)

# Controller - MFC Controller
from controller.controller import MFCController

# Services - 비즈니스 로직
from services import TestExecutor, StateMonitor, MemoryMonitor, MemoryMonitorConfig
from services.test_executor import TestRequest

# Domain - State Machine
from domain import (
    SlotState,
    SlotEvent,
    SlotStateMachineManager,
    InvalidTransitionError,
)
from config.constants import SlotConfig

logger = get_logger(__name__)


def setup_container() -> Container:
    """Configure DI Container.

    Registers all dependencies.
    These are actual implementations used in production environment.

    Returns:
        Configured Container instance.
    """
    container = get_container()

    # Infrastructure 레이어 등록 (싱글톤)
    container.register(IClock, SystemClock, singleton=True)
    container.register(IStateStore, InMemoryStateStore, singleton=True)
    container.register(IWindowFinder, PywinautoWindowFinder, singleton=True)

    logger.info("DI Container configured with production dependencies")
    return container


class Agent:
    """SS USB Test Agent.

    Main class for USB Test automation Agent.
    Maintains WebSocket connection with Backend and manages test execution.
    All dependencies are injected via DI Container.

    Attributes:
        settings: Agent settings.
        is_running: Running state.
        ws_client: WebSocket client.
        container: DI Container.
        test_executor: Test executor.
        state_monitor: State monitor.
        memory_monitor: Memory monitor (for long-running processes).
    """

    def __init__(self, container: Optional[Container] = None) -> None:
        """Initialize Agent.

        Args:
            container: DI Container (uses global container if None).
        """
        self.settings = get_settings()
        self.is_running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._ws_client: Optional[WebSocketClient] = None

        # DI Container 설정
        self._container = container or setup_container()

        # Services 인스턴스 (lazy initialization)
        self._test_executor: Optional[TestExecutor] = None
        self._state_monitor: Optional[StateMonitor] = None
        self._memory_monitor: Optional[MemoryMonitor] = None
        self._memory_manager: Optional[MemoryManager] = None

        # MFC Controller - 슬롯별 USB Test.exe 제어
        self._mfc_controller: Optional[MFCController] = None

        # Slot State Machine Manager (슬롯별 상태 관리)
        self._slot_manager: Optional[SlotStateMachineManager] = None

    @property
    def container(self) -> Container:
        """DI Container."""
        return self._container

    @property
    def ws_client(self) -> Optional[WebSocketClient]:
        """WebSocket client."""
        return self._ws_client

    @property
    def test_executor(self) -> Optional[TestExecutor]:
        """Test executor."""
        return self._test_executor

    @property
    def state_monitor(self) -> Optional[StateMonitor]:
        """State monitor."""
        return self._state_monitor

    @property
    def memory_monitor(self) -> Optional[MemoryMonitor]:
        """Memory monitor."""
        return self._memory_monitor

    @property
    def mfc_controller(self) -> Optional[MFCController]:
        """MFC Controller for slot-based USB Test.exe control."""
        return self._mfc_controller

    @property
    def slot_manager(self) -> Optional[SlotStateMachineManager]:
        """Slot state machine manager."""
        return self._slot_manager

    async def start(self) -> None:
        """Start Agent.

        Injects services from DI Container and sets up WebSocket connection.
        """
        self._shutdown_event = asyncio.Event()
        self.is_running = True

        logger.info(
            "Agent starting",
            agent_name=self.settings.name,
            version=self.settings.version,
            backend_url=self.settings.backend_url,
        )

        # 로깅 컨텍스트 설정
        bind_context(
            agent_name=self.settings.name,
            agent_version=self.settings.version,
        )

        # DI Container에서 의존성 resolve
        window_finder = self._container.resolve(IWindowFinder)
        state_store = self._container.resolve(IStateStore)
        clock = self._container.resolve(IClock)

        # 메모리 관리자 초기화 (장기 실행 프로세스용)
        self._memory_manager = MemoryManager(
            clock=clock,
            thresholds=MemoryThresholds(
                warning_mb=256.0,
                critical_mb=512.0,
                gc_interval_seconds=300.0,  # 5분
                max_gc_objects=100_000,
            ),
        )

        # 메모리 모니터 초기화
        self._memory_monitor = MemoryMonitor(
            memory_manager=self._memory_manager,
            clock=clock,
            logger=get_ilogger("memory_monitor"),
            config=MemoryMonitorConfig(
                check_interval_seconds=60.0,  # 1분마다 체크
                auto_optimize=True,
                log_stats_interval_seconds=3600.0,  # 1시간마다 로그
            ),
        )

        # 서비스 인스턴스 생성 (의존성 주입)
        self._test_executor = TestExecutor(
            window_finder=window_finder,
            state_store=state_store,
            clock=clock,
            logger=get_ilogger("test_executor"),
        )

        # MFC Controller 초기화 - 슬롯별 USB Test.exe 관리
        self._mfc_controller = MFCController()
        logger.info(
            "MFC Controller initialized",
            exe_path=self._mfc_controller._exe_path,
        )

        # Slot State Machine Manager 초기화
        self._slot_manager = SlotStateMachineManager(
            max_slots=SlotConfig.MAX_SLOTS,
            on_state_change=self._on_slot_state_change,
        )
        logger.info(
            "Slot state machine manager initialized",
            max_slots=SlotConfig.MAX_SLOTS,
        )

        # 메모리 정리 콜백 등록
        self._register_cleanup_callbacks()

        logger.info("Services initialized with DI")

        # WebSocket 클라이언트 생성
        self._ws_client = WebSocketClient(
            settings=self.settings,
            on_message=self._on_message,
        )

        # 메시지 핸들러 등록
        self._register_handlers()

        try:
            # 메모리 모니터 시작
            if self._memory_monitor:
                await self._memory_monitor.start()
                logger.info("Memory monitor started")

            # 메인 루프 실행
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("Agent cancelled")
        finally:
            await self._cleanup()

    def _register_cleanup_callbacks(self) -> None:
        """Register cleanup callbacks for memory management."""
        if not self._memory_monitor:
            return

        # WebSocket 메시지 핸들러 정리
        def cleanup_ws_handlers() -> None:
            if self._ws_client and hasattr(self._ws_client, "_message_handlers"):
                # 메시지 핸들러는 유지하되, 참조 정리 가능성 체크
                pass

        self._memory_monitor.register_cleanup("ws_handlers", cleanup_ws_handlers)

        # State Store 오래된 데이터 정리
        def cleanup_state_store() -> None:
            state_store = self._container.resolve(IStateStore)
            if hasattr(state_store, "reset_all"):
                # 필요시 오래된 상태 정리 (현재는 idle 상태만 리셋)
                pass

        self._memory_monitor.register_cleanup("state_store", cleanup_state_store)

        logger.info("Cleanup callbacks registered for memory management")

    def _on_slot_state_change(
        self,
        slot_idx: int,
        old_state: SlotState,
        new_state: SlotState,
    ) -> None:
        """Callback when slot state changes.

        Args:
            slot_idx: Slot index.
            old_state: Previous state.
            new_state: New state.
        """
        logger.info(
            "Slot state changed",
            slot_idx=slot_idx,
            old_state=old_state.value,
            new_state=new_state.value,
        )

        # 상태 변경 시 WebSocket으로 전송 (비동기 태스크로 실행)
        if self._ws_client and self._slot_manager:
            machine = self._slot_manager.get(slot_idx)
            if machine:
                asyncio.create_task(
                    self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={
                            "status": new_state.value,
                            "previous_status": old_state.value,
                            **machine.context.to_dict(),
                        },
                    )
                )

    def _register_handlers(self) -> None:
        """Register Backend message handlers."""
        if not self._ws_client:
            return

        # 테스트 시작 명령
        self._ws_client.register_handler(
            BackendMessageType.RUN_TEST,
            self._handle_start_test,
        )

        # 테스트 중지 명령
        self._ws_client.register_handler(
            BackendMessageType.STOP_TEST,
            self._handle_stop_test,
        )

        # 설정 업데이트
        self._ws_client.register_handler(
            BackendMessageType.CONFIG_UPDATE,
            self._handle_config_update,
        )

        logger.info("Message handlers registered")

    async def _handle_start_test(self, data: dict) -> None:
        """Handle start test command.

        Args:
            data: Test configuration data.
        """
        slot_idx = data.get("slot_idx")
        test_config = data.get("config", {})

        logger.info(
            "Start test command received",
            slot_idx=slot_idx,
            config=test_config,
        )

        # Validate slot_idx
        if slot_idx is None or not self._mfc_controller or not self._slot_manager:
            logger.warning("MFC Controller not available or invalid slot")
            return

        # Get slot state machine
        try:
            slot_machine = self._slot_manager[slot_idx]
        except KeyError:
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return

        # Check if slot is busy
        if slot_machine.is_busy():
            logger.warning(
                "Slot is busy, cannot start test",
                slot_idx=slot_idx,
                current_state=slot_machine.state.value,
            )
            if self._ws_client:
                await self._ws_client.send_state_update(
                    slot_idx=slot_idx,
                    state_data={
                        "status": "error",
                        "error": f"Slot {slot_idx} is busy ({slot_machine.state.value})",
                    },
                )
            return

        try:
            # State transition: START_TEST
            slot_machine.trigger(
                SlotEvent.START_TEST,
                context_update={
                    "test_name": test_config.get("test_name", "USB Test"),
                },
            )

            # USB Test.exe 슬롯별 연결 확인 (연결 안 되어 있으면 실행 및 연결)
            if not self._mfc_controller.is_slot_connected(slot_idx):
                logger.info(
                    "Launching and connecting USB Test.exe for slot",
                    slot_idx=slot_idx,
                )
                slot_machine.trigger(SlotEvent.CONFIGURE)  # PREPARING -> CONFIGURING

                connected = await self._mfc_controller.connect_slot(slot_idx)
                if not connected:
                    slot_machine.trigger(
                        SlotEvent.ERROR,
                        error_message="USB Test.exe에 연결할 수 없습니다. 프로그램 경로를 확인하세요.",
                    )
                    return

                pid = self._mfc_controller.get_slot_pid(slot_idx)
                logger.info(
                    "USB Test.exe connected for slot",
                    slot_idx=slot_idx,
                    pid=pid,
                )

            # TestConfig 객체 생성
            from domain.models.test_config import TestConfig

            config = TestConfig(
                slot_idx=slot_idx,
                jira_no=test_config.get("jira_no", ""),
                sample_no=test_config.get("sample_no", ""),
                capacity=test_config.get("capacity", "1TB"),
                drive=test_config.get("drive", "E"),
                method=test_config.get("method", "0HR"),
                test_type=test_config.get("test_type", "Full Photo"),
                loop_count=test_config.get("loop_count", 1),
                test_name=test_config.get("test_name", "USB Test"),
            )

            # State transition: CONFIGURE (if not already)
            if slot_machine.state == SlotState.PREPARING:
                slot_machine.trigger(SlotEvent.CONFIGURE)

            # Execute test using MFC Controller
            success = await self._mfc_controller.start_test(slot_idx, config)

            if success:
                # State transition: RUN
                slot_machine.trigger(
                    SlotEvent.RUN,
                    context_update={
                        "total_loop": test_config.get("loop_count", 1),
                    },
                )
            else:
                slot_machine.trigger(
                    SlotEvent.ERROR,
                    error_message="테스트 시작에 실패했습니다.",
                )

        except InvalidTransitionError as e:
            logger.error(
                "Invalid state transition",
                slot_idx=slot_idx,
                error=str(e),
            )
            if self._ws_client:
                await self._ws_client.send_state_update(
                    slot_idx=slot_idx,
                    state_data={"status": "error", "error": str(e)},
                )
        except Exception as e:
            logger.error("Failed to start test", slot_idx=slot_idx, error=str(e))
            # Transition to ERROR state
            try:
                slot_machine.trigger(SlotEvent.ERROR, error_message=str(e))
            except InvalidTransitionError:
                slot_machine.force_state(SlotState.ERROR, f"Exception: {e}")

    async def _handle_stop_test(self, data: dict) -> None:
        """Handle stop test command.

        Args:
            data: Stop request data.
        """
        slot_idx = data.get("slot_idx")

        logger.info("Stop test command received", slot_idx=slot_idx)

        # Validate slot_idx
        if slot_idx is None or not self._mfc_controller or not self._slot_manager:
            logger.warning("MFC Controller not available or invalid slot")
            return

        # Get slot state machine
        try:
            slot_machine = self._slot_manager[slot_idx]
        except KeyError:
            logger.error("Invalid slot index", slot_idx=slot_idx)
            return

        # Check if slot can be stopped
        if not slot_machine.can_transition(SlotEvent.STOP):
            logger.warning(
                "Cannot stop test in current state",
                slot_idx=slot_idx,
                current_state=slot_machine.state.value,
            )
            return

        try:
            # State transition: STOP
            slot_machine.trigger(SlotEvent.STOP)

            # Execute stop using MFC Controller
            success = await self._mfc_controller.stop_test(slot_idx)

            if success:
                # State transition: STOPPED
                slot_machine.trigger(SlotEvent.STOPPED)
            else:
                slot_machine.trigger(
                    SlotEvent.ERROR,
                    error_message="테스트 중지에 실패했습니다.",
                )

        except InvalidTransitionError as e:
            logger.error(
                "Invalid state transition during stop",
                slot_idx=slot_idx,
                error=str(e),
            )
        except Exception as e:
            logger.error("Failed to stop test", slot_idx=slot_idx, error=str(e))
            try:
                slot_machine.trigger(SlotEvent.ERROR, error_message=str(e))
            except InvalidTransitionError:
                slot_machine.force_state(SlotState.ERROR, f"Stop exception: {e}")

    async def _handle_config_update(self, data: dict) -> None:
        """Handle configuration update.

        Args:
            data: New configuration data.
        """
        logger.info("Config update received", data=data)

        # TODO: 설정 업데이트 적용

    async def _on_message(self, message: dict) -> None:
        """General message callback.

        Args:
            message: Received message.
        """
        logger.debug("Message callback", type=message.get("type"))

    async def stop(self) -> None:
        """Stop Agent.

        Cleans up all running tasks and terminates.
        """
        logger.info("Agent stopping")
        self.is_running = False

        # WebSocket 연결 종료
        if self._ws_client:
            await self._ws_client.disconnect()

        if self._shutdown_event:
            self._shutdown_event.set()

    async def _main_loop(self) -> None:
        """Main event loop.

        Maintains WebSocket connection and handles messages.
        """
        logger.info("Main loop started")

        if not self._ws_client:
            logger.error("WebSocket client not initialized")
            return

        # WebSocket 클라이언트 실행 (자동 연결, 재연결 처리)
        ws_task = asyncio.create_task(self._ws_client.run())

        try:
            while self.is_running:
                # Shutdown 이벤트 확인
                if self._shutdown_event and self._shutdown_event.is_set():
                    break

                # TODO: 추가적인 상태 모니터링 로직
                await asyncio.sleep(1)

        except Exception as e:
            logger.error("Error in main loop", error=str(e))
        finally:
            # WebSocket 태스크 취소
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

        logger.info("Main loop ended")

    async def _cleanup(self) -> None:
        """Clean up resources.

        Closes WebSocket connection, cleans up services, resets DI Container, etc.
        """
        logger.info("Cleaning up resources")

        # 메모리 모니터 중지
        if self._memory_monitor:
            await self._memory_monitor.stop()
            self._memory_monitor = None

        # StateMonitor 중지
        if self._state_monitor:
            self._state_monitor.stop()
            self._state_monitor = None

        # MFC Controller 정리 - 모든 슬롯 프로세스 종료
        if self._mfc_controller:
            logger.info("Terminating all USB Test.exe processes")
            await self._mfc_controller.terminate_all()
            self._mfc_controller = None

        # Slot State Machine Manager 정리
        if self._slot_manager:
            self._slot_manager.reset_all()
            self._slot_manager = None

        # TestExecutor 정리
        self._test_executor = None

        # MemoryManager 정리
        self._memory_manager = None

        # WebSocket 연결 종료
        if self._ws_client:
            await self._ws_client.disconnect()
            self._ws_client = None

        # 최종 GC 실행
        import gc
        gc.collect()

        logger.info("Cleanup completed")


async def main() -> None:
    """Main function.

    Performs logging setup, DI Container setup, Agent creation and execution.
    """
    # 로깅 초기화
    setup_logging()
    logger.info("Initializing SS USB Test Agent")

    # DI Container 설정
    container = setup_container()

    # Agent 생성 (컨테이너 주입)
    agent = Agent(container=container)

    # 시그널 핸들러 설정 (Ctrl+C 등)
    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(agent.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows에서는 add_signal_handler가 지원되지 않음
            pass

    # Agent 시작
    try:
        await agent.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        await agent.stop()


def run() -> None:
    """Script execution entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
