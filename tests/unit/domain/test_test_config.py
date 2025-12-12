"""Tests for TestConfig Model."""

import pytest
from domain.models import TestConfig
from domain.models.test_config import PreconditionConfig
from config.constants import (
    TestCapacity,
    TestFile,
    TestMethod,
    TestPreset,
    VendorId,
)


class TestTestConfig:
    """TestConfig 모델 테스트."""

    def test_create_valid_config(self, sample_test_config: TestConfig) -> None:
        """유효한 설정 생성 테스트."""
        assert sample_test_config.slot_idx == 0
        assert sample_test_config.jira_no == "TEST-123"
        assert sample_test_config.capacity == TestCapacity.GB_32
        assert sample_test_config.test_preset == TestPreset.FULL
        assert sample_test_config.test_file == TestFile.PHOTO
        assert sample_test_config.is_valid()

    def test_validate_invalid_slot_idx(self) -> None:
        """잘못된 slot_idx 검증 테스트."""
        config = TestConfig(
            slot_idx=5,  # Invalid: should be 0-3
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.FULL,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=10,
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("slot_idx" in e for e in errors)

    def test_validate_invalid_loop_count(self) -> None:
        """잘못된 loop_count 검증 테스트."""
        config = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.FULL,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=0,  # Invalid: should be >= 1
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("loop_count" in e for e in errors)

    def test_validate_missing_drive(self) -> None:
        """드라이브 누락 검증 테스트."""
        config = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="",  # Invalid: empty
            test_preset=TestPreset.FULL,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=10,
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("drive" in e for e in errors)

    def test_is_hot_test(self) -> None:
        """Hot 테스트 여부 확인 테스트."""
        config_hot = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.HOT,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_4,
            loop_count=10,
        )
        assert config_hot.is_hot_test()

        config_full = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.FULL,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=10,
        )
        assert not config_full.is_hot_test()

    def test_get_test_file_value(self) -> None:
        """테스트 파일 타입 반환 테스트."""
        config_photo = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.FULL,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=10,
        )
        assert config_photo.get_test_file_value() == "Photo"

        config_mp3 = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.FULL,
            test_file=TestFile.MP3,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=10,
        )
        assert config_mp3.get_test_file_value() == "MP3"

    def test_needs_precondition(self) -> None:
        """Precondition 필요 여부 테스트."""
        # Hot preset with precondition enabled
        config_hot_with_precondition = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.HOT,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_4,
            loop_count=10,
            precondition=PreconditionConfig(enabled=True),
        )
        assert config_hot_with_precondition.needs_precondition()

        # Hot preset with precondition disabled
        config_hot_no_precondition = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.HOT,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_4,
            loop_count=10,
            precondition=PreconditionConfig(enabled=False),
        )
        assert not config_hot_no_precondition.needs_precondition()

        # Full preset (precondition not applicable)
        config_full = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            drive="E",
            test_preset=TestPreset.FULL,
            test_file=TestFile.PHOTO,
            method=TestMethod.ZERO_HR,
            capacity=TestCapacity.GB_32,
            loop_count=10,
        )
        assert not config_full.needs_precondition()

    def test_to_dict_and_from_dict(self, sample_test_config: TestConfig) -> None:
        """딕셔너리 변환 테스트."""
        config_dict = sample_test_config.to_dict()
        restored = TestConfig.from_dict(config_dict)

        assert restored.slot_idx == sample_test_config.slot_idx
        assert restored.jira_no == sample_test_config.jira_no
        assert restored.capacity == sample_test_config.capacity
        assert restored.drive == sample_test_config.drive
        assert restored.method == sample_test_config.method
        assert restored.test_preset == sample_test_config.test_preset
        assert restored.test_file == sample_test_config.test_file
        assert restored.loop_count == sample_test_config.loop_count


class TestTestPreset:
    """TestPreset enum 테스트."""

    def test_is_hot_test(self) -> None:
        """Hot 테스트 여부 확인."""
        assert TestPreset.HOT.is_hot_test()
        assert not TestPreset.FULL.is_hot_test()

    def test_get_default_capacity_hot(self) -> None:
        """Hot preset 기본 용량 (4GB)."""
        capacity = TestPreset.HOT.get_default_capacity(drive_capacity_gb=128)
        assert capacity == TestCapacity.GB_4

    def test_get_default_capacity_full(self) -> None:
        """Full preset 기본 용량 (드라이브 용량 근사치)."""
        capacity = TestPreset.FULL.get_default_capacity(drive_capacity_gb=120)
        assert capacity == TestCapacity.GB_64  # 64GB는 120GB 이하의 가장 큰 용량


class TestTestCapacity:
    """TestCapacity enum 테스트."""

    def test_from_drive_capacity(self) -> None:
        """드라이브 용량에서 근사치 찾기."""
        # Exact matches
        assert TestCapacity.from_drive_capacity(32) == TestCapacity.GB_32
        assert TestCapacity.from_drive_capacity(64) == TestCapacity.GB_64

        # Approximate matches (find largest that fits)
        assert TestCapacity.from_drive_capacity(50) == TestCapacity.GB_32
        assert TestCapacity.from_drive_capacity(120) == TestCapacity.GB_64
        assert TestCapacity.from_drive_capacity(500) == TestCapacity.GB_256
        assert TestCapacity.from_drive_capacity(1000) == TestCapacity.GB_512
        assert TestCapacity.from_drive_capacity(2000) == TestCapacity.TB_1

    def test_to_gb(self) -> None:
        """용량을 GB로 변환."""
        assert TestCapacity.GB_1.to_gb() == 1.0
        assert TestCapacity.GB_4.to_gb() == 4.0
        assert TestCapacity.GB_32.to_gb() == 32.0
        assert TestCapacity.TB_1.to_gb() == 1024.0
