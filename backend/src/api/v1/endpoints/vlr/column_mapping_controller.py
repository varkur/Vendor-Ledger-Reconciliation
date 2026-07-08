"""
Column Mapping API endpoints.
Handles file preview, auto-mapping suggestions, and template persistence.

Routes:
- POST /api/v1/vlr/column-mapping/preview         — Upload file and get 10-row preview
- POST /api/v1/vlr/column-mapping/auto-map         — Get auto-mapping suggestions
- POST /api/v1/vlr/column-mapping/save-template    — Save mapping template
- GET  /api/v1/vlr/column-mapping/template/{vendor_id} — Retrieve saved template

Requirements: 9.1, 10.1, 10.2, 11.1
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.column_mapping_schemas import (
    AutoMapRequest,
    AutoMapResponse,
    ColumnMappingEntrySchema,
    ColumnSuggestionResponse,
    FilePreviewResponse,
    SaveTemplateRequest,
    SaveTemplateResponse,
    TemplateResponse,
)
from src.domain.entities.user import User
from src.domain.services.vlr.column_mapping_service import (
    ColumnMapping,
    ColumnMappingEntry,
    ColumnMappingService,
    HeaderLibrary,
    TransactionTypeTag,
)
from src.infrastructure.database.repositories.vlr.column_mapping_template_repository_impl import (
    ColumnMappingTemplateRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/column-mapping", tags=["VLR - Column Mapping"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_template_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ColumnMappingTemplateRepositoryImpl:
    """FastAPI dependency — creates ColumnMappingTemplateRepository."""
    return ColumnMappingTemplateRepositoryImpl(session)


def _get_column_mapping_service(
    template_repo: ColumnMappingTemplateRepositoryImpl = Depends(_get_template_repository),
) -> ColumnMappingService:
    """FastAPI dependency — creates ColumnMappingService with injected repo."""
    return ColumnMappingService(
        template_repository=template_repo,
        header_library=HeaderLibrary(),
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/preview",
    response_model=FilePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload file and get 10-row preview",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def preview_file(
    file: UploadFile = File(..., description="Vendor statement file (CSV or XLSX)"),
    current_user: User = Depends(get_current_active_user),
    service: ColumnMappingService = Depends(_get_column_mapping_service),
) -> FilePreviewResponse:
    """
    POST /api/v1/vlr/column-mapping/preview

    Uploads a vendor statement file and returns the first 10 rows
    as a preview, along with detected column headers. Supports CSV
    and XLSX formats.

    Requirements: 9.1
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    file_content = await file.read()
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty.",
        )

    try:
        preview = service.generate_preview(file_content, file.filename)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    logger.info(
        "File preview generated: filename=%s, headers=%d, rows=%d, user=%s",
        file.filename,
        len(preview.headers),
        len(preview.rows),
        current_user.username,
    )

    return FilePreviewResponse(
        headers=preview.headers,
        rows=preview.rows,
        total_row_count=preview.total_row_count,
        filename=preview.filename,
    )


@router.post(
    "/auto-map",
    response_model=AutoMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Get auto-mapping suggestions for column headers",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def auto_map_columns(
    request: AutoMapRequest,
    current_user: User = Depends(get_current_active_user),
    service: ColumnMappingService = Depends(_get_column_mapping_service),
) -> AutoMapResponse:
    """
    POST /api/v1/vlr/column-mapping/auto-map

    Compares provided column headers against a known header library
    and returns mapping suggestions with confidence scores (High, Medium, Low).
    High-confidence suggestions should be pre-selected in the UI.

    Requirements: 11.1
    """
    if not request.headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one header is required.",
        )

    suggestions = service.auto_map_columns(request.headers)

    logger.info(
        "Auto-mapping generated: headers=%d, suggestions_with_tag=%d, user=%s",
        len(request.headers),
        sum(1 for s in suggestions if s.suggested_tag is not None),
        current_user.username,
    )

    return AutoMapResponse(
        suggestions=[
            ColumnSuggestionResponse(
                column_index=s.column_index,
                header=s.header,
                suggested_tag=s.suggested_tag.value if s.suggested_tag else None,
                confidence=s.confidence.value if s.confidence else None,
                should_preselect=s.should_preselect,
            )
            for s in suggestions
        ]
    )


@router.post(
    "/save-template",
    response_model=SaveTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Save column mapping template for a vendor",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def save_template(
    request: SaveTemplateRequest,
    current_user: User = Depends(get_current_active_user),
    service: ColumnMappingService = Depends(_get_column_mapping_service),
) -> SaveTemplateResponse:
    """
    POST /api/v1/vlr/column-mapping/save-template

    Saves the column mapping configuration as a template associated
    with the specified vendor. If a template already exists for the
    vendor, it is updated.

    Requirements: 10.1, 10.2
    """
    if not request.mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one mapping entry is required.",
        )

    # Validate all tags
    for entry in request.mappings:
        try:
            TransactionTypeTag(entry.tag)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid transaction type tag: '{entry.tag}'. "
                f"Valid tags: {[t.value for t in TransactionTypeTag]}",
            )

    # Build domain ColumnMapping
    mapping = ColumnMapping(
        mappings=[
            ColumnMappingEntry(
                column_index=entry.column_index,
                header=entry.header,
                tag=TransactionTypeTag(entry.tag),
            )
            for entry in request.mappings
        ]
    )

    await service.save_template(
        vendor_id=request.vendor_id,
        mapping=mapping,
        created_by=current_user.username,
    )

    logger.info(
        "Column mapping template saved: vendor_id=%s, columns=%d, user=%s",
        request.vendor_id,
        len(request.mappings),
        current_user.username,
    )

    return SaveTemplateResponse(
        vendor_id=request.vendor_id,
        message=f"Column mapping template saved successfully for vendor {request.vendor_id}.",
    )


@router.get(
    "/template/{vendor_id}",
    response_model=TemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve saved column mapping template for a vendor",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_template(
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: ColumnMappingService = Depends(_get_column_mapping_service),
) -> TemplateResponse:
    """
    GET /api/v1/vlr/column-mapping/template/{vendor_id}

    Retrieves the saved column mapping template for the specified vendor.
    Returns 404 if no template exists.

    Requirements: 10.1, 10.2
    """
    mapping = await service.apply_template(vendor_id)

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No column mapping template found for vendor {vendor_id}.",
        )

    logger.info(
        "Column mapping template retrieved: vendor_id=%s, columns=%d, user=%s",
        vendor_id,
        len(mapping.mappings),
        current_user.username,
    )

    return TemplateResponse(
        vendor_id=vendor_id,
        mappings=[
            ColumnMappingEntrySchema(
                column_index=m.column_index,
                header=m.header,
                tag=m.tag.value,
            )
            for m in mapping.mappings
        ],
    )
