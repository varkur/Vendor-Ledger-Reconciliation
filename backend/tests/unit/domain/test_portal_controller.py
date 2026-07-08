"""
Unit tests for vendor portal controller new endpoints.

Tests the new endpoints added for Requirements 24.1, 24.2, 24.3, 24.4, 33.1, 33.2:
- POST /api/v1/vlr/portal/validate-token
- GET /api/v1/vlr/portal/statement/{case_id}
- POST /api/v1/vlr/portal/sign-off/{case_id}
"""

import pytest
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi import HTTPException

from src.api.v1.schemas.vlr.portal_schemas import (
    PortalCaseSignOffRequest,
    PortalValidateTokenRequest,
    PortalValidateTokenResponse,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeCase:
    """Fake reconciliation case for testing."""

    id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    vendor_id: UUID = field(default_factory=uuid4)
    status: str = "matched"
    portal_token: str = "test-token-abc123"
    token_expiry: datetime | None = None
    upload_count: int = 1
    is_deleted: bool = False
    vendor_opening_balance: Decimal | None = Decimal("10000.00")
    vendor_closing_balance: Decimal | None = Decimal("15000.00")
    net_difference: Decimal | None = Decimal("500.00")
    modified_date: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class FakeVendor:
    """Fake vendor for testing."""

    id: UUID = field(default_factory=uuid4)
    name: str = "Test Vendor Ltd"
    vendor_code: str = "V001"
    company_code: str = "CC01"


@dataclass
class FakeRequest:
    """Fake reconciliation request for testing."""

    id: UUID = field(default_factory=uuid4)
    period_start: date = field(default_factory=lambda: date(2024, 1, 1))
    period_end: date = field(default_factory=lambda: date(2024, 12, 31))
    company_code: str = "CC01"


# ─── Tests for _validate_portal_token_with_expiry ─────────────────────────────


class TestValidatePortalTokenWithExpiry:
    """Tests for the _validate_portal_token_with_expiry helper."""

    @pytest.mark.asyncio
    async def test_returns_case_for_valid_token(self):
        """Valid, non-expired token returns associated case."""
        from src.api.v1.endpoints.vlr.portal_controller import (
            _validate_portal_token_with_expiry,
        )

        case = FakeCase(
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30)
        )

        mock_session = AsyncMock()
        with patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_token.return_value = case
            MockRepo.return_value = mock_repo_instance

            result = await _validate_portal_token_with_expiry(
                "valid-token", mock_session
            )
            assert result == case

    @pytest.mark.asyncio
    async def test_raises_404_for_unknown_token(self):
        """Unknown token raises 404 Not Found."""
        from src.api.v1.endpoints.vlr.portal_controller import (
            _validate_portal_token_with_expiry,
        )

        mock_session = AsyncMock()
        with patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_token.return_value = None
            MockRepo.return_value = mock_repo_instance

            with pytest.raises(HTTPException) as exc_info:
                await _validate_portal_token_with_expiry(
                    "unknown-token", mock_session
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_410_for_expired_token(self):
        """Expired token raises 410 Gone (per design.md)."""
        from src.api.v1.endpoints.vlr.portal_controller import (
            _validate_portal_token_with_expiry,
        )

        case = FakeCase(
            token_expiry=datetime.now(timezone.utc) - timedelta(days=1)
        )

        mock_session = AsyncMock()
        with patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_token.return_value = case
            MockRepo.return_value = mock_repo_instance

            with pytest.raises(HTTPException) as exc_info:
                await _validate_portal_token_with_expiry(
                    "expired-token", mock_session
                )
            assert exc_info.value.status_code == 410
            assert "expired" in exc_info.value.detail.lower()
            assert "90 days" in exc_info.value.detail


# ─── Tests for POST /validate-token ──────────────────────────────────────────


class TestValidateTokenEndpoint:
    """Tests for POST /api/v1/vlr/portal/validate-token."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_case_summary(self):
        """Valid token returns vendor name, period, and status."""
        from src.api.v1.endpoints.vlr.portal_controller import validate_token

        case = FakeCase(
            token_expiry=datetime.now(timezone.utc) + timedelta(days=60)
        )
        vendor = FakeVendor(id=case.vendor_id)
        recon_request = FakeRequest(id=case.request_id)

        mock_session = AsyncMock()

        # Mock the scalar_one_or_none for vendor and request queries
        vendor_result = MagicMock()
        vendor_result.scalar_one_or_none.return_value = vendor
        request_result = MagicMock()
        request_result.scalar_one_or_none.return_value = recon_request
        mock_session.execute.side_effect = [vendor_result, request_result]

        body = PortalValidateTokenRequest(token=case.portal_token)

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_token.return_value = case
            MockRepo.return_value = mock_repo_instance

            result = await validate_token(body, mock_session)

            assert result.case_id == case.id
            assert result.vendor_name == "Test Vendor Ltd"
            assert result.period_start == date(2024, 1, 1)
            assert result.period_end == date(2024, 12, 31)
            assert result.status == "matched"
            assert result.upload_count == 1

    @pytest.mark.asyncio
    async def test_expired_token_returns_410(self):
        """Expired token (>90 days) returns 410 Gone."""
        from src.api.v1.endpoints.vlr.portal_controller import validate_token

        case = FakeCase(
            token_expiry=datetime.now(timezone.utc) - timedelta(days=5)
        )

        mock_session = AsyncMock()
        body = PortalValidateTokenRequest(token="expired-token")

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_token.return_value = case
            MockRepo.return_value = mock_repo_instance

            with pytest.raises(HTTPException) as exc_info:
                await validate_token(body, mock_session)
            assert exc_info.value.status_code == 410

    @pytest.mark.asyncio
    async def test_unknown_token_returns_404(self):
        """Non-existent token returns 404."""
        from src.api.v1.endpoints.vlr.portal_controller import validate_token

        mock_session = AsyncMock()
        body = PortalValidateTokenRequest(token="does-not-exist")

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_token.return_value = None
            MockRepo.return_value = mock_repo_instance

            with pytest.raises(HTTPException) as exc_info:
                await validate_token(body, mock_session)
            assert exc_info.value.status_code == 404


# ─── Tests for GET /statement/{case_id} ──────────────────────────────────────


class TestStatementByCaseEndpoint:
    """Tests for GET /api/v1/vlr/portal/statement/{case_id}."""

    @pytest.mark.asyncio
    async def test_returns_vendor_facing_results(self):
        """Valid request returns vendor-facing statement without internal SAP data."""
        from src.api.v1.endpoints.vlr.portal_controller import get_statement_by_case

        case = FakeCase(
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30)
        )
        vendor = FakeVendor(id=case.vendor_id)
        recon_request = FakeRequest(id=case.request_id)

        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get.return_value = None

        # Mock executes: vendor, request, matched_count, unmatched_count, match_summary
        vendor_result = MagicMock()
        vendor_result.scalar_one_or_none.return_value = vendor
        request_result = MagicMock()
        request_result.scalar_one_or_none.return_value = recon_request
        matched_count_result = MagicMock()
        matched_count_result.scalar_one.return_value = 15
        unmatched_count_result = MagicMock()
        unmatched_count_result.scalar_one.return_value = 3
        match_summary_result = MagicMock()
        match_summary_result.all.return_value = [
            MagicMock(match_type="exact", count=10, total_amount=Decimal("50000.00")),
            MagicMock(match_type="tolerance", count=5, total_amount=Decimal("25000.00")),
        ]

        mock_session.execute.side_effect = [
            vendor_result,
            request_result,
            matched_count_result,
            unmatched_count_result,
            match_summary_result,
        ]

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller._validate_portal_token_with_expiry",
            return_value=case,
        ):
            result = await get_statement_by_case(
                case_id=case.id,
                request=mock_request,
                x_portal_token="valid-token",
                session=mock_session,
            )

            assert result.case_id == case.id
            assert result.vendor_name == "Test Vendor Ltd"
            assert result.total_matched_entries == 15
            assert result.total_unmatched_vendor == 3
            assert result.vendor_opening_balance == Decimal("10000.00")
            assert result.vendor_closing_balance == Decimal("15000.00")
            assert result.net_difference == Decimal("500.00")
            assert len(result.match_summary) == 2

    @pytest.mark.asyncio
    async def test_wrong_case_id_returns_404(self):
        """Accessing a case that doesn't belong to the token returns 404."""
        from src.api.v1.endpoints.vlr.portal_controller import get_statement_by_case

        case = FakeCase(
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30)
        )
        different_case_id = uuid4()

        mock_session = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller._validate_portal_token_with_expiry",
            return_value=case,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_statement_by_case(
                    case_id=different_case_id,
                    request=mock_request,
                    x_portal_token="valid-token",
                    session=mock_session,
                )
            assert exc_info.value.status_code == 404


# ─── Tests for POST /sign-off/{case_id} ──────────────────────────────────────


class TestSignOffCaseEndpoint:
    """Tests for POST /api/v1/vlr/portal/sign-off/{case_id}."""

    @pytest.mark.asyncio
    async def test_successful_sign_off(self):
        """Valid sign-off creates record and updates status."""
        from src.api.v1.endpoints.vlr.portal_controller import sign_off_case

        case = FakeCase(
            status="matched",
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30),
        )

        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.headers.get.return_value = None

        body = PortalCaseSignOffRequest(
            confirmation_text="I confirm the reconciliation statement is accurate.",
            statement_version="abc123def456",
        )

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller._validate_portal_token_with_expiry",
            return_value=case,
        ), patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            result = await sign_off_case(
                case_id=case.id,
                body=body,
                request=mock_request,
                x_portal_token="valid-token",
                session=mock_session,
            )

            assert result.case_id == case.id
            assert result.ip_address == "10.0.0.1"
            assert result.confirmation_text == body.confirmation_text
            assert result.statement_version == "abc123def456"
            assert result.status == "signed_off"
            # Verify sign-off record was added to session
            mock_session.add.assert_called_once()
            mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_sign_off_wrong_case_returns_404(self):
        """Sign-off for a case that doesn't belong to the token returns 404."""
        from src.api.v1.endpoints.vlr.portal_controller import sign_off_case

        case = FakeCase(
            status="matched",
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30),
        )

        mock_session = AsyncMock()
        mock_request = MagicMock()
        body = PortalCaseSignOffRequest(
            confirmation_text="Confirmed",
            statement_version="v1",
        )

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller._validate_portal_token_with_expiry",
            return_value=case,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await sign_off_case(
                    case_id=uuid4(),  # Different case
                    body=body,
                    request=mock_request,
                    x_portal_token="valid-token",
                    session=mock_session,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_sign_off_wrong_status_returns_409(self):
        """Sign-off for a case not in allowed status returns 409."""
        from src.api.v1.endpoints.vlr.portal_controller import sign_off_case

        case = FakeCase(
            status="created",  # Not in allowed statuses
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30),
        )

        mock_session = AsyncMock()
        mock_request = MagicMock()
        body = PortalCaseSignOffRequest(
            confirmation_text="Confirmed",
            statement_version="v1",
        )

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller._validate_portal_token_with_expiry",
            return_value=case,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await sign_off_case(
                    case_id=case.id,
                    body=body,
                    request=mock_request,
                    x_portal_token="valid-token",
                    session=mock_session,
                )
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_sign_off_captures_forwarded_ip(self):
        """Sign-off captures X-Forwarded-For IP when behind a proxy."""
        from src.api.v1.endpoints.vlr.portal_controller import sign_off_case

        case = FakeCase(
            status="review",
            token_expiry=datetime.now(timezone.utc) + timedelta(days=30),
        )

        mock_session = AsyncMock()
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = "203.0.113.50, 10.0.0.1"

        body = PortalCaseSignOffRequest(
            confirmation_text="Approved",
            statement_version="v2",
        )

        with patch(
            "src.api.v1.endpoints.vlr.portal_controller._validate_portal_token_with_expiry",
            return_value=case,
        ), patch(
            "src.api.v1.endpoints.vlr.portal_controller.CaseRepositoryImpl"
        ) as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            result = await sign_off_case(
                case_id=case.id,
                body=body,
                request=mock_request,
                x_portal_token="valid-token",
                session=mock_session,
            )

            assert result.ip_address == "203.0.113.50"
