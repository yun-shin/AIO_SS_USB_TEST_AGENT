"""Constants and Enums for SS USB Test Agent.

Defines test-related constants and enumerations.
"""

from enum import IntEnum, StrEnum


class TestCapacity(StrEnum):
    """Test capacity.

    Memory capacity options supported by USB Test.
    """

    GB_1 = "1GB"
    GB_32 = "32GB"
    GB_64 = "64GB"
    GB_128 = "128GB"
    GB_256 = "256GB"
    GB_512 = "512GB"
    TB_1 = "1TB"

    @classmethod
    def from_string(cls, value: str) -> "TestCapacity":
        """Convert string to TestCapacity.

        Args:
            value: Capacity string.

        Returns:
            TestCapacity enum value.

        Raises:
            ValueError: If capacity string is invalid.
        """
        for capacity in cls:
            if capacity.value == value:
                return capacity
        raise ValueError(f"Invalid capacity: {value}")


class TestMethod(StrEnum):
    """Test method.

    Test methods supported by USB Test.
    """

    ZERO_HR = "0HR"
    READ = "Read"
    CYCLE = "Cycle"


class TestType(StrEnum):
    """Test type.

    Test types supported by USB Test.
    """

    FULL_PHOTO = "Full Photo"
    FULL_MP3 = "Full MP3"
    HOT_PHOTO = "Hot Photo"
    HOT_MP3 = "Hot MP3"

    def is_hot_test(self) -> bool:
        """Check if this is a hot test.

        Returns:
            True if hot test.
        """
        return self.value.startswith("Hot")

    def get_test_file(self) -> str:
        """Return test file type.

        Returns:
            "Photo" or "MP3".
        """
        return "Photo" if "Photo" in self.value else "MP3"


class ProcessState(IntEnum):
    """USB Test process state.

    Represents the main state of USB Test.exe.
    """

    IDLE = 0
    PASS = 1
    STOP = 2
    FAIL = 3
    TEST = 4
    UNKNOWN = 5

    @classmethod
    def from_text(cls, text: str) -> "ProcessState":
        """Convert UI text to ProcessState.

        Args:
            text: State text read from UI.

        Returns:
            ProcessState enum value.
        """
        state_map = {
            "Idle": cls.IDLE,
            "Pass": cls.PASS,
            "Stop": cls.STOP,
            "Fail": cls.FAIL,
            "Test": cls.TEST,
        }
        return state_map.get(text, cls.UNKNOWN)


class TestPhase(IntEnum):
    """Test phase.

    Represents the detailed test phase of USB Test.
    """

    IDLE = 0
    CONTACT = 1
    COPY = 2
    STOP = 3
    COMPARE = 4
    DELETE = 5
    IN_PROGRESS = 6
    UNKNOWN = 7

    @classmethod
    def from_text(cls, text: str) -> "TestPhase":
        """Convert UI text to TestPhase.

        Args:
            text: Test phase text read from UI.

        Returns:
            TestPhase enum value.
        """
        # Extract alphabets only
        cleaned = "".join(c for c in text if c.isalpha())
        phase_map = {
            "ContactTest": cls.CONTACT,
            "FileCopy": cls.COPY,
            "TestStop": cls.STOP,
            "FileCompare": cls.COMPARE,
            "FileDel": cls.DELETE,
            "IDLE": cls.IDLE,
        }
        return phase_map.get(cleaned, cls.UNKNOWN)


class ErrorCode(IntEnum):
    """Error code.

    Error types that can occur in the Agent.
    """

    NO_ERROR = 0
    TEST_COMPLETED = 1

    # 프로세스 관련 에러 (10-19)
    PROCESS_HANG = 10
    PROCESS_NOT_FOUND = 11
    PROCESS_CONNECTION_FAILED = 12
    PROCESS_TERMINATED = 13

    # 테스트 관련 에러 (20-29)
    TEST_FAILED = 20
    TEST_STATE_CHECK_FAILED = 21
    FOCUS_RETRY_FAILED = 22

    # Health Report 관련 에러 (30-39)
    HR_EXECUTION_FAILED = 30
    HR_LOG_NOT_FOUND = 31

    # 파일 I/O 에러 (40-49)
    FILE_IO_ERROR = 40
    LOG_COLLECTION_FAILED = 41

    # 네트워크 에러 (50-59)
    WEBSOCKET_CONNECTION_FAILED = 50
    API_REQUEST_FAILED = 51

    # 일반 에러 (90-99)
    GENERAL_ERROR = 99


class VendorId(StrEnum):
    """Vendor ID.

    Vendor identifier used by Health Report.
    """

    SS = "ss"
    OTHER = "other"


# =============================================================================
# WebSocket Message Types
# =============================================================================


class AgentMessageType(StrEnum):
    """Agent -> Backend message types."""

    REGISTER = "register"
    STATE_UPDATE = "state_update"
    TEST_COMPLETED = "test_completed"
    TEST_FAILED = "test_failed"
    HEARTBEAT = "heartbeat"
    LOG = "log"
    ERROR = "error"


class BackendMessageType(StrEnum):
    """Backend -> Agent message types."""

    REGISTER_ACK = "register_ack"
    RUN_TEST = "run_test"
    STOP_TEST = "stop_test"
    GET_STATUS = "get_status"
    HEARTBEAT_ACK = "heartbeat_ack"
    CONFIG_UPDATE = "config_update"


# =============================================================================
# Agent State
# =============================================================================


class AgentState(StrEnum):
    """Agent connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    REGISTERED = "registered"
    RECONNECTING = "reconnecting"


# =============================================================================
# Timeout Constants
# =============================================================================


class TimeoutConfig:
    """Timeout configuration constants."""

    # WebSocket 관련
    WEBSOCKET_CONNECT_TIMEOUT = 10  # 초
    WEBSOCKET_PING_INTERVAL = 30  # 초
    WEBSOCKET_PING_TIMEOUT = 10  # 초
    WEBSOCKET_RECONNECT_DELAY = 5  # 초
    WEBSOCKET_MAX_RECONNECT_ATTEMPTS = 10

    # 상태 체크 관련
    STATE_CHECK_INTERVAL = 10  # 초
    STATE_CHECK_RETRIES = 10
    STATE_CHECK_RETRY_DELAY = 5  # 초

    # 프로세스 관련
    PROCESS_HANG_THRESHOLD = 300  # 초 (5분)
    PROCESS_START_TIMEOUT = 30  # 초
    FOCUS_RETRY_COUNT = 10
    FOCUS_RETRY_DELAY = 2  # 초

    # 버튼 대기 관련
    BUTTON_WAIT_TIMEOUT = 30  # 초
    BUTTON_CHECK_INTERVAL = 0.5  # 초


class SlotConfig:
    """Slot configuration constants."""

    MAX_SLOTS = 4
    SLOT_INDICES = range(4)
