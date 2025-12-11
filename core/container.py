"""Dependency Injection Container.

A simple DI container that facilitates Mock injection during testing.
"""

from typing import Any, Callable, TypeVar, Generic, Optional
from dataclasses import dataclass, field

T = TypeVar("T")


@dataclass
class Dependency(Generic[T]):
    """Dependency definition.

    Attributes:
        factory: Instance creation factory.
        singleton: Whether singleton.
        instance: Cached instance.
    """

    factory: Callable[..., T]
    singleton: bool = True
    instance: Optional[T] = field(default=None, repr=False)


class Container:
    """Dependency injection container.

    Handles service registration and resolution.
    Can be easily replaced with Mock during testing.

    Example:
        ```python
        # Production setup
        container = Container()
        container.register(IWindowFinder, PywinautoWindowFinder)
        container.register(IWebSocketClient, WebSocketClient)

        # Test setup
        test_container = Container()
        test_container.register(IWindowFinder, lambda: MockWindowFinder())
        test_container.register(IWebSocketClient, lambda: MockWebSocketClient())

        # Use service
        finder = container.resolve(IWindowFinder)
        ```
    """

    def __init__(self) -> None:
        """Initialize container."""
        self._dependencies: dict[type, Dependency] = {}
        self._overrides: dict[type, Any] = {}

    def register(
        self,
        interface: type[T],
        factory: Callable[..., T] | type[T],
        singleton: bool = True,
    ) -> "Container":
        """Register dependency.

        Args:
            interface: Interface type.
            factory: Instance creation factory or class.
            singleton: Whether singleton (default: True).

        Returns:
            self (for method chaining).
        """
        if isinstance(factory, type):
            # 클래스인 경우 람다로 래핑
            cls = factory
            factory = lambda: cls()

        self._dependencies[interface] = Dependency(
            factory=factory,
            singleton=singleton,
        )
        return self

    def register_instance(
        self,
        interface: type[T],
        instance: T,
    ) -> "Container":
        """Register instance directly.

        Args:
            interface: Interface type.
            instance: Instance to register.

        Returns:
            self.
        """
        self._dependencies[interface] = Dependency(
            factory=lambda: instance,
            singleton=True,
            instance=instance,
        )
        return self

    def resolve(self, interface: type[T]) -> T:
        """Resolve dependency.

        Args:
            interface: Interface type.

        Returns:
            Resolved instance.

        Raises:
            KeyError: Unregistered dependency.
        """
        # Override가 있으면 우선 반환
        if interface in self._overrides:
            return self._overrides[interface]

        if interface not in self._dependencies:
            raise KeyError(
                f"Dependency not registered: {interface.__name__}. "
                f"Call container.register({interface.__name__}, ...) first."
            )

        dep = self._dependencies[interface]

        if dep.singleton and dep.instance is not None:
            return dep.instance

        instance = dep.factory()

        if dep.singleton:
            dep.instance = instance

        return instance

    def override(self, interface: type[T], instance: T) -> "Container":
        """Override dependency (for testing).

        Use a different instance temporarily while keeping existing registration.

        Args:
            interface: Interface type.
            instance: Instance to override with.

        Returns:
            self.
        """
        self._overrides[interface] = instance
        return self

    def clear_override(self, interface: type[T]) -> "Container":
        """Clear override.

        Args:
            interface: Interface type.

        Returns:
            self.
        """
        self._overrides.pop(interface, None)
        return self

    def clear_all_overrides(self) -> "Container":
        """Clear all overrides.

        Returns:
            self.
        """
        self._overrides.clear()
        return self

    def reset(self) -> "Container":
        """Reset container.

        Removes all dependencies and overrides.

        Returns:
            self.
        """
        self._dependencies.clear()
        self._overrides.clear()
        return self

    def has(self, interface: type) -> bool:
        """Check if dependency is registered.

        Args:
            interface: Interface type.

        Returns:
            Whether registered.
        """
        return interface in self._dependencies or interface in self._overrides


# Global container instance
_container: Optional[Container] = None


def get_container() -> Container:
    """Get global container.

    Returns:
        Container instance.
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


def set_container(container: Container) -> None:
    """Set global container (for testing).

    Args:
        container: Container to set.
    """
    global _container
    _container = container


def reset_container() -> None:
    """Reset global container."""
    global _container
    _container = None
