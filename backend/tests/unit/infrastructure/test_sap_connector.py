"""
Unit tests for SAP Connector Service.

Tests SAP field mapping, duplicate detection, retry logic,
rollback on failure, and health monitoring.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from src.infrastructure.external.sap_connector import (
    SAPConnectorService,
    SAPConfig,
    SAPLedgerEntry,
    SAPVendorData,
    DateRange,
    ConnectionTestResult,
    SAPHealthStatus,
    ExtractionResult,
    SAP_FIELD_MAPPING,
    INTERNAL_TO_SAP_MAPPING,
    MAX_RETRIES,
    BASE_BACKOFF_SECONDS,
    map_sap_entry_to_internal,
    map_internal_to_sap,
    detect_duplicates,
    _parse_sap_date,
)
from src.domain.exceptions.vlr import SAPConnectionException


# ---------------------------------------------------------------------------
# Test SAP Field Mapping
# ---------------------------------------------------------------------------


class TestSAPFieldMapping:
    """Test SAP field mapping constants and round-trip conversions."""

    def test_sap_field_mapping_has_all_required_fields(self):
        """Mapping must include all 7 required SAP fields."""
        assert SAP_FIELD_MAPPING == {
            "ZUONR": "assignment_number",
            "BELNR": "document_number",
            "BLART": "document_type",
            "DMBTR": "amount",
            "BUDAT": "posting_date",
            "AUGDT": "clearing_date",
            "AUGBL": "clearing_document",
        }

    def test_reverse_mapping_is_inverse(self):
        """Reverse mapping should be the exact inverse."""
        for sap_key, internal_key in SAP_FIELD_MAPPING.items():
            assert INTERNAL_TO_SAP_MAPPING[internal_key] == sap_key

    def test_map_sap_entry_to_internal_basic(self):
        """map_sap_entry_to_internal maps SAP field names correctly."""
        raw = {
            "ZUONR": "ASN001",
            "BELNR": "DOC123",
            "BLART": "RE",
            "DMBTR": "1500.50",
            "BUDAT": "20240115",
            "AUGDT": "20240220",
            "AUGBL": "CLR456",
            "LIFNR": "V001",
            "BUKRS": "1000",
            "WAERS": "INR",
        }
        entry = map_sap_entry_to_internal(raw)

        assert entry.assignment_number == "ASN001"
        assert entry.document_number == "DOC123"
        assert entry.document_type == "RE"
        assert entry.amount == Decimal("1500.50")
        assert entry.posting_date == date(2024, 1, 15)
        assert entry.clearing_date == date(2024, 2, 20)
        assert entry.clearing_document == "CLR456"
        assert entry.vendor_code == "V001"
        assert entry.company_code == "1000"
        assert entry.currency == "INR"

    def test_map_sap_entry_with_none_values(self):
        """Fields with None values should be mapped as None."""
        raw = {
            "ZUONR": None,
            "BELNR": "DOC001",
            "BLART": None,
            "DMBTR": "100.00",
            "BUDAT": "20240101",
            "AUGDT": None,
            "AUGBL": None,
        }
        entry = map_sap_entry_to_internal(raw)

        assert entry.assignment_number is None
        assert entry.document_number == "DOC001"
        assert entry.document_type is None
        assert entry.amount == Decimal("100.00")
        assert entry.posting_date == date(2024, 1, 1)
        assert entry.clearing_date is None
        assert entry.clearing_document is None

    def test_map_sap_entry_with_iso_date_format(self):
        """Should also parse ISO date format (YYYY-MM-DD)."""
        raw = {
            "ZUONR": "ASN001",
            "BELNR": "DOC001",
            "BLART": "RE",
            "DMBTR": "250.00",
            "BUDAT": "2024-03-15",
            "AUGDT": "2024-04-01",
            "AUGBL": "CLR001",
        }
        entry = map_sap_entry_to_internal(raw)

        assert entry.posting_date == date(2024, 3, 15)
        assert entry.clearing_date == date(2024, 4, 1)

    def test_map_internal_to_sap_round_trip(self):
        """Mapping to internal and back to SAP should preserve values."""
        raw = {
            "ZUONR": "ASN001",
            "BELNR": "DOC123",
            "BLART": "RE",
            "DMBTR": "1500.50",
            "BUDAT": "20240115",
            "AUGDT": "20240220",
            "AUGBL": "CLR456",
            "LIFNR": "V001",
            "BUKRS": "1000",
        }
        entry = map_sap_entry_to_internal(raw)
        result = map_internal_to_sap(entry)

        assert result["ZUONR"] == "ASN001"
        assert result["BELNR"] == "DOC123"
        assert result["BLART"] == "RE"
        assert result["DMBTR"] == 1500.50
        assert result["BUDAT"] == "20240115"
        assert result["AUGDT"] == "20240220"
        assert result["AUGBL"] == "CLR456"

    def test_map_sap_entry_zero_date_returns_none(self):
        """SAP zero-date (00000000) should parse to None."""
        raw = {
            "ZUONR": "ASN001",
            "BELNR": "DOC001",
            "BLART": "RE",
            "DMBTR": "100",
            "BUDAT": "20240101",
            "AUGDT": "00000000",
            "AUGBL": None,
        }
        entry = map_sap_entry_to_internal(raw)
        assert entry.clearing_date is None


# ---------------------------------------------------------------------------
# Test Date Parsing
# ---------------------------------------------------------------------------


class TestDateParsing:
    """Test SAP date parsing helper."""

    def test_parse_yyyymmdd(self):
        assert _parse_sap_date("20240315") == date(2024, 3, 15)

    def test_parse_iso_format(self):
        assert _parse_sap_date("2024-03-15") == date(2024, 3, 15)

    def test_parse_none(self):
        assert _parse_sap_date(None) is None

    def test_parse_empty_string(self):
        assert _parse_sap_date("") is None

    def test_parse_zero_date(self):
        assert _parse_sap_date("00000000") is None

    def test_parse_date_object(self):
        d = date(2024, 5, 20)
        assert _parse_sap_date(d) == d

    def test_parse_invalid_date(self):
        assert _parse_sap_date("invalid") is None


# ---------------------------------------------------------------------------
# Test Duplicate Detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Test SAP entry duplicate detection logic."""

    def test_no_duplicates(self):
        """All unique entries should be returned as-is."""
        entries = [
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC2", amount=Decimal("200.00")),
            SAPLedgerEntry(document_number="DOC3", amount=Decimal("300.00")),
        ]
        period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))

        unique, dupes = detect_duplicates(entries, "V001", period)
        assert len(unique) == 3
        assert len(dupes) == 0

    def test_with_duplicates(self):
        """Entries with same vendor+document_number+amount are duplicates."""
        entries = [
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC2", amount=Decimal("200.00")),
        ]
        period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))

        unique, dupes = detect_duplicates(entries, "V001", period)
        assert len(unique) == 2
        assert len(dupes) == 1

    def test_same_document_different_amount_not_duplicate(self):
        """Same document_number but different amount is NOT a duplicate."""
        entries = [
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("200.00")),
        ]
        period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))

        unique, dupes = detect_duplicates(entries, "V001", period)
        assert len(unique) == 2
        assert len(dupes) == 0

    def test_empty_entries(self):
        """Empty input should return empty results."""
        period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        unique, dupes = detect_duplicates([], "V001", period)
        assert len(unique) == 0
        assert len(dupes) == 0

    def test_multiple_duplicates(self):
        """Multiple duplicate groups detected correctly."""
        entries = [
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC1", amount=Decimal("100.00")),
            SAPLedgerEntry(document_number="DOC2", amount=Decimal("50.00")),
            SAPLedgerEntry(document_number="DOC2", amount=Decimal("50.00")),
        ]
        period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))

        unique, dupes = detect_duplicates(entries, "V001", period)
        assert len(unique) == 2  # DOC1 + DOC2
        assert len(dupes) == 3  # 2 extra DOC1 + 1 extra DOC2


# ---------------------------------------------------------------------------
# Test SAPConfig
# ---------------------------------------------------------------------------


class TestSAPConfig:
    """Test SAP configuration security."""

    def test_credentials_not_in_repr(self):
        """Credentials must be masked in repr."""
        config = SAPConfig(
            host="sap.example.com",
            username="admin",
            password="secret123",
        )
        repr_str = repr(config)
        assert "admin" not in repr_str
        assert "secret123" not in repr_str
        assert "***" in repr_str

    def test_credentials_not_in_str(self):
        """Credentials must be masked in str."""
        config = SAPConfig(
            host="sap.example.com",
            username="admin",
            password="secret123",
        )
        str_repr = str(config)
        assert "admin" not in str_repr
        assert "secret123" not in str_repr

    def test_is_configured_true(self):
        """is_configured True when host, username, password all set."""
        config = SAPConfig(host="h", username="u", password="p")
        assert config.is_configured is True

    def test_is_configured_false_missing_host(self):
        """is_configured False when host is empty."""
        config = SAPConfig(host="", username="u", password="p")
        assert config.is_configured is False

    def test_is_configured_false_missing_password(self):
        """is_configured False when password is empty."""
        config = SAPConfig(host="h", username="u", password="")
        assert config.is_configured is False


# ---------------------------------------------------------------------------
# Test SAPConnectorService
# ---------------------------------------------------------------------------


class TestSAPConnectorServiceNotConfigured:
    """Test that methods fail properly when SAP is not configured."""

    @pytest.mark.asyncio
    async def test_pull_vendor_master_raises_when_not_configured(self):
        """pull_vendor_master should raise when SAP is not configured."""
        svc = SAPConnectorService(config=SAPConfig())
        with pytest.raises(SAPConnectionException, match="not configured"):
            await svc.pull_vendor_master("1000")

    @pytest.mark.asyncio
    async def test_pull_ledger_entries_raises_when_not_configured(self):
        """pull_ledger_entries should raise when SAP is not configured."""
        svc = SAPConnectorService(config=SAPConfig())
        period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
        with pytest.raises(SAPConnectionException, match="not configured"):
            await svc.pull_ledger_entries("V001", "1000", period)

    @pytest.mark.asyncio
    async def test_incremental_pull_raises_when_not_configured(self):
        """incremental_pull should raise when SAP is not configured."""
        svc = SAPConnectorService(config=SAPConfig())
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(SAPConnectionException, match="not configured"):
            await svc.incremental_pull("V001", "1000", since)

    @pytest.mark.asyncio
    async def test_test_connection_returns_failure_when_not_configured(self):
        """test_connection should return failure result when not configured."""
        svc = SAPConnectorService(config=SAPConfig())
        result = await svc.test_connection()
        assert result.success is False
        assert "not configured" in result.message


class TestSAPConnectorServiceRetryLogic:
    """Test retry behavior with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_sap_exception(self):
        """After MAX_RETRIES failures, SAPConnectionException is raised."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Connection refused")

        with pytest.raises(SAPConnectionException, match="failed after 3 retries"):
            await svc._execute_with_retry(failing_operation, "test_op")

        assert call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """Should succeed if the operation succeeds on a retry."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection refused")
            return [{"BELNR": "DOC1"}]

        result = await svc._execute_with_retry(flaky_operation, "test_op")
        assert result == [{"BELNR": "DOC1"}]
        assert call_count == 2


class TestSAPConnectorServicePullLedger:
    """Test pull_ledger_entries with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_pull_ledger_entries_success(self):
        """Successful pull maps SAP fields and removes duplicates."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        mock_response_data = [
            {
                "ZUONR": "ASN001",
                "BELNR": "DOC1",
                "BLART": "RE",
                "DMBTR": "1000.00",
                "BUDAT": "20240115",
                "AUGDT": None,
                "AUGBL": None,
                "LIFNR": "V001",
                "BUKRS": "1000",
            },
            {
                "ZUONR": "ASN002",
                "BELNR": "DOC2",
                "BLART": "KR",
                "DMBTR": "2000.00",
                "BUDAT": "20240220",
                "AUGDT": "20240301",
                "AUGBL": "CLR001",
                "LIFNR": "V001",
                "BUKRS": "1000",
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
            result = await svc.pull_ledger_entries("V001", "1000", period)

        assert isinstance(result, ExtractionResult)
        assert result.row_count == 2
        assert result.duplicates_skipped == 0
        assert len(result.entries) == 2
        assert result.entries[0].document_number == "DOC1"
        assert result.entries[0].amount == Decimal("1000.00")
        assert result.entries[1].document_number == "DOC2"
        assert result.entries[1].posting_date == date(2024, 2, 20)

    @pytest.mark.asyncio
    async def test_pull_ledger_entries_with_duplicates(self):
        """Duplicate entries should be removed and counted."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        mock_response_data = [
            {"BELNR": "DOC1", "DMBTR": "100.00", "BUDAT": "20240101",
             "ZUONR": None, "BLART": None, "AUGDT": None, "AUGBL": None},
            {"BELNR": "DOC1", "DMBTR": "100.00", "BUDAT": "20240101",
             "ZUONR": None, "BLART": None, "AUGDT": None, "AUGBL": None},
            {"BELNR": "DOC2", "DMBTR": "200.00", "BUDAT": "20240115",
             "ZUONR": None, "BLART": None, "AUGDT": None, "AUGBL": None},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
            result = await svc.pull_ledger_entries("V001", "1000", period)

        assert result.row_count == 2
        assert result.duplicates_skipped == 1

    @pytest.mark.asyncio
    async def test_pull_ledger_entries_rollback_on_failure(self):
        """On failure, partial data should be discarded (rollback)."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            period = DateRange(start=date(2024, 1, 1), end=date(2024, 3, 31))
            with pytest.raises(SAPConnectionException):
                await svc.pull_ledger_entries("V001", "1000", period)


class TestSAPConnectorServiceTestConnection:
    """Test connection testing method."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Successful connection test returns success result."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc.test_connection()

        assert result.success is True
        assert "successful" in result.message
        assert result.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_test_connection_http_error(self):
        """HTTP error returns failure with status code."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized",
                request=MagicMock(),
                response=mock_response,
            )
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc.test_connection()

        assert result.success is False
        assert "401" in result.message


class TestSAPConnectorServiceHealthStatus:
    """Test health status reporting."""

    @pytest.mark.asyncio
    async def test_health_status_not_configured(self):
        """Health status shows not connected when not configured."""
        svc = SAPConnectorService(config=SAPConfig())
        status = await svc.get_health_status()

        assert status.is_connected is False
        assert status.last_check is not None

    @pytest.mark.asyncio
    async def test_health_status_tracks_errors(self):
        """Error count increments on failures."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)
        svc._record_error("test error 1")
        svc._record_error("test error 2")

        assert svc._error_count == 2
        assert svc._last_error == "test error 2"


class TestSAPConnectorServiceIncrementalPull:
    """Test incremental pull method."""

    @pytest.mark.asyncio
    async def test_incremental_pull_success(self):
        """Incremental pull maps and deduplicates entries."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        mock_response_data = [
            {"BELNR": "DOC1", "DMBTR": "500.00", "BUDAT": "20240301",
             "ZUONR": "A1", "BLART": "RE", "AUGDT": None, "AUGBL": None},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            since = datetime(2024, 2, 28, tzinfo=timezone.utc)
            result = await svc.incremental_pull("V001", "1000", since)

        assert isinstance(result, ExtractionResult)
        assert result.row_count == 1
        assert result.entries[0].document_number == "DOC1"
        assert result.entries[0].amount == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_incremental_pull_rollback_on_failure(self):
        """On failure, incremental pull discards partial data."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Failed")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            since = datetime(2024, 2, 28, tzinfo=timezone.utc)
            with pytest.raises(SAPConnectionException):
                await svc.incremental_pull("V001", "1000", since)


class TestSAPConnectorServiceVendorMaster:
    """Test pull_vendor_master method."""

    @pytest.mark.asyncio
    async def test_pull_vendor_master_success(self):
        """Successful vendor master pull maps SAP vendor fields."""
        config = SAPConfig(
            host="sap.test.com",
            username="user",
            password="pass",
            base_url="http://sap.test.com",
        )
        svc = SAPConnectorService(config=config)

        mock_response_data = [
            {
                "LIFNR": "V001",
                "NAME1": "Vendor One",
                "BUKRS": "1000",
                "ORT01": "Mumbai",
                "STCD3": "ABCDE1234F",
                "STCD4": "27ABCDE1234F1Z5",
            },
            {
                "LIFNR": "V002",
                "NAME1": "Vendor Two",
                "BUKRS": "1000",
                "ORT01": "Delhi",
                "STCD3": None,
                "STCD4": None,
            },
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await svc.pull_vendor_master("1000")

        assert len(result) == 2
        assert isinstance(result[0], SAPVendorData)
        assert result[0].vendor_code == "V001"
        assert result[0].name == "Vendor One"
        assert result[0].company_code == "1000"
        assert result[0].city == "Mumbai"
        assert result[0].pan == "ABCDE1234F"
        assert result[0].gstin == "27ABCDE1234F1Z5"
        assert result[1].vendor_code == "V002"
        assert result[1].pan is None
