"""
Seed script for Workflow Engine.
Creates a sample Commission Claim workflow with statuses, transitions, and approval matrix.
Run via: python -m scripts.seed_workflow

This is idempotent — re-running will skip existing data.
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.infrastructure.database.session import async_session_factory
from src.workflow.infrastructure.models.workflow_models import (
    WorkflowDefinitionModel,
    WorkflowStatusModel,
    WorkflowTransitionModel,
    WorkflowActionModel,
)
from src.workflow.infrastructure.models.approval_matrix_models import (
    ApprovalMatrixModel,
    ApprovalRuleModel,
    ApprovalAssignmentModel,
)


async def seed() -> None:
    """Seed a complete Commission Claim workflow example."""
    async with async_session_factory() as session:

        # ═══════════════════════════════════════════════════════════
        # 1. WORKFLOW DEFINITION
        # ═══════════════════════════════════════════════════════════

        print("\n── Workflow Definition ──")

        existing = await session.execute(
            select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.code == "COMMISSION_CLAIM")
        )
        definition = existing.scalar_one_or_none()

        if definition:
            print("  [skip] Workflow 'COMMISSION_CLAIM' already exists")
        else:
            definition = WorkflowDefinitionModel(
                id=uuid4(),
                code="COMMISSION_CLAIM",
                name="Commission Claim Approval",
                description="Multi-level approval workflow for commission claims. Routes based on claim amount.",
                entity_type="commission_claim",
                version=1,
                is_active=True,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(definition)
            await session.flush()
            print("  [new]  Workflow 'COMMISSION_CLAIM' created")

        def_id = str(definition.id)

        # ═══════════════════════════════════════════════════════════
        # 2. WORKFLOW STATUSES
        # ═══════════════════════════════════════════════════════════

        print("\n── Workflow Statuses ──")

        STATUS_DEFS = [
            {"code": "DRAFT", "name": "Draft", "is_initial": True, "is_terminal": False, "sequence": 1},
            {"code": "SUBMITTED", "name": "Submitted", "is_initial": False, "is_terminal": False, "sequence": 2},
            {"code": "L1_PENDING", "name": "L1 Approval Pending", "is_initial": False, "is_terminal": False, "sequence": 3},
            {"code": "L2_PENDING", "name": "L2 Approval Pending", "is_initial": False, "is_terminal": False, "sequence": 4},
            {"code": "APPROVED", "name": "Approved", "is_initial": False, "is_terminal": True, "sequence": 5},
            {"code": "REJECTED", "name": "Rejected", "is_initial": False, "is_terminal": True, "sequence": 6},
            {"code": "CANCELLED", "name": "Cancelled", "is_initial": False, "is_terminal": True, "sequence": 7},
            {"code": "CLOSED", "name": "Closed", "is_initial": False, "is_terminal": True, "sequence": 8},
        ]

        status_map: dict[str, str] = {}  # code → id

        for s_def in STATUS_DEFS:
            existing_s = await session.execute(
                select(WorkflowStatusModel).where(
                    WorkflowStatusModel.workflow_definition_id == def_id,
                    WorkflowStatusModel.code == s_def["code"],
                )
            )
            status = existing_s.scalar_one_or_none()

            if status:
                status_map[s_def["code"]] = str(status.id)
                print(f"  [skip] Status '{s_def['code']}' already exists")
            else:
                status = WorkflowStatusModel(
                    id=uuid4(),
                    workflow_definition_id=def_id,
                    code=s_def["code"],
                    name=s_def["name"],
                    is_initial=s_def["is_initial"],
                    is_terminal=s_def["is_terminal"],
                    sequence=s_def["sequence"],
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(status)
                status_map[s_def["code"]] = str(status.id)
                print(f"  [new]  Status '{s_def['code']}' created")

        await session.flush()

        # ═══════════════════════════════════════════════════════════
        # 3. WORKFLOW TRANSITIONS (State Machine Rules)
        # ═══════════════════════════════════════════════════════════

        print("\n── Workflow Transitions ──")

        TRANSITIONS = [
            # From DRAFT
            {"from": "DRAFT", "to": "SUBMITTED", "action": "SUBMIT", "comment": False},
            {"from": "DRAFT", "to": "CANCELLED", "action": "CANCEL", "comment": False},

            # From SUBMITTED
            {"from": "SUBMITTED", "to": "L1_PENDING", "action": "APPROVE", "comment": False},
            {"from": "SUBMITTED", "to": "REJECTED", "action": "REJECT", "comment": True},
            {"from": "SUBMITTED", "to": "CANCELLED", "action": "CANCEL", "comment": False},

            # From L1_PENDING
            {"from": "L1_PENDING", "to": "L2_PENDING", "action": "APPROVE", "comment": False},
            {"from": "L1_PENDING", "to": "REJECTED", "action": "REJECT", "comment": True},
            {"from": "L1_PENDING", "to": "SUBMITTED", "action": "REFER_BACK", "comment": True},

            # From L2_PENDING
            {"from": "L2_PENDING", "to": "APPROVED", "action": "APPROVE", "comment": False},
            {"from": "L2_PENDING", "to": "REJECTED", "action": "REJECT", "comment": True},
            {"from": "L2_PENDING", "to": "L1_PENDING", "action": "REFER_BACK", "comment": True},
            {"from": "L2_PENDING", "to": "CLOSED", "action": "CLOSE", "comment": True},
        ]

        for t_def in TRANSITIONS:
            from_id = status_map[t_def["from"]]
            to_id = status_map[t_def["to"]]

            existing_t = await session.execute(
                select(WorkflowTransitionModel).where(
                    WorkflowTransitionModel.workflow_definition_id == def_id,
                    WorkflowTransitionModel.from_status_id == from_id,
                    WorkflowTransitionModel.to_status_id == to_id,
                    WorkflowTransitionModel.action_code == t_def["action"],
                )
            )
            if existing_t.scalar_one_or_none():
                print(f"  [skip] {t_def['from']} + {t_def['action']} → {t_def['to']}")
            else:
                transition = WorkflowTransitionModel(
                    id=uuid4(),
                    workflow_definition_id=def_id,
                    from_status_id=from_id,
                    to_status_id=to_id,
                    action_code=t_def["action"],
                    requires_comment=t_def["comment"],
                    auto_execute=False,
                    priority=0,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(transition)
                print(f"  [new]  {t_def['from']} + {t_def['action']} → {t_def['to']}")

        await session.flush()

        # ═══════════════════════════════════════════════════════════
        # 4. WORKFLOW ACTIONS
        # ═══════════════════════════════════════════════════════════

        print("\n── Workflow Actions ──")

        ACTIONS = [
            {"code": "SUBMIT", "name": "Submit", "type": "SUBMIT"},
            {"code": "APPROVE", "name": "Approve", "type": "APPROVE"},
            {"code": "REJECT", "name": "Reject", "type": "REJECT"},
            {"code": "REFER_BACK", "name": "Refer Back", "type": "REFER_BACK"},
            {"code": "CANCEL", "name": "Cancel", "type": "CANCEL"},
            {"code": "CLOSE", "name": "Close", "type": "CLOSE"},
        ]

        for a_def in ACTIONS:
            existing_a = await session.execute(
                select(WorkflowActionModel).where(
                    WorkflowActionModel.workflow_definition_id == def_id,
                    WorkflowActionModel.code == a_def["code"],
                )
            )
            if existing_a.scalar_one_or_none():
                print(f"  [skip] Action '{a_def['code']}'")
            else:
                action = WorkflowActionModel(
                    id=uuid4(),
                    workflow_definition_id=def_id,
                    code=a_def["code"],
                    name=a_def["name"],
                    action_type=a_def["type"],
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(action)
                print(f"  [new]  Action '{a_def['code']}'")

        await session.flush()

        # ═══════════════════════════════════════════════════════════
        # 5. APPROVAL MATRIX — Amount Based
        # ═══════════════════════════════════════════════════════════

        print("\n── Approval Matrix (Amount < 500000) ──")

        existing_m1 = await session.execute(
            select(ApprovalMatrixModel).where(ApprovalMatrixModel.code == "COMMISSION_LOW_AMOUNT")
        )
        matrix1 = existing_m1.scalar_one_or_none()

        if matrix1:
            print("  [skip] Matrix 'COMMISSION_LOW_AMOUNT' already exists")
        else:
            matrix1 = ApprovalMatrixModel(
                id=uuid4(),
                code="COMMISSION_LOW_AMOUNT",
                name="Commission < 5L — L1 Manager Only",
                entity_type="commission_claim",
                priority=1,
                is_active=True,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(matrix1)
            await session.flush()

            # Rule: amount < 500000
            rule1 = ApprovalRuleModel(
                id=uuid4(),
                matrix_id=str(matrix1.id),
                field="amount",
                operator="LT",
                value="500000",
                data_type="NUMBER",
                logical_group="default",
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(rule1)

            # Assignment: L1 Manager (role-based)
            assign1 = ApprovalAssignmentModel(
                id=uuid4(),
                matrix_id=str(matrix1.id),
                assignment_type="ROLE",
                role_id=None,  # Would be manager role UUID in production
                user_id=None,
                level=1,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(assign1)
            print("  [new]  Matrix 'COMMISSION_LOW_AMOUNT' with 1 rule, 1 level")

        # ─── Matrix 2: Amount >= 500000 ───

        print("\n── Approval Matrix (Amount >= 500000) ──")

        existing_m2 = await session.execute(
            select(ApprovalMatrixModel).where(ApprovalMatrixModel.code == "COMMISSION_HIGH_AMOUNT")
        )
        matrix2 = existing_m2.scalar_one_or_none()

        if matrix2:
            print("  [skip] Matrix 'COMMISSION_HIGH_AMOUNT' already exists")
        else:
            matrix2 = ApprovalMatrixModel(
                id=uuid4(),
                code="COMMISSION_HIGH_AMOUNT",
                name="Commission >= 5L — L1 Manager + Finance Head",
                entity_type="commission_claim",
                priority=2,
                is_active=True,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(matrix2)
            await session.flush()

            # Rule: amount >= 500000
            rule2 = ApprovalRuleModel(
                id=uuid4(),
                matrix_id=str(matrix2.id),
                field="amount",
                operator="GTE",
                value="500000",
                data_type="NUMBER",
                logical_group="default",
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(rule2)

            # Assignment L1: Manager
            assign2a = ApprovalAssignmentModel(
                id=uuid4(),
                matrix_id=str(matrix2.id),
                assignment_type="ROLE",
                role_id=None,
                user_id=None,
                level=1,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(assign2a)

            # Assignment L2: Finance Head
            assign2b = ApprovalAssignmentModel(
                id=uuid4(),
                matrix_id=str(matrix2.id),
                assignment_type="ROLE",
                role_id=None,
                user_id=None,
                level=2,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(assign2b)
            print("  [new]  Matrix 'COMMISSION_HIGH_AMOUNT' with 1 rule, 2 levels")

        # ─── Matrix 3: Company = Emcure → CFO required ───

        print("\n── Approval Matrix (Company = Emcure) ──")

        existing_m3 = await session.execute(
            select(ApprovalMatrixModel).where(ApprovalMatrixModel.code == "COMMISSION_EMCURE_COMPANY")
        )
        matrix3 = existing_m3.scalar_one_or_none()

        if matrix3:
            print("  [skip] Matrix 'COMMISSION_EMCURE_COMPANY' already exists")
        else:
            matrix3 = ApprovalMatrixModel(
                id=uuid4(),
                code="COMMISSION_EMCURE_COMPANY",
                name="Emcure Company — CFO Approval Required",
                entity_type="commission_claim",
                priority=3,
                is_active=True,
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(matrix3)
            await session.flush()

            # Rule: company = Emcure AND amount >= 1000000
            rule3a = ApprovalRuleModel(
                id=uuid4(),
                matrix_id=str(matrix3.id),
                field="company",
                operator="EQ",
                value="Emcure",
                data_type="STRING",
                logical_group="default",
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(rule3a)

            rule3b = ApprovalRuleModel(
                id=uuid4(),
                matrix_id=str(matrix3.id),
                field="amount",
                operator="GTE",
                value="1000000",
                data_type="NUMBER",
                logical_group="default",
                created_by="seed_script",
                modified_by="seed_script",
            )
            session.add(rule3b)

            # Assignment L1: Manager, L2: Finance Head, L3: CFO
            for level in [1, 2, 3]:
                assign = ApprovalAssignmentModel(
                    id=uuid4(),
                    matrix_id=str(matrix3.id),
                    assignment_type="ROLE",
                    role_id=None,
                    user_id=None,
                    level=level,
                    created_by="seed_script",
                    modified_by="seed_script",
                )
                session.add(assign)
            print("  [new]  Matrix 'COMMISSION_EMCURE_COMPANY' with 2 rules, 3 levels")

        await session.commit()
        print("\n✓ Workflow seed complete.")
        print("\nSummary:")
        print("  • 1 Workflow Definition: COMMISSION_CLAIM")
        print("  • 8 Statuses: DRAFT → SUBMITTED → L1_PENDING → L2_PENDING → APPROVED/REJECTED/CANCELLED/CLOSED")
        print("  • 12 Transitions (state machine rules)")
        print("  • 6 Actions: SUBMIT, APPROVE, REJECT, REFER_BACK, CANCEL, CLOSE")
        print("  • 3 Approval Matrices:")
        print("      - COMMISSION_LOW_AMOUNT: amount < 5L → 1 level")
        print("      - COMMISSION_HIGH_AMOUNT: amount >= 5L → 2 levels")
        print("      - COMMISSION_EMCURE_COMPANY: company=Emcure & amount >= 10L → 3 levels")


if __name__ == "__main__":
    print("Seeding Workflow Engine — Commission Claim Example...")
    asyncio.run(seed())
