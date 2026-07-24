"""
Document Type Mappings CRUD API endpoints.
Manages document type classifications used in reconciliation matching.

Routes:
- GET    /api/v1/vlr/settings/document-types       — List all document type mappings
- POST   /api/v1/vlr/settings/document-types       — Create a new document type mapping
- PUT    /api/v1/vlr/settings/document-types/{id}  — Update an existing mapping
- DELETE /api/v1/vlr/settings/document-types/{id}  — Delete (soft-delete) a mapping

Requirements: 19
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.models.vlr.document_type_mapping_model import (
    DocumentTypeMappingModel,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/settings", tags=["VLR - Document Types"])


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class DocumentTypeCreateRequest(BaseModel):
    document_type_code: str = Field(..., min_length=1, max_length=10, description="SAP document type code")
    category: str = Field(..., min_length=1, max_length=30, description="Classification category")
    is_tds: bool = Field(default=False, description="Whether this is a TDS entry")
    is_active: bool = Field(default=True, description="Whether the mapping is active")
    company_code: str = Field(default="", description="Company code for entity scoping")


class DocumentTypeUpdateRequest(BaseModel):
    document_type_code: Optional[str] = Field(None, min_length=1, max_length=10)
    category: Optional[str] = Field(None, min_length=1, max_length=30)
    is_tds: Optional[bool] = None
    is_active: Optional[bool] = None
    company_code: str = Field(default="", description="Company code for entity scoping")


class DocumentTypeResponse(BaseModel):
    id: str
    document_type_code: str
    category: str
    is_tds: bool
    is_active: bool

    class Config:
        from_attributes = True


class DocumentTypeListResponse(BaseModel):
    items: List[DocumentTypeResponse]
    total: int
    page: int
    page_size: int


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _model_to_response(model: DocumentTypeMappingModel) -> DocumentTypeResponse:
    return DocumentTypeResponse(
        id=str(model.id),
        document_type_code=model.document_type_code,
        category=model.category,
        is_tds=model.is_tds,
        is_active=model.is_active,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/document-types",
    response_model=DocumentTypeListResponse,
    summary="List document type mappings",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def list_document_types(
    company_code: str = Query(default="", description="Company code for entity scoping"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentTypeListResponse:
    """
    GET /api/v1/vlr/settings/document-types

    Returns paginated list of document type mappings.
    """
    # Count total
    count_stmt = select(func.count()).select_from(DocumentTypeMappingModel)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Fetch paginated items
    offset = (page - 1) * page_size
    stmt = (
        select(DocumentTypeMappingModel)
        .order_by(DocumentTypeMappingModel.document_type_code)
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    models = result.scalars().all()

    items = [_model_to_response(m) for m in models]

    return DocumentTypeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/document-types",
    response_model=DocumentTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create document type mapping",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def create_document_type(
    request: DocumentTypeCreateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentTypeResponse:
    """
    POST /api/v1/vlr/settings/document-types

    Creates a new document type mapping. Code must be unique.
    """
    # Check for duplicate code
    existing_stmt = select(DocumentTypeMappingModel).where(
        DocumentTypeMappingModel.document_type_code == request.document_type_code
    )
    existing_result = await session.execute(existing_stmt)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document type code '{request.document_type_code}' already exists.",
        )

    # Validate category
    valid_categories = {"Invoice", "Payment", "Credit Note", "Debit Note", "TDS", "Other"}
    if request.category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}",
        )

    model = DocumentTypeMappingModel(
        document_type_code=request.document_type_code,
        category=request.category,
        is_tds=request.is_tds,
        is_active=request.is_active,
        created_by=current_user.username,
        modified_by=current_user.username,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)

    logger.info(
        "Document type created: code=%s, category=%s by user=%s",
        model.document_type_code,
        model.category,
        current_user.username,
    )

    return _model_to_response(model)


@router.put(
    "/document-types/{id}",
    response_model=DocumentTypeResponse,
    summary="Update document type mapping",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_document_type(
    id: str,
    request: DocumentTypeUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentTypeResponse:
    """
    PUT /api/v1/vlr/settings/document-types/{id}

    Updates an existing document type mapping.
    """
    stmt = select(DocumentTypeMappingModel).where(DocumentTypeMappingModel.id == id)
    result = await session.execute(stmt)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document type with id '{id}' not found.",
        )

    # Update fields if provided
    if request.document_type_code is not None:
        # Check uniqueness if code is being changed
        if request.document_type_code != model.document_type_code:
            dup_stmt = select(DocumentTypeMappingModel).where(
                DocumentTypeMappingModel.document_type_code == request.document_type_code,
                DocumentTypeMappingModel.id != id,
            )
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Document type code '{request.document_type_code}' already exists.",
                )
        model.document_type_code = request.document_type_code

    if request.category is not None:
        valid_categories = {"Invoice", "Payment", "Credit Note", "Debit Note", "TDS", "Other"}
        if request.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}",
            )
        model.category = request.category

    if request.is_tds is not None:
        model.is_tds = request.is_tds

    if request.is_active is not None:
        model.is_active = request.is_active

    model.modified_by = current_user.username

    await session.commit()
    await session.refresh(model)

    logger.info(
        "Document type updated: id=%s, code=%s by user=%s",
        id,
        model.document_type_code,
        current_user.username,
    )

    return _model_to_response(model)


@router.delete(
    "/document-types/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete document type mapping",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def delete_document_type(
    id: str,
    company_code: str = Query(default="", description="Company code for entity scoping"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """
    DELETE /api/v1/vlr/settings/document-types/{id}

    Soft-deletes a document type mapping by setting is_active=False.
    If already inactive, performs a hard delete.
    """
    stmt = select(DocumentTypeMappingModel).where(DocumentTypeMappingModel.id == id)
    result = await session.execute(stmt)
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document type with id '{id}' not found.",
        )

    if model.is_active:
        # Soft-delete: deactivate
        model.is_active = False
        model.modified_by = current_user.username
        await session.commit()
        logger.info(
            "Document type soft-deleted: id=%s, code=%s by user=%s",
            id,
            model.document_type_code,
            current_user.username,
        )
    else:
        # Already inactive — hard delete
        await session.delete(model)
        await session.commit()
        logger.info(
            "Document type hard-deleted: id=%s, code=%s by user=%s",
            id,
            model.document_type_code,
            current_user.username,
        )
