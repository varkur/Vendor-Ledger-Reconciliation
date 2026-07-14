"""
Approval Workflow API endpoints.
Thin controller — delegates all business logic to ApprovalEngineService.

Routes:
- GET    /api/v1/vlr/approvals/pending         — List pending approvals for current user
- POST   /api/v1/vlr/approvals/{id}/approve    — Approve a reconciliation case
- POST   /api/v1/vlr/approvals/{id}/reject     — Reject a reconciliation case
- POST   /api/v1/vlr/approvals/{id}/delegate   — Delegate approval authority

Requirements: 7.3, 7.4, 7.9, 11.3
"""

from datetime import timedelta
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.approval_schemas import (
    ApprovalResponse,
    ApproveRequest,
    DelegateRequest,
    DelegationResponse,
    PendingApprovalCaseResponse,
    PendingApprovalsListResponse,
    RejectRequest,
    SubmitForApprovalRequest,
    SubmitForApprovalResponse,
)
from src.domain.entities.user import User
from src.domain.services.vlr.approval_engine_service import ApprovalEngineService
from src.domain.services.vlr.exception_manager_service import ExceptionManagerService
from src.infrastructure.database.repositories.vlr.approval_repository_impl import (
    ApprovalRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.exception_repository_impl import (
    ExceptionRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import (
    LedgerEntryRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.request_repository_impl import (
    RequestRepositoryImpl,
)
from src.infrastructure.database.repositories.vlr.setting_repository_impl import (
    SettingRepositoryImpl,
)
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission
from src.domain.services.vlr.audit_trail_service import (
    AuditEvent,
    AuditEventType,
    AuditTrailService,
)
from src.infrastructure.database.repositories.vlr.audit_trail_repository_impl import (
    AuditTrailRepositoryImpl,
)

router = APIRouter(prefix="/vlr/approvals", tags=["VLR - Approval Workflow"])

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_approval_service(
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalEngineService:
    """FastAPI dependency — creates ApprovalEngineService with injected repositories."""
    approval_repo = ApprovalRepositoryImpl(session)
    case_repo = CaseRepositoryImpl(session)
    request_repo = RequestRepositoryImpl(session)
    setting_repo = SettingRepositoryImpl(session)

    # Create ExceptionManagerService for Row_10 calculation and write-off checks
    exception_repo = ExceptionRepositoryImpl(session)
    ledger_repo = LedgerEntryRepositoryImpl(session)
    exception_manager = ExceptionManagerService(
        exception_repository=exception_repo,
        case_repository=case_repo,
        ledger_entry_repository=ledger_repo,
        setting_repository=setting_repo,
    )

    return ApprovalEngineService(
        approval_repository=approval_repo,
        case_repository=case_repo,
        request_repository=request_repo,
        setting_repository=setting_repo,
        exception_manager_service=exception_manager,
    )


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/submit",
    response_model=SubmitForApprovalResponse,
    summary="Submit a reconciliation case for approval",
    dependencies=[Depends(require_permission("vlr.cases.submit"))],
)
async def submit_for_approval(
    request: SubmitForApprovalRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ApprovalEngineService = Depends(_get_approval_service),
    session: AsyncSession = Depends(get_db_session),
) -> SubmitForApprovalResponse:
    """
    POST /api/v1/vlr/approvals/submit

    Submit a reconciliation case for manager approval. The case must be in
    'review' status and have a zero Row_10 balance (net difference).

    Requirement 21: End-to-End Flow — Submit for Approval.
    """
    result = await service.submit_for_approval(
        case_id=request.case_id,
        submitted_by=current_user.id,
        company_code=company_code,
    )

    # Emit audit event for submission
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.APPROVAL,
        case_id=request.case_id,
        event_details={
            "decision": "submitted",
            "comments": request.comments,
            "approval_level": result.approval_level,
        },
    ))

    return SubmitForApprovalResponse(
        approval_id=result.approval_id,
        case_id=result.case_id,
        status="pending_approval",
        message="Case successfully submitted for approval.",
    )


@router.get(
    "/pending",
    response_model=PendingApprovalsListResponse,
    summary="List pending approvals for the current user",
    dependencies=[Depends(require_permission("vlr.approvals.approve"))],
)
async def get_pending_approvals(
    company_code: str = Query(..., min_length=1, description="Company code filter"),
    current_user: User = Depends(get_current_active_user),
    service: ApprovalEngineService = Depends(_get_approval_service),
) -> PendingApprovalsListResponse:
    """
    GET /api/v1/vlr/approvals/pending

    Returns all cases pending approval for the current user, including
    cases delegated to them.

    Requirement 7.3: Assign to designated Reconciliation Manager.
    Requirement 7.9: Support delegation of approval authority.
    """
    pending_cases = await service.get_pending_approvals(
        approver_id=current_user.id,
        company_code=company_code,
    )

    items = [
        PendingApprovalCaseResponse.model_validate(case)
        for case in pending_cases
    ]

    return PendingApprovalsListResponse(
        items=items,
        total=len(items),
    )


@router.post(
    "/{case_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve a reconciliation case",
    dependencies=[Depends(require_permission("vlr.approvals.approve"))],
)
async def approve_case(
    case_id: UUID,
    request: ApproveRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ApprovalEngineService = Depends(_get_approval_service),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    """
    POST /api/v1/vlr/approvals/{id}/approve

    Approves a reconciliation case pending approval.
    After approval, auto-triggers the portal sign-off email to the vendor.

    Requirement 7.4: Manager can approve a submitted case.
    Requirement 7.6: Transition to Sign Off stage.
    Requirement 7.7: Require senior approval if write-off exceeds threshold.
    Requirement 7.8: Record decision in audit log.
    Requirement 22: Auto-trigger sign-off request after approval.
    """
    result = await service.approve(
        case_id=case_id,
        approver_id=current_user.id,
        comments=request.comments,
        company_code=company_code,
    )

    # Emit audit event for approval (Requirement 38.2)
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.APPROVAL,
        case_id=case_id,
        event_details={
            "decision": "approved",
            "comments": request.comments,
            "approval_level": result.approval_level,
        },
    ))

    # Auto-trigger portal sign-off email after approval (Requirement 22)
    # Dispatches as a non-blocking Celery task so the response is not delayed.
    try:
        from src.infrastructure.tasks.vlr.notification_tasks import (
            send_notification_task,
        )

        send_notification_task.delay(
            case_id=str(case_id),
            notification_type="sign_off_request",
            recipient_email="",  # Resolved by the task from case vendor contact
            triggered_by=current_user.username or str(current_user.id),
            company_code=company_code,
            context_data={
                "case_id": str(case_id),
                "approved_by": current_user.username or str(current_user.id),
            },
        )
        logger.info(
            "Auto-triggered portal sign-off email after approval: case_id=%s",
            str(case_id),
        )
    except Exception as e:
        # Log the failure but don't block the approval response.
        # The sign-off can be triggered manually if the async dispatch fails.
        logger.warning(
            "Failed to auto-trigger portal sign-off email: case_id=%s, error=%s",
            str(case_id),
            str(e),
        )

    return ApprovalResponse(
        approval_id=result.approval_id,
        case_id=result.case_id,
        decision=result.decision,
        comments=result.comments,
        approver_id=result.approver_id,
        approval_level=result.approval_level,
        decision_date=result.decision_date,
    )


@router.post(
    "/{case_id}/reject",
    response_model=ApprovalResponse,
    summary="Reject a reconciliation case",
    dependencies=[Depends(require_permission("vlr.approvals.approve"))],
)
async def reject_case(
    case_id: UUID,
    request: RejectRequest,
    company_code: str = Query(..., min_length=1, description="Company code"),
    current_user: User = Depends(get_current_active_user),
    service: ApprovalEngineService = Depends(_get_approval_service),
    session: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    """
    POST /api/v1/vlr/approvals/{id}/reject

    Rejects a reconciliation case pending approval with mandatory comments.

    Requirement 7.4: Manager can reject with comments.
    Requirement 7.5: Transition back to Review stage with rejection comments.
    Requirement 7.8: Record decision in audit log.
    """
    result = await service.reject(
        case_id=case_id,
        approver_id=current_user.id,
        comments=request.comments,
        company_code=company_code,
    )

    # Emit audit event for rejection (Requirement 38.2)
    audit_service = AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.REJECTION,
        case_id=case_id,
        event_details={
            "decision": "rejected",
            "comments": request.comments,
        },
    ))

    return ApprovalResponse(
        approval_id=result.approval_id,
        case_id=result.case_id,
        decision=result.decision,
        comments=result.comments,
        approver_id=result.approver_id,
        approval_level=result.approval_level,
        decision_date=result.decision_date,
    )


@router.post(
    "/{case_id}/delegate",
    response_model=DelegationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Delegate approval authority",
    dependencies=[Depends(require_permission("vlr.approvals.approve"))],
)
async def delegate_approval(
    case_id: UUID,
    request: DelegateRequest,
    current_user: User = Depends(get_current_active_user),
    service: ApprovalEngineService = Depends(_get_approval_service),
) -> DelegationResponse:
    """
    POST /api/v1/vlr/approvals/{id}/delegate

    Delegates the current user's approval authority to another user
    for a time-limited period.

    Requirement 7.9: Support delegation when primary approver is unavailable.
    """
    duration = timedelta(days=request.duration_days)

    delegation = await service.delegate_authority(
        from_user_id=current_user.id,
        to_user_id=request.to_user_id,
        duration=duration,
    )

    return DelegationResponse(
        id=delegation.id,
        from_user_id=delegation.from_user_id,
        to_user_id=delegation.to_user_id,
        start_date=delegation.start_date,
        end_date=delegation.end_date,
        is_active=delegation.is_active,
    )
