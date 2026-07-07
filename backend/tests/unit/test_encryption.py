"""
Unit tests for the encryption utility module.

Tests encryption/decryption round-trip, credential masking,
and edge cases.
"""

import pytest

from src.infrastructure.security.encryption import (
    decrypt_value,
    encrypt_value,
    mask_credential,
)


class TestEncryptDecrypt:
    """Test symmetric encryption/decryption round-trip."""

    def test_encrypt_decrypt_round_trip(self):
        """Encrypting then decrypting should return the original value."""
        plaintext = "my-secret-password"
        ciphertext = encrypt_value(plaintext)
        assert ciphertext != plaintext  # not stored as plaintext
        assert decrypt_value(ciphertext) == plaintext

    def test_encrypt_empty_string_returns_empty(self):
        """Empty string should encrypt to empty string."""
        assert encrypt_value("") == ""
        assert decrypt_value("") == ""

    def test_encrypt_produces_different_ciphertexts(self):
        """Multiple encryptions of the same value should produce different ciphertexts (Fernet uses random IV)."""
        plaintext = "password123"
        ct1 = encrypt_value(plaintext)
        ct2 = encrypt_value(plaintext)
        # Fernet uses a random IV, so ciphertexts should differ
        assert ct1 != ct2
        # Both should decrypt to same value
        assert decrypt_value(ct1) == plaintext
        assert decrypt_value(ct2) == plaintext

    def test_decrypt_invalid_ciphertext_raises_value_error(self):
        """Decrypting invalid data should raise ValueError."""
        with pytest.raises(ValueError, match="Decryption failed"):
            decrypt_value("not-a-valid-fernet-token")

    def test_encrypt_unicode_value(self):
        """Should handle unicode characters in credentials."""
        plaintext = "pässwörd_ñ_中文"
        ciphertext = encrypt_value(plaintext)
        assert decrypt_value(ciphertext) == plaintext

    def test_encrypt_long_value(self):
        """Should handle long credential values."""
        plaintext = "a" * 1000
        ciphertext = encrypt_value(plaintext)
        assert decrypt_value(ciphertext) == plaintext


class TestMaskCredential:
    """Test credential masking for API responses."""

    def test_mask_normal_password(self):
        """Standard password should mask all but last 4 chars."""
        result = mask_credential("mypassword")
        assert result == "******word"

    def test_mask_short_value(self):
        """Short values (≤4 chars) should be fully masked."""
        assert mask_credential("abc") == "***"
        assert mask_credential("abcd") == "****"

    def test_mask_empty_string(self):
        """Empty string should return empty string."""
        assert mask_credential("") == ""

    def test_mask_exact_visible_chars(self):
        """Value exactly matching visible_chars length should be fully masked."""
        assert mask_credential("test", visible_chars=4) == "****"

    def test_mask_custom_visible_chars(self):
        """Custom visible_chars parameter should work correctly."""
        result = mask_credential("mysecretvalue", visible_chars=3)
        assert result == "**********lue"

    def test_mask_username(self):
        """Username masking should work the same way."""
        result = mask_credential("admin_user")
        assert result == "******user"
