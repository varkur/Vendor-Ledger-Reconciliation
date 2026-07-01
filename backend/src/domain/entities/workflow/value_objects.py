"""Value objects for the workflow domain."""
from enum import StrEnum


class ActionType(StrEnum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REFER_BACK = "REFER_BACK"
    CANCEL = "CANCEL"
    CLOSE = "CLOSE"
    ESCALATE = "ESCALATE"


class StepType(StrEnum):
    APPROVAL = "APPROVAL"
    REVIEW = "REVIEW"
    NOTIFICATION = "NOTIFICATION"
    AUTO = "AUTO"


class AssignmentType(StrEnum):
    ROLE = "ROLE"
    USER = "USER"
    MATRIX = "MATRIX"
    EXPRESSION = "EXPRESSION"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"


class StateType(StrEnum):
    INITIAL = "INITIAL"
    NORMAL = "NORMAL"
    TERMINAL = "TERMINAL"
