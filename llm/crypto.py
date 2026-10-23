"""
Encryption for provider API keys stored in the database.

Keys are encrypted with Fernet using LLM_ENCRYPTION_KEYS (comma-separated).
The first key encrypts; every key can decrypt, so a new key can be put first
and old values re-encrypted (`manage.py rotate_llm_keys`) before the old key
is removed.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionError(Exception):
    pass


def _fernet():
    keys = settings.LLM_ENCRYPTION_KEYS
    if not keys:
        raise ImproperlyConfigured(
            "LLM_ENCRYPTION_KEYS is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except ValueError as exc:
        raise ImproperlyConfigured(f"LLM_ENCRYPTION_KEYS contains an invalid Fernet key: {exc}")


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise DecryptionError("Stored API key cannot be decrypted with LLM_ENCRYPTION_KEYS.")


def rotate(token):
    """Re-encrypt with the current primary key."""
    return _fernet().rotate(token.encode()).decode()
