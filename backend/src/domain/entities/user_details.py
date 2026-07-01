"""
UserDetails domain entity.
Stores additional employee information from Darwin AD service.
One-to-one relationship with User entity (user.username == employee_id).
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.domain.entities.base_entity import BaseEntity


@dataclass
class UserDetails(BaseEntity):
    """
    UserDetails entity — holds all Darwin AD employee fields.

    Linked to User via user_id (one-to-one).
    """

    user_id: UUID | None = field(default=None)
    employee_id: str = field(default="")
    employee_name: str = field(default="")
    first_name: str = field(default="")
    middle_name: str = field(default="")
    last_name: str = field(default="")
    email: str = field(default="")
    designation_title: str = field(default="")
    department: str = field(default="")
    business_unit: str = field(default="")
    group_company: str = field(default="")
    location: str = field(default="")
    region: str = field(default="")
    zone: str = field(default="")
    grade: str = field(default="")
    office_mobile_no: str = field(default="")
    personal_mobile_no: str = field(default="")
    date_of_joining: str = field(default="")
    reporting_manager: str = field(default="")
    direct_manager_employee_id: str = field(default="")
    direct_manager_name: str = field(default="")
    direct_manager_email: str = field(default="")
    sap_user_id: str = field(default="")
    division_id: str = field(default="")
    territory_id: str = field(default="")
