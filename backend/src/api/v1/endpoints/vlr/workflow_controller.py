"""
Workflow Orchestration API endpoints.
Thin controller — delegates all business logic to WorkflowOrchestratorService.

Routes:
- POST /api/v1/vlr/workflow/{case_id}/advance       — Advance to next workflow step
- POST /api/v1/vlr/workflow/{case_id}/rollback      — Rollback to a previous step
- GET  /api/v1/vlr/workflow/{case_id}/status        — Get current workflow status
- GET  /api/v1/vlr/workflow/sla-violations          — List overdue cases

Requirements: 12.1, 12.4, 13.2
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.api.v1.schemas.vlr.workflow_schemas import (
    AdvanceRequest,
    RollbackRequest,
    SLAViolationResponse,
    SLAViolationsListResponse,
    StatusResponse,
)
from src.domain.entities.user import User
from src.domain.services.vlr.workflow_orchestrator_service import (
    CaseNotFoundError,
    SLAConfiguration,
    WorkflowOrchestratorService,
    WorkflowRollbackError,
    WorkflowTransitionError,
)
from src.infrastructure.database.models.vlr.reconciliation_case_model import (
    ReconciliationCaseModel,
)
from src.infrastructure.database.models.vlr.sla_configuration_model import (
    SLAConfigurationModel,
)
from src.infrastructure.database.repositories.vlr.case_repository_impl import (
    CaseRepositoryImpl,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/workflow", tags=["VLR - Workflow Orchestration"])


# ──────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────


def _get_case_repository(
    session: AsyncSession = Depends(get_db_session),
) -> CaseRepositoryImpl:
    """FastAPI dependency — creates CaseRepository."""
    return CaseRepositoryImpl(session)


async def _get_sla_configuration(
    session: AsyncSession = Depends(get_db_session),
) -> SLAConfiguration:
    """FastAPI dependency — loads SLA configuration from database."""
    stmt = select(SLAConfigurationModel).where(
        SLAConfigurationModel.is_active == True  # noqa: E712
    )
    result = await session.execute(stmt)
    sla_models = result.scalars().all()

    step_sla_hours: dict[str, int] = {}
    escalation_emails: dict[str, str] = {}

    for model in sla_models:
        step_sla_hours[model.step_name] = model.sla_hours
        if model.escalation_email:
            escalation_emails[model.step_name] = model.escalation_email

    return SLAConfiguration(
        step_sla_hours=step_sla_hours,
        escalation_emails=escalation_emails,
    )


def _get_workflow_service(
    case_repo: CaseRepositoryImpl = Depends(_get_case_repository),
    sla_config: SLAConfiguration = Depends(_get_sla_configuration),
) -> WorkflowOrchestratorService:
    """FastAPI dependency — creates WorkflowOrchestratorService with injected dependencies."""
    return WorkflowOrchestratorService(
        case_repository=case_repo,
        sla_config=sla_config,
    )


def _get_audit_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuditTrailService:
    """FastAPI dependency — creates AuditTrailService for audit logging."""
    return AuditTrailService(audit_repository=AuditTrailRepositoryImpl(session))


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/{case_id}/advance",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Advance a case to the next workflow step",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def advance_workflow(
    case_id: UUID,
    request: AdvanceRequest,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowOrchestratorService = Depends(_get_workflow_service),
    audit_service: AuditTrailService = Depends(_get_audit_service),
) -> StatusResponse:
    """
    POST /api/v1/vlr/workflow/{case_id}/advance

    Advances the reconciliation case to the specified target workflow step.
    The transition is validated against the VALID_TRANSITIONS map. Only
    forward transitions to the immediate next step are permitted.

    Requirement 12.1: Enforce step sequence.
    Requirement 12.4: Support transition validation.
    """
    try:
        case_status = await service.advance(
            case_id=case_id,
            target_step=request.target_step,
            triggered_by=current_user.username or str(current_user.id),
        )
    except CaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case '{case_id}' not found.",
        )
    except WorkflowTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Emit audit event for workflow transition (Requirement 38.2)
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.STATUS_CHANGED,
        case_id=case_id,
        event_details={
            "action": "advance",
            "target_step": case_status.current_step.value,
        },
    ))

    return StatusResponse(
        case_id=case_status.case_id,
        current_step=case_status.current_step,
        step_entered_at=case_status.step_entered_at,
        sla_deadline=case_status.sla_deadline,
        is_overdue=case_status.is_overdue,
    )


@router.post(
    "/{case_id}/rollback",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Rollback a case to a previous workflow step",
    dependencies=[Depends(require_permission("vlr.cases.write"))],
)
async def rollback_workflow(
    case_id: UUID,
    request: RollbackRequest,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowOrchestratorService = Depends(_get_workflow_service),
    audit_service: AuditTrailService = Depends(_get_audit_service),
) -> StatusResponse:
    """
    POST /api/v1/vlr/workflow/{case_id}/rollback

    Rolls back the reconciliation case to a previous workflow step.
    The rollback target must be a valid rollback target per the
    VALID_TRANSITIONS map and must be a step earlier in the sequence.

    Requirement 12.4: Support rollback to previous step.
    """
    try:
        case_status = await service.rollback(
            case_id=case_id,
            target_step=request.target_step,
            triggered_by=current_user.username or str(current_user.id),
        )
    except CaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case '{case_id}' not found.",
        )
    except WorkflowRollbackError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    # Emit audit event for workflow rollback (Requirement 38.2)
    await audit_service.log_event(AuditEvent(
        actor_username=current_user.username or str(current_user.id),
        actor_id=current_user.id,
        event_type=AuditEventType.STATUS_CHANGED,
        case_id=case_id,
        event_details={
            "action": "rollback",
            "target_step": case_status.current_step.value,
        },
    ))

    return StatusResponse(
        case_id=case_status.case_id,
        current_step=case_status.current_step,
        step_entered_at=case_status.step_entered_at,
        sla_deadline=case_status.sla_deadline,
        is_overdue=case_status.is_overdue,
    )


@router.get(
    "/{case_id}/status",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current workflow status for a case",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_workflow_status(
    case_id: UUID,
    current_user: User = Depends(get_current_active_user),
    service: WorkflowOrchestratorService = Depends(_get_workflow_service),
) -> StatusResponse:
    """
    GET /api/v1/vlr/workflow/{case_id}/status

    Returns the current workflow status of the reconciliation case,
    including the current step, when it was entered, and SLA information.

    Requirement 12.1: Track current status at all times.
    """
    try:
        case_status = await service.get_status(case_id=case_id)
    except CaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reconciliation case '{case_id}' not found.",
        )

    return StatusResponse(
        case_id=case_status.case_id,
        current_step=case_status.current_step,
        step_entered_at=case_status.step_entered_at,
        sla_deadline=case_status.sla_deadline,
        is_overdue=case_status.is_overdue,
    )


@router.get(
    "/sla-violations",
    response_model=SLAViolationsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all cases with SLA violations",
    dependencies=[Depends(require_permission("vlr.cases.read"))],
)
async def get_sla_violations(
    current_user: User = Depends(get_current_active_user),
    service: WorkflowOrchestratorService = Depends(_get_workflow_service),
    session: AsyncSession = Depends(get_db_session),
) -> SLAViolationsListResponse:
    """
    GET /api/v1/vlr/workflow/sla-violations

    Returns all reconciliation cases that have exceeded their SLA deadline.
    This identifies overdue cases for escalation and management attention.

    Requirement 13.2: Flag overdue cases.
    """
    now = datetime.now(timezone.utc)

    # Query for cases where SLA deadline has passed and not yet flagged
    stmt = select(ReconciliationCaseModel).where(
        and_(
            ReconciliationCaseModel.sla_deadline.isnot(None),
            ReconciliationCaseModel.sla_deadline < now,
            ReconciliationCaseModel.current_workflow_step.isnot(None),
            ReconciliationCaseModel.is_deleted == False,  # noqa: E712
        )
    )
    result = await session.execute(stmt)
    overdue_cases = list(result.scalars().all())

    # Use the service to process violations (updates is_overdue, sends notifications)
    violations = await service.check_sla_violations(overdue_cases=overdue_cases)

    items = [
        SLAViolationResponse(
            case_id=v.case_id,
            current_step=v.current_step,
            step_entered_at=v.step_entered_at,
            sla_deadline=v.sla_deadline,
            hours_overdue=round(v.hours_overdue, 2),
        )
        for v in violations
    ]

    return SLAViolationsListResponse(
        items=items,
        total=len(items),
    )
