"""Domain Enums Package.

Re-exports constants and enumerations used in the domain layer.
"""

from config.constants import (
    ErrorCode,
    ProcessState,
    SlotStatus,
    TestCapacity,
    TestFile,
    TestMethod,
    TestPhase,
    TestPreset,
    TestType,  # Backward compatibility alias for TestFile
    VendorId,
)

__all__ = [
    "ErrorCode",
    "ProcessState",
    "SlotStatus",
    "TestCapacity",
    "TestFile",
    "TestMethod",
    "TestPhase",
    "TestPreset",
    "TestType",  # Backward compatibility alias
    "VendorId",
]
