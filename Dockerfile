# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
# Secret CA facultatif : support du proxy Cloud sans le conserver dans l'image.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir --require-hashes -r requirements.txt
COPY . .
RUN chmod -R a+rX /app \
    && groupadd --gid 10001 muqola && useradd --uid 10001 --gid muqola --no-create-home muqola \
    && DJANGO_SECRET_KEY=build-only-placeholder-never-used-by-runtime-000000000000000000 \
       python manage.py collectstatic --noinput
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=30", "--graceful-timeout=20", "--error-logfile=-", "--log-level=warning"]
