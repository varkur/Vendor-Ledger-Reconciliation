"""Commission Claim Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClaimCreate(BaseModel):
    employee_name: str = Field(..., min_length=2, max_length=255)
    amount: float = Field(..., gt=0)
    company: str = Field(..., min_length=2, max_length=100)
    department: str = Field(default="")
    region: str = Field(default="")
    description: str = Field(default="")


class ClaimResponse(BaseModel):
    id: UUID
    claim_number: str
    employee_id: UUID
    employee_name: str
    amount: float
    company: str
    department: str
    region: str
    description: str
    status: str
    workflow_instance_id: UUID | None
    created_by: str
    created_date: datetime

    model_config = {"from_attributes": True}


class ClaimListResponse(BaseModel):
    claims: list[ClaimResponse]
    total: int
