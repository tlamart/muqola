"""A local SQL time budget for read-only search, never for domain writes."""

from collections.abc import Callable
from functools import wraps

from django.db import OperationalError, connection, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from psycopg.errors import QueryCanceled


def bounded_search(
    view: Callable[[HttpRequest], HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    @wraps(view)
    def wrapped(request: HttpRequest) -> HttpResponse:
        if request.method != "GET":
            return view(request)
        try:
            # SET LOCAL expires on commit/rollback: no connection-pool pollution,
            # and migrations/domain writes keep their existing time budgets.
            # Avoid JIT compilation for these short-lived, correlated OLTP reads.
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('statement_timeout', '5s', true), "
                        "set_config('jit', 'off', true)"
                    )
                return view(request)
        except OperationalError as error:
            if not isinstance(error.__cause__, QueryCanceled):
                raise
            response = render(request, "search_timeout.html", status=503)
            response["Retry-After"] = "1"
            return response

    return wrapped
