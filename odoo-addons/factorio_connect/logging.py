"""Redact at output handlers, including already-formatted exception tracebacks."""
import logging
import re
import traceback

_PATH = re.compile(r'(/odoo/events/)[^\s\"\'<>?#)]+')
_BEARER = re.compile(r'(?i)(Bearer\s+)[^\s\"\'<>]+')


class RedactionFilter(logging.Filter):
    def __init__(self, secrets=()):
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def redact(self, value):
        result = _PATH.sub(r'\1[REDACTED]', str(value))
        result = _BEARER.sub(r'\1[REDACTED]', result)
        for secret in self.secrets:
            result = result.replace(secret, '[REDACTED]')
        return result

    def _argument(self, value):
        # Structured formatters (notably Uvicorn's) unpack the original tuple.
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, tuple):
            return tuple(self._argument(item) for item in value)
        if isinstance(value, dict):
            return {key: self._argument(item) for key, item in value.items()}
        return self.redact(value)

    def filter(self, record):
        record.msg = self.redact(record.msg)
        record.args = self._argument(record.args)
        if record.exc_info:
            record.exc_text = self.redact(''.join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self.redact(record.stack_info)
        return True


def install_redaction(secrets=()):
    redaction = RedactionFilter(secrets)
    loggers = [logging.getLogger()] + [logger for logger in logging.Logger.manager.loggerDict.values() if isinstance(logger, logging.Logger)]
    for logger in loggers:
        for handler in logger.handlers:
            existing = next((item for item in handler.filters if isinstance(item, RedactionFilter)), None)
            if existing is None:
                handler.addFilter(redaction)
            else:
                existing.secrets = tuple(sorted(set(existing.secrets + redaction.secrets), key=len, reverse=True))
