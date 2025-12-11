"""Control Wrapper.

Provides safe wrappers for MFC controls.
Includes retry logic, error handling, etc.
"""

import asyncio
from typing import Any, Callable, Optional, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError

from ..config.constants import TimeoutConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class ControlWrapper:
    """MFC control wrapper.

    Provides safe access to pywinauto controls.

    Attributes:
        _control: Wrapped pywinauto control.
        _name: Control identifier name.
    """

    def __init__(self, control: UIAWrapper, name: str = "") -> None:
        """Initialize control wrapper.

        Args:
            control: pywinauto control.
            name: Control identifier name.
        """
        self._control = control
        self._name = name or control.element_info.name or "Unknown"

    @property
    def exists(self) -> bool:
        """Control existence."""
        try:
            return self._control.exists()
        except Exception:
            return False

    @property
    def is_enabled(self) -> bool:
        """Control enabled status."""
        try:
            return self._control.is_enabled()
        except Exception:
            return False

    @property
    def is_visible(self) -> bool:
        """Control visibility."""
        try:
            return self._control.is_visible()
        except Exception:
            return False

    @property
    def text(self) -> str:
        """Control text."""
        try:
            return self._control.window_text()
        except Exception:
            return ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        retry=retry_if_exception_type((ElementNotFoundError, Exception)),
    )
    async def click(self) -> bool:
        """Click control.

        Returns:
            Success status.
        """
        if not self.exists:
            logger.warning("Control not found for click", name=self._name)
            return False

        try:
            self._control.click_input()
            logger.debug("Clicked control", name=self._name)
            await asyncio.sleep(0.1)  # UI 반응 대기
            return True
        except Exception as e:
            logger.error("Click failed", name=self._name, error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        retry=retry_if_exception_type((ElementNotFoundError, Exception)),
    )
    async def double_click(self) -> bool:
        """Double-click control.

        Returns:
            Success status.
        """
        if not self.exists:
            logger.warning("Control not found for double click", name=self._name)
            return False

        try:
            self._control.double_click_input()
            logger.debug("Double clicked control", name=self._name)
            await asyncio.sleep(0.1)
            return True
        except Exception as e:
            logger.error("Double click failed", name=self._name, error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        retry=retry_if_exception_type((ElementNotFoundError, Exception)),
    )
    async def set_text(self, text: str, clear_first: bool = True) -> bool:
        """Input text.

        Args:
            text: Text to input.
            clear_first: Whether to clear existing text.

        Returns:
            Success status.
        """
        if not self.exists:
            logger.warning("Control not found for set_text", name=self._name)
            return False

        try:
            if clear_first:
                self._control.set_edit_text("")
            self._control.type_keys(text, with_spaces=True)
            logger.debug("Set text on control", name=self._name, text=text)
            return True
        except Exception as e:
            logger.error("Set text failed", name=self._name, error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        retry=retry_if_exception_type((ElementNotFoundError, Exception)),
    )
    async def select_item(self, item: str | int) -> bool:
        """Select combobox/list item.

        Args:
            item: Item to select (string or index).

        Returns:
            Success status.
        """
        if not self.exists:
            logger.warning("Control not found for select_item", name=self._name)
            return False

        try:
            if isinstance(item, str):
                self._control.select(item)
            else:
                self._control.select(item)
            logger.debug("Selected item", name=self._name, item=item)
            await asyncio.sleep(0.1)
            return True
        except Exception as e:
            logger.error("Select item failed", name=self._name, error=str(e))
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        retry=retry_if_exception_type((ElementNotFoundError, Exception)),
    )
    async def set_checkbox(self, checked: bool) -> bool:
        """Set checkbox state.

        Args:
            checked: Check status.

        Returns:
            Success status.
        """
        if not self.exists:
            logger.warning("Control not found for set_checkbox", name=self._name)
            return False

        try:
            current_state = self._control.get_toggle_state()
            if (checked and current_state == 0) or (not checked and current_state == 1):
                self._control.toggle()
            logger.debug("Set checkbox", name=self._name, checked=checked)
            return True
        except Exception as e:
            logger.error("Set checkbox failed", name=self._name, error=str(e))
            raise

    async def wait_for_enabled(
        self,
        timeout: float = TimeoutConfig.ELEMENT_WAIT,
    ) -> bool:
        """Wait for control to be enabled.

        Args:
            timeout: Timeout in seconds.

        Returns:
            Enabled status.
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            if self.is_enabled:
                return True
            await asyncio.sleep(0.2)

        logger.warning(
            "Timeout waiting for control to be enabled",
            name=self._name,
            timeout=timeout,
        )
        return False

    async def wait_for_text(
        self,
        expected: str,
        timeout: float = TimeoutConfig.ELEMENT_WAIT,
        contains: bool = False,
    ) -> bool:
        """Wait for specific text.

        Args:
            expected: Expected text.
            timeout: Timeout in seconds.
            contains: Whether to compare by containment.

        Returns:
            Text match status.
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            current_text = self.text
            if contains:
                if expected in current_text:
                    return True
            elif current_text == expected:
                return True
            await asyncio.sleep(0.2)

        logger.warning(
            "Timeout waiting for text",
            name=self._name,
            expected=expected,
            actual=self.text,
            timeout=timeout,
        )
        return False

    def get_info(self) -> dict[str, Any]:
        """Get control information.

        Returns:
            Control information dictionary.
        """
        try:
            return {
                "name": self._name,
                "text": self.text,
                "exists": self.exists,
                "enabled": self.is_enabled,
                "visible": self.is_visible,
                "control_type": self._control.element_info.control_type,
                "class_name": self._control.element_info.class_name,
                "rectangle": str(self._control.element_info.rectangle),
            }
        except Exception as e:
            return {"name": self._name, "error": str(e)}
