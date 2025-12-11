"""Drive Scanner Module.

Provides functionality to scan and retrieve removable drive information
on Windows systems using win32api.
"""

import ctypes
from dataclasses import dataclass
from typing import Optional

from utils.logging import get_logger

logger = get_logger(__name__)

# Windows drive type constants
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6


@dataclass
class DriveInfo:
    """Removable drive information.

    Attributes:
        letter: Drive letter (e.g., 'E', 'F').
        label: Volume label.
        total_size: Total capacity in bytes.
        free_size: Available space in bytes.
        file_system: File system type (e.g., 'NTFS', 'FAT32').
        is_removable: Whether the drive is removable.
    """

    letter: str
    label: str = ""
    total_size: int = 0
    free_size: int = 0
    file_system: str = ""
    is_removable: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "letter": self.letter,
            "label": self.label,
            "total_size": self.total_size,
            "free_size": self.free_size,
            "file_system": self.file_system,
            "is_removable": self.is_removable,
        }


def get_drive_type(drive_letter: str) -> int:
    """Get the type of a drive.

    Args:
        drive_letter: Drive letter (e.g., 'E').

    Returns:
        Windows drive type constant.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        drive_path = f"{drive_letter}:\\"
        return kernel32.GetDriveTypeW(drive_path)
    except Exception as e:
        logger.error("Failed to get drive type", drive=drive_letter, error=str(e))
        return DRIVE_UNKNOWN


def get_volume_info(drive_letter: str) -> tuple[str, str]:
    """Get volume label and file system type.

    Args:
        drive_letter: Drive letter (e.g., 'E').

    Returns:
        Tuple of (volume_label, file_system).
    """
    try:
        kernel32 = ctypes.windll.kernel32
        drive_path = f"{drive_letter}:\\"

        volume_name_buffer = ctypes.create_unicode_buffer(261)
        file_system_buffer = ctypes.create_unicode_buffer(261)
        serial_number = ctypes.c_ulong()
        max_component_length = ctypes.c_ulong()
        file_system_flags = ctypes.c_ulong()

        result = kernel32.GetVolumeInformationW(
            drive_path,
            volume_name_buffer,
            261,
            ctypes.byref(serial_number),
            ctypes.byref(max_component_length),
            ctypes.byref(file_system_flags),
            file_system_buffer,
            261,
        )

        if result:
            return volume_name_buffer.value, file_system_buffer.value
        return "", ""

    except Exception as e:
        logger.error("Failed to get volume info", drive=drive_letter, error=str(e))
        return "", ""


def get_drive_space(drive_letter: str) -> tuple[int, int]:
    """Get drive space information.

    Args:
        drive_letter: Drive letter (e.g., 'E').

    Returns:
        Tuple of (total_bytes, free_bytes).
    """
    try:
        kernel32 = ctypes.windll.kernel32
        drive_path = f"{drive_letter}:\\"

        free_bytes_available = ctypes.c_ulonglong()
        total_bytes = ctypes.c_ulonglong()
        total_free_bytes = ctypes.c_ulonglong()

        result = kernel32.GetDiskFreeSpaceExW(
            drive_path,
            ctypes.byref(free_bytes_available),
            ctypes.byref(total_bytes),
            ctypes.byref(total_free_bytes),
        )

        if result:
            return total_bytes.value, free_bytes_available.value
        return 0, 0

    except Exception as e:
        logger.error("Failed to get drive space", drive=drive_letter, error=str(e))
        return 0, 0


def get_logical_drives() -> list[str]:
    """Get list of logical drive letters.

    Returns:
        List of drive letters (e.g., ['C', 'D', 'E']).
    """
    try:
        kernel32 = ctypes.windll.kernel32
        bitmask = kernel32.GetLogicalDrives()

        drives = []
        for i in range(26):
            if bitmask & (1 << i):
                drives.append(chr(ord("A") + i))

        return drives

    except Exception as e:
        logger.error("Failed to get logical drives", error=str(e))
        return []


def scan_removable_drives(include_fixed: bool = True) -> list[DriveInfo]:
    """Scan for removable drives on the system.

    Args:
        include_fixed: Whether to include fixed drives (default True for USB SSDs).

    Returns:
        List of DriveInfo for removable/fixed drives (excluding C:).
    """
    drives = []
    logical_drives = get_logical_drives()

    logger.info("Scanning drives", total_drives=len(logical_drives))

    for letter in logical_drives:
        drive_type = get_drive_type(letter)

        # Filter by drive type
        is_removable = drive_type == DRIVE_REMOVABLE
        is_fixed = drive_type == DRIVE_FIXED

        # Include removable drives and optionally fixed drives
        if not is_removable and not (include_fixed and is_fixed):
            continue

        # Skip C: drive (usually system drive)
        if letter == "C":
            continue

        try:
            label, file_system = get_volume_info(letter)
            total_size, free_size = get_drive_space(letter)

            drive_info = DriveInfo(
                letter=letter,
                label=label,
                total_size=total_size,
                free_size=free_size,
                file_system=file_system,
                is_removable=is_removable,
            )
            drives.append(drive_info)

            logger.debug(
                "Drive found",
                letter=letter,
                label=label,
                total_gb=f"{total_size / (1024**3):.1f}",
                is_removable=is_removable,
            )

        except Exception as e:
            logger.warning("Failed to get drive info", drive=letter, error=str(e))
            continue

    logger.info("Drive scan complete", removable_count=len(drives))
    return drives


def get_drive_info(drive_letter: str) -> Optional[DriveInfo]:
    """Get information for a specific drive.

    Args:
        drive_letter: Drive letter (e.g., 'E').

    Returns:
        DriveInfo or None if drive not found.
    """
    drive_type = get_drive_type(drive_letter)
    if drive_type == DRIVE_UNKNOWN or drive_type == DRIVE_NO_ROOT_DIR:
        return None

    try:
        label, file_system = get_volume_info(drive_letter)
        total_size, free_size = get_drive_space(drive_letter)

        return DriveInfo(
            letter=drive_letter,
            label=label,
            total_size=total_size,
            free_size=free_size,
            file_system=file_system,
            is_removable=(drive_type == DRIVE_REMOVABLE),
        )
    except Exception as e:
        logger.error("Failed to get drive info", drive=drive_letter, error=str(e))
        return None
