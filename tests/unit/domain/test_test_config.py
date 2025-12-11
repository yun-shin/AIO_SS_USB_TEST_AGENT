"""Tests for TestConfig Model."""

import pytest
from domain.models import TestConfig
from config.constants import TestCapacity, TestMethod, TestType, VendorId


class TestTestConfig:
    """TestConfig 모델 테스트."""

    def test_create_valid_config(self, sample_test_config: TestConfig) -> None:
        """유효한 설정 생성 테스트."""
        assert sample_test_config.slot_idx == 0
        assert sample_test_config.jira_no == "TEST-123"
        assert sample_test_config.capacity == TestCapacity.GB_32
        assert sample_test_config.is_valid()

    def test_validate_invalid_slot_idx(self) -> None:
        """잘못된 slot_idx 검증 테스트."""
        config = TestConfig(
            slot_idx=5,  # Invalid: should be 0-3
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            capacity=TestCapacity.GB_32,
            drive="E",
            method=TestMethod.ZERO_HR,
            test_type=TestType.FULL_PHOTO,
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
            capacity=TestCapacity.GB_32,
            drive="E",
            method=TestMethod.ZERO_HR,
            test_type=TestType.FULL_PHOTO,
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
            capacity=TestCapacity.GB_32,
            drive="",  # Invalid: empty
            method=TestMethod.ZERO_HR,
            test_type=TestType.FULL_PHOTO,
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
            capacity=TestCapacity.GB_32,
            drive="E",
            method=TestMethod.ZERO_HR,
            test_type=TestType.HOT_PHOTO,
            loop_count=10,
        )
        assert config_hot.is_hot_test()

        config_full = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            capacity=TestCapacity.GB_32,
            drive="E",
            method=TestMethod.ZERO_HR,
            test_type=TestType.FULL_PHOTO,
            loop_count=10,
        )
        assert not config_full.is_hot_test()

    def test_get_test_file(self) -> None:
        """테스트 파일 타입 반환 테스트."""
        config_photo = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            capacity=TestCapacity.GB_32,
            drive="E",
            method=TestMethod.ZERO_HR,
            test_type=TestType.FULL_PHOTO,
            loop_count=10,
        )
        assert config_photo.get_test_file() == "Photo"

        config_mp3 = TestConfig(
            slot_idx=0,
            jira_no="TEST-123",
            sample_no="SAMPLE_001",
            capacity=TestCapacity.GB_32,
            drive="E",
            method=TestMethod.ZERO_HR,
            test_type=TestType.FULL_MP3,
            loop_count=10,
        )
        assert config_mp3.get_test_file() == "MP3"

    def test_to_dict_and_from_dict(self, sample_test_config: TestConfig) -> None:
        """딕셔너리 변환 테스트."""
        config_dict = sample_test_config.to_dict()
        restored = TestConfig.from_dict(config_dict)

        assert restored.slot_idx == sample_test_config.slot_idx
        assert restored.jira_no == sample_test_config.jira_no
        assert restored.capacity == sample_test_config.capacity
        assert restored.drive == sample_test_config.drive
        assert restored.method == sample_test_config.method
        assert restored.test_type == sample_test_config.test_type
        assert restored.loop_count == sample_test_config.loop_count
