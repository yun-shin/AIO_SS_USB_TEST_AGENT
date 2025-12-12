"""Unit tests for ControlWrapper.

Tests control existence checks, retry logic, timeout handling,
and wait_for_enabled/wait_for_text timeout paths.
"""

import asyncio
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class FakeControl:
    """Fake pywinauto control for testing."""

    def __init__(
        self,
        exists: bool = True,
        enabled: bool = True,
        visible: bool = True,
        text: str = "",
        toggle_state: int = 0,
    ):
        self._exists = exists
        self._enabled = enabled
        self._visible = visible
        self._text = text
        self._toggle_state = toggle_state
        self._click_count = 0
        self._double_click_count = 0
        self._typed_text = ""
        self._selected_item = None
        self._fail_on_click = False
        self._fail_on_toggle = False

        # element_info mock
        self.element_info = MagicMock()
        self.element_info.name = "TestControl"
        self.element_info.control_type = "Button"
        self.element_info.class_name = "Button"
        self.element_info.rectangle = "(0, 0, 100, 30)"

    def exists(self) -> bool:
        return self._exists

    def is_enabled(self) -> bool:
        return self._enabled

    def is_visible(self) -> bool:
        return self._visible

    def window_text(self) -> str:
        return self._text

    def click_input(self) -> None:
        if self._fail_on_click:
            raise Exception("Click failed")
        self._click_count += 1

    def double_click_input(self) -> None:
        if self._fail_on_click:
            raise Exception("Double click failed")
        self._double_click_count += 1

    def set_edit_text(self, text: str) -> None:
        self._text = text

    def type_keys(self, text: str, with_spaces: bool = False) -> None:
        self._typed_text = text
        self._text += text

    def select(self, item) -> None:
        self._selected_item = item

    def get_toggle_state(self) -> int:
        if self._fail_on_toggle:
            raise Exception("Toggle state failed")
        return self._toggle_state

    def toggle(self) -> None:
        if self._fail_on_toggle:
            raise Exception("Toggle failed")
        self._toggle_state = 1 if self._toggle_state == 0 else 0


class TestControlWrapperExistence:
    """Test control existence and property checks."""

    def test_exists_returns_true_when_control_exists(self):
        """[TC-CONTROL_WRAPPER-001] Exists returns true when control exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Exists returns true when control exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_exists_returns_true_when_control_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True)
        wrapper = ControlWrapper(fake, "TestButton")

        assert wrapper.exists is True

    def test_exists_returns_false_when_control_not_exists(self):
        """[TC-CONTROL_WRAPPER-002] Exists returns false when control not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Exists returns false when control not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_exists_returns_false_when_control_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=False)
        wrapper = ControlWrapper(fake, "TestButton")

        assert wrapper.exists is False

    def test_exists_returns_false_on_exception(self):
        """[TC-CONTROL_WRAPPER-003] Exists returns false on exception - 테스트 시나리오를 검증한다.

            테스트 목적:
                Exists returns false on exception 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_exists_returns_false_on_exception 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = MagicMock()
        fake.exists.side_effect = Exception("Access denied")
        fake.element_info = MagicMock()
        fake.element_info.name = "Test"

        wrapper = ControlWrapper(fake, "TestButton")

        assert wrapper.exists is False

    def test_is_enabled_returns_true(self):
        """[TC-CONTROL_WRAPPER-004] Is enabled returns true - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is enabled returns true 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_enabled_returns_true 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(enabled=True)
        wrapper = ControlWrapper(fake, "TestButton")

        assert wrapper.is_enabled is True

    def test_is_enabled_returns_false_on_exception(self):
        """[TC-CONTROL_WRAPPER-005] Is enabled returns false on exception - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is enabled returns false on exception 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_enabled_returns_false_on_exception 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = MagicMock()
        fake.is_enabled.side_effect = Exception("Access denied")
        fake.element_info = MagicMock()
        fake.element_info.name = "Test"

        wrapper = ControlWrapper(fake, "TestButton")

        assert wrapper.is_enabled is False

    def test_is_visible_returns_true(self):
        """[TC-CONTROL_WRAPPER-006] Is visible returns true - 테스트 시나리오를 검증한다.

            테스트 목적:
                Is visible returns true 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_is_visible_returns_true 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(visible=True)
        wrapper = ControlWrapper(fake, "TestButton")

        assert wrapper.is_visible is True

    def test_text_returns_window_text(self):
        """[TC-CONTROL_WRAPPER-007] Text returns window text - 테스트 시나리오를 검증한다.

            테스트 목적:
                Text returns window text 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_text_returns_window_text 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(text="Hello World")
        wrapper = ControlWrapper(fake, "TestEdit")

        assert wrapper.text == "Hello World"

    def test_text_returns_empty_on_exception(self):
        """[TC-CONTROL_WRAPPER-008] Text returns empty on exception - 테스트 시나리오를 검증한다.

            테스트 목적:
                Text returns empty on exception 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_text_returns_empty_on_exception 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = MagicMock()
        fake.window_text.side_effect = Exception("Access denied")
        fake.element_info = MagicMock()
        fake.element_info.name = "Test"

        wrapper = ControlWrapper(fake, "TestEdit")

        assert wrapper.text == ""


class TestControlWrapperClick:
    """Test click operations with retry logic."""

    @pytest.mark.asyncio
    async def test_click_success(self):
        """[TC-CONTROL_WRAPPER-009] Click success - 테스트 시나리오를 검증한다.

            테스트 목적:
                Click success 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_click_success 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True)
        wrapper = ControlWrapper(fake, "TestButton")

        result = await wrapper.click()

        assert result is True
        assert fake._click_count == 1

    @pytest.mark.asyncio
    async def test_click_returns_false_when_not_exists(self):
        """[TC-CONTROL_WRAPPER-010] Click returns false when not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Click returns false when not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_click_returns_false_when_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=False)
        wrapper = ControlWrapper(fake, "TestButton")

        result = await wrapper.click()

        assert result is False
        assert fake._click_count == 0

    @pytest.mark.asyncio
    async def test_click_retries_on_failure(self):
        """[TC-CONTROL_WRAPPER-011] Click retries on failure - 테스트 시나리오를 검증한다.

            테스트 목적:
                Click retries on failure 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_click_retries_on_failure 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True)
        fake._fail_on_click = True
        wrapper = ControlWrapper(fake, "TestButton")

        with pytest.raises(Exception):
            await wrapper.click()

    @pytest.mark.asyncio
    async def test_double_click_success(self):
        """[TC-CONTROL_WRAPPER-012] Double click success - 테스트 시나리오를 검증한다.

            테스트 목적:
                Double click success 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_double_click_success 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True)
        wrapper = ControlWrapper(fake, "TestButton")

        result = await wrapper.double_click()

        assert result is True
        assert fake._double_click_count == 1

    @pytest.mark.asyncio
    async def test_double_click_returns_false_when_not_exists(self):
        """[TC-CONTROL_WRAPPER-013] Double click returns false when not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Double click returns false when not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_double_click_returns_false_when_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=False)
        wrapper = ControlWrapper(fake, "TestButton")

        result = await wrapper.double_click()

        assert result is False


class TestControlWrapperSetText:
    """Test text input operations."""

    @pytest.mark.asyncio
    async def test_set_text_success(self):
        """[TC-CONTROL_WRAPPER-014] Set text success - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set text success 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_text_success 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True, text="")
        wrapper = ControlWrapper(fake, "TestEdit")

        result = await wrapper.set_text("Hello")

        assert result is True
        assert fake._typed_text == "Hello"

    @pytest.mark.asyncio
    async def test_set_text_returns_false_when_not_exists(self):
        """[TC-CONTROL_WRAPPER-015] Set text returns false when not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set text returns false when not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_text_returns_false_when_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=False)
        wrapper = ControlWrapper(fake, "TestEdit")

        result = await wrapper.set_text("Hello")

        assert result is False


class TestControlWrapperSelectItem:
    """Test combobox/list selection."""

    @pytest.mark.asyncio
    async def test_select_item_by_string(self):
        """[TC-CONTROL_WRAPPER-016] Select item by string - 테스트 시나리오를 검증한다.

            테스트 목적:
                Select item by string 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_select_item_by_string 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True)
        wrapper = ControlWrapper(fake, "TestCombo")

        result = await wrapper.select_item("Option A")

        assert result is True
        assert fake._selected_item == "Option A"

    @pytest.mark.asyncio
    async def test_select_item_by_index(self):
        """[TC-CONTROL_WRAPPER-017] Select item by index - 테스트 시나리오를 검증한다.

            테스트 목적:
                Select item by index 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_select_item_by_index 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True)
        wrapper = ControlWrapper(fake, "TestCombo")

        result = await wrapper.select_item(2)

        assert result is True
        assert fake._selected_item == 2

    @pytest.mark.asyncio
    async def test_select_item_returns_false_when_not_exists(self):
        """[TC-CONTROL_WRAPPER-018] Select item returns false when not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Select item returns false when not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_select_item_returns_false_when_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=False)
        wrapper = ControlWrapper(fake, "TestCombo")

        result = await wrapper.select_item("Option")

        assert result is False


class TestControlWrapperCheckbox:
    """Test checkbox operations."""

    @pytest.mark.asyncio
    async def test_set_checkbox_to_checked(self):
        """[TC-CONTROL_WRAPPER-019] Set checkbox to checked - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set checkbox to checked 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_checkbox_to_checked 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True, toggle_state=0)  # unchecked
        wrapper = ControlWrapper(fake, "TestCheckbox")

        result = await wrapper.set_checkbox(True)

        assert result is True
        assert fake._toggle_state == 1

    @pytest.mark.asyncio
    async def test_set_checkbox_to_unchecked(self):
        """[TC-CONTROL_WRAPPER-020] Set checkbox to unchecked - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set checkbox to unchecked 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_checkbox_to_unchecked 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True, toggle_state=1)  # checked
        wrapper = ControlWrapper(fake, "TestCheckbox")

        result = await wrapper.set_checkbox(False)

        assert result is True
        assert fake._toggle_state == 0

    @pytest.mark.asyncio
    async def test_set_checkbox_no_change_when_already_correct(self):
        """[TC-CONTROL_WRAPPER-021] Set checkbox no change when already correct - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set checkbox no change when already correct 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_checkbox_no_change_when_already_correct 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True, toggle_state=1)  # checked
        wrapper = ControlWrapper(fake, "TestCheckbox")

        result = await wrapper.set_checkbox(True)

        assert result is True
        assert fake._toggle_state == 1  # unchanged

    @pytest.mark.asyncio
    async def test_set_checkbox_returns_false_when_not_exists(self):
        """[TC-CONTROL_WRAPPER-022] Set checkbox returns false when not exists - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set checkbox returns false when not exists 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_checkbox_returns_false_when_not_exists 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=False)
        wrapper = ControlWrapper(fake, "TestCheckbox")

        result = await wrapper.set_checkbox(True)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_checkbox_raises_on_toggle_failure(self):
        """[TC-CONTROL_WRAPPER-023] Set checkbox raises on toggle failure - 테스트 시나리오를 검증한다.

            테스트 목적:
                Set checkbox raises on toggle failure 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_set_checkbox_raises_on_toggle_failure 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True, toggle_state=0)
        fake._fail_on_toggle = True
        wrapper = ControlWrapper(fake, "TestCheckbox")

        with pytest.raises(Exception):
            await wrapper.set_checkbox(True)


class TestControlWrapperWaitForEnabled:
    """Test wait_for_enabled timeout path."""

    @pytest.mark.asyncio
    async def test_wait_for_enabled_returns_true_immediately_when_enabled(self):
        """[TC-CONTROL_WRAPPER-024] Wait for enabled returns true immediately when enabled - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for enabled returns true immediately when enabled 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_enabled_returns_true_immediately_when_enabled 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(enabled=True)
        wrapper = ControlWrapper(fake, "TestButton")

        result = await wrapper.wait_for_enabled(timeout=1.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_enabled_returns_true_when_becomes_enabled(self):
        """[TC-CONTROL_WRAPPER-025] Wait for enabled returns true when becomes enabled - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for enabled returns true when becomes enabled 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_enabled_returns_true_when_becomes_enabled 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(enabled=False)
        wrapper = ControlWrapper(fake, "TestButton")

        async def enable_later():
            await asyncio.sleep(0.3)
            fake._enabled = True

        asyncio.create_task(enable_later())
        result = await wrapper.wait_for_enabled(timeout=2.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_enabled_timeout_returns_false(self):
        """[TC-CONTROL_WRAPPER-026] Wait for enabled timeout returns false - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for enabled timeout returns false 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_enabled_timeout_returns_false 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(enabled=False)
        wrapper = ControlWrapper(fake, "TestButton")

        with patch("controller.control_wrapper.logger"):
            result = await wrapper.wait_for_enabled(timeout=0.5)

        assert result is False


class TestControlWrapperWaitForText:
    """Test wait_for_text timeout path."""

    @pytest.mark.asyncio
    async def test_wait_for_text_exact_match_returns_true(self):
        """[TC-CONTROL_WRAPPER-027] Wait for text exact match returns true - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for text exact match returns true 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_text_exact_match_returns_true 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(text="Expected")
        wrapper = ControlWrapper(fake, "TestLabel")

        result = await wrapper.wait_for_text("Expected", timeout=1.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_text_contains_match_returns_true(self):
        """[TC-CONTROL_WRAPPER-028] Wait for text contains match returns true - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for text contains match returns true 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_text_contains_match_returns_true 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(text="Hello Expected World")
        wrapper = ControlWrapper(fake, "TestLabel")

        result = await wrapper.wait_for_text("Expected", timeout=1.0, contains=True)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_text_returns_true_when_text_changes(self):
        """[TC-CONTROL_WRAPPER-029] Wait for text returns true when text changes - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for text returns true when text changes 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_text_returns_true_when_text_changes 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(text="Initial")
        wrapper = ControlWrapper(fake, "TestLabel")

        async def change_text_later():
            await asyncio.sleep(0.3)
            fake._text = "Expected"

        asyncio.create_task(change_text_later())
        result = await wrapper.wait_for_text("Expected", timeout=2.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_text_timeout_returns_false(self):
        """[TC-CONTROL_WRAPPER-030] Wait for text timeout returns false - 테스트 시나리오를 검증한다.

            테스트 목적:
                Wait for text timeout returns false 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_wait_for_text_timeout_returns_false 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(text="Wrong")
        wrapper = ControlWrapper(fake, "TestLabel")

        with patch("controller.control_wrapper.logger"):
            result = await wrapper.wait_for_text("Expected", timeout=0.5)

        assert result is False


class TestControlWrapperGetInfo:
    """Test get_info method."""

    def test_get_info_returns_control_info(self):
        """[TC-CONTROL_WRAPPER-031] Get info returns control info - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get info returns control info 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_info_returns_control_info 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        fake = FakeControl(exists=True, enabled=True, visible=True, text="Test")
        wrapper = ControlWrapper(fake, "TestControl")

        info = wrapper.get_info()

        assert info["name"] == "TestControl"
        assert info["text"] == "Test"
        assert info["exists"] is True
        assert info["enabled"] is True
        assert info["visible"] is True
        assert "control_type" in info
        assert "class_name" in info

    def test_get_info_returns_error_on_exception(self):
        """[TC-CONTROL_WRAPPER-032] Get info returns error on exception - 테스트 시나리오를 검증한다.

            테스트 목적:
                Get info returns error on exception 시나리오에서 기대 동작이 유지되는지 확인한다.

            테스트 시나리오:
                Given: 테스트 코드에서 준비한 기본 상태
                When: test_get_info_returns_error_on_exception 케이스를 실행하면
                Then: 단언문에 명시된 기대 결과가 충족된다.

            Notes:
                None
            """
        from controller.control_wrapper import ControlWrapper

        # Create a control that raises exception when accessing element_info
        fake = MagicMock()
        type(fake).element_info = PropertyMock(side_effect=Exception("Access denied"))

        wrapper = ControlWrapper(fake, "TestControl")

        info = wrapper.get_info()

        assert "name" in info
        assert "error" in info
