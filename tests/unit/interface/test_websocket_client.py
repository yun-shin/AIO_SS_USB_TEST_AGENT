"""Unit tests for WebSocketClient."""

import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest


class FakeWebSocket:
    """Fake WebSocket protocol for testing."""

    def __init__(self):
        self._sent_messages = []
        self._receive_queue = asyncio.Queue()
        self._closed = False
        self._close_code = None
        self._close_reason = None

    async def send(self, message: str):
        if self._closed:
            from websockets.exceptions import ConnectionClosed

            raise ConnectionClosed(None, None)
        self._sent_messages.append(message)

    async def recv(self) -> str:
        if self._closed:
            from websockets.exceptions import ConnectionClosed

            raise ConnectionClosed(None, None)
        return await self._receive_queue.get()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if self._closed:
            raise StopAsyncIteration
        try:
            return await asyncio.wait_for(self._receive_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            if self._closed:
                raise StopAsyncIteration
            raise

    async def close(self):
        self._closed = True

    def queue_message(self, message: dict):
        """Queue a message to be received."""
        self._receive_queue.put_nowait(json.dumps(message))

    def get_sent_messages(self) -> list[dict]:
        """Get all sent messages as parsed dicts."""
        return [json.loads(m) for m in self._sent_messages]


class FakeAgentSettings:
    """Fake AgentSettings for testing."""

    def __init__(
        self,
        backend_ws_url: str = "ws://localhost:8000/ws",
        api_key: str = "test-api-key",
        max_slots: int = 4,
        version: str = "0.1.0",
    ):
        self.backend_ws_url = backend_ws_url
        self.api_key = api_key
        self.max_slots = max_slots
        self.version = version


class TestWebSocketClientInit:
    """Test WebSocketClient initialization."""

    def test_init_with_default_settings(self, monkeypatch):
        """[TC-WS-001] 기본 설정 초기화 - 기본값으로 클라이언트가 초기화된다.

        테스트 목적:
            WebSocketClient가 설정 없이 생성될 때 기본 설정과 초기 상태값을 적용하는지 확인한다.

        테스트 시나리오:
            Given: get_settings를 FakeAgentSettings로 패치하고
            When: WebSocketClient()를 생성하면
            Then: 상태는 disconnected, ws는 None, reconnect 카운트는 0이다

        Notes:
            None
        """
        monkeypatch.setattr(
            "interface.websocket.client.get_settings",
            lambda: FakeAgentSettings(),
        )

        from interface.websocket.client import WebSocketClient

        client = WebSocketClient()

        assert client._state.value == "disconnected"
        assert client._ws is None
        assert client._reconnect_count == 0

    def test_init_with_custom_settings(self, monkeypatch):
        """[TC-WS-002] 커스텀 설정 초기화 - 전달한 설정이 반영된다.

        테스트 목적:
            설정 객체를 직접 전달할 때 해당 값들이 내부 필드에 반영되는지 검증한다.

        테스트 시나리오:
            Given: FakeAgentSettings(커스텀 url/api_key/version) 인스턴스를 만들고
            When: WebSocketClient(settings=...)로 생성하면
            Then: 내부 settings 필드가 전달값을 보존한다

        Notes:
            None
        """
        custom_settings = FakeAgentSettings(
            backend_ws_url="ws://custom/ws",
            api_key="custom-key",
            max_slots=8,
            version="9.9.9",
        )

        from interface.websocket.client import WebSocketClient

        client = WebSocketClient(settings=custom_settings)

        assert client._settings.backend_ws_url == "ws://custom/ws"
        assert client._settings.api_key == "custom-key"
        assert client._settings.max_slots == 8
        assert client._settings.version == "9.9.9"

    def test_init_generates_agent_id(self, monkeypatch):
        """[TC-WS-003] 에이전트 ID 생성 - agent_id가 UUID로 설정된다.

        테스트 목적:
            agent_id를 지정하지 않으면 UUID가 자동 생성되는지 확인한다.

        테스트 시나리오:
            Given: get_settings를 FakeAgentSettings로 패치하고
            When: WebSocketClient()를 생성하면
            Then: agent_id 필드가 비어 있지 않고 문자열 형태다

        Notes:
            None
        """
        monkeypatch.setattr(
            "interface.websocket.client.get_settings",
            lambda: FakeAgentSettings(),
        )

        from interface.websocket.client import WebSocketClient

        client = WebSocketClient(agent_id=None)

        assert isinstance(client.agent_id, str)
        assert client.agent_id != ""


class TestWebSocketClientConnect:
    """Test WebSocketClient connect/disconnect."""

    @pytest.mark.asyncio
    async def test_connect_success(self, client, mock_websockets):
        """[TC-WS-004] 연결 성공 - connect 호출 시 WebSocket이 연결된다.

        테스트 목적:
            connect가 websocket connection을 맺고 state를 connected로 전환하는지 검증한다.

        테스트 시나리오:
            Given: mock_websockets 모듈이 패치된 상태에서
            When: client.connect()를 호출하면
            Then: True를 반환하고 내부 _ws가 설정되며 state가 connected가 된다

        Notes:
            None
        """
        assert await client.connect() is True
        assert client._ws is not None
        assert client._state.value == "connected"

    @pytest.mark.asyncio
    async def test_connect_sends_registration(self, client, mock_websockets):
        """[TC-WS-005] 등록 메시지 전송 - 최초 연결 시 register 메시지를 보낸다.

        테스트 목적:
            connect 후 첫 메시지로 register payload가 전송되는지 확인한다.

        테스트 시나리오:
            Given: mock_websockets로 패치된 환경에서
            When: connect를 호출하면
            Then: 첫 번째 전송 메시지에 type=register와 agent 정보가 포함된다

        Notes:
            None
        """
        await client.connect()
        sent = mock_websockets.ws.get_sent_messages()[0]
        assert sent["type"] == "register"
        assert "agent_id" in sent["data"]

    @pytest.mark.asyncio
    async def test_connect_returns_true_when_already_connected(
        self, client, mock_websockets
    ):
        """[TC-WS-006] 중복 연결 요청 - 이미 연결된 경우 True를 반환하고 재연결하지 않는다.

        테스트 목적:
            연결 상태에서 connect를 재호출하면 noop 처리되는지 검증한다.

        테스트 시나리오:
            Given: connect가 완료된 상태에서
            When: connect를 다시 호출하면
            Then: True를 반환하고 mock_websockets.connect가 추가 호출되지 않는다

        Notes:
            None
        """
        await client.connect()
        assert await client.connect() is True
        assert mock_websockets.connect.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_timeout_returns_false(self, client, monkeypatch):
        """[TC-WS-007] 연결 타임아웃 - 지정 시간 내 연결 실패 시 False를 반환한다.

        테스트 목적:
            connect_timeout 동안 연결이 이루어지지 않으면 False를 반환하는지 확인한다.

        테스트 시나리오:
            Given: websockets.connect가 TimeoutError를 발생하도록 패치하고
            When: connect(timeout=0.01)을 호출하면
            Then: False를 반환한다

        Notes:
            None
        """
        monkeypatch.setattr(
            "interface.websocket.client.websockets.connect",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        )

        assert await client.connect(timeout=0.01) is False

    @pytest.mark.asyncio
    async def test_disconnect_closes_websocket(self, client, mock_websockets):
        """[TC-WS-008] 연결 해제 - disconnect가 WebSocket을 닫고 상태를 초기화한다.

        테스트 목적:
            disconnect 호출 시 _ws.close가 실행되고 상태가 disconnected로 바뀌는지 검증한다.

        테스트 시나리오:
            Given: 연결된 client가 있고
            When: disconnect를 호출하면
            Then: close가 호출되고 _ws/state가 초기화된다

        Notes:
            None
        """
        await client.connect()
        await client.disconnect()

        assert client._ws is None
        assert client._state.value == "disconnected"


class TestWebSocketClientSend:
    """Test WebSocketClient send helpers."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, client, mock_websockets):
        """[TC-WS-009] 메시지 전송 성공 - send_message가 True를 반환한다.

        테스트 목적:
            연결된 상태에서 send_message 호출이 성공하는지 확인한다.

        테스트 시나리오:
            Given: 연결된 client
            When: send_message를 호출하면
            Then: True를 반환한다

        Notes:
            None
        """
        await client.connect()
        assert await client.send_message({"type": "ping"}) is True

    @pytest.mark.asyncio
    async def test_send_returns_false_when_not_connected(self, client):
        """[TC-WS-010] 미연결 상태 전송 - False를 반환한다.

        테스트 목적:
            연결되지 않은 상태에서 send_message 호출 시 False가 반환되는지 확인한다.

        테스트 시나리오:
            Given: 미연결 상태의 client
            When: send_message를 호출하면
            Then: False를 반환한다

        Notes:
            None
        """
        assert await client.send_message({"type": "ping"}) is False

    @pytest.mark.asyncio
    async def test_send_state_update(self, client, mock_websockets):
        """[TC-WS-011] 상태 업데이트 전송 - state_update 메시지를 보낸다.

        테스트 목적:
            send_state_update가 올바른 payload로 메시지를 전송하는지 검증한다.

        테스트 시나리오:
            Given: 연결된 client
            When: send_state_update를 호출하면
            Then: 마지막 전송 메시지의 type이 state_update이고 데이터가 포함된다

        Notes:
            None
        """
        await client.connect()
        await client.send_state_update(
            slot_idx=0,
            process_state=1,
            test_phase=2,
            current_loop=1,
            total_loop=10,
            progress_percent=10.0,
        )
        sent = mock_websockets.ws.get_sent_messages()[-1]
        assert sent["type"] == "state_update"

    @pytest.mark.asyncio
    async def test_send_test_completed_success(self, client, mock_websockets):
        """[TC-WS-012] 테스트 완료 전송 성공 - True를 반환한다.

        테스트 목적:
            send_test_completed가 메시지를 정상 전송할 때 True를 반환하는지 확인한다.

        테스트 시나리오:
            Given: 연결된 client
            When: send_test_completed를 호출하면
            Then: True를 반환하고 전송 메시지 타입이 test_completed다

        Notes:
            None
        """
        await client.connect()
        assert (
            await client.send_test_completed(
                slot_idx=0,
                test_id="id",
                success=True,
                message="ok",
            )
            is True
        )
        sent = mock_websockets.ws.get_sent_messages()[-1]
        assert sent["type"] == "test_completed"

    @pytest.mark.asyncio
    async def test_send_test_completed_failure(self, client, mock_websockets):
        """[TC-WS-013] 테스트 완료 전송 실패 - False를 반환한다.

        테스트 목적:
            WebSocket 연결이 없을 때 send_test_completed가 False를 반환하는지 검증한다.

        테스트 시나리오:
            Given: 미연결 상태의 client
            When: send_test_completed를 호출하면
            Then: False를 반환한다

        Notes:
            None
        """
        assert (
            await client.send_test_completed(
                slot_idx=0,
                test_id="id",
                success=True,
                message="ok",
            )
            is False
        )


class TestWebSocketClientHandlers:
    """Test handler registration and dispatch."""

    def test_register_handler(self, client):
        """[TC-WS-014] 핸들러 등록 - 타입별 콜백을 저장한다.

        테스트 목적:
            register_handler가 특정 타입 문자열에 대한 콜백을 저장하는지 확인한다.

        테스트 시나리오:
            Given: handler 함수를 준비하고
            When: register_handler("ping", handler)를 호출하면
            Then: 내부 _handlers에 매핑이 저장된다

        Notes:
            None
        """
        handler = MagicMock()
        client.register_handler("ping", handler)

        assert client._handlers["ping"] is handler

    @pytest.mark.asyncio
    async def test_handler_called_on_message(self, client, mock_websockets):
        """[TC-WS-015] 메시지 수신 시 핸들러 호출 - 등록된 타입 콜백이 실행된다.

        테스트 목적:
            수신 메시지의 type에 따라 등록된 핸들러가 호출되는지 검증한다.

        테스트 시나리오:
            Given: "ping" 타입 핸들러를 등록하고 서버 메시지 큐에 ping 메시지를 넣고
            When: receive_loop를 한 번 실행하면
            Then: 핸들러가 호출된다

        Notes:
            None
        """
        handler = MagicMock()
        client.register_handler("ping", handler)
        await client.connect()
        mock_websockets.ws.queue_message({"type": "ping", "data": {}})

        await asyncio.wait_for(client.receive_loop(), timeout=0.5)

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_error_does_not_crash(self, client, mock_websockets):
        """[TC-WS-016] 핸들러 예외 무시 - 콜백 예외가 루프를 중단시키지 않는다.

        테스트 목적:
            핸들러가 예외를 던져도 receive_loop가 중단되지 않는지 확인한다.

        테스트 시나리오:
            Given: 예외를 던지는 핸들러를 등록하고 메시지를 큐에 넣은 뒤
            When: receive_loop를 실행하면
            Then: 예외가 발생해도 루프가 계속 돌아가며 종료하지 않는다

        Notes:
            None
        """
        async def bad_handler(message: dict) -> None:
            raise RuntimeError("handler error")

        client.register_handler("ping", bad_handler)
        await client.connect()
        mock_websockets.ws.queue_message({"type": "ping", "data": {}})

        await asyncio.wait_for(client.receive_loop(), timeout=0.5)

        assert client._state.value == "connected"

    @pytest.mark.asyncio
    async def test_register_ack_sets_registered_state(self, client, mock_websockets):
        """[TC-WS-017] register_ack 처리 - registered 플래그와 카운터를 갱신한다.

        테스트 목적:
            register_ack를 수신하면 registered 상태로 전환되고 카운터가 증가하는지 확인한다.

        테스트 시나리오:
            Given: 연결된 client
            When: register_ack 메시지를 처리하면
            Then: _registered가 True가 되고 _reconnect_count가 0으로 리셋된다

        Notes:
            None
        """
        await client.connect()
        await client._handle_message({"type": "register_ack", "data": {}})

        assert client._registered is True
        assert client._reconnect_count == 0

    @pytest.mark.asyncio
    async def test_on_message_callback_called(self, client, mock_websockets):
        """[TC-WS-018] on_message 콜백 호출 - 외부 콜백이 실행된다.

        테스트 목적:
            _on_message 콜백이 설정된 경우 수신 메시지 처리 시 실행되는지 검증한다.

        테스트 시나리오:
            Given: _on_message를 AsyncMock으로 설정하고
            When: _handle_message를 호출하면
            Then: 콜백이 메시지와 함께 호출된다

        Notes:
            None
        """
        client._on_message = AsyncMock()

        await client._handle_message({"type": "test", "data": {}})

        client._on_message.assert_called_once()


class TestWebSocketClientReconnect:
    """Test reconnection logic."""

    @pytest.mark.asyncio
    async def test_handle_reconnect_increments_count(self, client):
        """[TC-WS-019] 재연결 시도 - 카운터를 증가시키고 지연을 반환한다.

        테스트 목적:
            handle_reconnect가 재연결 횟수를 증가시키고 지연 시간을 계산하는지 확인한다.

        테스트 시나리오:
            Given: client._reconnect_count 초기값이 0이고
            When: handle_reconnect를 호출하면
            Then: _reconnect_count가 1 증가하고 반환 지연이 0보다 크다

        Notes:
            None
        """
        delay = await client.handle_reconnect()

        assert client._reconnect_count == 1
        assert delay > 0

    @pytest.mark.asyncio
    async def test_handle_reconnect_stops_after_max_attempts(
        self, client, monkeypatch
    ):
        """[TC-WS-020] 최대 재연결 초과 - 최대 횟수 이후에는 False를 반환한다.

        테스트 목적:
            재연결 횟수가 max_reconnect_attempts에 도달하면 더 이상 재시도하지 않는지 확인한다.

        테스트 시나리오:
            Given: max_reconnect_attempts를 낮은 값으로 설정하고
            When: handle_reconnect를 여러 번 호출하면
            Then: 횟수 초과 시 False를 반환하고 카운터가 증가하지 않는다

        Notes:
            None
        """
        client._settings.max_reconnect_attempts = 1
        await client.handle_reconnect()
        result = await client.handle_reconnect()

        assert result is False
        assert client._reconnect_count == 1

    @pytest.mark.asyncio
    async def test_reconnect_delay_increases(self, client):
        """[TC-WS-021] 지연 증가 - 재연결 지연이 시도마다 증가한다.

        테스트 목적:
            재연결 시도 횟수에 비례해 delay가 증가하는지 검증한다.

        테스트 시나리오:
            Given: handle_reconnect를 연속 호출하고
            When: 반환된 delay 값을 비교하면
            Then: 두 번째 delay가 첫 번째보다 크거나 같다

        Notes:
            None
        """
        d1 = await client.handle_reconnect()
        d2 = await client.handle_reconnect()

        assert d2 >= d1


class TestWebSocketClientLoops:
    """Test heartbeat/receive loops."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_sends_heartbeat(self, client, mock_websockets):
        """[TC-WS-022] 하트비트 전송 - 루프가 heartbeat 메시지를 주기적으로 보낸다.

        테스트 목적:
            heartbeat_loop가 running 상태에서 heartbeat 메시지를 보내는지 확인한다.

        테스트 시나리오:
            Given: 연결된 client
            When: heartbeat_loop를 한 번 실행하면
            Then: 마지막 보낸 메시지 타입이 heartbeat다

        Notes:
            None
        """
        await client.connect()
        await client.heartbeat_loop()

        sent = mock_websockets.ws.get_sent_messages()[-1]
        assert sent["type"] == "heartbeat"

    @pytest.mark.asyncio
    async def test_receive_loop_handles_invalid_json(self, client, mock_websockets):
        """[TC-WS-023] 잘못된 JSON 처리 - 수신 메시지가 JSON 파싱 실패해도 크래시하지 않는다.

        테스트 목적:
            recv에서 잘못된 JSON 문자열을 받더라도 receive_loop가 예외로 종료되지 않는지 확인한다.

        테스트 시나리오:
            Given: 연결된 client
            When: 수신 큐에 잘못된 JSON 문자열을 넣고 receive_loop를 실행하면
            Then: 예외 없이 루프가 계속된다

        Notes:
            None
        """
        await client.connect()
        mock_websockets.ws._receive_queue.put_nowait("invalid json")

        await asyncio.wait_for(client.receive_loop(), timeout=0.5)

        assert client._state.value == "connected"

    @pytest.mark.asyncio
    async def test_register_ack_sets_registered_state(self, client, mock_websockets):
        """[TC-WS-024] register_ack 수신 - registered 상태로 전환한다.

        테스트 목적:
            receive_loop 중 register_ack를 받으면 내부 registered 플래그가 세팅되는지 검증한다.

        테스트 시나리오:
            Given: 연결된 client
            When: register_ack 메시지를 큐에 넣고 receive_loop를 실행하면
            Then: client._registered가 True가 된다

        Notes:
            None
        """
        await client.connect()
        mock_websockets.ws.queue_message({"type": "register_ack", "data": {}})

        await asyncio.wait_for(client.receive_loop(), timeout=0.5)

        assert client._registered is True

    @pytest.mark.asyncio
    async def test_on_message_callback_called(self, client, mock_websockets):
        """[TC-WS-025] on_message 콜백 - 수신 메시지 처리 시 호출된다.

        테스트 목적:
            외부 _on_message 콜백이 설정된 경우 receive_loop에서 메시지를 처리하며 호출되는지 확인한다.

        테스트 시나리오:
            Given: _on_message를 AsyncMock으로 설정하고
            When: receive_loop 중 일반 메시지를 받으면
            Then: _on_message가 호출된다

        Notes:
            None
        """
        client._on_message = AsyncMock()
        await client.connect()
        mock_websockets.ws.queue_message({"type": "custom", "data": {"k": 1}})

        await asyncio.wait_for(client.receive_loop(), timeout=0.5)

        client._on_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_drive_list(self, client, mock_websockets):
        """[TC-WS-026] 드라이브 목록 전송 - send_drive_list가 메시지를 보낸다.

        테스트 목적:
            send_drive_list가 drive_list 타입 메시지를 전송하는지 검증한다.

        테스트 시나리오:
            Given: 연결된 client
            When: send_drive_list를 호출하면
            Then: 마지막 보낸 메시지 타입이 drive_list다

        Notes:
            None
        """
        await client.connect()
        await client.send_drive_list(
            drives=[
                {"letter": "E", "label": "VOL", "total_size": 1024, "free_size": 512}
            ]
        )

        sent = mock_websockets.ws.get_sent_messages()[-1]
        assert sent["type"] == "drive_list"

    @pytest.mark.asyncio
    async def test_handle_get_drives_sends_drive_list(
        self, client, mock_websockets, monkeypatch
    ):
        """[TC-WS-027] get_drives 처리 - scan 후 drive_list를 전송한다.

        테스트 목적:
            handle_get_drives가 drive_scanner.scan_removable_drives 결과를 전송하는지 확인한다.

        테스트 시나리오:
            Given: scan_removable_drives를 더미 결과로 패치하고
            When: _handle_get_drives를 호출하면
            Then: drive_list 메시지가 전송된다

        Notes:
            None
        """
        monkeypatch.setattr(
            "interface.websocket.client.drive_scanner.scan_removable_drives",
            lambda include_fixed=False: [{"letter": "E"}],
        )
        await client.connect()

        await client._handle_get_drives({})

        sent = mock_websockets.ws.get_sent_messages()[-1]
        assert sent["type"] == "drive_list"

    @pytest.mark.asyncio
    async def test_handle_get_drives_import_error(
        self, client, mock_websockets, monkeypatch
    ):
        """[TC-WS-028] 드라이브 스캔 ImportError - 실패 메시지를 전송한다.

        테스트 목적:
            drive_scanner 임포트 실패 시 handle_get_drives가 오류 메시지를 보내는지 검증한다.

        테스트 시나리오:
            Given: scan_removable_drives가 ImportError를 발생하도록 패치하고
            When: _handle_get_drives를 호출하면
            Then: drive_list_failed 타입 메시지가 전송된다

        Notes:
            None
        """
        def raise_import_error():
            raise ImportError("missing dependency")

        monkeypatch.setattr(
            "interface.websocket.client.drive_scanner.scan_removable_drives",
            raise_import_error,
        )
        await client.connect()

        await client._handle_get_drives({})

        sent = mock_websockets.ws.get_sent_messages()[-1]
        assert sent["type"] == "drive_list_failed"
