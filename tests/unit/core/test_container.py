"""DI Container Unit Tests."""

import pytest

from core.container import (
    Container,
    get_container,
    set_container,
    reset_container,
)
from core.protocols import IClock, IStateStore


class FakeService:
    """테스트용 가짜 서비스"""

    def __init__(self, value: int = 0):
        self.value = value


class TestContainerRegistration:
    """Container 등록 테스트"""

    def test_register_and_resolve(self) -> None:
        """[TC-CONTAINER-001] 등록 후 resolve - 의존성이 정상 반환된다.

        테스트 목적:
            register로 등록한 팩토리가 resolve 호출 시 올바른 인스턴스를 반환하는지 확인한다.

        테스트 시나리오:
            Given: FakeService를 반환하는 팩토리로 Container에 등록하고
            When: resolve(FakeService)를 호출하면
            Then: FakeService 인스턴스가 반환되고 내부 값이 기대치(42)다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, lambda: FakeService(42))

        service = container.resolve(FakeService)

        assert isinstance(service, FakeService)
        assert service.value == 42

    def test_register_class_directly(self) -> None:
        """[TC-CONTAINER-002] 클래스 직접 등록 - 기본 생성자로 인스턴스화된다.

        테스트 목적:
            클래스를 직접 등록했을 때 resolve가 기본 생성자로 인스턴스를 만드는지 검증한다.

        테스트 시나리오:
            Given: FakeService 클래스를 Container에 register 하고
            When: resolve(FakeService)를 호출하면
            Then: 기본 value=0을 가진 FakeService 인스턴스를 반환한다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, FakeService)

        service = container.resolve(FakeService)

        assert isinstance(service, FakeService)
        assert service.value == 0

    def test_register_instance(self) -> None:
        """[TC-CONTAINER-003] 인스턴스 등록 - 등록한 객체를 그대로 반환한다.

        테스트 목적:
            register_instance로 등록한 동일 객체가 resolve 시 그대로 반환되는지 확인한다.

        테스트 시나리오:
            Given: value=100인 FakeService 인스턴스를 register_instance로 등록하고
            When: resolve(FakeService)를 호출하면
            Then: 같은 객체 인스턴스가 반환된다

        Notes:
            None
        """
        container = Container()
        instance = FakeService(100)
        container.register_instance(FakeService, instance)

        resolved = container.resolve(FakeService)

        assert resolved is instance

    def test_unregistered_dependency_raises(self) -> None:
        """[TC-CONTAINER-004] 미등록 의존성 - resolve 시 KeyError를 발생시킨다.

        테스트 목적:
            등록되지 않은 타입을 resolve하면 KeyError가 발생하는지 검증한다.

        테스트 시나리오:
            Given: 아무 것도 등록되지 않은 Container가 있고
            When: resolve(FakeService)를 호출하면
            Then: KeyError가 발생하고 메시지에 타입명이 포함된다

        Notes:
            None
        """
        container = Container()

        with pytest.raises(KeyError) as exc_info:
            container.resolve(FakeService)

        assert "FakeService" in str(exc_info.value)


class TestContainerSingleton:
    """Container 싱글톤 설정 테스트"""

    def test_singleton_returns_same_instance(self) -> None:
        """[TC-CONTAINER-005] 싱글톤 반환 - resolve 시 동일 인스턴스를 준다.

        테스트 목적:
            singleton=True로 등록하면 resolve가 항상 같은 객체를 반환하는지 확인한다.

        테스트 시나리오:
            Given: FakeService를 singleton=True로 등록하고
            When: 두 번 resolve를 호출하면
            Then: 동일 객체가 반환된다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, FakeService, singleton=True)

        first = container.resolve(FakeService)
        second = container.resolve(FakeService)

        assert first is second

    def test_non_singleton_returns_different_instances(self) -> None:
        """[TC-CONTAINER-006] 비싱글톤 반환 - 매 호출마다 새 인스턴스를 준다.

        테스트 목적:
            singleton=False로 등록하면 resolve가 매번 새로운 객체를 반환하는지 검증한다.

        테스트 시나리오:
            Given: FakeService를 singleton=False로 등록하고
            When: 두 번 resolve를 호출하면
            Then: 서로 다른 인스턴스를 반환한다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, FakeService, singleton=False)

        first = container.resolve(FakeService)
        second = container.resolve(FakeService)

        assert first is not second


class TestContainerOverride:
    """Container 오버라이드 테스트"""

    def test_override_replaces_dependency(self) -> None:
        """[TC-CONTAINER-007] 오버라이드 적용 - 등록된 의존성을 교체한다.

        테스트 목적:
            override로 등록된 객체가 기존 등록을 대체하는지 확인한다.

        테스트 시나리오:
            Given: value=1 팩토리로 등록 후 override로 value=999 인스턴스를 넣고
            When: resolve(FakeService)를 호출하면
            Then: override된 인스턴스가 반환되고 value가 999다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, lambda: FakeService(1))

        override_instance = FakeService(999)
        container.override(FakeService, override_instance)

        resolved = container.resolve(FakeService)

        assert resolved is override_instance
        assert resolved.value == 999

    def test_clear_override_restores_original(self) -> None:
        """[TC-CONTAINER-008] 오버라이드 해제 - 원래 등록이 복원된다.

        테스트 목적:
            clear_override 호출 시 override 이전 등록이 다시 사용되는지 확인한다.

        테스트 시나리오:
            Given: value=1로 등록 후 override를 value=999로 적용하고
            When: clear_override를 호출한 뒤 resolve하면
            Then: value=1인 새 인스턴스가 반환된다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, lambda: FakeService(1))
        container.override(FakeService, FakeService(999))

        container.clear_override(FakeService)
        resolved = container.resolve(FakeService)

        assert resolved.value == 1

    def test_clear_all_overrides(self) -> None:
        """[TC-CONTAINER-009] 전체 오버라이드 해제 - 모든 대체 등록을 초기화한다.

        테스트 목적:
            clear_all_overrides가 모든 override를 제거하고 원래 등록을 사용하게 하는지 검증한다.

        테스트 시나리오:
            Given: value=1 팩토리 등록 후 override로 value=999 인스턴스를 넣고
            When: clear_all_overrides를 호출한 뒤 resolve하면
            Then: value=1인 인스턴스가 반환된다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, lambda: FakeService(1))
        container.override(FakeService, FakeService(999))

        container.clear_all_overrides()
        resolved = container.resolve(FakeService)

        assert resolved.value == 1


class TestContainerMethodChaining:
    """Container 메서드 체이닝 테스트"""

    def test_chaining_registration(self) -> None:
        """[TC-CONTAINER-010] 체이닝 등록 - 연속 register 호출이 가능하다.

        테스트 목적:
            register 반환값을 활용한 메서드 체이닝이 정상 동작하는지 확인한다.

        테스트 시나리오:
            Given: Container().register(...).register_instance(...) 체인을 구성하고
            When: resolve로 두 의존성을 조회하면
            Then: FakeService와 문자열이 기대대로 반환된다

        Notes:
            None
        """
        container = (
            Container()
            .register(FakeService, FakeService)
            .register_instance(str, "test")
        )

        assert container.resolve(FakeService) is not None
        assert container.resolve(str) == "test"


class TestContainerHas:
    """Container has 메서드 테스트"""

    def test_has_registered(self) -> None:
        """[TC-CONTAINER-011] 등록 여부 확인 - 등록된 타입만 True를 반환한다.

        테스트 목적:
            has 호출이 등록 여부에 따라 올바른 불린 값을 반환하는지 검증한다.

        테스트 시나리오:
            Given: FakeService만 등록된 Container에서
            When: has(FakeService)와 has(str)를 호출하면
            Then: FakeService는 True, str은 False를 반환한다

        Notes:
            None
        """
        container = Container()
        container.register(FakeService, FakeService)

        assert container.has(FakeService) is True
        assert container.has(str) is False

    def test_has_with_override(self) -> None:
        """[TC-CONTAINER-012] 오버라이드된 타입도 has가 True를 반환한다.

        테스트 목적:
            override로만 등록된 타입에 대해서도 has가 True인지 확인한다.

        테스트 시나리오:
            Given: override로 FakeService 인스턴스만 등록하고
            When: has(FakeService)를 호출하면
            Then: True를 반환한다

        Notes:
            None
        """
        container = Container()
        container.override(FakeService, FakeService())

        assert container.has(FakeService) is True


class TestGlobalContainer:
    """글로벌 컨테이너 테스트"""

    def test_get_container_creates_singleton(self) -> None:
        """[TC-CONTAINER-013] 글로벌 컨테이너 싱글톤 - get_container가 동일 인스턴스를 반환한다.

        테스트 목적:
            get_container가 싱글톤으로 전역 컨테이너를 반환하는지 검증한다.

        테스트 시나리오:
            Given: reset_container로 초기화한 뒤
            When: get_container를 두 번 호출하면
            Then: 같은 객체를 반환한다

        Notes:
            None
        """
        reset_container()

        first = get_container()
        second = get_container()

        assert first is second

    def test_set_container_replaces_global(self) -> None:
        """[TC-CONTAINER-014] 글로벌 교체 - set_container로 전역 컨테이너를 교체한다.

        테스트 목적:
            set_container 호출로 전역 컨테이너가 교체되는지 확인한다.

        테스트 시나리오:
            Given: reset_container 후 custom_container를 만들고
            When: set_container(custom_container)를 호출한 뒤 get_container를 부르면
            Then: 반환값이 custom_container와 동일하다

        Notes:
            None
        """
        reset_container()
        custom_container = Container()

        set_container(custom_container)

        assert get_container() is custom_container

        reset_container()

    def test_reset_container_clears_global(self) -> None:
        """[TC-CONTAINER-015] 글로벌 초기화 - reset_container가 새 컨테이너를 생성한다.

        테스트 목적:
            reset_container 호출 시 전역 컨테이너가 초기화되어 새 인스턴스를 반환하는지 검증한다.

        테스트 시나리오:
            Given: get_container로 전역을 생성한 뒤
            When: reset_container를 호출하고 다시 get_container를 호출하면
            Then: 이전과 다른 새 컨테이너 인스턴스가 반환된다

        Notes:
            None
        """
        first = get_container()

        reset_container()
        new_container = get_container()

        assert new_container is not first
