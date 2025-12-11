"""Structured Logging Module.

Structured logging configuration using structlog.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from ..config.settings import get_log_settings


def setup_logging() -> None:
    """Initialize logging system.

    Configures logging in JSON or console format based on environment settings.
    """
    settings = get_log_settings()

    # Python 기본 로깅 설정
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.level.upper()),
    )

    # Processor 체인 구성
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.format.lower() == "json":
        # JSON 포맷 (프로덕션)
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # 콘솔 포맷 (개발)
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return Logger instance.

    Args:
        name: Logger name. If None, uses caller's module name.

    Returns:
        structlog BoundLogger instance.
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind values to global logging context.

    Bound values will be included in all subsequent logs.

    Args:
        **kwargs: Key-value pairs to bind.
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Remove values from global logging context.

    Args:
        *keys: List of keys to remove.
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear global logging context."""
    structlog.contextvars.clear_contextvars()
