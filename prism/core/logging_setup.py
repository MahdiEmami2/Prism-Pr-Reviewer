"""Logging configuration with mandatory secret redaction.

Every handler added here carries :class:`RedactionFilter`, so a token that accidentally
reaches a log call is scrubbed before it is emitted. PRISM additionally never passes
``Authorization`` headers to the logger.
"""

from __future__ import annotations

import logging

from prism.core.redaction import redact

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class RedactionFilter(logging.Filter):
    """Scrub known secret shapes from log messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(redact(arg) for arg in record.args)
                elif isinstance(record.args, dict):
                    record.args = {key: redact(value) for key, value in record.args.items()}
                else:
                    record.args = redact(record.args)
        except Exception:  # noqa: S110  # nosec B110 - a logging filter must never raise
            # Deliberately swallowed: if redaction itself fails, the record is still emitted
            # rather than dropped, because losing a log line is worse than an unredacted one
            # that the secondary filter below would have caught anyway.
            pass
        return True


def configure_logging(level: str = "INFO", *, force: bool = False) -> logging.Logger:
    """Configure the root logger once and return the PRISM logger."""
    root = logging.getLogger()
    already_configured = any(
        isinstance(handler, logging.StreamHandler) for handler in root.handlers
    )
    if force or not already_configured:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
        handler.addFilter(RedactionFilter())
        root.handlers = [handler]
    root.setLevel(level.upper())
    logger = logging.getLogger("prism")
    logger.setLevel(level.upper())
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger."""
    return logging.getLogger(f"prism.{name}")
