"""Agent Unit Tests.

메인 Agent 클래스에 대한 단위 테스트입니다.
DI Container가 올바르게 주입되는지 검증합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.main import Agent, setup_container
from src.core.container import Container
from src.core.protocols import IWindowFinder, IStateStore, IClock


class TestSetupContainer:
    """setup_container 함수 테스트."""

    def test_setup_container_registers_dependencies(self) -> None:
        """컨테이너에 필요한 의존성이 등록되는지 검증."""
        container = setup_container()

        # Infrastructure 인스턴스가 resolve 가능한지 확인
        clock = container.resolve(IClock)
        state_store = container.resolve(IStateStore)
        window_finder = container.resolve(IWindowFinder)

        assert clock is not None
        assert state_store is not None
        assert window_finder is not None

    def test_setup_container_singletons(self) -> None:
        """싱글톤으로 등록된 의존성이 동일 인스턴스인지 검증."""
        container = setup_container()

        clock1 = container.resolve(IClock)
        clock2 = container.resolve(IClock)

        assert clock1 is clock2


class TestAgent:
    """Agent 클래스 테스트."""

    def test_agent_accepts_custom_container(
        self,
        test_container: Container,
    ) -> None:
        """커스텀 컨테이너가 주입되는지 검증."""
        agent = Agent(container=test_container)

        assert agent.container is test_container

    def test_agent_initial_state(
        self,
        test_container: Container,
    ) -> None:
        """Agent 초기 상태 검증."""
        agent = Agent(container=test_container)

        assert agent.is_running is False
        assert agent.ws_client is None
        assert agent.test_executor is None
        assert agent.state_monitor is None

    @pytest.mark.asyncio
    async def test_agent_start_initializes_services(
        self,
        test_container: Container,
    ) -> None:
        """Agent start 시 서비스가 초기화되는지 검증."""
        agent = Agent(container=test_container)

        # WebSocket 클라이언트 mock
        with patch("src.main.WebSocketClient") as mock_ws_class:
            mock_ws_instance = MagicMock()
            mock_ws_instance.run = AsyncMock()
            mock_ws_instance.disconnect = AsyncMock()
            mock_ws_class.return_value = mock_ws_instance

            # Agent를 짧은 시간 후 중지
            async def stop_after_init():
                await agent.stop()

            import asyncio
            asyncio.get_event_loop().call_later(0.1, lambda: asyncio.create_task(stop_after_init()))

            # Agent 시작 (짧은 시간 후 자동 중지)
            try:
                await asyncio.wait_for(agent.start(), timeout=1.0)
            except asyncio.TimeoutError:
                await agent.stop()

            # 서비스가 초기화되었는지 확인
            # (cleanup에서 None으로 설정되므로, start 중에 설정되었는지는 로직으로 확인)
            mock_ws_class.assert_called_once()

    def test_agent_uses_default_container_if_not_provided(self) -> None:
        """컨테이너가 제공되지 않으면 기본 컨테이너가 사용되는지 검증."""
        # Agent 생성 시 setup_container가 호출됨
        with patch("src.main.setup_container") as mock_setup:
            mock_container = MagicMock(spec=Container)
            mock_setup.return_value = mock_container

            # 컨테이너 없이 Agent 생성
            agent = Agent(container=None)

            # setup_container가 호출되었는지 확인
            mock_setup.assert_called_once()
            assert agent._container is mock_container


class TestAgentMessageHandlers:
    """Agent 메시지 핸들러 테스트."""

    @pytest.fixture
    def agent_with_mocks(
        self,
        test_container: Container,
    ) -> Agent:
        """Mock이 설정된 Agent fixture."""
        agent = Agent(container=test_container)
        return agent

    @pytest.mark.asyncio
    async def test_handle_start_test_without_executor(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        """TestExecutor 없이 start_test 핸들러 호출 시 동작 검증."""
        # TestExecutor가 없는 상태
        agent_with_mocks._test_executor = None

        # 핸들러 호출 (예외 없이 완료되어야 함)
        await agent_with_mocks._handle_start_test({"slot_idx": 0, "config": {}})

    @pytest.mark.asyncio
    async def test_handle_stop_test_without_executor(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        """TestExecutor 없이 stop_test 핸들러 호출 시 동작 검증."""
        agent_with_mocks._test_executor = None

        # 핸들러 호출 (예외 없이 완료되어야 함)
        await agent_with_mocks._handle_stop_test({"slot_idx": 0})

    @pytest.mark.asyncio
    async def test_handle_config_update(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        """Config 업데이트 핸들러 테스트."""
        # 핸들러 호출 (현재는 로그만 출력)
        await agent_with_mocks._handle_config_update({"key": "value"})
