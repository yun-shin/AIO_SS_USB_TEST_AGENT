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
        """[TC-CONFIG-001] 유효 설정 생성 - 기본 필수 필드가 정상 저장된다.

        테스트 목적:
            샘플 설정으로 생성된 TestConfig가 필수 필드와 유효성 검사를 통과하는지 검증한다.

        테스트 시나리오:
            Given: slot_idx/용량/프리셋/파일 타입 등이 채워진 sample_test_config가 있고
            When: 해당 객체의 필드를 조회하고 is_valid를 호출하면
            Then: 필드 값이 기대대로 저장되고 is_valid가 True를 반환한다

        Notes:
            없음
        """
        assert sample_test_config.slot_idx == 0
        assert sample_test_config.jira_no == "TEST-123"
        assert sample_test_config.capacity == TestCapacity.GB_32
        assert sample_test_config.test_preset == TestPreset.FULL
        assert sample_test_config.test_file == TestFile.PHOTO
        assert sample_test_config.is_valid()

    def test_validate_invalid_slot_idx(self) -> None:
        """[TC-CONFIG-002] 슬롯 인덱스 검증 - 범위 밖이면 에러를 반환한다.

        테스트 목적:
            slot_idx가 0~3 범위를 벗어나면 validate가 오류를 보고하는지 확인한다.

        테스트 시나리오:
            Given: slot_idx=5로 설정된 TestConfig를 생성하고
            When: validate를 호출하면
            Then: 반환된 에러 목록에 slot_idx 관련 메시지가 포함된다

        Notes:
            없음
        """
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
        """[TC-CONFIG-003] 루프 횟수 검증 - 0이면 에러를 반환한다.

        테스트 목적:
            loop_count가 1 미만일 때 validate가 오류를 보고하는지 검증한다.

        테스트 시나리오:
            Given: loop_count=0으로 설정된 TestConfig를 생성하고
            When: validate를 호출하면
            Then: 반환된 에러 목록에 loop_count 관련 메시지가 포함된다

        Notes:
            없음
        """
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
        """[TC-CONFIG-004] 드라이브 누락 검증 - 공백이면 에러를 반환한다.

        테스트 목적:
            drive 값이 비어 있을 때 validate가 오류를 반환하는지 확인한다.

        테스트 시나리오:
            Given: drive가 빈 문자열인 TestConfig를 생성하고
            When: validate를 호출하면
            Then: 반환된 에러 목록에 drive 관련 메시지가 포함된다

        Notes:
            없음
        """
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
        """[TC-CONFIG-005] 핫/풀 프리셋 판별 - 프리셋에 따라 결과가 달라진다.

        테스트 목적:
            test_preset 값에 따라 is_hot_test 반환값이 올바른지 검증한다.

        테스트 시나리오:
            Given: HOT 프리셋 구성과 FULL 프리셋 구성을 준비하고
            When: 각 인스턴스에서 is_hot_test를 호출하면
            Then: HOT은 True, FULL은 False를 반환한다

        Notes:
            없음
        """
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
        """[TC-CONFIG-006] 테스트 파일 이름 변환 - Enum이 문자열로 반환된다.

        테스트 목적:
            test_file Enum 값이 API 호환 문자열로 변환되는지 검증한다.

        테스트 시나리오:
            Given: PHOTO와 MP3로 설정된 두 TestConfig 인스턴스가 있고
            When: get_test_file_value를 호출하면
            Then: PHOTO는 \"Photo\", MP3는 \"MP3\" 문자열을 반환한다

        Notes:
            없음
        """
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
        """[TC-CONFIG-007] Precondition 여부 결정 - 옵션과 프리셋에 따라 달라진다.

        테스트 목적:
            HOT 프리셋일 때 precondition.enabled 값에 따라 needs_precondition 결과가 변하는지 검증한다.

        테스트 시나리오:
            Given: HOT 프리셋에서 precondition enabled/disabled 구성과 FULL 프리셋 구성을 준비하고
            When: 각 인스턴스에서 needs_precondition을 호출하면
            Then: HOT+enabled만 True, 나머지는 False를 반환한다

        Notes:
            없음
        """
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
        """[TC-CONFIG-008] 직렬화 왕복 - dict 변환 후 복원 시 값이 유지된다.

        테스트 목적:
            to_dict와 from_dict를 거쳐도 설정 필드가 손실 없이 복원되는지 검증한다.

        테스트 시나리오:
            Given: 필드가 채워진 sample_test_config가 있고
            When: to_dict 후 from_dict로 복원하면
            Then: 슬롯, 용량, 프리셋, 파일 타입, 루프 수 등이 모두 동일하게 복원된다

        Notes:
            없음
        """
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
        """[TC-PRESET-001] HOT 여부 판별 - Enum 메서드가 프리셋에 맞춰 반환한다.

        테스트 목적:
            TestPreset Enum의 is_hot_test가 HOT에서 True, FULL에서 False를 반환하는지 검증한다.

        테스트 시나리오:
            Given: TestPreset.HOT과 TestPreset.FULL Enum 값이 있고
            When: 각 값에서 is_hot_test를 호출하면
            Then: HOT은 True, FULL은 False를 반환한다

        Notes:
            없음
        """
        assert TestPreset.HOT.is_hot_test()
        assert not TestPreset.FULL.is_hot_test()

    def test_get_default_capacity_hot(self) -> None:
        """[TC-PRESET-002] HOT 기본 용량 - 고정 4GB를 반환한다.

        테스트 목적:
            HOT 프리셋에서 drive_capacity_gb와 무관하게 4GB 용량을 반환하는지 확인한다.

        테스트 시나리오:
            Given: drive_capacity_gb=128 값을 전달하고
            When: TestPreset.HOT.get_default_capacity를 호출하면
            Then: 항상 TestCapacity.GB_4를 반환한다

        Notes:
            없음
        """
        capacity = TestPreset.HOT.get_default_capacity(drive_capacity_gb=128)
        assert capacity == TestCapacity.GB_4

    def test_get_default_capacity_full(self) -> None:
        """[TC-PRESET-003] FULL 기본 용량 - 드라이브 용량에 가장 가까운 Enum을 고른다.

        테스트 목적:
            FULL 프리셋에서 drive_capacity_gb에 근사한 TestCapacity를 선택하는 로직을 검증한다.

        테스트 시나리오:
            Given: drive_capacity_gb=120을 전달하고
            When: TestPreset.FULL.get_default_capacity를 호출하면
            Then: 120GB와 가장 가까운 TestCapacity.GB_128을 반환한다

        Notes:
            없음
        """
        # from_drive_capacity는 가장 가까운 값을 찾음
        # 120GB → 128GB (|120-128|=8 < |120-64|=56)
        capacity = TestPreset.FULL.get_default_capacity(drive_capacity_gb=120)
        assert capacity == TestCapacity.GB_128  # 120에서 가장 가까운 값


class TestTestCapacity:
    """TestCapacity enum 테스트."""

    def test_from_drive_capacity(self) -> None:
        """[TC-CAPACITY-001] 드라이브 용량 매핑 - 가장 가까운 표준 용량을 선택한다.

        테스트 목적:
            from_drive_capacity가 입력 용량과 가장 가까운 TestCapacity Enum을 반환하는지 검증한다.

        테스트 시나리오:
            Given: 32, 64, 50, 120, 500, 1000, 2000 GB 등의 값을 전달하고
            When: from_drive_capacity를 호출하면
            Then: 각 값에 대해 가장 근접한 Enum(TestCapacity.GB_32, GB_64, GB_128, GB_512, TB_1 등)을 반환한다

        Notes:
            없음
        """
        # Exact matches
        assert TestCapacity.from_drive_capacity(32) == TestCapacity.GB_32
        assert TestCapacity.from_drive_capacity(64) == TestCapacity.GB_64

        # from_drive_capacity는 가장 가까운 값(최소 차이)을 찾음
        # 50GB: |50-32|=18, |50-64|=14 → 64GB
        assert TestCapacity.from_drive_capacity(50) == TestCapacity.GB_64
        # 120GB: |120-64|=56, |120-128|=8 → 128GB
        assert TestCapacity.from_drive_capacity(120) == TestCapacity.GB_128
        # 500GB: |500-256|=244, |500-512|=12 → 512GB
        assert TestCapacity.from_drive_capacity(500) == TestCapacity.GB_512
        # 1000GB: |1000-512|=488, |1000-1024|=24 → 1TB
        assert TestCapacity.from_drive_capacity(1000) == TestCapacity.TB_1
        # 2000GB: |2000-1024|=976 (1TB가 최대) → 1TB
        assert TestCapacity.from_drive_capacity(2000) == TestCapacity.TB_1

    def test_to_gb(self) -> None:
        """[TC-CAPACITY-002] 용량 단위 변환 - Enum 값을 GB 부동소수로 변환한다.

        테스트 목적:
            TestCapacity Enum의 to_gb가 정해진 GB 값을 반환하는지 검증한다.

        테스트 시나리오:
            Given: 1GB, 4GB, 32GB, 1TB Enum 값을 준비하고
            When: 각 값에서 to_gb를 호출하면
            Then: 1.0, 4.0, 32.0, 1024.0을 반환한다

        Notes:
            없음
        """
        assert TestCapacity.GB_1.to_gb() == 1.0
        assert TestCapacity.GB_4.to_gb() == 4.0
        assert TestCapacity.GB_32.to_gb() == 32.0
        assert TestCapacity.TB_1.to_gb() == 1024.0
