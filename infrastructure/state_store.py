"""In-Memory State Store Implementation.

Memory-based implementation of the IStateStore protocol.
"""

from typing import Any, Optional
from threading import Lock
from dataclasses import dataclass, field
from datetime import datetime

from core.protocols import IStateStore


@dataclass
class SlotState:
    """Slot state."""

    slot_idx: int
    status: str = "idle"
    progress: float = 0.0
    current_phase: Optional[str] = None
    test_id: Optional[str] = None
    error_message: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "slot_idx": self.slot_idx,
            "status": self.status,
            "progress": self.progress,
            "current_phase": self.current_phase,
            "test_id": self.test_id,
            "error_message": self.error_message,
            "last_updated": self.last_updated.isoformat(),
        }


class InMemoryStateStore(IStateStore):
    """In-memory state store.

    A thread-safe state store.

    Example:
        ```python
        store = InMemoryStateStore(max_slots=16)

        # Set state
        store.set_slot_state(0, {"status": "running", "progress": 50.0})

        # Get state
        state = store.get_slot_state(0)
        print(state["status"])  # "running"
        ```
    """

    def __init__(self, max_slots: int = 16) -> None:
        """Initialize store.

        Args:
            max_slots: Maximum number of slots.
        """
        self._max_slots = max_slots
        self._states: dict[int, SlotState] = {}
        self._lock = Lock()

        # 초기 상태 설정
        for i in range(max_slots):
            self._states[i] = SlotState(slot_idx=i)

    def get_slot_state(self, slot_idx: int) -> Optional[dict[str, Any]]:
        """Get slot state.

        Args:
            slot_idx: Slot index.

        Returns:
            State dictionary or None.
        """
        with self._lock:
            state = self._states.get(slot_idx)
            return state.to_dict() if state else None

    def set_slot_state(self, slot_idx: int, state: dict[str, Any]) -> None:
        """Set slot state.

        Args:
            slot_idx: Slot index.
            state: State dictionary.
        """
        if slot_idx < 0 or slot_idx >= self._max_slots:
            raise ValueError(f"Invalid slot index: {slot_idx}")

        with self._lock:
            current = self._states.get(slot_idx) or SlotState(slot_idx=slot_idx)

            # 업데이트할 필드만 변경
            if "status" in state:
                current.status = state["status"]
            if "progress" in state:
                current.progress = state["progress"]
            if "current_phase" in state:
                current.current_phase = state["current_phase"]
            if "test_id" in state:
                current.test_id = state["test_id"]
            if "error_message" in state:
                current.error_message = state["error_message"]

            current.last_updated = datetime.now()
            self._states[slot_idx] = current

    def get_all_states(self) -> dict[int, dict[str, Any]]:
        """Get all states.

        Returns:
            Dictionary of states by slot.
        """
        with self._lock:
            return {idx: state.to_dict() for idx, state in self._states.items()}

    def reset_slot(self, slot_idx: int) -> None:
        """Reset slot state.

        Args:
            slot_idx: Slot index.
        """
        with self._lock:
            self._states[slot_idx] = SlotState(slot_idx=slot_idx)

    def reset_all(self) -> None:
        """Reset all slot states."""
        with self._lock:
            for i in range(self._max_slots):
                self._states[i] = SlotState(slot_idx=i)


class FakeStateStore(IStateStore):
    """Fake state store for testing.

    Tracks call history for verification in tests.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._states: dict[int, dict[str, Any]] = {}
        self._get_calls: list[int] = []
        self._set_calls: list[tuple[int, dict[str, Any]]] = []

    def get_slot_state(self, slot_idx: int) -> Optional[dict[str, Any]]:
        """Get slot state."""
        self._get_calls.append(slot_idx)
        return self._states.get(slot_idx)

    def set_slot_state(self, slot_idx: int, state: dict[str, Any]) -> None:
        """Set slot state."""
        self._set_calls.append((slot_idx, state.copy()))
        self._states[slot_idx] = state

    def get_all_states(self) -> dict[int, dict[str, Any]]:
        """Get all states."""
        return self._states.copy()

    @property
    def get_calls(self) -> list[int]:
        """get_slot_state call history."""
        return self._get_calls

    @property
    def set_calls(self) -> list[tuple[int, dict[str, Any]]]:
        """set_slot_state call history."""
        return self._set_calls

    def clear_calls(self) -> None:
        """Clear call history."""
        self._get_calls.clear()
        self._set_calls.clear()
