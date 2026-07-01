"""
Commission Claim Application Service.
Orchestrates claim CRUD and workflow integration.
"""

import random
import string
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.endpoints.commission_claim.schemas import ClaimCreate, ClaimListResponse, ClaimResponse
from src.application.services.workflow.workflow_engine import WorkflowEngine
from src.domain.entities.user import User
from src.infrastructure.database.models.commission_claim.commission_claim_model import CommissionClaimModel


class CommissionClaimService:
    """Application service for commission claim management."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workflow = WorkflowEngine(session)

    # ─── List Claims ───

    async def list_claims(self, skip: int = 0, limit: int = 50) -> ClaimListResponse:
        """Get all claims ordered by creation date."""
        stmt = (
            select(CommissionClaimModel)
            .order_by(CommissionClaimModel.created_date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        claims = result.scalars().all()
        return ClaimListResponse(
            claims=[ClaimResponse.model_validate(c) for c in claims],
            total=len(claims),
        )

    # ─── Create Claim ───

    async def create_claim(self, request: ClaimCreate, actor: User) -> ClaimResponse:
        """Create a new claim in DRAFT status."""
        claim = CommissionClaimModel(
            id=uuid4(),
            claim_number=self._generate_claim_number(),
            employee_id=str(actor.id),
            employee_name=request.employee_name,
            amount=request.amount,
            company=request.company,
            department=request.department,
            region=request.region,
            description=request.description,
            status="DRAFT",
            workflow_instance_id=None,
            created_by=actor.username,
            modified_by=actor.username,
        )
        self._session.add(claim)
        await self._session.flush()
        return ClaimResponse.model_validate(claim)

    # ─── Submit Claim ───

    async def submit_claim(self, claim_id: UUID, actor: User) -> ClaimResponse:
        """Submit a DRAFT claim — starts the workflow."""
        claim = await self._session.get(CommissionClaimModel, str(claim_id))
        if not claim:
            raise ValueError("Claim not found")
        if claim.status != "DRAFT":
            raise ValueError(f"Cannot submit claim in '{claim.status}' status")

        # Start workflow
        result = await self._workflow.start_workflow(
            definition_code="COMMISSION_CLAIM",
            entity_type="commission_claim",
            entity_id=claim_id,
            initiated_by=actor.id,
            metadata={
                "amount": float(claim.amount),
                "company": claim.company,
                "department": claim.department,
                "region": claim.region,
                "claim_number": claim.claim_number,
            },
        )

        # Update claim
        claim.status = "SUBMITTED"
        claim.workflow_instance_id = result["instance_id"]
        claim.modified_by = actor.username

        # Execute SUBMIT transition
        await self._workflow.execute_action(
            instance_id=UUID(result["instance_id"]),
            action_code="SUBMIT",
            actor_id=actor.id,
            actor_username=actor.username,
        )

        return ClaimResponse.model_validate(claim)

    # ─── Get Claim Details ───

    async def get_claim_details(self, claim_id: UUID) -> dict:
        """Get claim with workflow status and available actions."""
        claim = await self._session.get(CommissionClaimModel, str(claim_id))
        if not claim:
            raise ValueError("Claim not found")

        response: dict = {
            "claim": ClaimResponse.model_validate(claim),
            "workflow_status": None,
            "available_actions": [],
        }

        if claim.workflow_instance_id:
            response["workflow_status"] = await self._workflow.get_workflow_status(
                UUID(claim.workflow_instance_id)
            )
            response["available_actions"] = await self._workflow.get_available_actions(
                UUID(claim.workflow_instance_id)
            )

        return response

    # ─── Execute Workflow Action ───

    async def execute_action(self, claim_id: UUID, action_code: str, comments: str, actor: User) -> dict:
        """Execute a workflow action (approve, reject, etc.) on a claim."""
        claim = await self._session.get(CommissionClaimModel, str(claim_id))
        if not claim:
            raise ValueError("Claim not found")
        if not claim.workflow_instance_id:
            raise ValueError("Claim has no active workflow")

        result = await self._workflow.execute_action(
            instance_id=UUID(claim.workflow_instance_id),
            action_code=action_code,
            actor_id=actor.id,
            actor_username=actor.username,
            comments=comments,
        )

        # Sync claim status
        claim.status = result["current_status_code"]
        claim.modified_by = actor.username

        return {
            "claim_id": str(claim_id),
            "claim_number": claim.claim_number,
            "previous_status": result.get("previous_status"),
            "current_status": result["current_status_code"],
            "is_completed": result["is_completed"],
            "action_executed": action_code,
            "comments": comments,
        }

    # ─── Helpers ───

    @staticmethod
    def _generate_claim_number() -> str:
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        return f"CLM-{suffix}"
