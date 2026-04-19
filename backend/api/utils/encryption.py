"""
AES-256-GCM encryption utilities for storing GitHub OAuth tokens at rest.

Tokens are encrypted before being written to the database and decrypted
only when needed (e.g. to call the GitHub API). The key is derived from
the APP_SECRET_KEY environment variable, zero-padded to 32 bytes.
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from api.config import settings


def _get_key() -> bytes:
    """Return a 32-byte AES key derived from the configured secret."""
    key = settings.encryption_key.encode()
    return key[:32].ljust(32, b"0")


def encrypt_token(plaintext: str) -> tuple[bytes, bytes]:
    """
    Encrypt a GitHub access token using AES-256-GCM.

    Args:
        plaintext: The raw GitHub OAuth access token.

    Returns:
        (ciphertext, iv) — both as bytes. Store both in the database;
        the IV is required for decryption.
    """
    aesgcm = AESGCM(_get_key())
    iv = os.urandom(12)
    return aesgcm.encrypt(iv, plaintext.encode(), None), iv


def decrypt_token(ciphertext: bytes, iv: bytes) -> str:
    """
    Decrypt a GitHub access token that was encrypted with encrypt_token.

    Args:
        ciphertext: The encrypted token bytes from the database.
        iv: The 12-byte initialisation vector used during encryption.

    Returns:
        The plaintext GitHub access token string.
    """
    return AESGCM(_get_key()).decrypt(iv, ciphertext, None).decode()
