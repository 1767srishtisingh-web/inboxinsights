"""Fernet encryption/decryption for OAuth token storage."""
import json
from typing import Union
from cryptography.fernet import Fernet
from config.settings import FERNET_KEY

_fernet = Fernet(FERNET_KEY)


def encrypt_token(token_data: Union[str, dict]) -> bytes:
    """Encrypt a JSON string or dict and return bytes."""
    if isinstance(token_data, dict):
        token_str = json.dumps(token_data)
    else:
        token_str = str(token_data)
    return _fernet.encrypt(token_str.encode("utf-8"))


def decrypt_token(token_bytes: Union[bytes, str]) -> str:
    """Decrypt bytes back to a JSON string."""
    if isinstance(token_bytes, str):
        token_bytes = token_bytes.encode("utf-8")
    return _fernet.decrypt(token_bytes).decode("utf-8")
