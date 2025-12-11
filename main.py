"""Agent Entry Point.

Main entry point for SS USB Test Agent.
All dependencies are injected via DI Container.
"""

import asyncio
import signal
from typing import TYPE_CHECKING, Awaitable, Callable

from config.constants import (
    AgentMessageType,
    BackendMessageType,
    ProcessState,
    SlotConfig,
)
from config.settings import get_settings

# TYPE_CHECKING 블록: 순환 import 방지
if TYPE_CHECKING:
    from domain.models.test_config import TestConfig
    from services.batch_executor import BatchProgress

# Controller - MFC Controller
from controller.controller import MFCController

# Core - DI Container & Protocols
from core import (
    Container,
    IClock,
    IStateStore,
    IWindowFinder,
    MemoryManager,
    MemoryThresholds,
    get_container,
)

# Domain - State Machine
from domain import (
    InvalidTransitionError,
    SlotEvent,
    SlotState,
    SlotStateMachineManager,
)

# Infrastructure - 실제 구현체
from infrastructure import (
    InMemoryStateStore,
    PywinautoWindowFinder,
    SystemClock,
)
from interface.websocket.client import WebSocketClient

# Services - 비즈니스 로직
from services import (
    MemoryMonitor,
    MemoryMonitorConfig,
    MFCUIMonitor,
    MFCUIState,
    ProcessMonitor,
    ProcessTerminationEvent,
    StateMonitor,
    TestExecutor,
    UIStateChange,
)
from services.batch_executor import BatchExecutor, BatchExecutorManager, BatchProgress
from utils.logging import bind_context, get_ilogger, get_logger, setup_logging

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

    def __init__(self, container: Container | None = None) -> None:
        """Initialize Agent.

        Args:
            container: DI Container (uses global container if None).
        """
        self.settings = get_settings()
        self.is_running = False
        self._shutdown_event: asyncio.Event | None = None
        self._ws_client: WebSocketClient | None = None

        # DI Container 설정
        self._container = container or setup_container()

        # Services 인스턴스 (lazy initialization)
        self._test_executor: TestExecutor | None = None
        self._state_monitor: StateMonitor | None = None
        self._memory_monitor: MemoryMonitor | None = None
        self._memory_manager: MemoryManager | None = None

        # 프로세스 및 UI 모니터링 서비스
        self._process_monitor: ProcessMonitor | None = None
        self._mfc_ui_monitor: MFCUIMonitor | None = None

        # MFC Controller - 슬롯별 USB Test.exe 제어
        self._mfc_controller: MFCController | None = None

        # Slot State Machine Manager (슬롯별 상태 관리)
        self._slot_manager: SlotStateMachineManager | None = None

    @property
    def container(self) -> Container:
        """DI Container."""
        return self._container

    @property
    def ws_client(self) -> WebSocketClient | None:
        """WebSocket client."""
        return self._ws_client

    @property
    def test_executor(self) -> TestExecutor | None:
        """Test executor."""
        return self._test_executor

    @property
    def state_monitor(self) -> StateMonitor | None:
        """State monitor."""
        return self._state_monitor

    @property
    def memory_monitor(self) -> MemoryMonitor | None:
        """Memory monitor."""
        return self._memory_monitor

    @property
    def process_monitor(self) -> ProcessMonitor | None:
        """Process monitor for detecting unexpected terminations."""
        return self._process_monitor

    @property
    def mfc_ui_monitor(self) -> MFCUIMonitor | None:
        """MFC UI monitor for polling UI state."""
        return self._mfc_ui_monitor

    @property
    def mfc_controller(self) -> MFCController | None:
        """MFC Controller for slot-based USB Test.exe control."""
        return self._mfc_controller

    @property
    def slot_manager(self) -> SlotStateMachineManager | None:
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

        # 프로세스 모니터 초기화 (PID 감시)
        self._process_monitor = ProcessMonitor(
            clock=clock,
            logger=get_ilogger("process_monitor"),
            max_slots=SlotConfig.MAX_SLOTS,
        )
        self._process_monitor.set_termination_callback(
            self._on_process_terminated
        )
        logger.info("Process monitor initialized")

        # MFC UI 모니터 초기화 (UI 상태 폴링)
        self._mfc_ui_monitor = MFCUIMonitor(
            window_manager=self._mfc_controller.window_manager,
            clock=clock,
            logger=get_ilogger("mfc_ui_monitor"),
            max_slots=SlotConfig.MAX_SLOTS,
        )
        self._mfc_ui_monitor.set_change_callback(self._on_mfc_ui_changed)
        self._mfc_ui_monitor.set_poll_callback(self._on_mfc_ui_polled)
        self._mfc_ui_monitor.set_test_completed_callback(
            self._on_mfc_test_completed
        )
        self._mfc_ui_monitor.set_user_intervention_callback(
            self._on_user_intervention
        )
        logger.info("MFC UI monitor initialized")

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

            # 프로세스 모니터 시작 (5초 간격)
            if self._process_monitor:
                await self._process_monitor.start(interval=5.0)
                logger.info("Process monitor started")

            # MFC UI 모니터 시작 (2초 간격 - 실시간 진행상황 전송을 위해 빠른 폴링)
            if self._mfc_ui_monitor:
                await self._mfc_ui_monitor.start(interval=2.0)
                logger.info("MFC UI monitor started")

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

        Internal state machine transitions.
        Only final states are reported to Backend.

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

        # 내부 상태 전이는 Backend에 전송하지 않음
        # BatchExecutor와 MFC UI Monitor가 적절한 시점에 전송
        # 여기서는 모니터링 활성화/비활성화만 처리

        # 상태가 RUNNING으로 전환되면 모니터링 활성화
        if new_state == SlotState.RUNNING:
            pid = None
            if self._mfc_controller:
                pid = self._mfc_controller.get_slot_pid(slot_idx)
            if pid and self._process_monitor:
                self._process_monitor.watch_slot(slot_idx, pid, is_running=True)
            if self._mfc_ui_monitor:
                self._mfc_ui_monitor.add_monitored_slot(slot_idx)

        # 상태가 완료/실패/에러로 전환되면 모니터링 비활성화
        elif new_state in (SlotState.COMPLETED, SlotState.FAILED, SlotState.ERROR, SlotState.IDLE):
            if self._process_monitor:
                self._process_monitor.unwatch_slot(slot_idx)
            if self._mfc_ui_monitor:
                self._mfc_ui_monitor.remove_monitored_slot(slot_idx)

    async def _on_process_terminated(
        self,
        event: ProcessTerminationEvent,
    ) -> None:
        """Callback when USB Test.exe process is terminated unexpectedly.

        Args:
            event: Process termination event.
        """
        logger.error(
            "USB Test.exe process terminated unexpectedly",
            slot_idx=event.slot_idx,
            pid=event.pid,
            reason=event.reason.value,
            was_running=event.was_running,
        )

        # MFC Controller 슬롯 연결 정보 정리 (중요: 재시도 시 새 프로세스 실행을 위해)
        if self._mfc_controller:
            await self._mfc_controller.disconnect_slot(event.slot_idx)
            logger.info(
                "Slot connection cleaned up after process termination",
                slot_idx=event.slot_idx,
            )

        # 슬롯 상태 머신 업데이트
        if self._slot_manager:
            try:
                slot_machine = self._slot_manager.get(event.slot_idx)
                if slot_machine and slot_machine.state == SlotState.RUNNING:
                    # ERROR 상태로 전환
                    error_msg = (
                        f"USB Test.exe 프로세스가 예기치 않게 종료되었습니다. "
                        f"이유: {event.reason.value}"
                    )
                    slot_machine.trigger(SlotEvent.ERROR, error_message=error_msg)
            except InvalidTransitionError as e:
                logger.warning("Could not transition to ERROR state", error=str(e))
                if slot_machine:
                    slot_machine.force_state(
                        SlotState.ERROR,
                        f"Process terminated: {event.reason.value}"
                    )

        # Backend에 에러 알림
        if self._ws_client:
            await self._ws_client.send(
                {
                    "type": AgentMessageType.ERROR.value,
                    "data": {
                        "slot_idx": event.slot_idx,
                        "error_code": "PROCESS_TERMINATED",
                        "error_message": (
                            f"USB Test.exe process terminated unexpectedly "
                            f"(PID: {event.pid}, Reason: {event.reason.value})"
                        ),
                        "was_running": event.was_running,
                        "timestamp": event.timestamp.isoformat(),
                    },
                }
            )

        # MFC UI 모니터링에서도 제거
        if self._mfc_ui_monitor:
            self._mfc_ui_monitor.remove_monitored_slot(event.slot_idx)

    def _determine_status(self, state: MFCUIState) -> str:
        """Determine Frontend status from MFC UI state.

        Status determination logic (순서 중요!):
        1. Fail: 테스트 실패 -> "failed" (최우선)
        2. Stop: 중지됨 -> "stopping"
        3. 완료 조건 (루프 완료): current_loop == total_loop and Phase == IDLE -> "completed"
           - Pass 상태라도 루프가 모두 완료되고 Phase가 IDLE이면 completed
        4. Pass/Test: 테스트 진행 중 -> "running"
        5. Idle: 대기 상태 -> "idle"

        Args:
            state: Current MFC UI state.

        Returns:
            Frontend status string.
        """
        from config.constants import TestPhase

        process_state = state.process_state

        # 1. Fail은 항상 failed (최우선)
        if process_state == ProcessState.FAIL:
            return "failed"

        # 2. Stop은 항상 stopping
        if process_state == ProcessState.STOP:
            return "stopping"

        # 3. 루프 완료 조건 (Pass/Idle 상태이면서 완료)
        # Pass 상태에서도 루프가 끝나면 완료로 처리해야 함
        if (
            state.total_loop > 0
            and state.current_loop == state.total_loop
            and state.test_phase == TestPhase.IDLE
        ):
            return "completed"

        # 4. Pass 또는 Test는 running (테스트 진행 중)
        if process_state in (ProcessState.PASS, ProcessState.TEST):
            return "running"

        # 5. Idle 상태 (테스트 시작 전 대기)
        if process_state == ProcessState.IDLE:
            return "idle"

        # Unknown 또는 기타
        return "error"

    async def _on_mfc_ui_polled(self, state: MFCUIState) -> None:
        """Callback on every MFC UI poll.

        Sends current state to Backend regardless of changes.
        This ensures real-time progress updates.

        For batch mode:
        - Status remains 'running' until all batches complete
        - Loop values are calculated based on batch progress, not MFC values

        Args:
            state: Current MFC UI state.
        """
        if not self._ws_client or not self._slot_manager:
            return

        slot_idx = state.slot_idx

        # 슬롯 상태 머신에서 batch 정보 가져오기
        try:
            slot_machine = self._slot_manager.get(slot_idx)
            if not slot_machine:
                return
            context = slot_machine.context
        except (KeyError, AttributeError):
            return

        # Batch 모드 여부 확인 (total_batch > 1)
        is_batch_mode = context.total_batch > 1

        if is_batch_mode:
            # Batch 모드: 계산된 값 사용
            # current_loop = (current_batch - 1) * loop_step + mfc_current_loop
            calculated_loop = (
                (context.current_batch - 1) * context.loop_step
                + state.current_loop
            )
            # total_loop는 전체 loop_count 사용
            total_loop = context.total_loop

            # 진행률 계산
            progress_percent = (
                (calculated_loop / total_loop) * 100 if total_loop > 0 else 0
            )

            # 상태는 running 유지 (fail/error 제외)
            if state.process_state == ProcessState.FAIL:
                status = "failed"
            elif state.process_state == ProcessState.STOP:
                status = "stopping"
            else:
                # PASS, TEST, IDLE 모두 running으로 (batch 진행 중)
                status = "running"

            await self._ws_client.send_state_update(
                slot_idx=slot_idx,
                state_data={
                    "status": status,
                    "progress": progress_percent,
                    "current_loop": calculated_loop,
                    "total_loop": total_loop,
                    "current_batch": context.current_batch,
                    "total_batch": context.total_batch,
                    "current_phase": state.test_phase.name,
                },
            )
        else:
            # 단일 실행 모드: 기존 방식
            status = self._determine_status(state)
            await self._ws_client.send_state_update(
                slot_idx=slot_idx,
                state_data={
                    "status": status,
                    "progress": state.progress_percent,
                    "current_loop": state.current_loop,
                    "total_loop": state.total_loop,
                    "current_phase": state.test_phase.name,
                },
            )

    async def _on_mfc_ui_changed(self, change: UIStateChange) -> None:
        """Callback when MFC UI state changes.

        Note: State updates are sent via _on_mfc_ui_polled for consistency.
        This callback is primarily for logging significant changes.

        Args:
            change: UI state change event.
        """
        logger.debug(
            "MFC UI state changed",
            slot_idx=change.slot_idx,
            changed_fields=change.changed_fields,
        )

        # 상태 변경은 _on_mfc_ui_polled에서 전송하므로 여기서는 로깅만
        # 단, FAIL 상태 변경은 즉시 알림 (중요한 이벤트)
        if change.current_state and change.current_state.process_state == ProcessState.FAIL:
            logger.warning(
                "Test FAIL detected",
                slot_idx=change.slot_idx,
            )
            if self._ws_client:
                await self._ws_client.send_state_update(
                    slot_idx=change.slot_idx,
                    state_data={
                        "status": "failed",
                        "error": "Test failed",
                    },
                )

    async def _on_mfc_test_completed(
        self,
        slot_idx: int,
        final_state: ProcessState,
    ) -> None:
        """Callback when test completion is detected via MFC UI.

        This is triggered by the UI monitor when process state
        changes from TEST to PASS/FAIL/STOP.

        In batch mode:
        - PASS: Single batch completed, don't notify Backend (BatchExecutor handles it)
        - FAIL/STOP: Immediately notify Backend (error situation)

        In single mode:
        - Notify Backend of completion

        Args:
            slot_idx: Slot index.
            final_state: Final process state.
        """
        logger.info(
            "Test completion detected via MFC UI",
            slot_idx=slot_idx,
            final_state=final_state.name,
        )

        # 슬롯 상태 머신에서 batch 정보 확인
        is_batch_mode = False
        if self._slot_manager:
            try:
                slot_machine = self._slot_manager.get(slot_idx)
                if slot_machine:
                    context = slot_machine.context
                    is_batch_mode = context.total_batch > 1
            except (KeyError, AttributeError):
                pass

        # Batch 모드에서 PASS는 단일 배치 완료 → BatchExecutor가 처리하므로 무시
        if is_batch_mode and final_state == ProcessState.PASS:
            logger.debug(
                "Batch iteration PASS detected, BatchExecutor will handle",
                slot_idx=slot_idx,
            )
            # State machine 전이하지 않음 - BatchExecutor가 BATCH_COMPLETE 이벤트 처리
            return

        # FAIL/STOP은 즉시 처리 (에러 상황)
        if self._slot_manager:
            try:
                slot_machine = self._slot_manager.get(slot_idx)
                if slot_machine and slot_machine.state == SlotState.RUNNING:
                    if final_state == ProcessState.FAIL:
                        slot_machine.trigger(
                            SlotEvent.FAIL,
                            error_message="Test failed (detected via UI)",
                        )
                    elif final_state == ProcessState.STOP:
                        slot_machine.trigger(SlotEvent.STOPPED)
                    elif final_state == ProcessState.PASS and not is_batch_mode:
                        # 단일 모드에서만 COMPLETE 처리
                        slot_machine.trigger(SlotEvent.COMPLETE)
            except InvalidTransitionError as e:
                logger.warning(
                    "Could not transition state on test completion",
                    error=str(e),
                )

        # Backend에 알림 (FAIL/STOP 또는 단일 모드 완료 시에만)
        if self._ws_client:
            if final_state == ProcessState.FAIL:
                await self._ws_client.send_state_update(
                    slot_idx=slot_idx,
                    state_data={
                        "status": "failed",
                        "error": "Test failed",
                        "final_state": final_state.name,
                    },
                )
            elif final_state == ProcessState.STOP:
                await self._ws_client.send_state_update(
                    slot_idx=slot_idx,
                    state_data={
                        "status": "stopped",
                        "final_state": final_state.name,
                    },
                )
            elif not is_batch_mode:
                # 단일 모드 완료
                await self._ws_client.send_test_completed(
                    slot_idx=slot_idx,
                    success=True,
                    result_data={
                        "final_state": final_state.name,
                        "detected_via": "mfc_ui_monitor",
                    },
                )

    async def _on_user_intervention(
        self,
        slot_idx: int,
        description: str,
    ) -> None:
        """Callback when user intervention is detected.

        This is triggered when the user appears to have manually
        interacted with the USB Test.exe UI.

        Args:
            slot_idx: Slot index.
            description: Description of the intervention.
        """
        logger.warning(
            "User intervention detected",
            slot_idx=slot_idx,
            description=description,
        )

        # Backend에 사용자 개입 알림
        if self._ws_client:
            await self._ws_client.send(
                {
                    "type": AgentMessageType.ERROR.value,
                    "data": {
                        "slot_idx": slot_idx,
                        "error_code": "USER_INTERVENTION",
                        "error_message": description,
                        "severity": "warning",
                    },
                }
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

            # 받은 설정 로깅
            logger.info(
                "Received test config",
                slot_idx=slot_idx,
                test_config=test_config,
            )

            config = TestConfig(
                slot_idx=slot_idx,
                jira_no=test_config.get("jira_no", ""),
                sample_no=test_config.get("sample_no", ""),
                capacity=test_config.get("capacity", "1TB"),
                drive=test_config.get("drive", "D"),
                method=test_config.get("method", "0HR"),
                test_type=test_config.get("test_type", "Photo"),
                loop_count=test_config.get("loop_count", 1),
                loop_step=test_config.get("loop_step", 1),
                test_name=test_config.get("test_name", "USB Test"),
            )

            # State transition: CONFIGURE (if not already)
            if slot_machine.state == SlotState.PREPARING:
                slot_machine.trigger(SlotEvent.CONFIGURE)

            # Batch 실행 여부 결정 (loop_step < loop_count면 batch 모드)
            total_batch = (config.loop_count + config.loop_step - 1) // config.loop_step

            if total_batch > 1:
                # Batch 모드: BatchExecutor 사용
                logger.info(
                    "Starting batch test execution",
                    slot_idx=slot_idx,
                    total_loop=config.loop_count,
                    loop_step=config.loop_step,
                    total_batch=total_batch,
                )

                # BatchExecutor 생성 및 실행
                batch_executor = BatchExecutor(
                    controller=self._mfc_controller,
                    state_machine=slot_machine,
                )

                # Progress callback: WebSocket으로 진행 상황 전송
                async def on_batch_progress(progress: BatchProgress) -> None:
                    if self._ws_client:
                        await self._ws_client.send_state_update(
                            slot_idx=progress.slot_idx,
                            state_data={
                                "status": "running",
                                "current_batch": progress.current_batch,
                                "total_batch": progress.total_batch,
                                "current_loop": progress.current_loop,
                                "total_loop": progress.total_loop,
                                "loop_step": progress.loop_step,
                                "progress_percent": progress.progress_percent,
                            },
                        )

                # Batch 실행 (백그라운드 태스크로)
                asyncio.create_task(
                    self._run_batch_test(
                        slot_idx=slot_idx,
                        config=config,
                        batch_executor=batch_executor,
                        on_progress=on_batch_progress,
                    )
                )
            else:
                # 단일 실행 모드: 기존 방식
                success = await self._mfc_controller.start_test(slot_idx, config)

                if success:
                    # State transition: RUN
                    slot_machine.trigger(
                        SlotEvent.RUN,
                        context_update={
                            "total_loop": config.loop_count,
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

    async def _run_batch_test(
        self,
        slot_idx: int,
        config: "TestConfig",  # noqa: F821
        batch_executor: BatchExecutor,
        on_progress: "Callable[[BatchProgress], Awaitable[None]]",  # noqa: F821
    ) -> None:
        """Run batch test in background.

        Executes batch test with multiple iterations.

        Args:
            slot_idx: Slot index.
            config: Test configuration.
            batch_executor: Batch executor instance.
            on_progress: Progress callback.
        """
        try:
            success = await batch_executor.execute(
                slot_idx=slot_idx,
                config=config,
                on_progress=on_progress,
            )

            if success:
                logger.info(
                    "Batch test completed successfully",
                    slot_idx=slot_idx,
                    total_loop=config.loop_count,
                )
                if self._ws_client:
                    await self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={
                            "status": "completed",
                            "message": "All batches completed",
                        },
                    )
            else:
                logger.warning(
                    "Batch test failed or cancelled",
                    slot_idx=slot_idx,
                )
                if self._ws_client:
                    await self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={
                            "status": "failed",
                            "message": "Batch test failed or cancelled",
                        },
                    )
        except Exception as e:
            logger.error(
                "Batch test error",
                slot_idx=slot_idx,
                error=str(e),
            )
            if self._slot_manager:
                try:
                    slot_machine = self._slot_manager[slot_idx]
                    slot_machine.trigger(SlotEvent.ERROR, error_message=str(e))
                except (KeyError, InvalidTransitionError):
                    pass

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
                # State transition: STOPPED (if still in STOPPING state)
                if slot_machine.can_transition(SlotEvent.STOPPED):
                    slot_machine.trigger(SlotEvent.STOPPED)

                # Backend에 stopped 상태 전송
                if self._ws_client:
                    await self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={
                            "status": "stopped",
                            "message": "Test stopped by user",
                        },
                    )
            else:
                if slot_machine.can_transition(SlotEvent.ERROR):
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
            if slot_machine.can_transition(SlotEvent.ERROR):
                slot_machine.trigger(SlotEvent.ERROR, error_message=str(e))
            else:
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

        # 프로세스 모니터 중지
        if self._process_monitor:
            await self._process_monitor.stop()
            self._process_monitor = None

        # MFC UI 모니터 중지
        if self._mfc_ui_monitor:
            await self._mfc_ui_monitor.stop()
            self._mfc_ui_monitor = None

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
