"""DI Container Unit Tests.

Container 클래스의 단위 테스트입니다.
"""

import pytest

from src.core.container import (
    Container,
    get_container,
    set_container,
    reset_container,
)
from src.core.protocols import IClock, IStateStore


class FakeService:
    """테스트용 가짜 서비스."""

    def __init__(self, value: int = 0):
        self.value = value


class TestContainerRegistration:
    """Container 등록 테스트."""

    def test_register_and_resolve(self):
        """등록 및 해결 테스트."""
        # Given
        container = Container()
        container.register(FakeService, lambda: FakeService(42))

        # When
        service = container.resolve(FakeService)

        # Then
        assert isinstance(service, FakeService)
        assert service.value == 42

    def test_register_class_directly(self):
        """클래스 직접 등록 테스트."""
        # Given
        container = Container()
        container.register(FakeService, FakeService)

        # When
        service = container.resolve(FakeService)

        # Then
        assert isinstance(service, FakeService)
        assert service.value == 0  # 기본값

    def test_register_instance(self):
        """인스턴스 직접 등록 테스트."""
        # Given
        container = Container()
        instance = FakeService(100)
        container.register_instance(FakeService, instance)

        # When
        resolved = container.resolve(FakeService)

        # Then
        assert resolved is instance

    def test_unregistered_dependency_raises(self):
        """등록되지 않은 의존성 해결 시 예외."""
        # Given
        container = Container()

        # When/Then
        with pytest.raises(KeyError) as exc_info:
            container.resolve(FakeService)

        assert "FakeService" in str(exc_info.value)


class TestContainerSingleton:
    """Container 싱글톤 동작 테스트."""

    def test_singleton_returns_same_instance(self):
        """싱글톤 등록 시 동일 인스턴스 반환."""
        # Given
        container = Container()
        container.register(FakeService, FakeService, singleton=True)

        # When
        first = container.resolve(FakeService)
        second = container.resolve(FakeService)

        # Then
        assert first is second

    def test_non_singleton_returns_different_instances(self):
        """비-싱글톤 등록 시 다른 인스턴스 반환."""
        # Given
        container = Container()
        container.register(FakeService, FakeService, singleton=False)

        # When
        first = container.resolve(FakeService)
        second = container.resolve(FakeService)

        # Then
        assert first is not second


class TestContainerOverride:
    """Container 오버라이드 테스트."""

    def test_override_replaces_dependency(self):
        """오버라이드가 의존성을 대체."""
        # Given
        container = Container()
        container.register(FakeService, lambda: FakeService(1))

        override_instance = FakeService(999)
        container.override(FakeService, override_instance)

        # When
        resolved = container.resolve(FakeService)

        # Then
        assert resolved is override_instance
        assert resolved.value == 999

    def test_clear_override_restores_original(self):
        """오버라이드 해제 후 원래 의존성 복원."""
        # Given
        container = Container()
        container.register(FakeService, lambda: FakeService(1))
        container.override(FakeService, FakeService(999))

        # When
        container.clear_override(FakeService)
        resolved = container.resolve(FakeService)

        # Then
        assert resolved.value == 1

    def test_clear_all_overrides(self):
        """모든 오버라이드 해제."""
        # Given
        container = Container()
        container.register(FakeService, lambda: FakeService(1))
        container.override(FakeService, FakeService(999))

        # When
        container.clear_all_overrides()
        resolved = container.resolve(FakeService)

        # Then
        assert resolved.value == 1


class TestContainerMethodChaining:
    """Container 메서드 체이닝 테스트."""

    def test_chaining_registration(self):
        """메서드 체이닝으로 등록."""
        # Given/When
        container = (
            Container()
            .register(FakeService, FakeService)
            .register_instance(str, "test")
        )

        # Then
        assert container.resolve(FakeService) is not None
        assert container.resolve(str) == "test"


class TestContainerHas:
    """Container has 메서드 테스트."""

    def test_has_registered(self):
        """등록된 의존성 확인."""
        # Given
        container = Container()
        container.register(FakeService, FakeService)

        # When/Then
        assert container.has(FakeService) is True
        assert container.has(str) is False

    def test_has_with_override(self):
        """오버라이드된 의존성도 has=True."""
        # Given
        container = Container()
        container.override(FakeService, FakeService())

        # When/Then
        assert container.has(FakeService) is True


class TestGlobalContainer:
    """글로벌 컨테이너 테스트."""

    def test_get_container_creates_singleton(self):
        """글로벌 컨테이너는 싱글톤."""
        # Given
        reset_container()

        # When
        first = get_container()
        second = get_container()

        # Then
        assert first is second

    def test_set_container_replaces_global(self):
        """set_container로 글로벌 컨테이너 교체."""
        # Given
        reset_container()
        custom_container = Container()

        # When
        set_container(custom_container)

        # Then
        assert get_container() is custom_container

        # Cleanup
        reset_container()

    def test_reset_container_clears_global(self):
        """reset_container로 글로벌 컨테이너 초기화."""
        # Given
        get_container()  # 생성

        # When
        reset_container()
        new_container = get_container()

        # Then: 새 컨테이너 생성됨
        assert new_container is not None
