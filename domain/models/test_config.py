"""Test Configuration Model.

Domain model defining settings required for test execution.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from domain.enums import TestCapacity, TestMethod, TestType, VendorId


@dataclass
class TestConfig:
    """Test configuration model.

    Contains all settings required for test execution.

    Attributes:
        slot_idx: Test slot index (0-3).
        jira_no: Jira issue number.
        sample_no: Sample test number.
        capacity: Test capacity.
        drive: Test drive letter.
        method: Test method (0HR, Read, Cycle).
        test_type: Test type (Full Photo, Full MP3, Hot Photo, Hot MP3).
        loop_count: Total loop count.
        loop_step: Loop step unit (for batch execution).
        start_loop: Starting loop number.
        hot_precondition: Whether to run precondition before Hot test.
        hr_enabled: Whether to run Health Report.
        adaptive_vol: Whether to use Adaptive Voltage.
        die_count: Die count.
        vendor_id: Vendor ID.
        batch_enabled: Whether batch mode is enabled.
        created_at: Settings creation time.
    """

    slot_idx: int
    jira_no: str
    sample_no: str
    capacity: TestCapacity
    drive: str
    method: TestMethod
    test_type: TestType
    loop_count: int
    test_name: str = "USB Test"  # Test name for display

    # Optional settings
    loop_step: int = 1
    start_loop: int = 0
    hot_precondition: bool = True
    batch_enabled: bool = True

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
            True if hot test.
        """
        return self.test_type.is_hot_test()

    def get_test_file(self) -> str:
        """Return test file type.

        Returns:
            "Photo" or "MP3".
        """
        return self.test_type.get_test_file()

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Settings dictionary.
        """
        return {
            "slot_idx": self.slot_idx,
            "jira_no": self.jira_no,
            "sample_no": self.sample_no,
            "capacity": self.capacity.value,
            "drive": self.drive,
            "method": self.method.value,
            "test_type": self.test_type.value,
            "loop_count": self.loop_count,
            "loop_step": self.loop_step,
            "start_loop": self.start_loop,
            "hot_precondition": self.hot_precondition,
            "batch_enabled": self.batch_enabled,
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

        Args:
            data: Settings dictionary.

        Returns:
            TestConfig instance.
        """
        return cls(
            slot_idx=data["slot_idx"],
            jira_no=data["jira_no"],
            sample_no=data["sample_no"],
            capacity=TestCapacity(data["capacity"]),
            drive=data["drive"],
            method=TestMethod(data["method"]),
            test_type=TestType(data["test_type"]),
            loop_count=data["loop_count"],
            loop_step=data.get("loop_step", 1),
            start_loop=data.get("start_loop", 0),
            hot_precondition=data.get("hot_precondition", True),
            batch_enabled=data.get("batch_enabled", True),
            hr_enabled=data.get("hr_enabled", True),
            adaptive_vol=data.get("adaptive_vol", False),
            die_count=data.get("die_count", 1),
            vendor_id=VendorId(data.get("vendor_id", "ss")),
            test_id=data.get("test_id"),
        )
