"""
Vendor Management API endpoints.
Thin controller — delegates all business logic to VendorService.

Routes:
- GET    /api/v1/vlr/vendors          — List vendors with filters & pagination
- POST   /api/v1/vlr/vendors          — Create a new vendor
- GET    /api/v1/vlr/vendors/{id}     — Get vendor by ID
- PUT    /api/v1/vlr/vendors/{id}     — Update vendor
- DELETE /api/v1/vlr/vendors/{id}     — Soft-delete vendor
- POST   /api/v1/vlr/vendors/bulk-import — Bulk import from CSV
- GET    /api/v1/vlr/vendors/export   — Export vendor data to CSV/Excel

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.9, 11.2, 11.6
"""

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.vendor_schemas import (
    BulkImportResultResponse,
    BulkImportRowErrorResponse,
    CreateVendorRequest,
    UpdateVendorRequest,
    VendorContactResponse,
    VendorListResponse,
    VendorResponse,
)
from src.domain.entities.user import User
from src.domain.repositories.vlr.vendor_repository import PaginationParams, VendorFilters
from src.domain.services.vlr.vendor_service import (
    ExportFormat,
    VendorContactDTO,
    VendorCreateDTO,
    VendorService,
    VendorUpdateDTO,
)
from src.infrastructure.database.repositories.vlr.vendor_repository_impl import (
    VendorRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/vlr/vendors", tags=["VLR - Vendor Management"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_vendor_service(
    session: AsyncSession = Depends(get_db_session),
) -> VendorService:
    """FastAPI dependency — creates VendorService with injected repository."""
    vendor_repo = VendorRepositoryImpl(session)
    return VendorService(vendor_repository=vendor_repo)


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=VendorListResponse,
    summary="List vendors with filters and pagination",
    dependencies=[Depends(require_permission("vlr.vendors.read"))],
)
async def list_vendors(
    company_code: str = Query(..., min_length=1, description="Company code filter"),
    vendor_code: str | None = Query(default=None, description="Filter by vendor code (partial)"),
    name: str | None = Query(default=None, description="Filter by vendor name (partial)"),
    vendor_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    city: str | None = Query(default=None, description="Filter by city (partial)"),
    pan: str | None = Query(default=None, description="Filter by PAN (partial)"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorListResponse:
    """GET /api/v1/vlr/vendors — List vendors with filtering and pagination."""
    filters = VendorFilters(
        vendor_code=vendor_code,
        name=name,
        status=vendor_status,
        city=city,
        pan=pan,
    )
    pagination = PaginationParams(page=page, page_size=page_size)

    result = await service.list_vendors(
        company_code=company_code,
        filters=filters,
        pagination=pagination,
    )

    return VendorListResponse(
        items=result.items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.post(
    "",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new vendor",
    dependencies=[Depends(require_permission("vlr.vendors.write"))],
)
async def create_vendor(
    request: CreateVendorRequest,
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """POST /api/v1/vlr/vendors — Create a new vendor record."""
    contacts = [
        VendorContactDTO(
            name=c.name,
            email=c.email,
            phone=c.phone,
            designation=c.designation,
            is_primary=c.is_primary,
            source="manual",
        )
        for c in request.contacts
    ]

    dto = VendorCreateDTO(
        vendor_code=request.vendor_code,
        company_code=request.company_code,
        name=request.name,
        pan=request.pan,
        gstin=request.gstin,
        city=request.city,
        status=request.status,
        contacts=contacts,
    )

    vendor = await service.create_vendor(dto)
    return VendorResponse.model_validate(vendor)


@router.get(
    "/template",
    summary="Download vendor import Excel template",
    dependencies=[Depends(require_permission("vlr.vendors.read"))],
)
async def download_template():
    """GET /api/v1/vlr/vendors/template — Download blank Excel import template."""
    import io

    import openpyxl
    from fastapi.responses import Response

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master"

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

    buffer = io.BytesIO()
    wb.save(buffer)

    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Party_Import_Template.xlsx"},
    )


@router.get(
    "/export",
    summary="Export vendors to CSV or Excel",
    dependencies=[Depends(require_permission("vlr.vendors.read"))],
)
async def export_vendors(
    company_code: str = Query(..., min_length=1, description="Company code filter"),
    format: str = Query(default="csv", pattern=r"^(csv|excel)$", description="Export format: csv or excel"),
    vendor_code: str | None = Query(default=None, description="Filter by vendor code"),
    name: str | None = Query(default=None, description="Filter by vendor name"),
    vendor_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    city: str | None = Query(default=None, description="Filter by city"),
    pan: str | None = Query(default=None, description="Filter by PAN"),
    service: VendorService = Depends(_get_vendor_service),
):
    """GET /api/v1/vlr/vendors/export — Export vendor data to CSV or Excel."""
    from fastapi.responses import Response

    filters = VendorFilters(
        vendor_code=vendor_code,
        name=name,
        status=vendor_status,
        city=city,
        pan=pan,
    )

    export_format = ExportFormat.EXCEL if format == "excel" else ExportFormat.CSV
    data = await service.export_vendors(
        company_code=company_code,
        filters=filters,
        export_format=export_format,
    )

    if export_format == ExportFormat.EXCEL:
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=vendors.xlsx"},
        )
    else:
        return Response(
            content=data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=vendors.csv"},
        )


@router.get(
    "/{vendor_id}/contacts",
    response_model=list[VendorContactResponse],
    summary="Get contacts for a vendor",
    dependencies=[Depends(require_permission("vlr.vendors.read"))],
)
async def get_vendor_contacts(
    vendor_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    service: VendorService = Depends(_get_vendor_service),
) -> list[VendorContactResponse]:
    """
    GET /api/v1/vlr/vendors/{vendor_id}/contacts

    Returns a list of contacts associated with the given vendor.
    Used to populate the Contact Person dropdown on the Request Statement page.

    Requirements: 10
    """
    # Verify vendor exists (this will raise 404 if not found)
    vendor = await service.get_vendor(vendor_id, company_code)
    contacts = getattr(vendor, "contacts", [])
    return [VendorContactResponse.model_validate(c) for c in contacts]


@router.get(
    "/{vendor_id}",
    response_model=VendorResponse,
    summary="Get vendor by ID",
    dependencies=[Depends(require_permission("vlr.vendors.read"))],
)
async def get_vendor(
    vendor_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """GET /api/v1/vlr/vendors/{id} — Retrieve a vendor by ID."""
    vendor = await service.get_vendor(vendor_id, company_code)
    return VendorResponse.model_validate(vendor)


@router.put(
    "/{vendor_id}",
    response_model=VendorResponse,
    summary="Update an existing vendor",
    dependencies=[Depends(require_permission("vlr.vendors.write"))],
)
async def update_vendor(
    vendor_id: UUID,
    request: UpdateVendorRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> VendorResponse:
    """PUT /api/v1/vlr/vendors/{id} — Update vendor fields and/or contacts."""
    contacts = None
    if request.contacts is not None:
        contacts = [
            VendorContactDTO(
                name=c.name,
                email=c.email,
                phone=c.phone,
                designation=c.designation,
                is_primary=c.is_primary,
                source="manual",
            )
            for c in request.contacts
        ]

    dto = VendorUpdateDTO(
        name=request.name,
        pan=request.pan,
        gstin=request.gstin,
        city=request.city,
        status=request.status,
        contacts=contacts,
    )

    vendor = await service.update_vendor(vendor_id, company_code, dto)
    return VendorResponse.model_validate(vendor)


@router.delete(
    "/{vendor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a vendor",
    dependencies=[Depends(require_permission("vlr.vendors.delete"))],
)
async def delete_vendor(
    vendor_id: UUID,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> None:
    """DELETE /api/v1/vlr/vendors/{id} — Soft-delete a vendor record."""
    await service.delete_vendor(vendor_id, company_code)


@router.post(
    "/bulk-import",
    response_model=BulkImportResultResponse,
    summary="Bulk import vendors from CSV or Excel",
    dependencies=[Depends(require_permission("vlr.vendors.write"))],
)
async def bulk_import_vendors(
    company_code: str = Query(..., min_length=1, description="Company code for imported vendors"),
    file: UploadFile = File(..., description="CSV or Excel file with vendor data"),
    current_user: User = Depends(get_current_active_user),
    service: VendorService = Depends(_get_vendor_service),
) -> BulkImportResultResponse:
    """POST /api/v1/vlr/vendors/bulk-import — Import vendors from CSV or Excel file."""
    from src.domain.exceptions.vlr import FileValidationException

    filename = file.filename or ""
    is_excel = filename.lower().endswith((".xlsx", ".xls"))
    is_csv = filename.lower().endswith(".csv")

    if not is_excel and not is_csv:
        # Check content type as fallback
        excel_types = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        )
        csv_types = ("text/csv", "application/octet-stream")
        if file.content_type in excel_types:
            is_excel = True
        elif file.content_type in csv_types:
            is_csv = True
        else:
            raise FileValidationException(
                errors=["Unsupported file type. Please upload a CSV (.csv) or Excel (.xlsx) file."]
            )

    # Read file content
    content = await file.read()

    if is_excel:
        # Parse Excel file using openpyxl
        try:
            import openpyxl

            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            if sheet is None:
                raise FileValidationException(errors=["Excel file has no active worksheet."])

            all_rows = list(sheet.iter_rows(values_only=True))
            if not all_rows:
                raise FileValidationException(errors=["Excel file is empty."])

            # First row is header
            headers = [str(h).strip() if h else "" for h in all_rows[0]]
            rows = []
            for row_data in all_rows[1:]:
                # Skip empty rows
                if all(cell is None or str(cell).strip() == "" for cell in row_data):
                    continue
                row_dict = {}
                for col_idx, header in enumerate(headers):
                    if header and col_idx < len(row_data):
                        value = row_data[col_idx]
                        row_dict[header] = str(value).strip() if value is not None else ""
                rows.append(row_dict)

            workbook.close()
        except FileValidationException:
            raise
        except Exception as e:
            raise FileValidationException(errors=[f"Failed to parse Excel file: {str(e)}"])
    else:
        # Parse CSV file
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except UnicodeDecodeError:
                raise FileValidationException(errors=["File encoding not supported. Use UTF-8."])

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

    if not rows:
        raise FileValidationException(errors=["File is empty or has no data rows."])

    # Map template column names to backend field names
    mapped_rows = []
    for row in rows:
        mapped = {}
        # Map from template headers to internal field names
        mapped["vendor_code"] = (
            row.get("Party Code *", "") or row.get("Party Code", "") or
            row.get("party_code", "") or row.get("vendor_code", "")
        ).strip()
        mapped["name"] = (
            row.get("Party Name *", "") or row.get("Party Name", "") or
            row.get("party_name", "") or row.get("name", "")
        ).strip()
        mapped["company_code"] = company_code
        mapped["status"] = (
            row.get("Status *", "") or row.get("Status", "") or
            row.get("status", "") or "active"
        ).strip().lower() or "active"
        mapped["pan"] = (
            row.get("PAN", "") or row.get("pan", "")
        ).strip()
        mapped["gstin"] = (
            row.get("GSTIN", "") or row.get("gstin", "")
        ).strip()
        mapped["city"] = (
            row.get("City", "") or row.get("city", "")
        ).strip()

        # Extract contacts from template columns (up to 10 contacts)
        contacts = []
        # Contact 1
        c1_name = (row.get("Contact 1 Name *", "") or row.get("Contact 1 Name", "") or row.get("contact_1_name", "")).strip()
        c1_email = (row.get("Contact 1 Email *", "") or row.get("Contact 1 Email", "") or row.get("contact_1_email", "")).strip()
        c1_mobile = (row.get("Contact Mobile", "") or row.get("Contact 1 Mobile", "") or row.get("contact_mobile", "")).strip()
        if c1_name or c1_email:
            contacts.append({"name": c1_name or "Contact", "email": c1_email, "phone": c1_mobile, "is_primary": True})

        # Contacts 2-10
        for i in range(2, 11):
            cn_name = (row.get(f"Contact {i} Name", "") or row.get(f"contact_{i}_name", "")).strip()
            cn_email = (row.get(f"Contact {i} Email", "") or row.get(f"contact_{i}_email", "")).strip()
            cn_mobile = (row.get(f"Contact {i} Mobile", "") or row.get(f"contact_{i}_mobile", "")).strip()
            if cn_name or cn_email:
                contacts.append({"name": cn_name or f"Contact {i}", "email": cn_email, "phone": cn_mobile, "is_primary": False})

        if contacts:
            mapped["_contacts"] = contacts

        # Only include rows that have at least a vendor_code or name
        if mapped["vendor_code"] or mapped["name"]:
            mapped_rows.append(mapped)

    if not mapped_rows:
        raise FileValidationException(errors=["No valid party data found in the file."])

    result = await service.bulk_import(mapped_rows, company_code)

    return BulkImportResultResponse(
        total_rows=result.total_rows,
        successful=result.successful,
        failed=result.failed,
        errors=[
            BulkImportRowErrorResponse(
                row_number=e.row_number,
                vendor_code=e.vendor_code,
                errors=e.errors,
            )
            for e in result.errors
        ],
    )
