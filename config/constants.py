"""Constants and Enums for SS USB Test Agent.

Defines test-related constants and enumerations.
"""

from enum import Enum, IntEnum


# Python 3.10 호환성을 위한 StrEnum 대체
class StrEnum(str, Enum):
    """String enumeration compatible with Python 3.10+."""

    def __str__(self) -> str:
        return self.value


class TestCapacity(StrEnum):
    """Test capacity.

    Memory capacity options supported by USB Test.
    """

    GB_1 = "1GB"
    GB_4 = "4GB"  # Used for HOT preset
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

    def to_gb(self) -> float:
        """Convert capacity to gigabytes.

        Returns:
            Capacity in GB.
        """
        capacity_map = {
            TestCapacity.GB_1: 1.0,
            TestCapacity.GB_4: 4.0,
            TestCapacity.GB_32: 32.0,
            TestCapacity.GB_64: 64.0,
            TestCapacity.GB_128: 128.0,
            TestCapacity.GB_256: 256.0,
            TestCapacity.GB_512: 512.0,
            TestCapacity.TB_1: 1024.0,
        }
        return capacity_map.get(self, 0.0)

    @classmethod
    def from_drive_capacity(cls, drive_capacity_gb: float) -> "TestCapacity":
        """Find nearest capacity for given drive capacity.

        Finds the closest capacity to the drive capacity (not just <= ).
        Examples:
            - 59.7GB → 64GB (closer to 64 than 32)
            - 66GB → 64GB (closer to 64 than 128)
            - 100GB → 128GB (closer to 128 than 64)

        Args:
            drive_capacity_gb: Drive capacity in GB.

        Returns:
            Nearest TestCapacity enum value.
        """
        if drive_capacity_gb <= 0:
            return cls.GB_32  # Default fallback

        # Sorted by capacity value (ascending)
        capacities = [
            (cls.GB_1, 1.0),
            (cls.GB_4, 4.0),
            (cls.GB_32, 32.0),
            (cls.GB_64, 64.0),
            (cls.GB_128, 128.0),
            (cls.GB_256, 256.0),
            (cls.GB_512, 512.0),
            (cls.TB_1, 1024.0),
        ]

        # Find the closest capacity (minimum absolute difference)
        closest = cls.GB_32
        min_diff = float("inf")

        for capacity_enum, capacity_gb in capacities:
            diff = abs(drive_capacity_gb - capacity_gb)
            if diff < min_diff:
                min_diff = diff
                closest = capacity_enum

        return closest


class TestMethod(StrEnum):
    """Test method.

    Test methods supported by USB Test.
    """

    ZERO_HR = "0HR"
    READ = "Read"
    CYCLE = "Cycle"


class TestPreset(StrEnum):
    """Test preset type.

    Determines capacity setting behavior:
    - FULL: Capacity is set to approximate drive capacity
    - HOT: Capacity is fixed to 4GB, precondition option available
    """

    FULL = "Full"
    HOT = "Hot"

    def is_hot_test(self) -> bool:
        """Check if this is a hot test.

        Returns:
            True if this is a HOT preset.
        """
        return self == TestPreset.HOT

    def get_default_capacity(self, drive_capacity_gb: float = 0) -> "TestCapacity":
        """Get default capacity for this preset.

        Args:
            drive_capacity_gb: Drive capacity in GB (used for FULL preset).

        Returns:
            TestCapacity enum value.
        """
        if self == TestPreset.HOT:
            return TestCapacity.GB_4
        # FULL preset: find nearest capacity
        return TestCapacity.from_drive_capacity(drive_capacity_gb)


class TestFile(StrEnum):
    """Test file type.

    File types used in USB Test.
    Values match USB Test.exe ComboBox items.
    """

    MP3 = "MP3"
    PHOTO = "Photo"


# Backward compatibility alias
TestType = TestFile


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

        Handles both simple text ('Idle', 'Pass') and complex text ('10/10 IDLE').

        Args:
            text: State text read from UI.

        Returns:
            ProcessState enum value.
        """
        if not text:
            return cls.UNKNOWN

        # 정확한 매칭 먼저 시도 (Button6 스타일)
        state_map = {
            "Idle": cls.IDLE,
            "Pass": cls.PASS,
            "Stop": cls.STOP,
            "Fail": cls.FAIL,
            "Test": cls.TEST,
        }
        if text in state_map:
            return state_map[text]

        # 대소문자 무시 매칭 시도
        text_lower = text.lower().strip()
        for key, value in state_map.items():
            if key.lower() == text_lower:
                return value

        # 복합 텍스트에서 상태 추출 (예: '10/10 IDLE' → 'IDLE')
        # Static 컨트롤이 '숫자/숫자 상태' 형식으로 표시되는 경우
        parts = text.split()
        if len(parts) >= 2:
            # 마지막 부분이 상태일 가능성
            last_part = parts[-1]
            for key, value in state_map.items():
                if key.lower() == last_part.lower():
                    return value

        return cls.UNKNOWN


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

        Handles various text formats:
        - Simple: 'FileCopy', 'FileCompare'
        - Complex from Static: '4/10  File Copy 35/88' -> 'FileCopy'

        Args:
            text: Test phase text read from UI.

        Returns:
            TestPhase enum value.
        """
        if not text:
            return cls.UNKNOWN

        # Extract alphabets only for mapping
        cleaned = "".join(c for c in text if c.isalpha())

        phase_map = {
            "ContactTest": cls.CONTACT,
            "FileCopy": cls.COPY,
            "TestStop": cls.STOP,
            "FileCompare": cls.COMPARE,
            "FileDel": cls.DELETE,
            "IDLE": cls.IDLE,
        }

        # 직접 매핑 시도
        if cleaned in phase_map:
            return phase_map[cleaned]

        # 부분 문자열 매칭 (예: 'FileCopy' in 'FileCompare35/88' 형태)
        for key, value in phase_map.items():
            if key in cleaned:
                return value

        # 공백 제거 후 부분 매칭 (예: 'File Copy' -> 'FileCopy')
        text_no_space = text.replace(" ", "")
        for key, value in phase_map.items():
            if key.lower() in text_no_space.lower():
                return value

        return cls.UNKNOWN


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

    REGISTER = "agent:register"
    STATE_UPDATE = "agent:state_update"
    TEST_COMPLETED = "agent:test_completed"
    TEST_FAILED = "agent:test_failed"
    HEARTBEAT = "agent:heartbeat"
    LOG = "agent:log"
    ERROR = "agent:error"
    DRIVE_LIST = "agent:drive_list"


class BackendMessageType(StrEnum):
    """Backend -> Agent message types."""

    REGISTER_ACK = "backend:register_ack"
    RUN_TEST = "backend:run_test"
    STOP_TEST = "backend:stop_test"
    GET_STATUS = "backend:get_status"
    HEARTBEAT_ACK = "backend:heartbeat_ack"
    CONFIG_UPDATE = "backend:config_update"
    GET_DRIVES = "backend:get_drives"


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
    """Timeout configuration constants.

    통신, 프로세스, UI 대기 시간에 대한 단일 기준값.
    """

    # WebSocket 관련
    WEBSOCKET_CONNECT_TIMEOUT = 10.0
    WEBSOCKET_PING_INTERVAL = 30.0
    WEBSOCKET_PING_TIMEOUT = 10.0
    WEBSOCKET_RECONNECT_DELAY = 5.0
    WEBSOCKET_MAX_RECONNECT_ATTEMPTS = 10

    # 상태 체크 관련
    STATE_CHECK_INTERVAL = 10.0
    STATE_CHECK_RETRIES = 10
    STATE_CHECK_RETRY_DELAY = 5.0

    # 프로세스 관련
    PROCESS_HANG_THRESHOLD = 300.0  # 초 (5분)
    PROCESS_START_TIMEOUT = 30.0  # 초
    PROCESS_TERMINATE_TIMEOUT = 10.0  # 초

    # 포커스/클릭 재시도
    FOCUS_RETRY_COUNT = 10
    FOCUS_RETRY_DELAY = 2.0  # 초

    # 버튼 대기 관련
    BUTTON_WAIT_TIMEOUT = 30.0  # 초
    BUTTON_CHECK_INTERVAL = 0.5  # 초
    CONTACT_BUTTON_TIMEOUT = 15.0  # 초
    TEST_BUTTON_TIMEOUT = 30.0  # 초

    # 윈도우/드라이브 대기
    WINDOW_CONNECT_TIMEOUT = 10.0  # 초
    DRIVE_SCAN_TIMEOUT = 30.0  # 초

    # 엘리먼트 관련
    ELEMENT_WAIT = 10.0  # 초 (UI 엘리먼트 대기 기본 시간)


class SlotStatus(StrEnum):
    """Slot status.

    Represents the current status of a test slot.
    """

    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class SlotConfig:
    """Slot configuration constants."""

    MAX_SLOTS = 4
    SLOT_INDICES = range(4)


class MFCControlId:
    """USB Test.exe MFC Control IDs.

    Control IDs extracted from USB Test V2.0.1.
    Uses integer IDs for win32 backend.
    """

    # Buttons
    BTN_EXIT = 1000
    BTN_CONTACT = 1019
    BTN_TEST = 1014  # Start/Test button
    BTN_STOP = 1016
    BTN_FORMAT = 1015
    BTN_BROWSE = 1013  # "..." button
    BTN_CONNECT = 1044
    BTN_DISCONNECT = 1045

    # ComboBoxes
    CMB_CAPACITY = 1028  # Memory capacity
    CMB_METHOD = 1033  # Test method (0HR, Read, Cycle)
    CMB_TEST_TYPE = 1039  # Test file type (MP3, Photo, Option)
    CMB_DRIVE = 1029  # Test drive

    # Edit fields
    EDT_LOOP = 1021  # Loop count
    EDT_LOOP_CURRENT = 1023  # Current loop (read-only display)
    EDT_READ_COUNT = 1005
    EDT_CONTROL_NO = 1018
    EDT_SAMPLE = 1009
    EDT_JIRA = 1022

    # Status displays
    TXT_STATUS = 1034  # Status text (IDLE, Test, Pass, Fail, etc.)
    PROGRESS_BAR = 1035

    # CheckBoxes
    CHK_DENSITY_LOOP = 1036
    CHK_IGNORE_FAIL = 1037
    CHK_AUTO_DENSITY = 1038

    # List
    LST_TEST_DIR = 1020


# ============================================================================
# Retry/Timeout Settings
# ============================================================================
# 유저가 실수로 건드렸을 때도 Agent가 너그럽게 재시도하도록 설정
# MFC USB Test.exe 실패는 엄격하게, Agent 실패는 유연하게 처리


class RetryConfig:
    """Retry configuration constants.

    Agent-side retry settings for resilient operation.
    These values are designed to be forgiving when users accidentally interact
    with the window during automated testing.
    """

    # Button click retries
    BUTTON_CLICK_MAX_RETRIES: int = 5  # 버튼 클릭 최대 재시도 (기존 2 → 5)
    BUTTON_CLICK_RETRY_DELAY: float = 1.0  # 재시도 간격 (초) (기존 0.5 → 1.0)

    # Focus setting retries
    FOCUS_MAX_RETRIES: int = 5  # 포커스 설정 최대 재시도 (기존 3 → 5)
    FOCUS_RETRY_DELAY: float = 1.0  # 재시도 간격 (초) (기존 0.5 → 1.0)

    # Post-action delays
    FOCUS_SETTLE_DELAY: float = 0.3  # 포커스 전환 후 대기 (기존 0.2 → 0.3)
    CLICK_SETTLE_DELAY: float = 0.5  # 클릭 후 대기 (기존 0.3 → 0.5)
