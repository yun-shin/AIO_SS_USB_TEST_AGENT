"""Agent Unit Tests."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from main import Agent, setup_container
from core.container import Container
from core.protocols import IWindowFinder, IStateStore, IClock


class TestSetupContainer:
    """setup_container 테스트 클래스"""

    def test_setup_container_registers_dependencies(self) -> None:
        """[TC-AGENT-001] DI 등록 - 필수 의존성이 컨테이너에 등록된다.

        테스트 목적:
            setup_container 실행 시 시계/상태저장소/윈도우파인더가 resolve 가능한지 확인한다.

        테스트 시나리오:
            Given: setup_container를 호출해 컨테이너를 만들고
            When: IClock/IStateStore/IWindowFinder를 resolve 하면
            Then: 세 의존성이 모두 None이 아닌 인스턴스로 반환된다

        Notes:
            None
        """
        container = setup_container()

        clock = container.resolve(IClock)
        state_store = container.resolve(IStateStore)
        window_finder = container.resolve(IWindowFinder)

        assert clock is not None
        assert state_store is not None
        assert window_finder is not None

    def test_setup_container_singletons(self) -> None:
        """[TC-AGENT-002] 싱글톤 보장 - 등록된 인스턴스가 동일하게 반환된다.

        테스트 목적:
            컨테이너에 싱글톤으로 등록된 의존성이 반복 resolve에도 동일 객체인지 검증한다.

        테스트 시나리오:
            Given: setup_container로 컨테이너를 생성하고
            When: 같은 IClock을 두 번 resolve 하면
            Then: 반환된 두 객체가 동일한 인스턴스다

        Notes:
            None
        """
        container = setup_container()

        clock1 = container.resolve(IClock)
        clock2 = container.resolve(IClock)

        assert clock1 is clock2


class TestAgent:
    """Agent 클래스 테스트"""

    def test_agent_accepts_custom_container(
        self,
        test_container: Container,
    ) -> None:
        """[TC-AGENT-003] 사용자 컨테이너 주입 - 전달된 컨테이너를 사용한다.

        테스트 목적:
            Agent 생성 시 외부에서 전달한 컨테이너가 내부에 그대로 설정되는지 확인한다.

        테스트 시나리오:
            Given: 미리 구성된 test_container가 있고
            When: Agent(container=test_container)로 생성하면
            Then: agent.container가 전달한 컨테이너 객체와 동일하다

        Notes:
            None
        """
        agent = Agent(container=test_container)

        assert agent.container is test_container

    def test_agent_initial_state(
        self,
        test_container: Container,
    ) -> None:
        """[TC-AGENT-004] 초기 상태 - 기본 필드가 None/False로 설정된다.

        테스트 목적:
            Agent 초기 생성 시 실행 플래그와 서비스 객체가 비활성/None인지 확인한다.

        테스트 시나리오:
            Given: 컨테이너를 전달해 Agent를 생성하고
            When: is_running/ws_client/test_executor/state_monitor를 조회하면
            Then: is_running은 False이며 나머지는 None이다

        Notes:
            None
        """
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
        """[TC-AGENT-005] 서비스 초기화 - start 호출 시 WS 클라이언트를 준비한다.

        테스트 목적:
            Agent.start 실행 시 WebSocketClient가 생성되고 실행 루프를 시작하는지 검증한다.

        테스트 시나리오:
            Given: 컨테이너가 주입된 Agent와 WebSocketClient를 Mock 패치하고
            When: agent.start를 호출 후 타임아웃 전에 stop을 예약하면
            Then: WebSocketClient가 한 번 생성 호출된다

        Notes:
            None
        """
        agent = Agent(container=test_container)

        with patch("main.WebSocketClient") as mock_ws_class:
            mock_ws_instance = MagicMock()
            mock_ws_instance.run = AsyncMock()
            mock_ws_instance.disconnect = AsyncMock()
            mock_ws_class.return_value = mock_ws_instance

            async def stop_after_init():
                await agent.stop()

            asyncio.get_event_loop().call_later(
                0.1, lambda: asyncio.create_task(stop_after_init())
            )

            try:
                await asyncio.wait_for(agent.start(), timeout=1.0)
            except asyncio.TimeoutError:
                await agent.stop()

            mock_ws_class.assert_called_once()

    def test_agent_uses_default_container_if_not_provided(self) -> None:
        """[TC-AGENT-006] 기본 컨테이너 사용 - 인자가 없으면 setup_container를 호출한다.

        테스트 목적:
            컨테이너를 주지 않았을 때 setup_container가 호출되어 내부 컨테이너가 설정되는지 검증한다.

        테스트 시나리오:
            Given: setup_container를 Mock 패치한 상태에서
            When: Agent(container=None)로 생성하면
            Then: setup_container가 한 번 호출되고 agent._container가 반환값으로 설정된다

        Notes:
            None
        """
        with patch("main.setup_container") as mock_setup:
            mock_container = MagicMock(spec=Container)
            mock_setup.return_value = mock_container

            agent = Agent(container=None)

            mock_setup.assert_called_once()
            assert agent._container is mock_container


class TestAgentMessageHandlers:
    """Agent 메시지 핸들러 테스트"""

    @pytest.fixture
    def agent_with_mocks(
        self,
        test_container: Container,
    ) -> Agent:
        """Mock 의존성을 가진 Agent fixture."""
        agent = Agent(container=test_container)
        return agent

    @pytest.mark.asyncio
    async def test_handle_start_test_without_executor(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        """[TC-AGENT-007] 실행기 미존재 시 안전 처리 - 예외 없이 반환한다.

        테스트 목적:
            _test_executor가 None일 때 start 요청을 받아도 예외 없이 종료되는지 확인한다.

        테스트 시나리오:
            Given: _test_executor가 None인 Agent가 있고
            When: _handle_start_test를 호출하면
            Then: 예외 없이 반환한다

        Notes:
            None
        """
        agent_with_mocks._test_executor = None

        await agent_with_mocks._handle_start_test({"slot_idx": 0, "config": {}})

    @pytest.mark.asyncio
    async def test_handle_stop_test_without_executor(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        """[TC-AGENT-008] 실행기 미존재 중지 - 예외 없이 반환한다.

        테스트 목적:
            _test_executor가 None인 상황에서 stop 요청을 받아도 예외 없이 처리되는지 검증한다.

        테스트 시나리오:
            Given: _test_executor가 None인 Agent가 있고
            When: _handle_stop_test를 호출하면
            Then: 예외 없이 반환한다

        Notes:
            None
        """
        agent_with_mocks._test_executor = None

        await agent_with_mocks._handle_stop_test({"slot_idx": 0})

    @pytest.mark.asyncio
    async def test_handle_config_update(
        self,
        agent_with_mocks: Agent,
    ) -> None:
        """[TC-AGENT-009] 설정 업데이트 - 메시지가 오류 없이 처리된다.

        테스트 목적:
            _handle_config_update 호출 시 예외 없이 로깅 처리만 수행되는지 확인한다.

        테스트 시나리오:
            Given: 임의의 설정 딕셔너리를 준비하고
            When: _handle_config_update를 호출하면
            Then: 예외 없이 완료된다

        Notes:
            None
        """
        await agent_with_mocks._handle_config_update({"key": "value"})
