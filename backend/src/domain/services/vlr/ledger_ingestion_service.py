"""
Shared helpers for writing parsed ledger entries into the database.

Extracted so both the direct company-ledger upload (single request, cases
already exist) and the consolidated multi-vendor auto-detect flow (request +
cases created on confirmation) store entries/headers identically instead of
duplicating the logic.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.domain.services.vlr.file_parser_service import ParsedLedgerEntry


async def save_company_file_headers(
    session: AsyncSession,
    case_id: UUID,
    headers: list[str],
) -> None:
    """Persist the original (mixed-case) file headers for a case's company
    side so the column-mapping UI can show them."""
    if not headers:
        return
    from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
        SettingRepositoryImpl,
    )

    repo = SettingRepositoryImpl(session)
    await repo.upsert(
        company_code="__global__",
        key=f"file_headers.{case_id}.company",
        value=json.dumps(headers),
        value_type="json",
        description="Original file headers from company ledger upload",
    )


def store_company_entries(
    session: AsyncSession,
    case_id: UUID,
    entries: list["ParsedLedgerEntry"],
    actor_username: str,
) -> None:
    """Add LedgerEntryModel rows (side='company') for the given case."""
    from src.infrastructure.database.models.vlr.ledger_entry_model import LedgerEntryModel

    for entry in entries:
        session.add(LedgerEntryModel(
            case_id=case_id,
            side="company",
            document_number=entry.document_number,
            document_type=entry.document_type,
            reference_number=entry.reference_number,
            posting_date=entry.posting_date,
            clearing_date=entry.clearing_date,
            clearing_document=entry.clearing_document,
            amount=float(entry.amount),
            currency=entry.currency,
            assignment_number=entry.assignment_number,
            description=entry.description,
            raw_data=getattr(entry, "raw_data", None),
            source="upload",
            created_by=actor_username,
            modified_by=actor_username,
        ))
