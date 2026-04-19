import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from api.config import settings

def _get_key() -> bytes:
    key = settings.encryption_key.encode()
    return key[:32].ljust(32, b"0")

def encrypt_token(plaintext: str) -> tuple[bytes, bytes]:
    aesgcm = AESGCM(_get_key())
    iv = os.urandom(12)
    return aesgcm.encrypt(iv, plaintext.encode(), None), iv

def decrypt_token(ciphertext: bytes, iv: bytes) -> str:
    return AESGCM(_get_key()).decrypt(iv, ciphertext, None).decode()
