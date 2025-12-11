"""Structured Logging Module.

Structured logging configuration matching Backend's logger format.
Uses standard logging module for consistency with AIO_EVT_Parser backend.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

from config.settings import get_log_settings

# Context variable for agent context tracking
agent_context_var: ContextVar[Dict[str, Any]] = ContextVar(
    "agent_context",
    default={}
)


class ContextFilter(logging.Filter):
    """Filter to inject extra fields into log records.

    This filter merges extra keyword arguments from logger calls
    into the record so that formatters can access them.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject extra fields into log record.

        Args:
            record: Log record to process.

        Returns:
            Always True to allow the record to be processed.
        """
        # Initialize extra_fields if not present
        if not hasattr(record, "extra_fields"):
            record.extra_fields = {}

        # Merge agent context (bound context like agent_name, agent_version)
        context = agent_context_var.get()
        if context:
            record.extra_fields.update(context)

        # Merge any custom attributes added via extra={...}
        # Exclude standard LogRecord attributes
        standard_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "message", "pathname", "process", "processName", "relativeCreated",
            "thread", "threadName", "exc_info", "exc_text", "stack_info",
            "extra_fields", "taskName"
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                record.extra_fields[key] = value

        return True


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Outputs log records as JSON objects matching Backend format:
    {"timestamp", "level", "logger", "message", "module", "function", "line", ...extra}
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (including agent context)
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Text log formatter for human-readable output.

    Outputs readable log messages with extra fields appended.
    """

    def __init__(self) -> None:
        """Initialize text formatter."""
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as text.

        Args:
            record: Log record to format.

        Returns:
            Text-formatted log string.
        """
        base_msg = super().format(record)

        # Append extra fields if present
        if hasattr(record, "extra_fields") and record.extra_fields:
            extras = " ".join(f"{k}={v}" for k, v in record.extra_fields.items())
            return f"{base_msg} | {extras}"

        return base_msg


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that supports keyword arguments for extra fields.

    Allows logging with extra fields like:
        logger.info("message", key1=value1, key2=value2)
    """

    def process(
        self, msg: str, kwargs: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """Process log message and extract extra fields.

        Args:
            msg: Log message.
            kwargs: Keyword arguments passed to logging call.

        Returns:
            Tuple of (message, modified kwargs).
        """
        # Extract extra fields from kwargs (non-standard logging kwargs)
        extra = kwargs.get("extra", {})
        standard_kwargs = {"exc_info", "stack_info", "stacklevel", "extra"}

        for key in list(kwargs.keys()):
            if key not in standard_kwargs:
                extra[key] = kwargs.pop(key)

        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging() -> None:
    """Initialize logging system.

    Configures logging in JSON or console format based on environment settings.
    Matches Backend's logger configuration for consistent log format.
    """
    settings = get_log_settings()

    # Validate log level
    numeric_level = getattr(logging, settings.level.upper(), logging.INFO)

    # Select formatter based on format setting
    if settings.format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Add context filter to capture extra fields
    context_filter = ContextFilter()

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    root_logger.addHandler(console_handler)

    # Silence noisy third-party loggers
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> ContextLogger:
    """Return Logger instance.

    Args:
        name: Logger name. If None, uses caller's module name.

    Returns:
        ContextLogger instance that supports keyword arguments.
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, {})


def bind_context(**kwargs: Any) -> None:
    """Bind values to global logging context.

    Bound values will be included in all subsequent logs.

    Args:
        **kwargs: Key-value pairs to bind.
    """
    current = agent_context_var.get().copy()
    current.update(kwargs)
    agent_context_var.set(current)


def unbind_context(*keys: str) -> None:
    """Remove values from global logging context.

    Args:
        *keys: List of keys to remove.
    """
    current = agent_context_var.get().copy()
    for key in keys:
        current.pop(key, None)
    agent_context_var.set(current)


def clear_context() -> None:
    """Clear global logging context."""
    agent_context_var.set({})


class StructlogLoggerAdapter:
    """Logger adapter implementing ILogger protocol.

    Wraps ContextLogger to conform to ILogger interface.
    """

    def __init__(self, logger: ContextLogger) -> None:
        """Initialize adapter.

        Args:
            logger: ContextLogger instance.
        """
        self._logger = logger

    def debug(self, message: str, **kwargs: Any) -> None:
        """Debug log."""
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Info log."""
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Warning log."""
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Error log."""
        self._logger.error(message, **kwargs)


def get_ilogger(name: Optional[str] = None) -> StructlogLoggerAdapter:
    """Return ILogger-compatible logger instance.

    Args:
        name: Logger name. If None, uses caller's module name.

    Returns:
        StructlogLoggerAdapter implementing ILogger protocol.
    """
    return StructlogLoggerAdapter(get_logger(name))
