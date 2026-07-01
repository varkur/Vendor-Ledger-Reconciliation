"""
Unit tests for password hashing and verification.
"""

from src.infrastructure.security.password_encoder import hash_password, verify_password


class TestPasswordEncoder:
    """Password encoder unit tests."""

    def test_hash_password_returns_hash(self):
        """Hashing should return a non-empty string different from input."""
        plain = "MySecurePassword123!"
        hashed = hash_password(plain)

        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != plain

    def test_verify_correct_password(self):
        """Correct password should verify successfully."""
        plain = "MySecurePassword123!"
        hashed = hash_password(plain)

        assert verify_password(plain, hashed) is True

    def test_verify_incorrect_password(self):
        """Incorrect password should fail verification."""
        hashed = hash_password("CorrectPassword123!")

        assert verify_password("WrongPassword456!", hashed) is False

    def test_different_hashes_for_same_password(self):
        """BCrypt should produce different hashes for the same input (salted)."""
        plain = "SamePassword!"
        hash1 = hash_password(plain)
        hash2 = hash_password(plain)

        assert hash1 != hash2
        # Both should still verify
        assert verify_password(plain, hash1) is True
        assert verify_password(plain, hash2) is True
