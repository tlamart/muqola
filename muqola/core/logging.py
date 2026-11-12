import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_EVENTS = frozenset({"database_unavailable", "notification_retry", "notification_failed"})


class SafeJsonFormatter(logging.Formatter):
    """JSON fermé : métadonnées de code uniquement, jamais de texte d'exception."""

    def format(self, record: logging.LogRecord) -> str:
        event = (
            record.msg if isinstance(record.msg, str) and record.msg in _EVENTS else "runtime_event"
        )
        payload: dict[str, str | int] = {
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        }
        # Ne jamais appeler getMessage(), formatException() ou formatStack().
        filename, function, line = record.pathname, record.funcName, record.lineno
        if record.exc_info and record.exc_info[0] is not None:
            name = record.exc_info[0].__name__
            payload["exception_type"] = name if _IDENTIFIER.fullmatch(name) else "Exception"
            traceback = record.exc_info[2]
            # Dernière frame applicative : pas de chemin système ou de source/locals.
            while traceback is not None:
                code = traceback.tb_frame.f_code
                if self._module(code.co_filename) is not None:
                    filename, function, line = code.co_filename, code.co_name, traceback.tb_lineno
                traceback = traceback.tb_next
        module = self._module(filename)
        if module is not None:
            payload["module"] = module
            if isinstance(function, str) and _IDENTIFIER.fullmatch(function):
                payload["function"] = function
            if type(line) is int and line > 0:
                payload["line"] = line
        return json.dumps(payload)

    @staticmethod
    def _module(filename: str) -> str | None:
        try:
            relative = Path(filename).resolve().relative_to(_PROJECT_ROOT)
        except (ValueError, OSError):
            return None
        if relative.suffix != ".py":
            return None
        parts = relative.with_suffix("").parts
        if parts[0] in {"muqola", "config"} and all(_IDENTIFIER.fullmatch(part) for part in parts):
            return ".".join(parts)
        return None
