import json
import os
from pathlib import Path
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from muqola.identity.models import User
from muqola.loans.models import Loan
from muqola.operations import privacy


class Command(BaseCommand):
    help = "Vie privée : simulation par défaut ; effacement ciblé sous rôle maintenance uniquement."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "action",
            choices=["account", "notice", "inactivity", "retention", "receipts", "hold", "replay"],
        )
        parser.add_argument("--operator-id", required=True, type=int)
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--after-id", type=int, default=0)
        parser.add_argument("--loan-id")
        parser.add_argument("--ledger-file", type=Path)
        parser.add_argument("--backup-at", default="")
        parser.add_argument("--until", default="")
        parser.add_argument("--code", choices=["legal", "dispute"])
        parser.add_argument("--approved", default="")
        parser.add_argument("--review-confirmed", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            actor = User.objects.get(pk=options["operator_id"])
            action = options["action"]
            if action in {"inactivity", "receipts"}:
                if options["approved"]:
                    raise ValidationError("Cette action est en lecture seule.")
                if action == "inactivity":
                    result: Any = privacy.candidates(actor, options["after_id"])
                else:
                    path = options["ledger_file"]
                    if path is None:
                        raise ValidationError(
                            "--ledger-file privé requis ; aucun ledger sur stdout."
                        )
                    signed = privacy.export_receipts(actor)
                    descriptor = os.open(
                        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    with os.fdopen(descriptor, "w") as stream:
                        json.dump({"signed_ledger": signed}, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    result = {"ledger_written": str(path)}
            elif action == "replay":
                path = options["ledger_file"]
                backup = parse_datetime(options["backup_at"])
                if (
                    path is None
                    or path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_mode & 0o077
                    or path.stat().st_size > 1024 * 1024
                    or backup is None
                    or timezone.is_naive(backup)
                ):
                    raise ValidationError(
                        "Preuve JSON privée ≤1 Mio et --backup-at avec fuseau requis."
                    )
                signed = json.loads(path.read_text())["signed_ledger"]
                result = privacy.replay_operation(
                    actor,
                    signed,
                    backup,
                    options["approved"],
                    review_confirmed=options["review_confirmed"],
                )
            elif action == "hold":
                until = parse_datetime(options["until"])
                if until is None or timezone.is_naive(until) or not options["loan_id"]:
                    raise ValidationError("--loan-id et --until avec fuseau requis.")
                result = privacy.hold_operation(
                    actor, options["loan_id"], until, options["code"], options["approved"]
                )
            elif action == "retention":
                result = privacy.retention_operation(actor, options["approved"])
            else:
                if options["user_id"] is None:
                    raise ValidationError("--user-id obligatoire.")
                result = privacy.account_operation(
                    actor,
                    options["user_id"],
                    action,
                    options["approved"],
                    review_confirmed=options["review_confirmed"],
                )
        except (PermissionDenied, User.DoesNotExist) as error:
            raise CommandError(
                "Opération refusée : opérateur, cible ou rôle non autorisé."
            ) from error
        except (ProtectedError, DatabaseError) as error:
            raise CommandError(
                "Opération annulée : référence protégée ou base indisponible. "
                "Refaire une simulation."
            ) from error
        except (ValidationError, ValueError, KeyError, OSError, Loan.DoesNotExist) as error:
            raise CommandError(
                " ".join(error.messages)
                if isinstance(error, ValidationError)
                else "Paramètres invalides."
            ) from error
        self.stdout.write(json.dumps(result, default=str))
