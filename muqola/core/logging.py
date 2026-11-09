import json
import logging


class SafeJsonFormatter(logging.Formatter):
    """Aucune URL, paramètre, exception ou donnée de requête dans les logs."""

    def format(self, record: logging.LogRecord) -> str:
        # Liste fermée : les événements utiles seront ajoutés avec leurs fonctionnalités.
        event = (
            record.msg
            if record.msg in {"database_unavailable", "account_email_retry"}
            else "runtime_event"
        )
        return json.dumps({"level": record.levelname, "logger": record.name, "event": event})
