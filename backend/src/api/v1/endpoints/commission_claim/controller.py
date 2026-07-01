"""
Commission Claim API — Thin controller.
Delegates all business logic to CommissionClaimService.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.endpoints.commission_claim.schemas import ClaimCreate, ClaimListResponse, ClaimResponse
from src.application.services.commission_claim_service import CommissionClaimService
from src.domain.entities.user import User
from src.infrastructure.database.session import get_db_session

router = APIRouter(prefix="/claims", tags=["Commission Claims (Example)"])


def _get_claim_service(session: AsyncSession = Depends(get_db_session)) -> CommissionClaimService:
    """FastAPI dependency — creates CommissionClaimService."""
    return CommissionClaimService(session=session)


@router.get("", response_model=ClaimListResponse, summary="List all commission claims")
async def list_claims(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimListResponse:
    """GET /claims"""
    return await service.list_claims(skip=skip, limit=limit)


@router.post("", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED, summary="Create a new commission claim")
async def create_claim(
    request: ClaimCreate,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimResponse:
    """POST /claims"""
    return await service.create_claim(request=request, actor=current_user)


@router.post("/{claim_id}/submit", response_model=ClaimResponse, summary="Submit claim — starts workflow")
async def submit_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> ClaimResponse:
    """POST /claims/{id}/submit"""
    try:
        return await service.submit_claim(claim_id=claim_id, actor=current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{claim_id}", summary="Get claim details with workflow status")
async def get_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> dict:
    """GET /claims/{id}"""
    try:
        return await service.get_claim_details(claim_id=claim_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{claim_id}/action", summary="Execute workflow action on claim")
async def execute_claim_action(
    claim_id: UUID,
    action_code: str = Query(..., description="Action: APPROVE, REJECT, REFER_BACK, CANCEL, CLOSE"),
    comments: str = Query(default=""),
    current_user: User = Depends(get_current_active_user),
    service: CommissionClaimService = Depends(_get_claim_service),
) -> dict:
    """POST /claims/{id}/action?action_code=APPROVE"""
    try:
        return await service.execute_action(
            claim_id=claim_id, action_code=action_code, comments=comments, actor=current_user
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
