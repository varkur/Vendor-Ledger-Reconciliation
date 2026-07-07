"""
Unit tests for VendorService domain logic.

Tests CRUD operations, soft-delete logic, bulk import validation,
SAP data merge, vendor-code uniqueness enforcement, inactive vendor blocking,
active case check before deletion, and vendor filter/search logic.
"""

import pytest
from dataclasses import dataclass, field
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from src.domain.exceptions.vlr import (
    DuplicateVendorCodeException,
    FileValidationException,
    VendorHasActiveCaseException,
    VendorInactiveException,
    VendorNotFoundException,
)
from src.domain.repositories.vlr.vendor_repository import (
    PaginatedResult,
    PaginationParams,
    VendorFilters,
)
from src.domain.services.vlr.vendor_service import (
    BulkImportResult,
    ExportFormat,
    SAPVendorData,
    VendorContactDTO,
    VendorCreateDTO,
    VendorService,
    VendorUpdateDTO,
)


# ─── Test Helpers ─────────────────────────────────────────────────────────────


@dataclass
class FakeVendor:
    """Fake vendor object for testing."""

    id: UUID = field(default_factory=uuid4)
    vendor_code: str = "V001"
    company_code: str = "CC01"
    name: str = "Test Vendor"
    pan: str | None = None
    gstin: str | None = None
    city: str | None = None
    status: str = "active"
    is_deleted: bool = False
    contacts: list = field(default_factory=list)


@dataclass
class FakeContact:
    """Fake contact object for testing."""

    id: UUID = field(default_factory=uuid4)
    vendor_id: UUID = field(default_factory=uuid4)
    name: str = "John Doe"
    email: str = "john@test.com"
    phone: str | None = None
    designation: str | None = None
    is_primary: bool = False
    source: str = "manual"


@pytest.fixture
def mock_vendor_repo() -> AsyncMock:
    """Create a mock vendor repository."""
    repo = AsyncMock()
    repo.exists_by_vendor_code = AsyncMock(return_value=False)
    repo.has_active_cases = AsyncMock(return_value=False)
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_vendor_code = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.soft_delete = AsyncMock()
    repo.list_vendors = AsyncMock()
    repo.bulk_create = AsyncMock(return_value=[])
    repo.count = AsyncMock(return_value=0)
    repo.add_contacts = AsyncMock(return_value=[])
    repo.remove_contacts_by_source = AsyncMock()
    repo.get_contacts = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def vendor_service(mock_vendor_repo: AsyncMock) -> VendorService:
    """Create VendorService with mocked repository."""
    return VendorService(vendor_repository=mock_vendor_repo)


# ─── Create Vendor Tests ──────────────────────────────────────────────────────


class TestCreateVendor:
    """Tests for vendor creation with uniqueness enforcement."""

    async def test_create_vendor_success(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should create a vendor when vendor_code is unique."""
        mock_vendor_repo.exists_by_vendor_code.return_value = False
        fake_vendor = FakeVendor()
        mock_vendor_repo.create.return_value = fake_vendor

        dto = VendorCreateDTO(
            vendor_code="V001",
            company_code="CC01",
            name="Test Vendor",
            pan="ABCDE1234F",
            city="Mumbai",
        )

        result = await vendor_service.create_vendor(dto)

        assert result == fake_vendor
        mock_vendor_repo.exists_by_vendor_code.assert_called_once_with("V001", "CC01")
        mock_vendor_repo.create.assert_called_once()

    async def test_create_vendor_duplicate_code_raises(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise DuplicateVendorCodeException when code exists."""
        mock_vendor_repo.exists_by_vendor_code.return_value = True

        dto = VendorCreateDTO(
            vendor_code="V001",
            company_code="CC01",
            name="Test Vendor",
        )

        with pytest.raises(DuplicateVendorCodeException):
            await vendor_service.create_vendor(dto)

        mock_vendor_repo.create.assert_not_called()


# ─── Get Vendor Tests ─────────────────────────────────────────────────────────


class TestGetVendor:
    """Tests for vendor retrieval."""

    async def test_get_vendor_success(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should return vendor when found."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor

        result = await vendor_service.get_vendor(fake_vendor.id, "CC01")
        assert result == fake_vendor

    async def test_get_vendor_not_found_raises(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorNotFoundException when not found."""
        mock_vendor_repo.get_by_id.return_value = None

        with pytest.raises(VendorNotFoundException):
            await vendor_service.get_vendor(uuid4(), "CC01")


# ─── Update Vendor Tests ──────────────────────────────────────────────────────


class TestUpdateVendor:
    """Tests for vendor update."""

    async def test_update_vendor_success(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should update vendor fields."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor
        updated_vendor = FakeVendor(name="Updated Name")
        mock_vendor_repo.update.return_value = updated_vendor

        dto = VendorUpdateDTO(name="Updated Name")
        result = await vendor_service.update_vendor(fake_vendor.id, "CC01", dto)

        assert result.name == "Updated Name"
        mock_vendor_repo.update.assert_called_once()

    async def test_update_vendor_not_found_raises(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorNotFoundException for missing vendor."""
        mock_vendor_repo.get_by_id.return_value = None

        dto = VendorUpdateDTO(name="Updated")
        with pytest.raises(VendorNotFoundException):
            await vendor_service.update_vendor(uuid4(), "CC01", dto)

    async def test_update_vendor_no_changes(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should return existing vendor when no fields are changed."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor

        dto = VendorUpdateDTO()  # all None
        result = await vendor_service.update_vendor(fake_vendor.id, "CC01", dto)

        assert result == fake_vendor
        mock_vendor_repo.update.assert_not_called()


# ─── Delete Vendor Tests ──────────────────────────────────────────────────────


class TestDeleteVendor:
    """Tests for soft-delete with active case check."""

    async def test_delete_vendor_success(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should soft-delete vendor when no active cases."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor
        mock_vendor_repo.has_active_cases.return_value = False

        await vendor_service.delete_vendor(fake_vendor.id, "CC01")

        mock_vendor_repo.soft_delete.assert_called_once_with(fake_vendor.id, "CC01")

    async def test_delete_vendor_with_active_cases_raises(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorHasActiveCaseException when active cases exist."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor
        mock_vendor_repo.has_active_cases.return_value = True

        with pytest.raises(VendorHasActiveCaseException):
            await vendor_service.delete_vendor(fake_vendor.id, "CC01")

        mock_vendor_repo.soft_delete.assert_not_called()

    async def test_delete_vendor_not_found_raises(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorNotFoundException for missing vendor."""
        mock_vendor_repo.get_by_id.return_value = None

        with pytest.raises(VendorNotFoundException):
            await vendor_service.delete_vendor(uuid4(), "CC01")


# ─── Inactive Vendor Blocking Tests ──────────────────────────────────────────


class TestInactiveVendorBlocking:
    """Tests for inactive vendor blocking on request creation."""

    async def test_validate_active_vendor_passes(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should pass for an active vendor."""
        fake_vendor = FakeVendor(status="active")
        mock_vendor_repo.get_by_id.return_value = fake_vendor

        # Should not raise
        await vendor_service.validate_vendor_active_for_request(fake_vendor.id, "CC01")

    async def test_validate_inactive_vendor_raises(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorInactiveException for inactive vendor."""
        fake_vendor = FakeVendor(status="inactive")
        mock_vendor_repo.get_by_id.return_value = fake_vendor

        with pytest.raises(VendorInactiveException):
            await vendor_service.validate_vendor_active_for_request(fake_vendor.id, "CC01")

    async def test_validate_multiple_vendors_all_active(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should pass when all vendors are active."""
        v1 = FakeVendor(status="active", vendor_code="V001")
        v2 = FakeVendor(status="active", vendor_code="V002")
        mock_vendor_repo.get_by_id.side_effect = [v1, v2]

        result = await vendor_service.validate_vendors_active_for_request(
            [v1.id, v2.id], "CC01"
        )
        assert result == []

    async def test_validate_multiple_vendors_some_inactive(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorInactiveException listing inactive vendor codes."""
        v1 = FakeVendor(status="active", vendor_code="V001")
        v2 = FakeVendor(status="inactive", vendor_code="V002")
        mock_vendor_repo.get_by_id.side_effect = [v1, v2]

        with pytest.raises(VendorInactiveException) as exc_info:
            await vendor_service.validate_vendors_active_for_request(
                [v1.id, v2.id], "CC01"
            )
        assert "V002" in str(exc_info.value)


# ─── Bulk Import Tests ────────────────────────────────────────────────────────


class TestBulkImport:
    """Tests for bulk vendor import with validation."""

    async def test_bulk_import_success(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should import valid rows successfully."""
        mock_vendor_repo.exists_by_vendor_code.return_value = False
        mock_vendor_repo.bulk_create.return_value = []

        rows = [
            {"vendor_code": "V001", "company_code": "CC01", "name": "Vendor 1"},
            {"vendor_code": "V002", "company_code": "CC01", "name": "Vendor 2"},
        ]

        result = await vendor_service.bulk_import(rows, "CC01")

        assert result.total_rows == 2
        assert result.successful == 2
        assert result.failed == 0
        assert result.errors == []

    async def test_bulk_import_missing_required_columns(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise FileValidationException for missing required columns."""
        rows = [{"vendor_code": "V001", "city": "Mumbai"}]  # missing 'name'

        with pytest.raises(FileValidationException) as exc_info:
            await vendor_service.bulk_import(rows, "CC01")
        assert "name" in str(exc_info.value)

    async def test_bulk_import_empty_rows(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should return zero result for empty input."""
        result = await vendor_service.bulk_import([], "CC01")

        assert result.total_rows == 0
        assert result.successful == 0
        assert result.failed == 0

    async def test_bulk_import_row_validation_errors(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should report per-row errors for invalid data."""
        mock_vendor_repo.exists_by_vendor_code.return_value = False
        mock_vendor_repo.bulk_create.return_value = []

        rows = [
            {"vendor_code": "", "company_code": "CC01", "name": "Vendor 1"},  # empty code
            {"vendor_code": "V002", "company_code": "CC01", "name": "Vendor 2"},
        ]

        result = await vendor_service.bulk_import(rows, "CC01")

        assert result.failed == 1
        assert result.successful == 1
        assert len(result.errors) == 1
        assert result.errors[0].row_number == 1

    async def test_bulk_import_duplicate_in_batch(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should detect duplicate vendor codes within the batch."""
        mock_vendor_repo.exists_by_vendor_code.return_value = False
        mock_vendor_repo.bulk_create.return_value = []

        rows = [
            {"vendor_code": "V001", "company_code": "CC01", "name": "Vendor 1"},
            {"vendor_code": "V001", "company_code": "CC01", "name": "Vendor 1 Dup"},
        ]

        result = await vendor_service.bulk_import(rows, "CC01")

        assert result.successful == 1
        assert result.failed == 1

    async def test_bulk_import_existing_vendor_code(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should reject rows with vendor codes already in database."""
        mock_vendor_repo.exists_by_vendor_code.side_effect = [True, False]
        mock_vendor_repo.bulk_create.return_value = []

        rows = [
            {"vendor_code": "V001", "company_code": "CC01", "name": "Existing"},
            {"vendor_code": "V002", "company_code": "CC01", "name": "New"},
        ]

        result = await vendor_service.bulk_import(rows, "CC01")

        assert result.successful == 1
        assert result.failed == 1
        assert any("already exists" in e.errors[0] for e in result.errors)


# ─── SAP Data Merge Tests ─────────────────────────────────────────────────────


class TestSAPDataMerge:
    """Tests for SAP vendor data merge preserving manual contacts."""

    async def test_merge_creates_new_vendor(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should create vendor when not found in database."""
        mock_vendor_repo.get_by_vendor_code.return_value = None
        mock_vendor_repo.exists_by_vendor_code.return_value = False
        new_vendor = FakeVendor(vendor_code="SAP001")
        mock_vendor_repo.create.return_value = new_vendor

        sap_data = SAPVendorData(
            vendor_code="SAP001",
            company_code="CC01",
            name="SAP Vendor",
            pan="XYZAB1234C",
            city="Delhi",
        )

        result = await vendor_service.merge_sap_data(sap_data)
        assert result == new_vendor

    async def test_merge_updates_existing_vendor(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should update existing vendor fields from SAP data."""
        existing_vendor = FakeVendor(
            vendor_code="SAP001",
            name="Old Name",
            contacts=[
                FakeContact(name="Manual Contact", source="manual"),
            ],
        )
        mock_vendor_repo.get_by_vendor_code.return_value = existing_vendor
        mock_vendor_repo.update.return_value = existing_vendor

        sap_data = SAPVendorData(
            vendor_code="SAP001",
            company_code="CC01",
            name="New Name From SAP",
            pan="NEWPAN1234X",
            city="Bangalore",
        )

        await vendor_service.merge_sap_data(sap_data)

        mock_vendor_repo.update.assert_called_once()
        call_args = mock_vendor_repo.update.call_args
        update_data = call_args[0][2]  # Third positional arg
        assert update_data["name"] == "New Name From SAP"
        assert update_data["pan"] == "NEWPAN1234X"
        assert update_data["city"] == "Bangalore"

    async def test_merge_preserves_manual_contacts(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should preserve manually-added contacts during SAP merge."""
        manual_contact = FakeContact(name="Manual Contact", source="manual")
        sap_contact = FakeContact(name="SAP Contact", source="sap")
        existing_vendor = FakeVendor(
            vendor_code="SAP001",
            contacts=[manual_contact, sap_contact],
        )
        mock_vendor_repo.get_by_vendor_code.return_value = existing_vendor
        mock_vendor_repo.update.return_value = existing_vendor

        sap_data = SAPVendorData(
            vendor_code="SAP001",
            company_code="CC01",
            name="Updated Name",
        )

        result = await vendor_service.merge_sap_data(sap_data)

        # Verify manual contacts are still there
        manual_contacts = vendor_service.get_manual_contacts(result)
        assert len(manual_contacts) == 1
        assert manual_contacts[0].name == "Manual Contact"


# ─── Search/Filter Tests ──────────────────────────────────────────────────────


class TestSearchVendors:
    """Tests for vendor search/filter logic."""

    async def test_search_with_all_filters(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should pass all filter criteria to repository."""
        mock_vendor_repo.list_vendors.return_value = PaginatedResult(
            items=[], total=0, page=1, page_size=50
        )

        await vendor_service.search_vendors(
            company_code="CC01",
            vendor_code="V001",
            name="Test",
            status="active",
            city="Mumbai",
            pan="ABCDE",
        )

        mock_vendor_repo.list_vendors.assert_called_once()
        call_args = mock_vendor_repo.list_vendors.call_args
        assert call_args[1]["company_code"] == "CC01"
        filters = call_args[1]["filters"]
        assert filters.vendor_code == "V001"
        assert filters.name == "Test"
        assert filters.status == "active"
        assert filters.city == "Mumbai"
        assert filters.pan == "ABCDE"

    async def test_search_with_pagination(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should pass pagination params to repository."""
        mock_vendor_repo.list_vendors.return_value = PaginatedResult(
            items=[], total=0, page=2, page_size=25
        )

        pagination = PaginationParams(page=2, page_size=25)
        await vendor_service.search_vendors(
            company_code="CC01",
            pagination=pagination,
        )

        call_args = mock_vendor_repo.list_vendors.call_args
        assert call_args[1]["pagination"] == pagination

    async def test_list_vendors(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should delegate to repository with filters."""
        vendors = [FakeVendor(), FakeVendor(vendor_code="V002")]
        mock_vendor_repo.list_vendors.return_value = PaginatedResult(
            items=vendors, total=2, page=1, page_size=50
        )

        result = await vendor_service.list_vendors("CC01")

        assert result.total == 2
        assert len(result.items) == 2


# ─── Export Tests ─────────────────────────────────────────────────────────────


class TestExportVendors:
    """Tests for vendor export functionality."""

    async def test_export_csv(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should export vendors as CSV bytes."""
        vendors = [FakeVendor(vendor_code="V001", name="Vendor 1", city="Mumbai")]
        mock_vendor_repo.list_vendors.return_value = PaginatedResult(
            items=vendors, total=1, page=1, page_size=500
        )

        result = await vendor_service.export_vendors("CC01", export_format=ExportFormat.CSV)

        assert isinstance(result, bytes)
        content = result.decode("utf-8")
        assert "vendor_code" in content  # header
        assert "V001" in content
        assert "Vendor 1" in content
        assert "Mumbai" in content


# ─── Get Vendor By Code Tests ─────────────────────────────────────────────────


class TestGetVendorByCode:
    """Tests for get_vendor_by_code."""

    async def test_get_vendor_by_code_success(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should return vendor when found by code."""
        fake_vendor = FakeVendor(vendor_code="V001")
        mock_vendor_repo.get_by_vendor_code.return_value = fake_vendor

        result = await vendor_service.get_vendor_by_code("V001", "CC01")
        assert result == fake_vendor

    async def test_get_vendor_by_code_not_found(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should raise VendorNotFoundException when not found."""
        mock_vendor_repo.get_by_vendor_code.return_value = None

        with pytest.raises(VendorNotFoundException):
            await vendor_service.get_vendor_by_code("MISSING", "CC01")


# ─── Contact Handling Tests ───────────────────────────────────────────────────


class TestContactHandling:
    """Tests for vendor contact management during CRUD and SAP merge."""

    async def test_create_vendor_with_contacts(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should add contacts when creating a vendor with contacts."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.create.return_value = fake_vendor

        dto = VendorCreateDTO(
            vendor_code="V001",
            company_code="CC01",
            name="Test Vendor",
            contacts=[
                VendorContactDTO(name="John", email="john@test.com", is_primary=True),
                VendorContactDTO(name="Jane", email="jane@test.com"),
            ],
        )

        await vendor_service.create_vendor(dto)

        mock_vendor_repo.add_contacts.assert_called_once()
        contact_args = mock_vendor_repo.add_contacts.call_args[0]
        assert contact_args[0] == fake_vendor.id
        assert len(contact_args[1]) == 2
        assert contact_args[1][0]["name"] == "John"
        assert contact_args[1][0]["is_primary"] is True
        assert contact_args[1][1]["name"] == "Jane"

    async def test_create_vendor_without_contacts(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should not call add_contacts when no contacts are provided."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.create.return_value = fake_vendor

        dto = VendorCreateDTO(
            vendor_code="V001",
            company_code="CC01",
            name="Test Vendor",
        )

        await vendor_service.create_vendor(dto)

        mock_vendor_repo.add_contacts.assert_not_called()

    async def test_update_vendor_with_contacts_replaces_manual(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should replace manual contacts when contacts list provided in update."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor
        mock_vendor_repo.update.return_value = fake_vendor

        dto = VendorUpdateDTO(
            name="Updated",
            contacts=[
                VendorContactDTO(name="New Contact", email="new@test.com"),
            ],
        )

        await vendor_service.update_vendor(fake_vendor.id, "CC01", dto)

        mock_vendor_repo.remove_contacts_by_source.assert_called_once_with(
            fake_vendor.id, "manual"
        )
        mock_vendor_repo.add_contacts.assert_called_once()
        contact_args = mock_vendor_repo.add_contacts.call_args[0]
        assert contact_args[1][0]["name"] == "New Contact"

    async def test_update_vendor_without_contacts_does_not_touch_them(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should not modify contacts when contacts field is None in update."""
        fake_vendor = FakeVendor()
        mock_vendor_repo.get_by_id.return_value = fake_vendor
        mock_vendor_repo.update.return_value = fake_vendor

        dto = VendorUpdateDTO(name="Updated")

        await vendor_service.update_vendor(fake_vendor.id, "CC01", dto)

        mock_vendor_repo.remove_contacts_by_source.assert_not_called()
        mock_vendor_repo.add_contacts.assert_not_called()

    async def test_sap_merge_replaces_sap_contacts_preserves_manual(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should remove old SAP contacts and add new ones, preserving manual."""
        manual_contact = FakeContact(name="Manual Contact", source="manual")
        sap_contact = FakeContact(name="Old SAP Contact", source="sap")
        existing_vendor = FakeVendor(
            vendor_code="SAP001",
            contacts=[manual_contact, sap_contact],
        )
        mock_vendor_repo.get_by_vendor_code.return_value = existing_vendor
        mock_vendor_repo.update.return_value = existing_vendor

        sap_data = SAPVendorData(
            vendor_code="SAP001",
            company_code="CC01",
            name="Updated Name",
            contacts=[
                VendorContactDTO(
                    name="New SAP Contact",
                    email="newsap@vendor.com",
                    source="sap",
                ),
            ],
        )

        await vendor_service.merge_sap_data(sap_data)

        # Should remove old SAP contacts
        mock_vendor_repo.remove_contacts_by_source.assert_called_once_with(
            existing_vendor.id, "sap"
        )
        # Should add new SAP contacts
        mock_vendor_repo.add_contacts.assert_called_once()
        contact_args = mock_vendor_repo.add_contacts.call_args[0]
        assert contact_args[1][0]["name"] == "New SAP Contact"
        assert contact_args[1][0]["source"] == "sap"

    async def test_sap_merge_no_contacts_does_not_modify(
        self, vendor_service: VendorService, mock_vendor_repo: AsyncMock
    ):
        """Should not modify contacts when SAP data has no contacts."""
        existing_vendor = FakeVendor(vendor_code="SAP001")
        mock_vendor_repo.get_by_vendor_code.return_value = existing_vendor
        mock_vendor_repo.update.return_value = existing_vendor

        sap_data = SAPVendorData(
            vendor_code="SAP001",
            company_code="CC01",
            name="Updated",
            contacts=[],
        )

        await vendor_service.merge_sap_data(sap_data)

        mock_vendor_repo.remove_contacts_by_source.assert_not_called()
        mock_vendor_repo.add_contacts.assert_not_called()
