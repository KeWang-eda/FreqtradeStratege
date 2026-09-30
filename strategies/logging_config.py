"""Structured standard-library logging for every layered-strategy mode."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from functools import wraps
from typing import Any, Callable, TypeVar


class LayerLogLevel:
    """Application logging levels mapped to Python's standard levels."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


ROOT_LOGGER_NAME = "layered_vtech"
_FUNCTION = TypeVar("_FUNCTION", bound=Callable[..., Any])


def configure_layered_logging() -> None:
    """Configure a fallback stream only when the host has no handlers.

    Freqtrade configures the root logger and logfile itself. Offline training
    scripts often do not, so this fallback keeps their events visible without
    replacing Freqtrade's handlers.
    """
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=os.getenv("LAYERED_LOG_LEVEL", "INFO").upper(),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    logging.getLogger(ROOT_LOGGER_NAME).setLevel(
        os.getenv("LAYERED_LOG_LEVEL", "INFO").upper()
    )


def get_layer_logger(component: str) -> logging.Logger:
    """Return a child logger compatible with Freqtrade's logging handlers."""
    if not component:
        raise ValueError("component must not be empty")
    configure_layered_logging()
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{component}")


def log_layer_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    """Emit one machine-readable event through the caller's logger."""
    if not event:
        raise ValueError("event must not be empty")
    payload = {
        "event": event,
        "run_mode": os.getenv("LAYERED_RUN_MODE", "unknown"),
        "level": logging.getLevelName(level),
        **fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=_json_default))


def log_layer_failure(
    logger: logging.Logger,
    function_name: str,
    error: Exception,
    **fields: Any,
) -> None:
    """Emit a detailed failure event and preserve the original exception."""
    log_layer_event(
        logger,
        logging.ERROR,
        "layer_call_failed",
        error_code=f"{type(error).__module__}.{type(error).__name__}",
        function=function_name,
        exception_type=type(error).__name__,
        exception_message=str(error),
        **fields,
    )
    logger.exception("layer_call_failed function=%s", function_name)


def log_failures(component: str) -> Callable[[_FUNCTION], _FUNCTION]:
    """Log every uncaught public-layer exception before re-raising it."""
    logger = get_layer_logger(component)

    def decorator(function: _FUNCTION) -> _FUNCTION:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return function(*args, **kwargs)
            except Exception as error:
                log_layer_failure(logger, function.__qualname__, error)
                raise

        return wrapped  # type: ignore[return-value]

    return decorator


def _json_default(value: Any) -> str:
    """Serialize timestamps and scalar-like values without leaking secrets."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return str(value.item())
    return str(value)
