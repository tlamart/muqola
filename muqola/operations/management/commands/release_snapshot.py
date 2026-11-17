"""Read-only schema and migration inventory for reviewed releases."""

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        from muqola.operations.migration_policy import REVIEWED

        executor = MigrationExecutor(connection)
        pending = []
        for migration, backwards in executor.migration_plan(executor.loader.graph.leaf_nodes()):
            filename = inspect.getsourcefile(type(migration))
            digest = hashlib.sha256(Path(filename or "").read_bytes()).hexdigest()
            key = f"{migration.app_label}/{migration.name}"
            pending.append(
                {
                    "migration": key,
                    "sha256": digest,
                    "operations": [operation.describe() for operation in migration.operations],
                    "reviewed": not backwards and REVIEWED.get(key) == digest,
                }
            )
        recorder = MigrationRecorder(connection)
        applied = sorted([list(key) for key in recorder.applied_migrations()])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name,column_name,data_type,is_nullable,column_default, "
                "character_maximum_length,numeric_precision,numeric_scale,datetime_precision, "
                "collation_name "
                "FROM information_schema.columns WHERE table_schema='public' "
                "ORDER BY table_name,ordinal_position"
            )
            columns = cursor.fetchall()
            cursor.execute(
                "SELECT tablename,indexname,indexdef FROM pg_indexes "
                "WHERE schemaname='public' ORDER BY tablename,indexname"
            )
            indexes = cursor.fetchall()
            cursor.execute(
                "SELECT c.relname,p.conname,pg_get_constraintdef(p.oid) "
                "FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
                "ORDER BY c.relname,p.conname"
            )
            constraints = cursor.fetchall()
            cursor.execute(
                "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND NOT i.indisvalid"
            )
            invalid = cursor.fetchone()[0]
            cursor.execute(
                "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t "
                "JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname"
            )
            triggers = cursor.fetchall()
            cursor.execute(
                "SELECT p.oid,pg_get_functiondef(p.oid) FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' "
                "AND p.prokind IN ('f','p') ORDER BY p.oid"
            )
            functions = cursor.fetchall()
            cursor.execute(
                "SELECT relname,relkind,relowner,relacl::text,relrowsecurity,relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' ORDER BY relname"
            )
            relations = cursor.fetchall()
        fingerprint = hashlib.sha256(
            json.dumps(
                [applied, columns, indexes, constraints, triggers, functions, relations],
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        self.stdout.write(
            json.dumps(
                {
                    "schema": fingerprint,
                    "applied": applied,
                    "bootstrap": not bool(applied),
                    "pending": pending,
                    "invalid_indexes": invalid,
                }
            )
        )
