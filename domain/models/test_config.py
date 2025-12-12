"""Test Configuration Model.

Domain model defining settings required for test execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from domain.enums import TestCapacity, TestFile, TestMethod, TestPreset, VendorId


@dataclass
class PreconditionConfig:
    """Precondition configuration for Hot test.

    Precondition runs a 0HR test once with drive capacity before the main test.

    Attributes:
        enabled: Whether precondition is enabled.
        method: Precondition method (always 0HR).
        capacity: Precondition capacity (drive capacity).
        loop_count: Precondition loop count (always 1).
    """

    enabled: bool = True
    method: TestMethod = TestMethod.ZERO_HR
    capacity: Optional[TestCapacity] = None  # None means use drive capacity
    loop_count: int = 1


@dataclass
class TestConfig:
    """Test configuration model.

    Contains all settings required for test execution.

    Attributes:
        slot_idx: Test slot index (0-3).
        jira_no: Jira issue number.
        sample_no: Sample test number.
        drive: Test drive letter.
        test_preset: Test preset (Full or Hot).
        test_file: Test file type (Photo or MP3).
        method: Test method (0HR, Read, Cycle).
        capacity: Test capacity.
        loop_count: Total loop count.
        loop_step: Loop step unit (for batch execution).
        start_loop: Starting loop number.
        precondition: Precondition configuration (for Hot test).
        hr_enabled: Whether to run Health Report.
        adaptive_vol: Whether to use Adaptive Voltage.
        die_count: Die count.
        vendor_id: Vendor ID.
        batch_enabled: Whether batch mode is enabled.
        drive_capacity_gb: Drive capacity in GB (for auto capacity selection).
        created_at: Settings creation time.
    """

    slot_idx: int
    jira_no: str
    sample_no: str
    drive: str
    test_preset: TestPreset
    test_file: TestFile
    method: TestMethod
    capacity: TestCapacity
    loop_count: int
    test_name: str = "USB Test"  # Test name for display

    # Optional settings
    loop_step: int = 1
    start_loop: int = 0
    batch_enabled: bool = True

    # Precondition settings (for Hot test)
    precondition: PreconditionConfig = field(default_factory=PreconditionConfig)

    # Drive capacity (for auto capacity calculation)
    drive_capacity_gb: float = 0.0

    # Health Report settings
    hr_enabled: bool = True
    adaptive_vol: bool = False
    die_count: int = 1
    vendor_id: VendorId = VendorId.SS

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    test_id: Optional[str] = None  # Unique ID assigned by Backend

    def validate(self) -> list[str]:
        """Validate settings.

        Returns:
            List of error messages. Empty list if valid.
        """
        errors: list[str] = []

        if not 0 <= self.slot_idx < 4:
            errors.append(f"slot_idx must be between 0 and 3, got {self.slot_idx}")

        if self.loop_count < 1:
            errors.append(f"loop_count must be at least 1, got {self.loop_count}")

        if self.loop_step < 1:
            errors.append(f"loop_step must be at least 1, got {self.loop_step}")

        if self.start_loop < 0:
            errors.append(f"start_loop must be non-negative, got {self.start_loop}")

        if self.start_loop >= self.loop_count:
            errors.append(
                f"start_loop ({self.start_loop}) must be less than "
                f"loop_count ({self.loop_count})"
            )

        if not self.drive:
            errors.append("drive is required")

        if not self.jira_no:
            errors.append("jira_no is required")

        if not self.sample_no:
            errors.append("sample_no is required")

        if self.hr_enabled and self.die_count < 1:
            errors.append(f"die_count must be at least 1, got {self.die_count}")

        return errors

    def is_valid(self) -> bool:
        """Check if settings are valid.

        Returns:
            True if valid.
        """
        return len(self.validate()) == 0

    def is_hot_test(self) -> bool:
        """Check if this is a hot test.

        Returns:
            True if using Hot preset.
        """
        return self.test_preset.is_hot_test()

    def needs_precondition(self) -> bool:
        """Check if precondition should be run.

        Precondition is only available for Hot preset.

        Returns:
            True if precondition should be run.
        """
        return self.is_hot_test() and self.precondition.enabled

    def get_precondition_capacity(self) -> TestCapacity:
        """Get precondition capacity.

        .. deprecated::
            Use `self.precondition.capacity` directly instead.
            Backend now calculates and sends the precondition capacity.
            Agent should not recalculate.

        R&R (Role & Responsibility):
        - Backend: Calculate precondition.capacity based on drive_capacity_gb
        - Agent: Use precondition.capacity directly (no recalculation)

        Returns:
            TestCapacity from precondition.capacity or fallback to drive calculation.
        """
        # Backend에서 계산된 값 사용, fallback은 하위 호환성을 위해 유지
        if self.precondition.capacity is not None:
            return self.precondition.capacity
        # Fallback: 이전 방식 (하위 호환성, 권장하지 않음)
        return TestCapacity.from_drive_capacity(self.drive_capacity_gb)

    def get_test_file_value(self) -> str:
        """Return test file type value for MFC.

        Returns:
            "Photo" or "MP3".
        """
        return str(self.test_file)

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Settings dictionary.
        """
        return {
            "slot_idx": self.slot_idx,
            "jira_no": self.jira_no,
            "sample_no": self.sample_no,
            "drive": self.drive,
            "test_preset": self.test_preset.value,
            "test_file": self.test_file.value,
            "method": self.method.value,
            "capacity": self.capacity.value,
            "loop_count": self.loop_count,
            "loop_step": self.loop_step,
            "start_loop": self.start_loop,
            "batch_enabled": self.batch_enabled,
            "precondition": {
                "enabled": self.precondition.enabled,
                "method": self.precondition.method.value,
                "capacity": (
                    self.precondition.capacity.value
                    if self.precondition.capacity
                    else None
                ),
                "loop_count": self.precondition.loop_count,
            },
            "drive_capacity_gb": self.drive_capacity_gb,
            "hr_enabled": self.hr_enabled,
            "adaptive_vol": self.adaptive_vol,
            "die_count": self.die_count,
            "vendor_id": self.vendor_id.value,
            "created_at": self.created_at.isoformat(),
            "test_id": self.test_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestConfig":
        """Create TestConfig from dictionary.

        Supports two JSON formats:

        1. Backend format (nested 'test' field):
        {
            "slot_idx": 0,
            "drive": "H",
            "test_preset": "Hot",
            "test_file": "Photo",
            "precondition": {
                "enabled": true,
                "capacity": "64GB",
                "method": "0HR",
                "loop_count": 1
            },
            "test": {
                "capacity": "4GB",
                "method": "0HR",
                "loop_count": 10,
                "loop_step": 1
            }
        }

        2. Flat format (from to_dict()):
        {
            "slot_idx": 0,
            "drive": "H",
            "capacity": "32GB",
            "method": "0HR",
            "loop_count": 10,
            ...
        }

        Args:
            data: Settings dictionary (Backend or serialized format).

        Returns:
            TestConfig instance.
        """
        # Parse precondition config (Backend에서 capacity를 계산해서 보내줌)
        precondition_data = data.get("precondition", {})
        precondition = PreconditionConfig(
            enabled=precondition_data.get("enabled", True),
            method=TestMethod(precondition_data.get("method", "0HR")),
            capacity=(
                TestCapacity(precondition_data["capacity"])
                if precondition_data.get("capacity")
                else None
            ),
            loop_count=precondition_data.get("loop_count", 1),
        )

        # Parse main test config
        # Support both nested 'test' field (Backend) and flat format (to_dict)
        test_data = data.get("test")
        if test_data:
            # Backend format with nested 'test' field
            test_capacity = TestCapacity(test_data.get("capacity", "4GB"))
            test_method = TestMethod(test_data.get("method", "0HR"))
            test_loop_count = test_data.get("loop_count", 10)
            test_loop_step = test_data.get("loop_step", 1)
        else:
            # Flat format (from to_dict or direct fields)
            test_capacity = TestCapacity(data.get("capacity", "32GB"))
            test_method = TestMethod(data.get("method", "0HR"))
            test_loop_count = data.get("loop_count", 10)
            test_loop_step = data.get("loop_step", 1)

        return cls(
            slot_idx=data["slot_idx"],
            jira_no=data.get("jira_no", ""),
            sample_no=data.get("sample_no", ""),
            drive=data["drive"],
            test_preset=TestPreset(data["test_preset"]),
            test_file=TestFile(data["test_file"]),
            method=test_method,
            capacity=test_capacity,
            loop_count=test_loop_count,
            loop_step=test_loop_step,
            start_loop=data.get("start_loop", 0),
            batch_enabled=data.get("batch_enabled", True),
            precondition=precondition,
            drive_capacity_gb=data.get("drive_capacity_gb", 0.0),
            hr_enabled=data.get("hr_enabled", True),
            adaptive_vol=data.get("adaptive_vol", False),
            die_count=data.get("die_count", 1),
            vendor_id=VendorId(data.get("vendor_id", "ss")),
            test_id=data.get("test_id"),
            test_name=data.get("test_name", "USB Test"),
        )
