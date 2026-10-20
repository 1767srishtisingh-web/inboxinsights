"""Fernet encryption/decryption for OAuth token storage."""
from cryptography.fernet import Fernet
from config.settings import FERNET_KEY

_fernet = Fernet(FERNET_KEY)


def encrypt_token(token_json: str) -> bytes:
    """Encrypt a JSON string and return bytes."""
    return _fernet.encrypt(token_json.encode("utf-8"))


def decrypt_token(token_bytes: bytes) -> str:
    """Decrypt bytes back to a JSON string."""
    return _fernet.decrypt(token_bytes).decode("utf-8")
