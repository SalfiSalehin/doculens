"""Logging with secret redaction.

Every log record passes through :class:`RedactingFilter`, which masks common secret
patterns (tokens, passwords, API keys, Authorization headers), e-mail addresses, and
any exact secret values registered at startup.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization: Bearer abc / authorization=abc
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?[^\s,;]+"), r"\1" + REDACTED),
    # Bare bearer tokens
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}"), "Bearer " + REDACTED),
    # key=value / key: value for sensitive key names
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)"
            r"[A-Za-z0-9_]*)(\s*[:=]\s*)(['\"]?)[^\s'\",;&]+"
        ),
        r"\1\2\3" + REDACTED,
    ),
    # E-mail addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
]


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    for value in secrets:
        if value and len(value) >= 6:
            text = text.replace(value, REDACTED)
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # malformed format args: keep the raw msg, still redact
            message = str(record.msg)
        record.msg = redact(message, self._secrets)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self._secrets)
        return True


def configure_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    """Configure the root logger once with a redacting handler."""
    root = logging.getLogger()
    root.setLevel(level)
    redactor = RedactingFilter(secrets)
    handler = next((h for h in root.handlers if getattr(h, "_doculens", False)), None)
    if handler is None:
        handler = logging.StreamHandler()
        handler._doculens = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    handler.filters = [redactor]
    # Uvicorn's own loggers propagate to root; make sure they are filtered too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.filters = [f for f in lg.filters if not isinstance(f, RedactingFilter)] + [redactor]
