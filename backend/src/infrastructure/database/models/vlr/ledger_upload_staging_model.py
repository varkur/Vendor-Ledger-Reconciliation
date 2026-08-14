"""
Staging area for consolidated multi-vendor ledger uploads awaiting user
confirmation.

When a company ledger covering many vendors (PAN-per-row) is uploaded
WITHOUT the user manually selecting vendors first, we can't create the
ReconciliationRequest yet — some PANs in the file might not exist in the
vendor master. So the upload is first "previewed": parsed, matched against
the vendor master, and staged here (raw bytes + intended request settings)
while the caller decides whether to proceed with only the matched vendors
or to fix the vendor master first.

Nothing is created in vlr_reconciliation_requests / vlr_reconciliation_cases
until the user explicitly confirms. If they choose to "fix masters first",
the frontend simply discards the staging row (or lets it expire) — no
partial request is ever left behind.
"""

from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class LedgerUploadStagingModel(BaseModel):
    """A pending consolidated ledger upload, not yet confirmed into a request."""

    __tablename__ = "vlr_ledger_upload_staging"

    company_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(150), nullable=False, default="application/octet-stream"
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Serialized RequestCreateDTO fields (everything except vendor_ids, which
    # is only known once we've matched PANs against the vendor master).
    request_params: Mapped[dict] = mapped_column(JSON, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
