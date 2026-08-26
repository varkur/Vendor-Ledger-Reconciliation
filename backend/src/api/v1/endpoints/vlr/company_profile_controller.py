"""
Company Profile API endpoints.
Manages entity-level company profile settings: name, PAN, contact details,
letterhead images, logo, and registered office address.

Routes:
- GET  /api/v1/vlr/settings/company-profile     — Get company profile
- PUT  /api/v1/vlr/settings/company-profile     — Update company profile

Requirements: Company Profile configuration for letterhead and entity details.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/settings", tags=["VLR - Company Profile"])

GLOBAL_COMPANY_CODE = "__global__"

# Setting key constants
CP_PREFIX = "company_profile"
CP_ENTITY_NAME_KEY = f"{CP_PREFIX}.entity_name"
CP_ENTITY_TYPE_KEY = f"{CP_PREFIX}.entity_type"
CP_PAN_CARD_KEY = f"{CP_PREFIX}.pan_card"
CP_EMAIL_KEY = f"{CP_PREFIX}.email"
CP_WEBSITE_KEY = f"{CP_PREFIX}.website"
CP_TELEPHONE_KEY = f"{CP_PREFIX}.telephone"
CP_REGISTERED_ADDRESS_KEY = f"{CP_PREFIX}.registered_address"
CP_COMPANY_CODE_KEY = f"{CP_PREFIX}.company_code"
CP_LETTERHEAD_HEADER_KEY = f"{CP_PREFIX}.letterhead_header"
CP_LETTERHEAD_FOOTER_KEY = f"{CP_PREFIX}.letterhead_footer"
CP_LOGO_KEY = f"{CP_PREFIX}.logo"
CP_VERIFIED_KEY = f"{CP_PREFIX}.verified"

# Default entities used both as the /entities fallback response AND by
# resolve_company_display_name below when the "entities.list" setting has
# never been saved (fresh install). Kept as a single source of truth so the
# two lookups never disagree about what an unconfigured company_code maps to.
DEFAULT_ENTITIES: list[dict] = [
    {"id": "1", "company_code": "1000", "name": "Emcure Pharmaceuticals Limited", "entity_type": "Public company", "pan_card": "AAACE4574C", "is_active": True},
    {"id": "2", "company_code": "2000", "name": "Gennova Biopharmaceuticals Ltd", "entity_type": "Private company", "pan_card": "AABCG1234A", "is_active": True},
    {"id": "3", "company_code": "3000", "name": "ZUVENTUS HEALTHCARE LIMITED", "entity_type": "Private company", "pan_card": "AAACZ5678B", "is_active": True},
    {"id": "4", "company_code": "4000", "name": "EMCUTIX BIOPHARMACEUTICALS LTD", "entity_type": "Private company", "pan_card": "AABCE9012C", "is_active": True},
]


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────


class CompanyProfileResponse(BaseModel):
    """Company profile data."""

    entity_name: str = ""
    entity_type: str = ""
    pan_card: str = ""
    email: str = ""
    website: str = ""
    telephone: str = ""
    registered_address: str = ""
    company_code: str = ""
    letterhead_header: str = ""
    letterhead_footer: str = ""
    logo: str = ""
    verified: bool = False


class CompanyEntityResponse(BaseModel):
    """A single company entity in the entities list (for the entity switcher)."""

    id: str
    company_code: str
    name: str
    entity_type: str = ""
    pan_card: str = ""
    is_active: bool = True


class CompanyProfileUpdateRequest(BaseModel):
    """Request to update company profile. Only provided fields are changed."""

    entity_name: Optional[str] = Field(None, description="Company entity name")
    entity_type: Optional[str] = Field(None, description="Entity type (e.g. Public company, Private)")
    pan_card: Optional[str] = Field(None, description="Entity PAN card number")
    email: Optional[str] = Field(None, description="Company email address")
    website: Optional[str] = Field(None, description="Company website URL")
    telephone: Optional[str] = Field(None, description="Company telephone number")
    registered_address: Optional[str] = Field(None, description="Registered office address")
    company_code: Optional[str] = Field(None, description="Company code")
    letterhead_header: Optional[str] = Field(None, description="Letterhead header image URL/path")
    letterhead_footer: Optional[str] = Field(None, description="Letterhead footer image URL/path")
    logo: Optional[str] = Field(None, description="Company logo image URL/path")


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_setting_repository(
    session: AsyncSession = Depends(get_db_session),
) -> SettingRepositoryImpl:
    return SettingRepositoryImpl(session)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _get_setting_value(
    repo: SettingRepositoryImpl,
    key: str,
    default: str = "",
) -> str:
    setting = await repo.get_by_key(GLOBAL_COMPANY_CODE, key)
    return setting.value if setting else default


async def _upsert_setting(
    repo: SettingRepositoryImpl,
    key: str,
    value: str,
    *,
    description: str = "",
    modified_by: str = "system",
) -> None:
    await repo.upsert(
        GLOBAL_COMPANY_CODE,
        key,
        value,
        value_type="string",
        description=description,
        modified_by=modified_by,
    )


async def resolve_company_display_name(
    repo: SettingRepositoryImpl, company_code: str, fallback: str = "",
) -> str:
    """
    Resolve the human-readable entity name for a `company_code` (e.g. "1000"
    -> "Emcure Pharmaceuticals Limited", "2000" -> "Gennova Biopharmaceuticals
    Ltd") by looking it up in the stored `entities.list` setting — the same
    list the entity switcher and Company Profile screen read from.

    Bug fix: every outbound vendor email (ledger request invite, sign-off
    request) had "Emcure Pharmaceuticals Limited" hardcoded regardless of
    which company entity the request was actually created under, so a
    request created from e.g. Gennova's entity still told the vendor they'd
    been invited by Emcure. This is the single shared lookup all outbound
    email builders should use instead of a literal string.

    Falls back to `fallback` (or the raw company_code if no fallback is
    given) when the code isn't found in the entities list — this can happen
    for a company_code that predates the entities list being populated, or
    hasn't been configured yet.
    """
    import json

    if not company_code:
        return fallback or company_code

    entities_json = await _get_setting_value(repo, "entities.list", "")
    entities_data: list[dict] | None = None
    if entities_json:
        try:
            entities_data = json.loads(entities_json)
        except (json.JSONDecodeError, TypeError):
            entities_data = None
    if not entities_data:
        entities_data = DEFAULT_ENTITIES

    entity = next(
        (e for e in entities_data if e.get("company_code") == company_code),
        None,
    )
    if entity and entity.get("name"):
        return entity["name"]

    return fallback or company_code


async def _load_company_profile(repo: SettingRepositoryImpl) -> CompanyProfileResponse:
    return CompanyProfileResponse(
        entity_name=await _get_setting_value(repo, CP_ENTITY_NAME_KEY, ""),
        entity_type=await _get_setting_value(repo, CP_ENTITY_TYPE_KEY, ""),
        pan_card=await _get_setting_value(repo, CP_PAN_CARD_KEY, ""),
        email=await _get_setting_value(repo, CP_EMAIL_KEY, ""),
        website=await _get_setting_value(repo, CP_WEBSITE_KEY, ""),
        telephone=await _get_setting_value(repo, CP_TELEPHONE_KEY, ""),
        registered_address=await _get_setting_value(repo, CP_REGISTERED_ADDRESS_KEY, ""),
        company_code=await _get_setting_value(repo, CP_COMPANY_CODE_KEY, ""),
        letterhead_header=await _get_setting_value(repo, CP_LETTERHEAD_HEADER_KEY, ""),
        letterhead_footer=await _get_setting_value(repo, CP_LETTERHEAD_FOOTER_KEY, ""),
        logo=await _get_setting_value(repo, CP_LOGO_KEY, ""),
        verified=(await _get_setting_value(repo, CP_VERIFIED_KEY, "false")).lower() == "true",
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/company-profile",
    response_model=CompanyProfileResponse,
    summary="Get company profile",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_company_profile(
    company_code: str = Query(default="", description="Company code to load profile for"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> CompanyProfileResponse:
    """
    GET /api/v1/vlr/settings/company-profile?company_code=1000

    Returns the company entity profile. If company_code is provided,
    loads entity-specific data from the entities list.
    """
    import json

    # If a company_code is provided, look up entity details from the stored list
    if company_code:
        entities_json = await _get_setting_value(repo, "entities.list", "")
        if entities_json:
            try:
                entities_data = json.loads(entities_json)
                entity = next(
                    (e for e in entities_data if e.get("company_code") == company_code),
                    None,
                )
                if entity:
                    # Load entity-scoped settings (keyed by company_code prefix)
                    prefix = f"cp.{company_code}."
                    return CompanyProfileResponse(
                        entity_name=entity.get("name", ""),
                        entity_type=entity.get("entity_type", ""),
                        pan_card=entity.get("pan_card", ""),
                        email=await _get_setting_value(repo, f"{prefix}email", ""),
                        website=await _get_setting_value(repo, f"{prefix}website", ""),
                        telephone=await _get_setting_value(repo, f"{prefix}telephone", ""),
                        registered_address=await _get_setting_value(repo, f"{prefix}registered_address", ""),
                        company_code=company_code,
                        letterhead_header=await _get_setting_value(repo, f"{prefix}letterhead_header", ""),
                        letterhead_footer=await _get_setting_value(repo, f"{prefix}letterhead_footer", ""),
                        logo=await _get_setting_value(repo, f"{prefix}logo", ""),
                        verified=entity.get("is_active", False),
                    )
            except (json.JSONDecodeError, TypeError):
                pass

    # Fallback to global settings
    return await _load_company_profile(repo)


@router.get(
    "/entities",
    response_model=list[CompanyEntityResponse],
    summary="List all company entities",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def list_entities(
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> list[CompanyEntityResponse]:
    """
    GET /api/v1/vlr/settings/entities

    Returns a list of all company entities/subsidiaries. Used by the
    entity switcher in the topbar.
    """
    import json

    # Try to load entities from settings (stored as JSON list)
    entities_json = await _get_setting_value(repo, "entities.list", "")
    if entities_json:
        try:
            entities_data = json.loads(entities_json)
            return [CompanyEntityResponse(**e) for e in entities_data]
        except (json.JSONDecodeError, TypeError):
            pass

    # Return default entities if none stored
    return [CompanyEntityResponse(**e) for e in DEFAULT_ENTITIES]


@router.put(
    "/company-profile",
    response_model=CompanyProfileResponse,
    summary="Update company profile",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_company_profile(
    request: CompanyProfileUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> CompanyProfileResponse:
    """
    PUT /api/v1/vlr/settings/company-profile

    Updates company profile fields. Only provided (non-null) fields are changed.
    """
    modifier = current_user.username

    field_map = {
        CP_ENTITY_NAME_KEY: (request.entity_name, "Entity name"),
        CP_ENTITY_TYPE_KEY: (request.entity_type, "Entity type"),
        CP_PAN_CARD_KEY: (request.pan_card, "PAN card number"),
        CP_EMAIL_KEY: (request.email, "Company email"),
        CP_WEBSITE_KEY: (request.website, "Company website"),
        CP_TELEPHONE_KEY: (request.telephone, "Company telephone"),
        CP_REGISTERED_ADDRESS_KEY: (request.registered_address, "Registered office address"),
        CP_COMPANY_CODE_KEY: (request.company_code, "Company code"),
        CP_LETTERHEAD_HEADER_KEY: (request.letterhead_header, "Letterhead header image"),
        CP_LETTERHEAD_FOOTER_KEY: (request.letterhead_footer, "Letterhead footer image"),
        CP_LOGO_KEY: (request.logo, "Company logo"),
    }

    for key, (value, description) in field_map.items():
        if value is not None:
            await _upsert_setting(
                repo, key, value, description=description, modified_by=modifier
            )

    # When editing a specific entity (company_code provided), keep the entities
    # list in sync so the switcher and profile GET reflect the edited core
    # details (name/type/pan) — these are read from the entities list, not the
    # global keys.
    if request.company_code:
        import json as _json

        entities_json = await _get_setting_value(repo, "entities.list", "")
        entities: list[dict] = []
        if entities_json:
            try:
                entities = _json.loads(entities_json)
            except (ValueError, TypeError):
                entities = []

        code = request.company_code.strip().upper()
        match = next(
            (e for e in entities if (e.get("company_code") or "").upper() == code),
            None,
        )
        if match is not None:
            if request.entity_name is not None:
                match["name"] = request.entity_name
            if request.entity_type is not None:
                match["entity_type"] = request.entity_type
            if request.pan_card is not None:
                match["pan_card"] = request.pan_card.upper()
            await _upsert_setting(
                repo, "entities.list", _json.dumps(entities),
                description="List of company entities", modified_by=modifier,
            )

    logger.info("Company profile updated by user=%s", current_user.username)
    return await _load_company_profile(repo)


class CreateEntityRequest(BaseModel):
    """Request to create a new company entity."""

    country: str = Field(..., description="Country of the entity")
    entity_type: str = Field(..., min_length=1, description="Entity type (Public company, Private, etc.)")
    name: str = Field(..., min_length=1, description="Entity name")
    pan_card: str = Field(..., min_length=1, description="Entity PAN card")
    company_code: str = Field(..., min_length=1, max_length=20, description="Company code (used as request ID prefix, e.g. EPL)")


@router.post(
    "/entities",
    response_model=CompanyEntityResponse,
    summary="Create a new company entity",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
    status_code=201,
)
async def create_entity(
    request: CreateEntityRequest,
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> CompanyEntityResponse:
    """
    POST /api/v1/vlr/settings/entities

    Creates a new company entity and adds it to the entity list.
    """
    import json
    import uuid

    # Load existing entities
    entities_json = await _get_setting_value(repo, "entities.list", "")
    entities: list[dict] = []
    if entities_json:
        try:
            entities = json.loads(entities_json)
        except (json.JSONDecodeError, TypeError):
            entities = []

    # If no stored entities, seed with defaults
    if not entities:
        entities = [e.copy() for e in DEFAULT_ENTITIES]

    # Company code is user-provided and mandatory; must be unique.
    new_code = request.company_code.strip().upper()
    if any((e.get("company_code") or "").upper() == new_code for e in entities):
        from fastapi import HTTPException, status as _status
        raise HTTPException(
            status_code=_status.HTTP_409_CONFLICT,
            detail=f"An entity with company code '{new_code}' already exists.",
        )

    # Generate new entity
    new_id = str(uuid.uuid4())[:8]
    new_entity = {
        "id": new_id,
        "company_code": new_code,
        "name": request.name,
        "entity_type": request.entity_type,
        "pan_card": request.pan_card.upper(),
        "is_active": True,
    }
    entities.append(new_entity)

    # Persist the updated list
    await _upsert_setting(
        repo,
        "entities.list",
        json.dumps(entities),
        description="List of company entities",
        modified_by=current_user.username,
    )

    logger.info("Entity created: name=%s by user=%s", request.name, current_user.username)

    return CompanyEntityResponse(**new_entity)
