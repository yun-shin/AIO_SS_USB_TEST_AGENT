"""Enum Conversion Utilities.

Provides simple helpers for converting string literals to Enum values.
Used when receiving data from Backend/Frontend (JSON) and converting
to internal Enum types for MFC control.

Note:
    Backend/Frontend/Agent 간 통신은 항상 문자열 리터럴을 사용합니다.
    Agent 내부에서만 필요시 이 헬퍼를 사용하여 Enum으로 변환합니다.
"""

from enum import Enum
from typing import TypeVar

from domain.enums import (
    TestCapacity,
    TestFile,
    TestMethod,
    TestPreset,
)

E = TypeVar("E", bound=Enum)


def to_enum(value: str, enum_class: type[E], default: E) -> E:
    """문자열을 Enum으로 변환. 실패 시 기본값 반환.

    Args:
        value: 변환할 문자열 값.
        enum_class: 대상 Enum 클래스.
        default: 변환 실패 시 반환할 기본값.

    Returns:
        변환된 Enum 값 또는 기본값.

    Example:
        >>> to_enum("32GB", TestCapacity, TestCapacity.GB_32)
        <TestCapacity.GB_32: '32GB'>
        >>> to_enum("invalid", TestCapacity, TestCapacity.GB_32)
        <TestCapacity.GB_32: '32GB'>
    """
    try:
        return enum_class(value)
    except ValueError:
        return default


def to_capacity(value: str) -> TestCapacity:
    """문자열을 TestCapacity로 변환.

    Args:
        value: 용량 문자열 (예: "32GB", "1TB").

    Returns:
        TestCapacity enum 값. 실패 시 GB_32 반환.
    """
    return to_enum(value, TestCapacity, TestCapacity.GB_32)


def to_method(value: str) -> TestMethod:
    """문자열을 TestMethod로 변환.

    Args:
        value: 메서드 문자열 (예: "0HR", "Read").

    Returns:
        TestMethod enum 값. 실패 시 ZERO_HR 반환.
    """
    return to_enum(value, TestMethod, TestMethod.ZERO_HR)


def to_preset(value: str) -> TestPreset:
    """문자열을 TestPreset으로 변환.

    Args:
        value: 프리셋 문자열 (예: "Full", "Hot").

    Returns:
        TestPreset enum 값. 실패 시 FULL 반환.
    """
    return to_enum(value, TestPreset, TestPreset.FULL)


def to_file(value: str) -> TestFile:
    """문자열을 TestFile로 변환.

    Args:
        value: 파일 타입 문자열 (예: "Photo", "MP3").

    Returns:
        TestFile enum 값. 실패 시 PHOTO 반환.
    """
    return to_enum(value, TestFile, TestFile.PHOTO)
