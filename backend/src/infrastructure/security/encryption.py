"""
Symmetric encryption utilities for sensitive data (SAP credentials, etc.).

Uses Fernet (AES-128-CBC with HMAC-SHA256) for authenticated encryption.
If no ENCRYPTION_KEY is configured, falls back to a deterministic key derived
from the JWT_SECRET_KEY (not ideal for production — a dedicated key is recommended).

Security: Encrypted values are stored as URL-safe base64 strings.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from src.config.settings import settings

logger = logging.getLogger(__name__)


def _get_fernet_key() -> bytes:
    """
    Derive a valid 32-byte Fernet key.

    Priority:
    1. ENCRYPTION_KEY from settings (must be a valid Fernet key / base64-encoded 32 bytes)
    2. Derived from JWT_SECRET_KEY via SHA-256 (fallback for dev environments)
    """
    if settings.ENCRYPTION_KEY:
        # Assume it's already a valid Fernet key (base64-encoded 32 bytes)
        return settings.ENCRYPTION_KEY.encode()

    # Fallback: derive from JWT secret (deterministic, suitable for dev only)
    digest = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string and return a URL-safe base64-encoded ciphertext.

    Args:
        plaintext: The value to encrypt.

    Returns:
        Encrypted string (Fernet token).
    """
    if not plaintext:
        return ""
    key = _get_fernet_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted ciphertext string.

    Args:
        ciphertext: The encrypted value (Fernet token).

    Returns:
        Decrypted plaintext string.

    Raises:
        ValueError: If decryption fails (invalid key or corrupted data).
    """
    if not ciphertext:
        return ""
    key = _get_fernet_key()
    f = Fernet(key)
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        logger.error("Failed to decrypt value — invalid key or corrupted ciphertext.")
        raise ValueError("Decryption failed: invalid key or corrupted data.") from exc


def mask_credential(value: str, visible_chars: int = 4) -> str:
    """
    Mask a credential value for safe display in API responses.

    Shows only the last `visible_chars` characters, replacing the rest with asterisks.
    Returns '****' if the value is shorter than the visible portion.

    Args:
        value: The credential value to mask.
        visible_chars: Number of trailing characters to keep visible.

    Returns:
        Masked string (e.g., '********word' for 'password').
    """
    if not value:
        return ""
    if len(value) <= visible_chars:
        return "*" * len(value)
    masked_len = len(value) - visible_chars
    return "*" * masked_len + value[-visible_chars:]
