import pytest

from config.constants import MFCControlId, ProcessState, TestPhase
from infrastructure.clock import FakeClock
from services.mfc_ui_monitor import MFCUIMonitor, MFCUIState


class DummyLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class FakeControl:
    def __init__(self, text: str = "", enabled: bool = True):
        self._text = text
        self._enabled = enabled

    def window_text(self) -> str:
        return self._text

    def is_enabled(self) -> bool:
        return self._enabled


class FakeSlotWindow:
    def __init__(self):
        self._controls: list[
            tuple[FakeControl, str | None, int | None, str | None]
        ] = []

    def add_control(
        self,
        control: FakeControl,
        name: str | None = None,
        control_id: int | None = None,
        class_name: str | None = None,
    ) -> None:
        self._controls.append((control, name, control_id, class_name))

    def get_control_by_name(self, name: str):
        for control, ctrl_name, _, _ in self._controls:
            if ctrl_name == name:
                return control
        return None

    def find_control(
        self, control_id: int | None = None, class_name: str | None = None
    ):
        for control, _, cid, cls in self._controls:
            if (control_id is None or cid == control_id) and (
                class_name is None or cls == class_name
            ):
                return control
        return None


class FakeWindowManager:
    def __init__(self, slot_window: FakeSlotWindow):
        self._slot_window = slot_window

    def get_slot_window(self, slot_idx: int):
        return self._slot_window


@pytest.mark.asyncio
async def test_read_ui_state_parses_status_and_progress():
    """[TC-MFC_UI_MONITOR-001] Read ui state parses status and progress - 테스트 시나리오를 검증한다.

        테스트 목적:
            Read ui state parses status and progress 시나리오에서 기대 동작이 유지되는지 확인한다.

        테스트 시나리오:
            Given: 테스트 코드에서 준비한 기본 상태
            When: test_read_ui_state_parses_status_and_progress 케이스를 실행하면
            Then: 단언문에 명시된 기대 결과가 충족된다.

        Notes:
            None
        """
    slot = FakeSlotWindow()
    slot.add_control(FakeControl("Test"), name="Button6")  # status button
    slot.add_control(
        FakeControl("10/10 IDLE"),
        control_id=MFCControlId.TXT_STATUS,
        class_name="Static",
    )
    slot.add_control(
        FakeControl("4/10  File Copy 35/88"), name="Static"
    )  # progress text
    slot.add_control(
        FakeControl("12"), control_id=MFCControlId.EDT_LOOP, class_name="Edit"
    )
    slot.add_control(
        FakeControl("", enabled=True),
        control_id=MFCControlId.BTN_TEST,
        class_name="Button",
    )
    slot.add_control(
        FakeControl("", enabled=False),
        control_id=MFCControlId.BTN_STOP,
        class_name="Button",
    )

    monitor = MFCUIMonitor(
        window_manager=FakeWindowManager(slot),
        clock=FakeClock(),
        logger=DummyLogger(),
        max_slots=1,
    )

    state = await monitor._read_ui_state(slot_idx=0, slot_window=slot)

    assert state.process_state == ProcessState.TEST
    assert state.test_phase == TestPhase.COPY
    assert state.current_loop == 4
    assert state.total_loop == 12  # EDT_LOOP 우선
    assert state.is_test_button_enabled is True
    assert state.is_stop_button_enabled is False
    assert state.progress_text.startswith("4/10")


def test_parse_progress_sets_total_when_missing():
    """[TC-MFC_UI_MONITOR-002] Parse progress sets total when missing - 테스트 시나리오를 검증한다.

        테스트 목적:
            Parse progress sets total when missing 시나리오에서 기대 동작이 유지되는지 확인한다.

        테스트 시나리오:
            Given: 테스트 코드에서 준비한 기본 상태
            When: test_parse_progress_sets_total_when_missing 케이스를 실행하면
            Then: 단언문에 명시된 기대 결과가 충족된다.

        Notes:
            None
        """
    monitor = MFCUIMonitor(
        window_manager=FakeWindowManager(FakeSlotWindow()),
        clock=FakeClock(),
        logger=DummyLogger(),
        max_slots=1,
    )
    state = MFCUIState(slot_idx=0, progress_text="3/5  File Copy", total_loop=0)

    monitor._parse_progress_text(state)

    assert state.current_loop == 3
    assert state.total_loop == 5
