"""Agent Entry Point.

Main entry point for SS USB Test Agent.
All dependencies are injected via DI Container.
"""

import asyncio
import signal
from typing import Optional

from .config.settings import get_settings
from .config.constants import BackendMessageType
from .interface.websocket.client import WebSocketClient
from .utils.logging import setup_logging, get_logger, bind_context

# Core - DI Container & Protocols
from .core import (
    Container,
    get_container,
    IWindowFinder,
    IStateStore,
    IClock,
)

# Infrastructure - 실제 구현체
from .infrastructure import (
    SystemClock,
    PywinautoWindowFinder,
    InMemoryStateStore,
)

# Services - 비즈니스 로직
from .services import TestExecutor, StateMonitor

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

    async def start(self) -> None:
        """Start Agent.

        Injects services from DI Container and sets up WebSocket connection.
        """
        self._shutdown_event = asyncio.Event()
        self.is_running = True

        logger.info(
            "Agent starting",
            name=self.settings.name,
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

        # 서비스 인스턴스 생성 (의존성 주입)
        self._test_executor = TestExecutor(
            window_finder=window_finder,
            state_store=state_store,
            clock=clock,
        )

        logger.info("Services initialized with DI")

        # WebSocket 클라이언트 생성
        self._ws_client = WebSocketClient(
            settings=self.settings,
            on_message=self._on_message,
        )

        # 메시지 핸들러 등록
        self._register_handlers()

        try:
            # 메인 루프 실행
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("Agent cancelled")
        finally:
            await self._cleanup()

    def _register_handlers(self) -> None:
        """Register Backend message handlers."""
        if not self._ws_client:
            return

        # 테스트 시작 명령
        self._ws_client.register_handler(
            BackendMessageType.START_TEST,
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

        # TestExecutor를 통해 테스트 시작
        if self._test_executor and slot_idx is not None:
            try:
                await self._test_executor.start_test(slot_idx, test_config)

                # 상태 업데이트 전송
                if self._ws_client:
                    await self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={"status": "running"},
                    )
            except Exception as e:
                logger.error("Failed to start test", slot_idx=slot_idx, error=str(e))
                if self._ws_client:
                    await self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={"status": "error", "error": str(e)},
                    )
        else:
            logger.warning("Test executor not available or invalid slot")

    async def _handle_stop_test(self, data: dict) -> None:
        """Handle stop test command.

        Args:
            data: Stop request data.
        """
        slot_idx = data.get("slot_idx")

        logger.info("Stop test command received", slot_idx=slot_idx)

        # TestExecutor를 통해 테스트 중지
        if self._test_executor and slot_idx is not None:
            try:
                await self._test_executor.stop_test(slot_idx)

                if self._ws_client:
                    await self._ws_client.send_state_update(
                        slot_idx=slot_idx,
                        state_data={"status": "stopped"},
                    )
            except Exception as e:
                logger.error("Failed to stop test", slot_idx=slot_idx, error=str(e))

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

        # StateMonitor 중지
        if self._state_monitor:
            self._state_monitor.stop()
            self._state_monitor = None

        # TestExecutor 정리
        self._test_executor = None

        # WebSocket 연결 종료
        if self._ws_client:
            await self._ws_client.disconnect()
            self._ws_client = None

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
