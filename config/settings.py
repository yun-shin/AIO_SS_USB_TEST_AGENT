"""Agent Settings Module.

Environment variable based configuration management using Pydantic Settings.
Supports YAML config file for user-modifiable settings.
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_config_paths() -> list[Path]:
    """Get possible config file paths in priority order.

    Returns:
        List of possible config file paths.
    """
    paths = []

    # 1. 사용자 AppData 폴더 (Windows) - 설치된 환경에서 최우선
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "SS USB Test Agent" / "config.yaml")

    # 2. PyInstaller frozen 상태에서의 경로
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        paths.append(exe_dir / "config.yaml")

    # 3. 현재 작업 디렉토리
    paths.append(Path.cwd() / "config.yaml")

    # 4. 프로젝트 루트 (개발 환경)
    paths.append(Path(__file__).parent.parent / "config.yaml")

    return paths


def _load_yaml_config() -> dict[str, Any]:
    """Load YAML config file.

    Searches for config.yaml in multiple locations and loads the first found.

    Returns:
        Loaded config dictionary or empty dict if not found.
    """
    for config_path in _get_config_paths():
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    # 어떤 config 파일이 로드되었는지 표시
                    config["_config_path"] = str(config_path)
                    return config
            except Exception:
                continue
    return {}


def _flatten_yaml_config(config: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested YAML config to flat dict for Pydantic.

    Args:
        config: Nested YAML config.

    Returns:
        Flattened config dict.
    """
    flat = {}

    # paths section
    if "paths" in config:
        paths = config["paths"]
        if "usb_test_exe" in paths:
            flat["usb_test_path"] = paths["usb_test_exe"]
        if "health_report_exe" in paths:
            flat["health_report_path"] = paths["health_report_exe"]

    # slots section
    if "slots" in config:
        slots = config["slots"]
        if "max_slots" in slots:
            flat["max_slots"] = slots["max_slots"]

    # backend section
    if "backend" in config:
        backend = config["backend"]
        if "url" in backend:
            flat["backend_url"] = backend["url"]
        if "ws_url" in backend:
            flat["backend_ws_url"] = backend["ws_url"]
        if "api_key" in backend:
            flat["api_key"] = backend["api_key"]

    # timeouts section
    if "timeouts" in config:
        timeouts = config["timeouts"]
        if "state_check_interval" in timeouts:
            flat["state_check_interval"] = timeouts["state_check_interval"]
        if "state_check_retries" in timeouts:
            flat["state_check_retries"] = timeouts["state_check_retries"]
        if "hang_threshold" in timeouts:
            flat["hang_threshold"] = timeouts["hang_threshold"]

    # notification section
    if "notification" in config:
        notification = config["notification"]
        if "enabled" in notification:
            flat["notification_enabled"] = notification["enabled"]
        if "jandi_webhook_url" in notification:
            flat["jandi_webhook_url"] = notification["jandi_webhook_url"]

    # logging section (separate handling for LogSettings)
    if "logging" in config:
        logging_cfg = config["logging"]
        if "level" in logging_cfg:
            flat["log_level"] = logging_cfg["level"]
        if "format" in logging_cfg:
            flat["log_format"] = logging_cfg["format"]

    # Store config path
    if "_config_path" in config:
        flat["_config_path"] = config["_config_path"]

    return flat


# Load YAML config once at module load
_yaml_config = _flatten_yaml_config(_load_yaml_config())


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
        default="ws://localhost:8000/api/agent/ws",
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

    Priority: Environment Variables > YAML Config > Defaults

    Returns:
        AgentSettings instance.
    """
    # YAML 설정을 기본값으로 사용
    yaml_overrides = {
        k: v for k, v in _yaml_config.items()
        if k in AgentSettings.model_fields and not k.startswith("_")
    }

    # AgentSettings 생성 (env vars가 YAML보다 우선)
    settings = AgentSettings(**yaml_overrides)

    # 로드된 config 경로 로깅용
    if "_config_path" in _yaml_config:
        # settings에 직접 추가는 하지 않고, 필요시 별도로 접근
        pass

    return settings


@lru_cache
def get_log_settings() -> LogSettings:
    """Return LogSettings singleton instance.

    Priority: Environment Variables > YAML Config > Defaults

    Returns:
        LogSettings instance.
    """
    # YAML 설정을 기본값으로 사용
    yaml_overrides = {}
    if "log_level" in _yaml_config:
        yaml_overrides["level"] = _yaml_config["log_level"]
    if "log_format" in _yaml_config:
        yaml_overrides["format"] = _yaml_config["log_format"]

    return LogSettings(**yaml_overrides)


def get_config_path() -> Optional[str]:
    """Return the path to the loaded config file.

    Returns:
        Config file path or None if not loaded.
    """
    return _yaml_config.get("_config_path")
