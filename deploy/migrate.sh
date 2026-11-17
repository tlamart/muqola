#!/bin/sh
set -eu
python manage.py migrate --noinput
exec python manage.py grant_runtime_privileges
