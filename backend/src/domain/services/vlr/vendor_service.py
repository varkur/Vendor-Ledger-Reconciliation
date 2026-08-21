"""
Vendor Management Domain Service.

Implements CRUD operations, soft-delete logic, bulk import validation,
SAP data merge, vendor-code uniqueness enforcement, inactive vendor blocking,
active case check before deletion, and vendor filter/search logic.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10
"""

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from src.domain.exceptions.vlr import (
    DuplicateVendorCodeException,
    FileValidationException,
    VendorHasActiveCaseException,
    VendorInactiveException,
    VendorNotFoundException,
)
from src.domain.repositories.vlr.vendor_repository import (
    IVendorRepository,
    PaginatedResult,
    PaginationParams,
    VendorFilters,
)


class VendorStatus(str, Enum):
    """Vendor status values."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class ExportFormat(str, Enum):
    """Supported export formats."""

    CSV = "csv"
    EXCEL = "excel"


@dataclass
class VendorContactDTO:
    """Data transfer object for vendor contact creation/update."""

    name: str
    email: str
    phone: str | None = None
    designation: str | None = None
    is_primary: bool = False
    source: str = "manual"


@dataclass
class VendorCreateDTO:
    """Data transfer object for vendor creation."""

    vendor_code: str
    company_code: str
    name: str
    pan: str | None = None
    gstin: str | None = None
    city: str | None = None
    status: str = "active"
    contacts: list[VendorContactDTO] = field(default_factory=list)


@dataclass
class VendorUpdateDTO:
    """Data transfer object for vendor update."""

    name: str | None = None
    pan: str | None = None
    gstin: str | None = None
    city: str | None = None
    status: str | None = None
    contacts: list[VendorContactDTO] | None = None


@dataclass
class SAPVendorData:
    """Data received from SAP for vendor master merge."""

    vendor_code: str
    company_code: str
    name: str
    pan: str | None = None
    gstin: str | None = None
    city: str | None = None
    contacts: list[VendorContactDTO] = field(default_factory=list)


@dataclass
class BulkImportRowError:
    """Error detail for a single row in bulk import."""

    row_number: int
    vendor_code: str | None
    errors: list[str]


@dataclass
class BulkImportResult:
    """Result of a bulk vendor import operation."""

    total_rows: int
    successful: int
    failed: int
    errors: list[BulkImportRowError] = field(default_factory=list)


# Required columns for bulk import CSV
BULK_IMPORT_REQUIRED_COLUMNS = {"vendor_code", "company_code", "name"}
BULK_IMPORT_OPTIONAL_COLUMNS = {"pan", "gstin", "city", "status"}
BULK_IMPORT_ALL_COLUMNS = BULK_IMPORT_REQUIRED_COLUMNS | BULK_IMPORT_OPTIONAL_COLUMNS


class VendorService:
    """
    Domain service for Vendor management.

    Encapsulates business rules for vendor CRUD, bulk import,
    SAP data merge, and enforcement of vendor-related constraints.
    """

    def __init__(self, vendor_repository: IVendorRepository) -> None:
        self._vendor_repo = vendor_repository

    # ──────────────────────────────────────────────────────────────────────
    # CRUD Operations
    # ──────────────────────────────────────────────────────────────────────

    async def create_vendor(self, data: VendorCreateDTO) -> object:
        """
        Create a new vendor with uniqueness enforcement.

        Requirement 2.2: Vendor code must be unique within company code.
        Requirement 2.7: Store multiple contact persons per vendor.
        """
        # Enforce vendor code uniqueness within company
        if await self._vendor_repo.exists_by_vendor_code(
            data.vendor_code, data.company_code
        ):
            raise DuplicateVendorCodeException(vendor_code=data.vendor_code)

        # Build vendor data dict
        vendor_data: dict = {
            "vendor_code": data.vendor_code,
            "company_code": data.company_code,
            "name": data.name,
            "pan": data.pan,
            "gstin": data.gstin,
            "city": data.city,
            "status": data.status,
        }

        vendor = await self._vendor_repo.create(vendor_data)

        # Add contacts if provided
        if data.contacts:
            vendor_id = getattr(vendor, "id")
            contact_dicts = [
                {
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "designation": c.designation,
                    "is_primary": c.is_primary,
                    "source": c.source,
                }
                for c in data.contacts
            ]
            await self._vendor_repo.add_contacts(vendor_id, contact_dicts)

            # Re-fetch instead of returning the freshly-flushed `vendor`
            # object as-is: `VendorModel.contacts` is lazy="selectin", which
            # only eager-loads when the object comes back from a SELECT.
            # The object here was populated via session.add()+flush(), so
            # its `contacts` collection was never loaded. The API layer
            # (VendorResponse.model_validate) accesses `.contacts`
            # synchronously — SQLAlchemy's async lazy-load has no greenlet
            # context to run in at that point and raises MissingGreenlet
            # ("greenlet_spawn has not been called"), which the exception
            # middleware doesn't recognize and surfaces as a raw 500 on
            # every single vendor creation that includes a contact.
            refreshed = await self._vendor_repo.get_by_id(vendor_id, data.company_code)
            if refreshed is not None:
                vendor = refreshed

        return vendor

    async def get_vendor(self, vendor_id: UUID, company_code: str) -> object:
        """
        Retrieve a vendor by ID within a company.

        Raises VendorNotFoundException if not found.
        """
        vendor = await self._vendor_repo.get_by_id(vendor_id, company_code)
        if vendor is None:
            raise VendorNotFoundException(
                f"Vendor with id '{vendor_id}' not found in company '{company_code}'."
            )
        return vendor

    async def update_vendor(
        self, vendor_id: UUID, company_code: str, data: VendorUpdateDTO
    ) -> object:
        """
        Update a vendor record.

        Requirement 2.3: Record previous and new values in audit log.
        (Audit log recording is handled by the infrastructure layer via
         SQLAlchemy event listeners.)
        Requirement 2.7: Support updating contacts.
        """
        # Ensure vendor exists
        await self.get_vendor(vendor_id, company_code)

        # Build update dict, only including non-None fields
        update_data: dict = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.pan is not None:
            update_data["pan"] = data.pan
        if data.gstin is not None:
            update_data["gstin"] = data.gstin
        if data.city is not None:
            update_data["city"] = data.city
        if data.status is not None:
            update_data["status"] = data.status

        if update_data:
            vendor = await self._vendor_repo.update(vendor_id, company_code, update_data)
        else:
            vendor = await self.get_vendor(vendor_id, company_code)

        # Handle contact updates if provided
        contacts_changed = False
        if data.contacts is not None:
            # Replace ALL contacts with the new set (user explicitly provided the full list)
            await self._vendor_repo.remove_all_contacts(vendor_id)
            contact_dicts = [
                {
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "designation": c.designation,
                    "is_primary": c.is_primary,
                    "source": "manual",
                }
                for c in data.contacts
            ]
            if contact_dicts:
                await self._vendor_repo.add_contacts(vendor_id, contact_dicts)
            contacts_changed = True

        # Re-fetch when contacts were touched — same MissingGreenlet issue as
        # create_vendor: VendorModel.contacts is lazy="selectin", which only
        # eager-loads on a fresh SELECT. `vendor` here may be the object
        # returned by repo.update() (mutated in place, contacts never
        # (re)loaded) or a stale get_vendor() snapshot from before the
        # contacts were replaced — either way it doesn't reflect the new
        # contacts, and touching `.contacts` outside an async context would
        # crash the same way on serialization.
        if contacts_changed:
            refreshed = await self._vendor_repo.get_by_id(vendor_id, company_code)
            if refreshed is not None:
                vendor = refreshed

        return vendor

    async def delete_vendor(self, vendor_id: UUID, company_code: str) -> None:
        """
        Soft-delete a vendor.

        Requirement 2.8: Prevent deletion if vendor has active reconciliation cases.
        """
        # Ensure vendor exists
        await self.get_vendor(vendor_id, company_code)

        # Check for active cases
        if await self._vendor_repo.has_active_cases(vendor_id):
            raise VendorHasActiveCaseException()

        await self._vendor_repo.soft_delete(vendor_id, company_code)

    async def list_vendors(
        self,
        company_code: str,
        filters: VendorFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """
        List vendors with filtering and pagination.

        Requirement 2.9: Support filtering by code, name, status, city, PAN.
        """
        return await self._vendor_repo.list_vendors(
            company_code=company_code,
            filters=filters,
            pagination=pagination,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Inactive Vendor Blocking
    # ──────────────────────────────────────────────────────────────────────

    async def validate_vendor_active_for_request(
        self, vendor_id: UUID, company_code: str
    ) -> None:
        """
        Validate that a vendor is active for request creation.

        Requirement 2.6: Inactive vendors cannot be used for new reconciliation requests.
        """
        vendor = await self.get_vendor(vendor_id, company_code)
        if getattr(vendor, "status", None) == VendorStatus.INACTIVE:
            raise VendorInactiveException(
                f"Vendor '{getattr(vendor, 'vendor_code', vendor_id)}' is inactive "
                "and cannot be included in a reconciliation request."
            )

    async def validate_vendors_active_for_request(
        self, vendor_ids: list[UUID], company_code: str
    ) -> list[str]:
        """
        Validate multiple vendors are active for request creation.

        Returns list of inactive vendor codes. Raises VendorInactiveException
        if any vendors are inactive.

        Requirement 2.6, 3.9: Reject requests with inactive vendors.
        """
        inactive_vendors: list[str] = []
        for vendor_id in vendor_ids:
            vendor = await self.get_vendor(vendor_id, company_code)
            if getattr(vendor, "status", None) == VendorStatus.INACTIVE:
                inactive_vendors.append(
                    getattr(vendor, "vendor_code", str(vendor_id))
                )

        if inactive_vendors:
            raise VendorInactiveException(
                f"The following vendors are inactive and cannot be included: "
                f"{', '.join(inactive_vendors)}"
            )

        return inactive_vendors

    # ──────────────────────────────────────────────────────────────────────
    # Bulk Import
    # ──────────────────────────────────────────────────────────────────────

    async def bulk_import(
        self, rows: list[dict], company_code: str
    ) -> BulkImportResult:
        """
        Validate and import vendor records from parsed CSV/Excel rows.

        Requirement 2.4: Support bulk import with validation and error
        reporting per row.

        Each row is expected to be a dict with column names as keys.
        """
        if not rows:
            return BulkImportResult(total_rows=0, successful=0, failed=0)

        # Validate column structure from first row
        first_row_keys = set(rows[0].keys())
        missing_columns = BULK_IMPORT_REQUIRED_COLUMNS - first_row_keys
        if missing_columns:
            raise FileValidationException(
                errors=[f"Missing required columns: {', '.join(sorted(missing_columns))}"]
            )

        errors: list[BulkImportRowError] = []
        valid_rows: list[dict] = []

        for idx, row in enumerate(rows, start=1):
            row_errors = self._validate_import_row(row)
            if row_errors:
                errors.append(
                    BulkImportRowError(
                        row_number=idx,
                        vendor_code=row.get("vendor_code"),
                        errors=row_errors,
                    )
                )
            else:
                valid_rows.append(
                    {
                        "vendor_code": str(row["vendor_code"]).strip(),
                        "company_code": company_code,
                        "name": str(row["name"]).strip(),
                        "pan": str(row.get("pan", "")).strip() or None,
                        "gstin": str(row.get("gstin", "")).strip() or None,
                        "city": str(row.get("city", "")).strip() or None,
                        "status": str(row.get("status", "active")).strip().lower(),
                        "_contacts": row.get("_contacts", []),
                    }
                )

        # Check for duplicates within the import batch
        seen_codes: set[str] = set()
        deduplicated_rows: list[dict] = []
        for row_data in valid_rows:
            code = row_data["vendor_code"]
            if code in seen_codes:
                # Find index for error reporting
                for idx, original_row in enumerate(rows, start=1):
                    if (
                        str(original_row.get("vendor_code", "")).strip() == code
                        and not any(
                            e.row_number == idx and e.vendor_code == code
                            for e in errors
                        )
                    ):
                        errors.append(
                            BulkImportRowError(
                                row_number=idx,
                                vendor_code=code,
                                errors=[f"Duplicate vendor_code '{code}' in import batch"],
                            )
                        )
                        break
            else:
                seen_codes.add(code)
                deduplicated_rows.append(row_data)

        # Separate rows into new vendors and existing vendors (for upsert)
        new_rows: list[dict] = []
        update_rows: list[dict] = []
        for row_data in deduplicated_rows:
            existing_vendor = await self._vendor_repo.get_by_vendor_code(
                row_data["vendor_code"], company_code
            )
            if existing_vendor:
                row_data["_existing_vendor"] = existing_vendor
                update_rows.append(row_data)
            else:
                new_rows.append(row_data)

        # Update existing vendors (upsert)
        for row_data in update_rows:
            existing_vendor = row_data.pop("_existing_vendor")
            contacts_list = row_data.pop("_contacts", [])
            vendor_id = getattr(existing_vendor, "id")

            # Update vendor fields
            update_data: dict = {}
            if row_data.get("name"):
                update_data["name"] = row_data["name"]
            if row_data.get("status"):
                update_data["status"] = row_data["status"]
            if row_data.get("pan"):
                update_data["pan"] = row_data["pan"]
            if row_data.get("gstin"):
                update_data["gstin"] = row_data["gstin"]
            if row_data.get("city"):
                update_data["city"] = row_data["city"]

            if update_data:
                await self._vendor_repo.update(vendor_id, company_code, update_data)

            # Upsert contacts: match on email within the vendor
            if contacts_list:
                existing_contacts = await self._vendor_repo.get_contacts(vendor_id)
                existing_email_map = {
                    c.email.lower().strip(): c for c in existing_contacts
                }

                for contact_data in contacts_list:
                    email = (contact_data.get("email") or "").lower().strip()
                    if not email:
                        continue

                    if email in existing_email_map:
                        # Update existing contact
                        existing_contact = existing_email_map[email]
                        await self._vendor_repo.update_contact(
                            getattr(existing_contact, "id"),
                            {
                                "name": contact_data.get("name") or getattr(existing_contact, "name"),
                                "phone": contact_data.get("phone") or getattr(existing_contact, "phone", None),
                                "is_primary": contact_data.get("is_primary", getattr(existing_contact, "is_primary", False)),
                            },
                        )
                    else:
                        # Add new contact
                        await self._vendor_repo.add_contacts(
                            vendor_id,
                            [
                                {
                                    "name": contact_data.get("name", "") or "Contact",
                                    "email": contact_data.get("email", ""),
                                    "phone": contact_data.get("phone") or None,
                                    "is_primary": contact_data.get("is_primary", False),
                                    "source": "import",
                                }
                            ],
                        )

        # Bulk create new vendors
        if new_rows:
            # Separate contacts from vendor data before bulk_create
            contacts_by_code: dict[str, list[dict]] = {}
            vendor_data_rows = []
            for row_data in new_rows:
                contacts_list = row_data.pop("_contacts", [])
                if contacts_list:
                    contacts_by_code[row_data["vendor_code"]] = contacts_list
                vendor_data_rows.append(row_data)

            created_vendors = await self._vendor_repo.bulk_create(vendor_data_rows)

            # Add contacts for created vendors
            for vendor in created_vendors:
                v_code = getattr(vendor, "vendor_code", "")
                v_id = getattr(vendor, "id", None)
                if v_code in contacts_by_code and v_id:
                    contact_dicts = [
                        {
                            "name": c.get("name", "") or "Contact",
                            "email": c.get("email", ""),
                            "phone": c.get("phone") or None,
                            "is_primary": c.get("is_primary", False),
                            "source": "import",
                        }
                        for c in contacts_by_code[v_code]
                        if c.get("email")  # Email is required (NOT NULL in DB)
                    ]
                    if contact_dicts:
                        await self._vendor_repo.add_contacts(v_id, contact_dicts)

        total_successful = len(new_rows) + len(update_rows)
        return BulkImportResult(
            total_rows=len(rows),
            successful=total_successful,
            failed=len(rows) - total_successful,
            errors=errors,
        )

    def _validate_import_row(self, row: dict) -> list[str]:
        """Validate a single import row and return list of error messages."""
        errors: list[str] = []

        # Required field checks
        vendor_code = row.get("vendor_code")
        if not vendor_code or not str(vendor_code).strip():
            errors.append("vendor_code is required")

        name = row.get("name")
        if not name or not str(name).strip():
            errors.append("name is required")

        # Status validation
        status = row.get("status", "active")
        if status and str(status).strip().lower() not in ("active", "inactive"):
            errors.append(f"Invalid status '{status}'. Must be 'active' or 'inactive'.")

        return errors

    # ──────────────────────────────────────────────────────────────────────
    # Export
    # ──────────────────────────────────────────────────────────────────────

    async def export_vendors(
        self,
        company_code: str,
        filters: VendorFilters | None = None,
        export_format: ExportFormat = ExportFormat.CSV,
    ) -> bytes:
        """
        Export vendor data to CSV or Excel format.

        Requirement 2.5: Support export of vendor master data.
        """
        # Fetch all matching vendors (no pagination for export)
        all_vendors: list[object] = []
        page = 1
        page_size = 500
        while True:
            result = await self._vendor_repo.list_vendors(
                company_code=company_code,
                filters=filters,
                pagination=PaginationParams(page=page, page_size=page_size),
            )
            all_vendors.extend(result.items)
            if page >= result.total_pages:
                break
            page += 1

        if export_format == ExportFormat.CSV:
            return self._export_to_csv(all_vendors)
        else:
            return self._export_to_excel(all_vendors)

    def _export_to_csv(self, vendors: list[object]) -> bytes:
        """Convert vendors to CSV bytes in template format (includes up to 10 contacts)."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Template headers matching the import template with all 10 contacts
        headers = [
            "Party Type *", "Party Code *", "Party Name *", "ERP Code", "ERP Name",
            "Status *", "Contact 1 Name *", "Contact 1 Email *", "Contact Mobile",
            "Contact 1 Workphone", "Category", "Frequence", "GST rate", "TDS rate",
            "PAN", "GSTIN", "MSME Class", "MSME Type", "Udhyam Registration Number",
            "Owner", "Reviewer 1", "Reviewer 2", "Business Users",
        ]
        # Add contact 2-10 columns
        for i in range(2, 11):
            headers.extend([f"Contact {i} Name", f"Contact {i} Email", f"Contact {i} Mobile", f"Contact {i} Workphone"])
        # Add TDS tolerance columns
        headers.extend(["TDS min tolerance", "TDS max tolerance"])
        writer.writerow(headers)

        for vendor in vendors:
            contacts = getattr(vendor, "contacts", []) or []

            row = [
                "Vendor",  # Party Type
                getattr(vendor, "vendor_code", "") or "",  # Party Code
                getattr(vendor, "name", "") or "",  # Party Name
                "",  # ERP Code
                "",  # ERP Name
                (getattr(vendor, "status", "") or "active").capitalize(),  # Status
                (getattr(contacts[0], "name", "") or "") if len(contacts) > 0 else "",  # Contact 1 Name
                (getattr(contacts[0], "email", "") or "") if len(contacts) > 0 else "",  # Contact 1 Email
                (getattr(contacts[0], "phone", "") or "") if len(contacts) > 0 else "",  # Contact Mobile
                "",  # Contact 1 Workphone
                "",  # Category
                "",  # Frequence
                "",  # GST rate
                "",  # TDS rate
                getattr(vendor, "pan", "") or "",  # PAN
                getattr(vendor, "gstin", "") or "",  # GSTIN
                "",  # MSME Class
                "",  # MSME Type
                "",  # Udhyam Registration Number
                "",  # Owner
                "",  # Reviewer 1
                "",  # Reviewer 2
                "",  # Business Users
            ]
            # Add contact 2-10 data
            for i in range(2, 11):
                c = contacts[i - 1] if len(contacts) > (i - 1) else None
                row.extend([
                    (getattr(c, "name", "") or "") if c else "",
                    (getattr(c, "email", "") or "") if c else "",
                    (getattr(c, "phone", "") or "") if c else "",
                    "",  # Workphone
                ])
            # TDS tolerance
            row.extend(["", ""])
            writer.writerow(row)

        return output.getvalue().encode("utf-8")

    def _export_to_excel(self, vendors: list[object]) -> bytes:
        """Convert vendors to Excel bytes in template format (includes up to 10 contacts)."""
        import io

        try:
            import openpyxl

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Master"

            # Template headers matching the import template with all 10 contacts
            headers = [
                "Party Type *", "Party Code *", "Party Name *", "ERP Code", "ERP Name",
                "Status *", "Contact 1 Name *", "Contact 1 Email *", "Contact Mobile",
                "Contact 1 Workphone", "Category", "Frequence", "GST rate", "TDS rate",
                "PAN", "GSTIN", "MSME Class", "MSME Type", "Udhyam Registration Number",
                "Owner", "Reviewer 1", "Reviewer 2", "Business Users",
            ]
            for i in range(2, 11):
                headers.extend([f"Contact {i} Name", f"Contact {i} Email", f"Contact {i} Mobile", f"Contact {i} Workphone"])
            headers.extend(["TDS min tolerance", "TDS max tolerance"])
            ws.append(headers)

            for vendor in vendors:
                contacts = getattr(vendor, "contacts", []) or []

                row = [
                    "Vendor",
                    getattr(vendor, "vendor_code", "") or "",
                    getattr(vendor, "name", "") or "",
                    "",  # ERP Code
                    "",  # ERP Name
                    (getattr(vendor, "status", "") or "active").capitalize(),
                    (getattr(contacts[0], "name", "") or "") if len(contacts) > 0 else "",
                    (getattr(contacts[0], "email", "") or "") if len(contacts) > 0 else "",
                    (getattr(contacts[0], "phone", "") or "") if len(contacts) > 0 else "",
                    "",  # Contact 1 Workphone
                    "",  # Category
                    "",  # Frequence
                    "",  # GST rate
                    "",  # TDS rate
                    getattr(vendor, "pan", "") or "",
                    getattr(vendor, "gstin", "") or "",
                    "",  # MSME Class
                    "",  # MSME Type
                    "",  # Udhyam Registration Number
                    "",  # Owner
                    "",  # Reviewer 1
                    "",  # Reviewer 2
                    "",  # Business Users
                ]
                # Add contact 2-10 data
                for i in range(2, 11):
                    c = contacts[i - 1] if len(contacts) > (i - 1) else None
                    row.extend([
                        (getattr(c, "name", "") or "") if c else "",
                        (getattr(c, "email", "") or "") if c else "",
                        (getattr(c, "phone", "") or "") if c else "",
                        "",  # Workphone
                    ])
                # TDS tolerance
                row.extend(["", ""])
                ws.append(row)

            buffer = io.BytesIO()
            wb.save(buffer)
            return buffer.getvalue()
        except ImportError:
            return self._export_to_csv(vendors)

    # ──────────────────────────────────────────────────────────────────────
    # SAP Data Merge
    # ──────────────────────────────────────────────────────────────────────

    async def merge_sap_data(
        self, sap_data: SAPVendorData
    ) -> object:
        """
        Merge SAP vendor master data into existing records.

        Requirement 2.10: Merge updates without overwriting manual contact additions.
        - Updates vendor fields (name, pan, gstin, city) from SAP
        - Preserves manually-added contacts (source='manual')
        - Replaces SAP-sourced contacts (source='sap') with new SAP data
        """
        existing_vendor = await self._vendor_repo.get_by_vendor_code(
            sap_data.vendor_code, sap_data.company_code
        )

        if existing_vendor is None:
            # Create new vendor from SAP data with SAP-sourced contacts
            sap_contacts = [
                VendorContactDTO(
                    name=c.name,
                    email=c.email,
                    phone=c.phone,
                    designation=c.designation,
                    is_primary=c.is_primary,
                    source="sap",
                )
                for c in sap_data.contacts
            ]
            create_dto = VendorCreateDTO(
                vendor_code=sap_data.vendor_code,
                company_code=sap_data.company_code,
                name=sap_data.name,
                pan=sap_data.pan,
                gstin=sap_data.gstin,
                city=sap_data.city,
                status="active",
                contacts=sap_contacts,
            )
            return await self.create_vendor(create_dto)

        # Update existing vendor fields from SAP (overwrite core fields)
        update_data: dict = {
            "name": sap_data.name,
        }
        if sap_data.pan is not None:
            update_data["pan"] = sap_data.pan
        if sap_data.gstin is not None:
            update_data["gstin"] = sap_data.gstin
        if sap_data.city is not None:
            update_data["city"] = sap_data.city

        vendor_id = getattr(existing_vendor, "id")
        company_code = sap_data.company_code

        vendor = await self._vendor_repo.update(vendor_id, company_code, update_data)

        # Handle contacts: preserve manual, replace SAP contacts
        # Remove old SAP-sourced contacts and add new ones from SAP data
        if sap_data.contacts:
            await self._vendor_repo.remove_contacts_by_source(vendor_id, "sap")
            sap_contact_dicts = [
                {
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "designation": c.designation,
                    "is_primary": c.is_primary,
                    "source": "sap",
                }
                for c in sap_data.contacts
            ]
            await self._vendor_repo.add_contacts(vendor_id, sap_contact_dicts)

        return vendor

    def get_manual_contacts(self, vendor: object) -> list[object]:
        """
        Get all manually-added contacts for a vendor.

        Used to verify SAP merge preserves manual contacts.
        Requirement 2.10.
        """
        contacts = getattr(vendor, "contacts", []) or []
        return [c for c in contacts if getattr(c, "source", "") == "manual"]

    def get_sap_contacts(self, vendor: object) -> list[object]:
        """Get all SAP-sourced contacts for a vendor."""
        contacts = getattr(vendor, "contacts", []) or []
        return [c for c in contacts if getattr(c, "source", "") == "sap"]

    # ──────────────────────────────────────────────────────────────────────
    # Query / Search
    # ──────────────────────────────────────────────────────────────────────

    async def search_vendors(
        self,
        company_code: str,
        vendor_code: str | None = None,
        name: str | None = None,
        status: str | None = None,
        city: str | None = None,
        pan: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """
        Search vendors by multiple criteria.

        Requirement 2.9: Support filtering and searching by code, name,
        status, city, and PAN.

        All text filters use case-insensitive partial matching except
        status which uses exact match.
        """
        filters = VendorFilters(
            vendor_code=vendor_code,
            name=name,
            status=status,
            city=city,
            pan=pan,
        )
        return await self._vendor_repo.list_vendors(
            company_code=company_code,
            filters=filters,
            pagination=pagination,
        )

    async def get_vendor_by_code(
        self, vendor_code: str, company_code: str
    ) -> object:
        """
        Retrieve a vendor by vendor_code within a company.

        Raises VendorNotFoundException if not found.
        """
        vendor = await self._vendor_repo.get_by_vendor_code(vendor_code, company_code)
        if vendor is None:
            raise VendorNotFoundException(
                f"Vendor with code '{vendor_code}' not found in company '{company_code}'."
            )
        return vendor
