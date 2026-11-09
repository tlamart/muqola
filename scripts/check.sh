#!/bin/sh
set -eu
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy config muqola tests manage.py
uv run --frozen python manage.py check
uv run --frozen python manage.py makemigrations --check --dry-run
uv run --frozen python manage.py migrate --noinput
uv run --frozen python manage.py collectstatic --noinput
uv run --frozen pytest
