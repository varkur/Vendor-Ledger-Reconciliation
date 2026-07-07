"""
VLR Repository Implementations (Adapters).

Concrete implementations of VLR repository interfaces using async SQLAlchemy.
All implementations enforce:
- company_code scoping for multi-tenant isolation
- soft-delete filtering (is_deleted=False)
- pagination with default page size of 50
"""

from src.infrastructure.database.repositories.vlr.vendor_repository_impl import VendorRepositoryImpl
from src.infrastructure.database.repositories.vlr.request_repository_impl import RequestRepositoryImpl
from src.infrastructure.database.repositories.vlr.case_repository_impl import CaseRepositoryImpl
from src.infrastructure.database.repositories.vlr.ledger_entry_repository_impl import LedgerEntryRepositoryImpl
from src.infrastructure.database.repositories.vlr.match_result_repository_impl import MatchResultRepositoryImpl
from src.infrastructure.database.repositories.vlr.exception_repository_impl import ExceptionRepositoryImpl
from src.infrastructure.database.repositories.vlr.approval_repository_impl import ApprovalRepositoryImpl
from src.infrastructure.database.repositories.vlr.notification_repository_impl import NotificationRepositoryImpl
from src.infrastructure.database.repositories.vlr.setting_repository_impl import SettingRepositoryImpl
from src.infrastructure.database.repositories.vlr.automation_rule_repository_impl import AutomationRuleRepositoryImpl

__all__ = [
    "VendorRepositoryImpl",
    "RequestRepositoryImpl",
    "CaseRepositoryImpl",
    "LedgerEntryRepositoryImpl",
    "MatchResultRepositoryImpl",
    "ExceptionRepositoryImpl",
    "ApprovalRepositoryImpl",
    "NotificationRepositoryImpl",
    "SettingRepositoryImpl",
    "AutomationRuleRepositoryImpl",
]
