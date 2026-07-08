"""
VLR Repository Interfaces (Ports).

Abstract repository contracts for the Vendor Ledger Reconciliation module.
The domain layer owns these interfaces; infrastructure implements them.
"""

from src.domain.repositories.vlr.vendor_repository import IVendorRepository
from src.domain.repositories.vlr.request_repository import IRequestRepository
from src.domain.repositories.vlr.case_repository import ICaseRepository
from src.domain.repositories.vlr.ledger_entry_repository import ILedgerEntryRepository
from src.domain.repositories.vlr.match_result_repository import IMatchResultRepository
from src.domain.repositories.vlr.exception_repository import IExceptionRepository
from src.domain.repositories.vlr.approval_repository import IApprovalRepository
from src.domain.repositories.vlr.notification_repository import INotificationRepository
from src.domain.repositories.vlr.setting_repository import ISettingRepository
from src.domain.repositories.vlr.automation_rule_repository import IAutomationRuleRepository
from src.domain.repositories.vlr.column_mapping_template_repository import IColumnMappingTemplateRepository
from src.domain.repositories.vlr.recovery_repository import IRecoveryRepository

__all__ = [
    "IVendorRepository",
    "IRequestRepository",
    "ICaseRepository",
    "ILedgerEntryRepository",
    "IMatchResultRepository",
    "IExceptionRepository",
    "IApprovalRepository",
    "INotificationRepository",
    "ISettingRepository",
    "IAutomationRuleRepository",
    "IColumnMappingTemplateRepository",
    "IRecoveryRepository",
]
