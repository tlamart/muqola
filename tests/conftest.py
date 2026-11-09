import os

# Valeurs synthétiques de tests uniquement ; aucune lecture de secrets réels.
os.environ.setdefault(
    "DJANGO_SECRET_KEY", "test-only-key-00000000000000000000000000000000000000000000000000"
)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
