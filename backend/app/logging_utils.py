from __future__ import annotations

import logging
import re

PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
ACCOUNT_PATTERN = re.compile(r"\b[0-9]{10,18}\b")
BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
SECRET_PATTERN = re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+")


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = PAN_PATTERN.sub("[REDACTED_PAN]", message)
        message = ACCOUNT_PATTERN.sub("[REDACTED_ACCOUNT]", message)
        message = BEARER_PATTERN.sub(r"\1[REDACTED]", message)
        message = SECRET_PATTERN.sub(lambda m: f"{m.group(1)}=[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in root.handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(SensitiveDataFilter())
