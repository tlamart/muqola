import base64

from cryptography.fernet import Fernet
from django.utils.crypto import salted_hmac


def secret_cipher(context: str) -> Fernet:
    key = salted_hmac(f"muqola.{context}", "v1", algorithm="sha256").digest()
    return Fernet(base64.urlsafe_b64encode(key))
