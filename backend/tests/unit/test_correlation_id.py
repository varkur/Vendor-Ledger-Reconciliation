"""
Unit tests for Correlation ID management.
"""

from src.observability.correlation import (
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
)


class TestCorrelationId:
    """Correlation ID context management tests."""

    def test_generate_correlation_id_is_uuid(self):
        """Generated correlation ID should be a valid UUID string."""
        cid = generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 36  # UUID format: 8-4-4-4-12

    def test_set_and_get_correlation_id(self):
        """Setting a correlation ID should be retrievable."""
        test_id = "test-correlation-123"
        set_correlation_id(test_id)
        assert get_correlation_id() == test_id

    def test_correlation_id_propagation(self):
        """Correlation ID should persist within the same context."""
        cid = generate_correlation_id()
        set_correlation_id(cid)

        # Simulate accessing it from another function in the same context
        retrieved = get_correlation_id()
        assert retrieved == cid

    def test_different_generations_are_unique(self):
        """Each generated ID should be unique."""
        id1 = generate_correlation_id()
        id2 = generate_correlation_id()
        assert id1 != id2
