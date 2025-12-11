"""Agent Settings Module.

Environment variable based configuration management using Pydantic Settings.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Agent settings.

    Loads settings from environment variables or .env file.
    All environment variables use the AGENT_ prefix.

    Attributes:
        name: Agent name.
        version: Agent version.
        debug: Enable debug mode.
        usb_test_path: Path to USB Test.exe.
        health_report_path: Path to Card_HealthReport.exe.
        max_slots: Maximum number of test slots.
        backend_url: Backend REST API URL.
        backend_ws_url: Backend WebSocket URL.
        api_key: API authentication key.
        state_check_interval: State check interval in seconds.
        state_check_retries: Maximum state check retries.
        hang_threshold: Process hang detection threshold in seconds.
        jandi_webhook_url: Jandi webhook URL.
        notification_enabled: Enable notifications.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        case_sensitive=False,
        extra="ignore",
    )

    # Basic settings
    name: str = Field(default="ss-usb-test-agent", description="Agent name")
    version: str = Field(default="0.1.0", description="Agent version")
    debug: bool = Field(default=False, description="Debug mode")

    # USB Test settings
    usb_test_path: str = Field(
        default="C:/USB_Test/USB Test.exe",
        description="Path to USB Test.exe",
    )
    health_report_path: str = Field(
        default="C:/USB_Test/Card_HealthReport.exe",
        description="Path to Card_HealthReport.exe",
    )
    max_slots: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Maximum number of test slots",
    )

    # Backend connection
    backend_url: str = Field(
        default="http://localhost:8000",
        description="Backend REST API URL",
    )
    backend_ws_url: str = Field(
        default="ws://localhost:8000/ws/agent",
        description="Backend WebSocket URL",
    )
    api_key: str = Field(
        default="",
        description="API authentication key",
    )

    # Timeout settings
    state_check_interval: int = Field(
        default=10,
        ge=1,
        description="State check interval in seconds",
    )
    state_check_retries: int = Field(
        default=10,
        ge=1,
        description="Maximum state check retries",
    )
    hang_threshold: int = Field(
        default=300,
        ge=60,
        description="Process hang detection threshold in seconds",
    )

    # Notification settings
    jandi_webhook_url: str = Field(
        default="",
        description="Jandi webhook URL",
    )
    notification_enabled: bool = Field(
        default=True,
        description="Enable notifications",
    )


class LogSettings(BaseSettings):
    """Logging settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Log level",
    )
    format: str = Field(
        default="json",
        alias="LOG_FORMAT",
        description="Log format (json/text)",
    )


@lru_cache
def get_settings() -> AgentSettings:
    """Return AgentSettings singleton instance.

    Returns:
        AgentSettings instance.
    """
    return AgentSettings()


@lru_cache
def get_log_settings() -> LogSettings:
    """Return LogSettings singleton instance.

    Returns:
        LogSettings instance.
    """
    return LogSettings()
