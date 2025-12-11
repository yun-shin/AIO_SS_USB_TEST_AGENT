"""Slot State Machine.

Finite State Machine (FSM) for managing test slot states.
Each slot has its own independent state machine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Callable, Optional

from domain.enums import ProcessState, TestPhase
from utils.logging import get_logger

logger = get_logger(__name__)


class SlotState(str, Enum):
    """Slot state enumeration.

    Represents the high-level state of a test slot.
    """

    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    PREPARING = "preparing"
    CONFIGURING = "configuring"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR = "error"


class SlotEvent(str, Enum):
    """Events that trigger state transitions."""

    # Connection events
    CONNECT = "connect"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTION_FAILED = "connection_failed"

    # Test lifecycle events
    START_TEST = "start_test"
    CONFIGURE = "configure"
    CONFIGURED = "configured"
    RUN = "run"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    STOPPED = "stopped"

    # Result events
    COMPLETE = "complete"
    FAIL = "fail"
    ERROR = "error"

    # Recovery events
    RESET = "reset"
    RETRY = "retry"


@dataclass
class Transition:
    """State transition definition.

    Attributes:
        from_state: Source state.
        event: Triggering event.
        to_state: Target state.
        guard: Optional condition function.
        action: Optional action to execute on transition.
    """

    from_state: SlotState
    event: SlotEvent
    to_state: SlotState
    guard: Optional[Callable[[], bool]] = None
    action: Optional[Callable[[], None]] = None


@dataclass
class SlotContext:
    """Context data for a slot.

    Contains runtime data associated with the slot's current operation.

    Attributes:
        slot_idx: Slot index.
        test_id: Current test ID.
        test_name: Current test name.
        process_state: USB Test process state.
        test_phase: Current test phase.
        current_loop: Current loop number.
        total_loop: Total loop count.
        started_at: Test start time.
        updated_at: Last update time.
        error_message: Last error message.
        error_count: Error occurrence count.
        retry_count: Retry count.
    """

    slot_idx: int
    test_id: Optional[str] = None
    test_name: Optional[str] = None
    process_state: ProcessState = ProcessState.IDLE
    test_phase: TestPhase = TestPhase.IDLE
    current_loop: int = 0
    total_loop: int = 0
    started_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    error_count: int = 0
    retry_count: int = 0

    def reset(self) -> "SlotContext":
        """Reset context to initial state.

        Returns:
            New SlotContext with reset values.
        """
        return SlotContext(
            slot_idx=self.slot_idx,
            updated_at=datetime.now(),
        )

    def update(self, **kwargs) -> "SlotContext":
        """Update context fields.

        Args:
            **kwargs: Fields to update.

        Returns:
            New SlotContext with updated values.
        """
        return SlotContext(
            slot_idx=kwargs.get("slot_idx", self.slot_idx),
            test_id=kwargs.get("test_id", self.test_id),
            test_name=kwargs.get("test_name", self.test_name),
            process_state=kwargs.get("process_state", self.process_state),
            test_phase=kwargs.get("test_phase", self.test_phase),
            current_loop=kwargs.get("current_loop", self.current_loop),
            total_loop=kwargs.get("total_loop", self.total_loop),
            started_at=kwargs.get("started_at", self.started_at),
            updated_at=datetime.now(),
            error_message=kwargs.get("error_message", self.error_message),
            error_count=kwargs.get("error_count", self.error_count),
            retry_count=kwargs.get("retry_count", self.retry_count),
        )

    def get_progress_percent(self) -> float:
        """Calculate progress percentage.

        Returns:
            Progress percentage (0.0 ~ 100.0).
        """
        if self.total_loop == 0:
            return 0.0
        return (self.current_loop / self.total_loop) * 100.0

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Context as dictionary.
        """
        return {
            "slot_idx": self.slot_idx,
            "test_id": self.test_id,
            "test_name": self.test_name,
            "process_state": self.process_state.value,
            "process_state_name": self.process_state.name,
            "test_phase": self.test_phase.value,
            "test_phase_name": self.test_phase.name,
            "current_loop": self.current_loop,
            "total_loop": self.total_loop,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat(),
            "progress_percent": self.get_progress_percent(),
            "error_message": self.error_message,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
        }


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(
        self,
        current_state: SlotState,
        event: SlotEvent,
        slot_idx: int,
    ) -> None:
        self.current_state = current_state
        self.event = event
        self.slot_idx = slot_idx
        super().__init__(
            f"Invalid transition: {current_state.value} + {event.value} "
            f"(slot {slot_idx})"
        )


class SlotStateMachine:
    """Finite State Machine for a single test slot.

    Manages state transitions and ensures valid state changes.

    Attributes:
        slot_idx: Slot index.
        state: Current state.
        context: Slot context data.
        history: State transition history.
    """

    # Valid state transitions
    TRANSITIONS: list[Transition] = [
        # Idle transitions
        Transition(SlotState.IDLE, SlotEvent.CONNECT, SlotState.CONNECTING),
        Transition(SlotState.IDLE, SlotEvent.START_TEST, SlotState.PREPARING),
        Transition(SlotState.IDLE, SlotEvent.RESET, SlotState.IDLE),

        # Connecting transitions
        Transition(SlotState.CONNECTING, SlotEvent.CONNECTED, SlotState.READY),
        Transition(SlotState.CONNECTING, SlotEvent.CONNECTION_FAILED, SlotState.ERROR),
        Transition(SlotState.CONNECTING, SlotEvent.DISCONNECTED, SlotState.IDLE),

        # Ready transitions
        Transition(SlotState.READY, SlotEvent.START_TEST, SlotState.PREPARING),
        Transition(SlotState.READY, SlotEvent.DISCONNECTED, SlotState.IDLE),
        Transition(SlotState.READY, SlotEvent.RESET, SlotState.IDLE),

        # Preparing transitions
        Transition(SlotState.PREPARING, SlotEvent.CONFIGURE, SlotState.CONFIGURING),
        Transition(SlotState.PREPARING, SlotEvent.FAIL, SlotState.FAILED),
        Transition(SlotState.PREPARING, SlotEvent.ERROR, SlotState.ERROR),
        Transition(SlotState.PREPARING, SlotEvent.STOP, SlotState.STOPPING),

        # Configuring transitions
        Transition(SlotState.CONFIGURING, SlotEvent.CONFIGURED, SlotState.READY),
        Transition(SlotState.CONFIGURING, SlotEvent.RUN, SlotState.RUNNING),
        Transition(SlotState.CONFIGURING, SlotEvent.FAIL, SlotState.FAILED),
        Transition(SlotState.CONFIGURING, SlotEvent.ERROR, SlotState.ERROR),
        Transition(SlotState.CONFIGURING, SlotEvent.STOP, SlotState.STOPPING),

        # Running transitions
        Transition(SlotState.RUNNING, SlotEvent.PAUSE, SlotState.PAUSED),
        Transition(SlotState.RUNNING, SlotEvent.STOP, SlotState.STOPPING),
        Transition(SlotState.RUNNING, SlotEvent.COMPLETE, SlotState.COMPLETED),
        Transition(SlotState.RUNNING, SlotEvent.FAIL, SlotState.FAILED),
        Transition(SlotState.RUNNING, SlotEvent.ERROR, SlotState.ERROR),
        Transition(SlotState.RUNNING, SlotEvent.DISCONNECTED, SlotState.ERROR),

        # Paused transitions
        Transition(SlotState.PAUSED, SlotEvent.RESUME, SlotState.RUNNING),
        Transition(SlotState.PAUSED, SlotEvent.STOP, SlotState.STOPPING),
        Transition(SlotState.PAUSED, SlotEvent.ERROR, SlotState.ERROR),

        # Stopping transitions
        Transition(SlotState.STOPPING, SlotEvent.STOPPED, SlotState.IDLE),
        Transition(SlotState.STOPPING, SlotEvent.ERROR, SlotState.ERROR),

        # Completed transitions
        Transition(SlotState.COMPLETED, SlotEvent.RESET, SlotState.IDLE),
        Transition(SlotState.COMPLETED, SlotEvent.START_TEST, SlotState.PREPARING),

        # Failed transitions
        Transition(SlotState.FAILED, SlotEvent.RESET, SlotState.IDLE),
        Transition(SlotState.FAILED, SlotEvent.RETRY, SlotState.PREPARING),
        Transition(SlotState.FAILED, SlotEvent.START_TEST, SlotState.PREPARING),

        # Error transitions
        Transition(SlotState.ERROR, SlotEvent.RESET, SlotState.IDLE),
        Transition(SlotState.ERROR, SlotEvent.RETRY, SlotState.IDLE),
        Transition(SlotState.ERROR, SlotEvent.START_TEST, SlotState.PREPARING),
    ]

    # Build transition lookup table
    _TRANSITION_MAP: dict[tuple[SlotState, SlotEvent], SlotState] = {
        (t.from_state, t.event): t.to_state for t in TRANSITIONS
    }

    def __init__(
        self,
        slot_idx: int,
        initial_state: SlotState = SlotState.IDLE,
        on_state_change: Optional[Callable[[int, SlotState, SlotState], None]] = None,
    ) -> None:
        """Initialize state machine.

        Args:
            slot_idx: Slot index.
            initial_state: Initial state.
            on_state_change: Callback for state changes (slot_idx, old_state, new_state).
        """
        self._slot_idx = slot_idx
        self._state = initial_state
        self._context = SlotContext(slot_idx=slot_idx)
        self._history: list[tuple[datetime, SlotState, SlotEvent, SlotState]] = []
        self._on_state_change = on_state_change

        logger.debug(
            "State machine initialized",
            slot_idx=slot_idx,
            initial_state=initial_state.value,
        )

    @property
    def slot_idx(self) -> int:
        """Slot index."""
        return self._slot_idx

    @property
    def state(self) -> SlotState:
        """Current state."""
        return self._state

    @property
    def context(self) -> SlotContext:
        """Slot context."""
        return self._context

    @property
    def history(self) -> list[tuple[datetime, SlotState, SlotEvent, SlotState]]:
        """State transition history."""
        return self._history.copy()

    def can_transition(self, event: SlotEvent) -> bool:
        """Check if a transition is valid.

        Args:
            event: Event to check.

        Returns:
            True if transition is valid.
        """
        return (self._state, event) in self._TRANSITION_MAP

    def get_valid_events(self) -> list[SlotEvent]:
        """Get list of valid events for current state.

        Returns:
            List of valid events.
        """
        return [
            event
            for (state, event) in self._TRANSITION_MAP.keys()
            if state == self._state
        ]

    def trigger(
        self,
        event: SlotEvent,
        context_update: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> SlotState:
        """Trigger a state transition.

        Args:
            event: Event to trigger.
            context_update: Optional context updates.
            error_message: Optional error message (for FAIL/ERROR events).

        Returns:
            New state after transition.

        Raises:
            InvalidTransitionError: If transition is invalid.
        """
        if not self.can_transition(event):
            raise InvalidTransitionError(self._state, event, self._slot_idx)

        old_state = self._state
        new_state = self._TRANSITION_MAP[(self._state, event)]

        # Update context
        update_data = context_update or {}
        if error_message:
            update_data["error_message"] = error_message
            update_data["error_count"] = self._context.error_count + 1

        if event == SlotEvent.START_TEST:
            update_data["started_at"] = datetime.now()
            # 에러/실패/완료 상태에서 재시작 시 이전 에러 정보 초기화
            if old_state in (SlotState.ERROR, SlotState.FAILED, SlotState.COMPLETED):
                update_data["error_message"] = None
                update_data["error_count"] = 0
                update_data["retry_count"] = 0
                update_data["current_loop"] = 0
        elif event in (SlotEvent.RESET, SlotEvent.STOPPED):
            self._context = self._context.reset()
            update_data = {}

        if update_data:
            self._context = self._context.update(**update_data)

        # Record history
        self._history.append((datetime.now(), old_state, event, new_state))

        # Limit history size
        if len(self._history) > 100:
            self._history = self._history[-50:]

        self._state = new_state

        logger.info(
            "State transition",
            slot_idx=self._slot_idx,
            old_state=old_state.value,
            event=event.value,
            new_state=new_state.value,
        )

        # Invoke callback
        if self._on_state_change:
            try:
                self._on_state_change(self._slot_idx, old_state, new_state)
            except Exception as e:
                logger.error(
                    "State change callback error",
                    slot_idx=self._slot_idx,
                    error=str(e),
                )

        return new_state

    def force_state(self, state: SlotState, reason: str) -> None:
        """Force state change (bypass transition rules).

        Use with caution, only for recovery scenarios.

        Args:
            state: State to force.
            reason: Reason for forcing state.
        """
        old_state = self._state
        self._state = state

        logger.warning(
            "State forced",
            slot_idx=self._slot_idx,
            old_state=old_state.value,
            new_state=state.value,
            reason=reason,
        )

        self._history.append(
            (datetime.now(), old_state, SlotEvent.RESET, state)
        )

    def is_idle(self) -> bool:
        """Check if slot is idle."""
        return self._state == SlotState.IDLE

    def is_busy(self) -> bool:
        """Check if slot is busy (not idle)."""
        return self._state not in (
            SlotState.IDLE,
            SlotState.COMPLETED,
            SlotState.FAILED,
            SlotState.ERROR,
        )

    def is_running(self) -> bool:
        """Check if test is running."""
        return self._state == SlotState.RUNNING

    def is_terminal(self) -> bool:
        """Check if in terminal state (completed/failed/error)."""
        return self._state in (
            SlotState.COMPLETED,
            SlotState.FAILED,
            SlotState.ERROR,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            State machine data as dictionary.
        """
        return {
            "slot_idx": self._slot_idx,
            "state": self._state.value,
            "is_busy": self.is_busy(),
            "is_running": self.is_running(),
            "valid_events": [e.value for e in self.get_valid_events()],
            "context": self._context.to_dict(),
        }


class SlotStateMachineManager:
    """Manager for multiple slot state machines.

    Creates and manages state machines for all slots.

    Attributes:
        max_slots: Maximum number of slots.
        machines: Dictionary of slot state machines.
    """

    def __init__(
        self,
        max_slots: int = 8,
        on_state_change: Optional[Callable[[int, SlotState, SlotState], None]] = None,
    ) -> None:
        """Initialize manager.

        Args:
            max_slots: Maximum number of slots.
            on_state_change: Callback for state changes.
        """
        self._max_slots = max_slots
        self._on_state_change = on_state_change
        self._machines: dict[int, SlotStateMachine] = {}

        # Create state machines for all slots
        for slot_idx in range(max_slots):
            self._machines[slot_idx] = SlotStateMachine(
                slot_idx=slot_idx,
                on_state_change=on_state_change,
            )

        logger.info(
            "State machine manager initialized",
            max_slots=max_slots,
        )

    @property
    def max_slots(self) -> int:
        """Maximum number of slots."""
        return self._max_slots

    def get(self, slot_idx: int) -> Optional[SlotStateMachine]:
        """Get state machine for a slot.

        Args:
            slot_idx: Slot index.

        Returns:
            SlotStateMachine or None.
        """
        return self._machines.get(slot_idx)

    def __getitem__(self, slot_idx: int) -> SlotStateMachine:
        """Get state machine by index.

        Args:
            slot_idx: Slot index.

        Returns:
            SlotStateMachine.

        Raises:
            KeyError: If slot index is invalid.
        """
        if slot_idx not in self._machines:
            raise KeyError(f"Invalid slot index: {slot_idx}")
        return self._machines[slot_idx]

    def trigger(
        self,
        slot_idx: int,
        event: SlotEvent,
        context_update: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> SlotState:
        """Trigger event on a slot.

        Args:
            slot_idx: Slot index.
            event: Event to trigger.
            context_update: Optional context updates.
            error_message: Optional error message.

        Returns:
            New state after transition.
        """
        machine = self[slot_idx]
        return machine.trigger(event, context_update, error_message)

    def get_all_states(self) -> dict[int, SlotState]:
        """Get states of all slots.

        Returns:
            Dictionary of slot index to state.
        """
        return {idx: m.state for idx, m in self._machines.items()}

    def get_busy_slots(self) -> list[int]:
        """Get list of busy slot indices.

        Returns:
            List of busy slot indices.
        """
        return [idx for idx, m in self._machines.items() if m.is_busy()]

    def get_running_slots(self) -> list[int]:
        """Get list of running slot indices.

        Returns:
            List of running slot indices.
        """
        return [idx for idx, m in self._machines.items() if m.is_running()]

    def get_idle_slots(self) -> list[int]:
        """Get list of idle slot indices.

        Returns:
            List of idle slot indices.
        """
        return [idx for idx, m in self._machines.items() if m.is_idle()]

    def reset_all(self) -> None:
        """Reset all state machines to IDLE."""
        for machine in self._machines.values():
            if not machine.is_idle():
                machine.force_state(SlotState.IDLE, "Manager reset")

        logger.info("All state machines reset")

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Manager data as dictionary.
        """
        return {
            "max_slots": self._max_slots,
            "busy_slots": self.get_busy_slots(),
            "running_slots": self.get_running_slots(),
            "idle_slots": self.get_idle_slots(),
            "slots": {idx: m.to_dict() for idx, m in self._machines.items()},
        }
