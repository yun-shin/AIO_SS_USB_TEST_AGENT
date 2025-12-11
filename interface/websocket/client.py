"""WebSocket Client Module.

Client responsible for WebSocket communication with Host PC Backend.
Agent initiates and maintains the connection.
"""

import asyncio
import json
import socket
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, WebSocketException

from config.settings import AgentSettings, get_settings
from config.constants import (
    AgentMessageType,
    BackendMessageType,
    AgentState,
    TimeoutConfig,
)
from utils.logging import get_logger

logger = get_logger(__name__)


class WebSocketClient:
    """WebSocket client.

    Manages WebSocket connection with Host PC Backend.
    Handles auto-reconnect, message send/receive, and heartbeat.

    Attributes:
        settings: Agent settings.
        agent_id: Agent unique ID.
        state: Current connection state.
    """

    def __init__(
        self,
        settings: Optional[AgentSettings] = None,
        on_message: Optional[Callable[[dict], asyncio.coroutine]] = None,
    ) -> None:
        """Initialize WebSocket client.

        Args:
            settings: Agent settings (uses default if None).
            on_message: Callback function to call when message is received.
        """
        self._settings = settings or get_settings()
        self._ws: Optional[WebSocketClientProtocol] = None
        self._state = AgentState.DISCONNECTED
        self._reconnect_count = 0
        self._should_run = False
        self._on_message = on_message

        # Agent 식별 정보
        self._agent_id = str(uuid.uuid4())
        self._pc_name = socket.gethostname()

        # 메시지 핸들러 등록
        self._message_handlers: dict[str, Callable[[dict], asyncio.coroutine]] = {}

        # 태스크
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def agent_id(self) -> str:
        """Agent unique ID."""
        return self._agent_id

    @property
    def state(self) -> AgentState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Connection status."""
        return self._state in (AgentState.CONNECTED, AgentState.REGISTERED)

    def register_handler(
        self,
        message_type: BackendMessageType,
        handler: Callable[[dict], asyncio.coroutine],
    ) -> None:
        """Register message handler.

        Args:
            message_type: Message type to handle.
            handler: Handler function (async).
        """
        self._message_handlers[message_type.value] = handler
        logger.debug("Handler registered", message_type=message_type.value)

    async def connect(self) -> bool:
        """Start WebSocket connection.

        Returns:
            Connection success status.
        """
        if self.is_connected:
            logger.warning("Already connected")
            return True

        self._state = AgentState.CONNECTING
        logger.info(
            "Connecting to backend",
            url=self._settings.backend_ws_url,
            agent_id=self._agent_id,
        )

        try:
            # 인증 헤더 설정
            headers = {
                "X-Agent-ID": self._agent_id,
                "X-PC-Name": self._pc_name,
            }

            # WebSocket URL 구성 (Query parameter로 인증 토큰 전달)
            # 모범사례: WebSocket handshake 시 헤더 접근이 제한되는 환경이 있으므로
            # Query parameter와 Header 양쪽에 인증 정보 전달
            ws_url = self._settings.backend_ws_url
            if self._settings.api_key:
                # URL에 token query parameter 추가
                separator = "&" if "?" in ws_url else "?"
                ws_url = f"{ws_url}{separator}token={self._settings.api_key}"
                # Header에도 추가 (백업)
                headers["Authorization"] = f"Bearer {self._settings.api_key}"
                headers["X-API-Key"] = self._settings.api_key
                logger.debug(
                    "Auth configured",
                    has_api_key=True,
                    api_key_prefix=self._settings.api_key[:10] + "...",
                )
            else:
                logger.warning("No API key configured - connection may be rejected")

            self._ws = await asyncio.wait_for(
                websockets.connect(
                    ws_url,
                    ping_interval=TimeoutConfig.WEBSOCKET_PING_INTERVAL,
                    ping_timeout=TimeoutConfig.WEBSOCKET_PING_TIMEOUT,
                    additional_headers=headers,
                ),
                timeout=TimeoutConfig.WEBSOCKET_CONNECT_TIMEOUT,
            )

            self._state = AgentState.CONNECTED
            self._reconnect_count = 0
            logger.info("WebSocket connected", url=self._settings.backend_ws_url)

            # Agent 등록
            await self._register()

            return True

        except asyncio.TimeoutError:
            logger.error("Connection timeout")
            self._state = AgentState.DISCONNECTED
            return False

        except WebSocketException as e:
            logger.error("WebSocket connection failed", error=str(e))
            self._state = AgentState.DISCONNECTED
            return False

        except Exception as e:
            logger.error("Unexpected connection error", error=str(e))
            self._state = AgentState.DISCONNECTED
            return False

    async def _register(self) -> None:
        """Register Agent with Backend."""
        register_msg = {
            "type": AgentMessageType.REGISTER.value,
            "data": {
                "agent_id": self._agent_id,
                "pc_name": self._pc_name,
                "slots": list(range(self._settings.max_slots)),
                "version": self._settings.version,
                "timestamp": datetime.now().isoformat(),
            },
        }
        await self.send(register_msg)
        logger.info("Registration message sent", agent_id=self._agent_id)

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._should_run = False

        # 태스크 취소
        for task in [self._receive_task, self._heartbeat_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # WebSocket 종료
        if self._ws:
            await self._ws.close()
            self._ws = None

        self._state = AgentState.DISCONNECTED
        logger.info("WebSocket disconnected")

    async def send(self, message: dict) -> bool:
        """Send message.

        Args:
            message: Message dictionary to send.

        Returns:
            Send success status.
        """
        if not self._ws or not self.is_connected:
            logger.warning("Cannot send: not connected")
            return False

        try:
            await self._ws.send(json.dumps(message))
            logger.debug("Message sent", type=message.get("type"))
            return True
        except ConnectionClosed:
            logger.warning("Connection closed while sending")
            self._state = AgentState.DISCONNECTED
            return False
        except Exception as e:
            logger.error("Send failed", error=str(e))
            return False

    async def send_state_update(self, slot_idx: int, state_data: dict) -> bool:
        """Send state update.

        Args:
            slot_idx: Slot index.
            state_data: State data.

        Returns:
            Send success status.
        """
        message = {
            "type": AgentMessageType.STATE_UPDATE.value,
            "data": {
                "slot_idx": slot_idx,
                "timestamp": datetime.now().isoformat(),
                **state_data,
            },
        }
        return await self.send(message)

    async def send_test_completed(
        self,
        slot_idx: int,
        success: bool,
        result_data: Optional[dict] = None,
    ) -> bool:
        """Send test completed.

        Args:
            slot_idx: Slot index.
            success: Success status.
            result_data: Result data.

        Returns:
            Send success status.
        """
        msg_type = (
            AgentMessageType.TEST_COMPLETED if success else AgentMessageType.TEST_FAILED
        )
        message = {
            "type": msg_type.value,
            "data": {
                "slot_idx": slot_idx,
                "success": success,
                "timestamp": datetime.now().isoformat(),
                **(result_data or {}),
            },
        }
        return await self.send(message)

    async def run(self) -> None:
        """Run main event loop.

        Handles connection maintenance, message reception, and reconnection.
        """
        self._should_run = True

        while self._should_run:
            # 연결 시도
            if not self.is_connected:
                connected = await self.connect()
                if not connected:
                    await self._handle_reconnect()
                    continue

            # 수신 및 Heartbeat 태스크 시작
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 태스크 완료 대기
            done, pending = await asyncio.wait(
                [self._receive_task, self._heartbeat_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # 남은 태스크 취소
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # 연결 끊김 처리
            if self._should_run:
                logger.warning("Connection lost, will reconnect")
                self._state = AgentState.DISCONNECTED
                await self._handle_reconnect()

    async def _receive_loop(self) -> None:
        """Message receive loop."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received", message=message[:100])

        except ConnectionClosed as e:
            logger.warning("Connection closed", code=e.code, reason=e.reason)
        except Exception as e:
            logger.error("Receive loop error", error=str(e))

    async def _handle_message(self, message: dict) -> None:
        """Handle received message.

        Args:
            message: Received message.
        """
        msg_type = message.get("type")
        data = message.get("data", {})

        logger.debug("Message received", type=msg_type)

        # 등록 확인 처리
        if msg_type == BackendMessageType.REGISTER_ACK.value:
            self._state = AgentState.REGISTERED
            logger.info("Agent registered successfully")

        # Heartbeat 응답 처리
        elif msg_type == BackendMessageType.HEARTBEAT_ACK.value:
            logger.debug("Heartbeat acknowledged")

        # 등록된 핸들러 호출
        if msg_type in self._message_handlers:
            handler = self._message_handlers[msg_type]
            try:
                await handler(data)
            except Exception as e:
                logger.error("Handler error", type=msg_type, error=str(e))

        # 기본 콜백 호출
        if self._on_message:
            try:
                await self._on_message(message)
            except Exception as e:
                logger.error("Callback error", error=str(e))

    async def _heartbeat_loop(self) -> None:
        """Heartbeat send loop."""
        while self._should_run and self.is_connected:
            await asyncio.sleep(TimeoutConfig.WEBSOCKET_PING_INTERVAL)
            if self.is_connected:
                heartbeat_msg = {
                    "type": AgentMessageType.HEARTBEAT.value,
                    "data": {"timestamp": datetime.now().isoformat()},
                }
                await self.send(heartbeat_msg)

    async def _handle_reconnect(self) -> None:
        """Handle reconnection."""
        self._reconnect_count += 1
        self._state = AgentState.RECONNECTING

        if self._reconnect_count > TimeoutConfig.WEBSOCKET_MAX_RECONNECT_ATTEMPTS:
            logger.error(
                "Max reconnect attempts reached",
                attempts=self._reconnect_count,
            )
            self._should_run = False
            return

        delay = TimeoutConfig.WEBSOCKET_RECONNECT_DELAY * min(self._reconnect_count, 5)
        logger.info(
            "Reconnecting",
            attempt=self._reconnect_count,
            delay=delay,
        )
        await asyncio.sleep(delay)
