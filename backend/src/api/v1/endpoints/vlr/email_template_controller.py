"""
Email Template API endpoints.
Manages reusable email templates for ledger request workflows.

Routes:
- GET    /api/v1/vlr/email-templates              — List all templates (paginated)
- POST   /api/v1/vlr/email-templates              — Create a template
- GET    /api/v1/vlr/email-templates/{id}         — Get template by ID
- PUT    /api/v1/vlr/email-templates/{id}         — Update a template
- DELETE /api/v1/vlr/email-templates/{id}         — Delete a template
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.repositories.vlr.setting_repository_impl import SettingRepositoryImpl
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.permission_manager import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vlr/email-templates", tags=["VLR - Email Templates"])

GLOBAL_COMPANY_CODE = "__global__"


# Schemas

class AttachmentConfig(BaseModel):
    include_pdf_ledger: bool = False
    include_excel_statement: bool = False
    include_custom_attachments: bool = False
    custom_attachment_note: str = ""


class EmailTemplateResponse(BaseModel):
    id: str
    name: str
    subject: str
    body: str
    category: str = "general"  # general, ledger_request, reminder, escalation
    include_portal_link: bool = True
    include_letterhead: bool = False
    attachments: AttachmentConfig = AttachmentConfig()
    placeholders_used: list[str] = []
    created_by: str = "Admin"
    is_default: bool = False


class EmailTemplateListResponse(BaseModel):
    items: list[EmailTemplateResponse]
    total: int
    page: int
    page_size: int


class CreateEmailTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    category: str = "general"
    include_portal_link: bool = True
    include_letterhead: bool = False
    attachments: AttachmentConfig = AttachmentConfig()


class UpdateEmailTemplateRequest(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    include_portal_link: Optional[bool] = None
    include_letterhead: Optional[bool] = None
    attachments: Optional[AttachmentConfig] = None


# Helpers

def _storage_key(company_code: str) -> str:
    code = company_code if company_code else GLOBAL_COMPANY_CODE
    return f"email_templates.{code}"


# Available placeholders for reference
AVAILABLE_PLACEHOLDERS = [
    "{{vendor_name}}", "{{vendor_code}}", "{{company_name}}", "{{portal_link}}",
    "{{period_start}}", "{{period_end}}", "{{due_date}}", "{{contact_person}}",
    "{{sender_name}}", "{{sender_email}}", "{{case_id}}", "{{fiscal_year}}",
    "{{reminder_count}}", "{{branch_name}}", "{{remarks}}",
]


def _extract_placeholders(text: str) -> list[str]:
    """Extract {{placeholder}} patterns from text."""
    return list(set(re.findall(r'\{\{(\w+)\}\}', text)))


# Category -> heading shown at the top of the rendered email (the red "Vendor
# Ledger Reconciliation Request" banner in the reference format). Templates
# store plain-text bodies (rendered through the same Jinja2 engine as the
# preview endpoint), and this heading is layered on by build_email_html so
# every template in a category keeps a consistent, recognizable look without
# each template author needing to hand-write HTML.
CATEGORY_EMAIL_HEADINGS: dict[str, str] = {
    "ledger_request": "Vendor Ledger Reconciliation Request",
    "reminder": "Ledger Confirmation Reminder",
    "escalation": "Escalation - Overdue Response",
    "general": "Notification",
}


async def get_template_for_category(
    repo: SettingRepositoryImpl,
    company_code: str,
    category: str,
    template_id: str | None = None,
) -> dict | None:
    """
    Resolve which stored template to use for a given category.

    If `template_id` is given, returns that exact template (regardless of
    category) when found. Otherwise returns the entity's default template
    for `category` (is_default=True), falling back to the first template of
    that category if none is marked default. Returns None if no template of
    that category exists at all.
    """
    templates = await _load_templates(repo, company_code)
    if template_id:
        match = next((t for t in templates if t["id"] == template_id), None)
        if match:
            return match
    same_category = [t for t in templates if t.get("category") == category]
    if not same_category:
        return None
    default = next((t for t in same_category if t.get("is_default")), None)
    return default or same_category[0]


def render_email_template(template: dict, context: dict) -> tuple[str, str]:
    """
    Render a stored template's subject + body with `context` via Jinja2, and
    wrap the body in the standard HTML shell (red heading matching the
    template's category, portal-link call-to-action button when
    `include_portal_link` is set on the template, letterhead-style
    margins/typography). Returns (rendered_subject, rendered_html_body).

    This is the single place that turns a plain-text, placeholder-driven
    template into the actual outbound email HTML, so every category (ledger
    request, reminder, escalation) — including any NEW template a user
    creates — renders consistently instead of each call site hand-building
    its own HTML string.
    """
    from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError

    env = Environment(
        loader=BaseLoader(),
        variable_start_string="{{",
        variable_end_string="}}",
        autoescape=False,
    )

    try:
        rendered_subject = env.from_string(template.get("subject", "")).render(**context)
        rendered_body = env.from_string(template.get("body", "")).render(**context)
    except (TemplateSyntaxError, UndefinedError):
        # A malformed/edited template must never crash email sending —
        # fall back to the raw (unrendered) text rather than losing the
        # email entirely.
        rendered_subject = template.get("subject", "")
        rendered_body = template.get("body", "")

    # Collapse 3+ consecutive blank lines (e.g. an empty {{remarks}} leaving
    # a gap) down to a single paragraph break before converting to HTML.
    rendered_body = re.sub(r"\n{3,}", "\n\n", rendered_body.strip())

    def _linkify(text: str) -> str:
        """Turn bare http(s) URLs (e.g. a rendered {{portal_link}}) into
        clickable anchors so templates that embed the link inline still
        produce a real link, not just plain text."""
        return re.sub(
            r"(https?://[^\s<]+)",
            r'<a href="\1">\1</a>',
            text,
        )

    body_html_paragraphs = "".join(
        f"<p>{_linkify(para.replace(chr(10), '<br/>'))}</p>"
        for para in rendered_body.split("\n\n")
        if para.strip()
    )

    heading = CATEGORY_EMAIL_HEADINGS.get(template.get("category", ""), "Notification")

    # Only auto-append the button + raw-link footer when the template body
    # doesn't already reference {{portal_link}} inline (e.g. the reminder/
    # escalation defaults write "...convenience:\n{{portal_link}}" directly)
    # — otherwise the link would appear twice.
    portal_section = ""
    portal_url = context.get("portal_link", "")
    body_references_portal_link = "{{portal_link}}" in (template.get("body") or "")
    if template.get("include_portal_link", True) and portal_url and not body_references_portal_link:
        portal_section = f"""
                <p style="text-align: center; margin: 30px 0;">
                    <a href="{portal_url}"
                       style="background-color: #C41E3A; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Upload Statement
                    </a>
                </p>
                <p style="font-size: 12px; color: #666;">
                    Portal Link: <a href="{portal_url}">{portal_url}</a>
                </p>"""

    rendered_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #C41E3A;">{heading}</h2>
                {body_html_paragraphs}{portal_section}
            </div>
        </body>
        </html>
        """

    return rendered_subject, rendered_html


# Default templates
DEFAULT_TEMPLATES: list[dict] = [
    {
        "id": "tpl-ledger-request",
        "name": "Ledger Request - Standard",
        "subject": "Ledger Reconciliation Request - {{period_start}} to {{period_end}}",
        "body": (
            "Dear Sir/Madam,\n\n"
            "You have been invited to participate in a ledger reconciliation by "
            "{{company_name}}.\n\n"
            "Vendor: {{vendor_name}} ({{vendor_code}})\n"
            "Reconciliation Period: {{period_start}} to {{period_end}}\n\n"
            "{{remarks}}\n\n"
            "Please click the link below to access the portal and upload your "
            "ledger statement:\n\n"
            "This link is valid for 90 days. If you have any questions, please "
            "contact the reconciliation team."
        ),
        "category": "ledger_request",
        "include_portal_link": True,
        "include_letterhead": True,
        "attachments": {
            "include_pdf_ledger": True,
            "include_excel_statement": False,
            "include_custom_attachments": False,
            "custom_attachment_note": "",
        },
        "created_by": "System",
        "is_default": True,
    },
    {
        "id": "tpl-reminder-1",
        "name": "Reminder - First Follow-up",
        "subject": "Reminder {{reminder_count}}: Ledger Confirmation Pending - {{company_name}}",
        "body": (
            "Dear {{contact_person}},\n\n"
            "This is a gentle reminder that we have not received your response to our "
            "ledger confirmation request for {{company_name}} ({{period_start}} to {{period_end}}).\n\n"
            "Please respond at your earliest convenience:\n{{portal_link}}\n\n"
            "Due date: {{due_date}}\n\n"
            "Regards,\n{{sender_name}}\n{{company_name}}"
        ),
        "category": "reminder",
        "include_portal_link": True,
        "include_letterhead": False,
        "attachments": {
            "include_pdf_ledger": False,
            "include_excel_statement": False,
            "include_custom_attachments": False,
            "custom_attachment_note": "",
        },
        "created_by": "System",
        "is_default": True,
    },
    {
        "id": "tpl-escalation",
        "name": "Escalation - Overdue Response",
        "subject": "URGENT: Ledger Confirmation Overdue - {{company_name}} - {{vendor_name}}",
        "body": (
            "Dear {{contact_person}},\n\n"
            "Despite multiple reminders, we have not received your confirmation "
            "for the ledger balance with {{company_name}}.\n\n"
            "Period: {{period_start}} to {{period_end}}\n"
            "Due date: {{due_date}} (OVERDUE)\n\n"
            "Please respond immediately:\n{{portal_link}}\n\n"
            "This matter will be escalated if no response is received within 48 hours.\n\n"
            "Regards,\n{{sender_name}}\n{{company_name}}"
        ),
        "category": "escalation",
        "include_portal_link": True,
        "include_letterhead": True,
        "attachments": {
            "include_pdf_ledger": True,
            "include_excel_statement": True,
            "include_custom_attachments": False,
            "custom_attachment_note": "",
        },
        "created_by": "System",
        "is_default": True,
    },
]


def _get_setting_repository(session: AsyncSession = Depends(get_db_session)) -> SettingRepositoryImpl:
    return SettingRepositoryImpl(session)


async def _load_templates(repo: SettingRepositoryImpl, company_code: str) -> list[dict]:
    key = _storage_key(company_code)
    setting = await repo.get_by_key(GLOBAL_COMPANY_CODE, key)
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            pass
    return [t.copy() for t in DEFAULT_TEMPLATES]


async def _save_templates(
    repo: SettingRepositoryImpl,
    company_code: str,
    templates: list[dict],
    user: str = "system",
) -> None:
    key = _storage_key(company_code)
    await repo.upsert(
        GLOBAL_COMPANY_CODE,
        key,
        json.dumps(templates),
        value_type="json",
        description="Email templates",
        modified_by=user,
    )


# Endpoints

@router.get(
    "",
    response_model=EmailTemplateListResponse,
    summary="List email templates",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def list_templates(
    company_code: str = Query(default="", description="Company code"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    search: Optional[str] = Query(default=None, description="Search by name"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> EmailTemplateListResponse:
    templates = await _load_templates(repo, company_code)

    if category:
        templates = [t for t in templates if t.get("category") == category]
    if search:
        s = search.lower()
        templates = [
            t for t in templates
            if s in t.get("name", "").lower() or s in t.get("subject", "").lower()
        ]

    total = len(templates)
    start = (page - 1) * page_size
    page_items = templates[start:start + page_size]

    items = []
    for t in page_items:
        placeholders = _extract_placeholders(t.get("subject", "") + " " + t.get("body", ""))
        items.append(EmailTemplateResponse(
            **{k: v for k, v in t.items() if k != "placeholders_used"},
            placeholders_used=placeholders,
        ))

    return EmailTemplateListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post(
    "",
    response_model=EmailTemplateResponse,
    summary="Create email template",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    request: CreateEmailTemplateRequest,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> EmailTemplateResponse:
    templates = await _load_templates(repo, company_code)

    new_tpl: dict = {
        "id": f"tpl-{uuid.uuid4().hex[:8]}",
        "name": request.name,
        "subject": request.subject,
        "body": request.body,
        "category": request.category,
        "include_portal_link": request.include_portal_link,
        "include_letterhead": request.include_letterhead,
        "attachments": request.attachments.model_dump(),
        "created_by": current_user.username or "Admin",
        "is_default": False,
    }

    templates.append(new_tpl)
    await _save_templates(repo, company_code, templates, user=current_user.username or "system")

    placeholders = _extract_placeholders(new_tpl["subject"] + " " + new_tpl["body"])
    return EmailTemplateResponse(**new_tpl, placeholders_used=placeholders)


@router.get(
    "/{template_id}",
    response_model=EmailTemplateResponse,
    summary="Get template by ID",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_template(
    template_id: str,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> EmailTemplateResponse:
    templates = await _load_templates(repo, company_code)
    for t in templates:
        if t["id"] == template_id:
            placeholders = _extract_placeholders(
                t.get("subject", "") + " " + t.get("body", "")
            )
            return EmailTemplateResponse(
                **{k: v for k, v in t.items() if k != "placeholders_used"},
                placeholders_used=placeholders,
            )
    raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")


@router.put(
    "/{template_id}",
    response_model=EmailTemplateResponse,
    summary="Update email template",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def update_template(
    template_id: str,
    request: UpdateEmailTemplateRequest,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> EmailTemplateResponse:
    templates = await _load_templates(repo, company_code)

    for t in templates:
        if t["id"] == template_id:
            if request.name is not None:
                t["name"] = request.name
            if request.subject is not None:
                t["subject"] = request.subject
            if request.body is not None:
                t["body"] = request.body
            if request.category is not None:
                t["category"] = request.category
            if request.include_portal_link is not None:
                t["include_portal_link"] = request.include_portal_link
            if request.include_letterhead is not None:
                t["include_letterhead"] = request.include_letterhead
            if request.attachments is not None:
                t["attachments"] = request.attachments.model_dump()

            await _save_templates(
                repo, company_code, templates, user=current_user.username or "system"
            )
            placeholders = _extract_placeholders(
                t.get("subject", "") + " " + t.get("body", "")
            )
            return EmailTemplateResponse(
                **{k: v for k, v in t.items() if k != "placeholders_used"},
                placeholders_used=placeholders,
            )

    raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete email template",
    dependencies=[Depends(require_permission("vlr.settings.write"))],
)
async def delete_template(
    template_id: str,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> None:
    templates = await _load_templates(repo, company_code)
    original_len = len(templates)
    templates = [t for t in templates if t["id"] != template_id]

    if len(templates) == original_len:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")

    await _save_templates(repo, company_code, templates, user=current_user.username or "system")


@router.get(
    "/{template_id}/preview",
    response_model=dict,
    summary="Preview rendered email template with sample data",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def preview_template(
    template_id: str,
    company_code: str = Query(default="", description="Company code"),
    current_user: User = Depends(get_current_active_user),
    repo: SettingRepositoryImpl = Depends(_get_setting_repository),
) -> dict:
    """
    GET /api/v1/vlr/email-templates/{id}/preview

    Renders the email template body using Jinja2 with sample placeholder data.
    Returns the rendered HTML string for previewing in the frontend.

    Requirements: 9
    """
    from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError

    templates = await _load_templates(repo, company_code)

    template_data = None
    for t in templates:
        if t["id"] == template_id:
            template_data = t
            break

    if template_data is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")

    # Sample data for rendering preview
    sample_data = {
        "vendor_name": "Acme Supplies Pvt Ltd",
        "vendor_code": "V-001234",
        "company_name": "Your Company Ltd",
        "portal_link": "https://portal.example.com/access/sample-token",
        "period_start": "01-Apr-2024",
        "period_end": "31-Mar-2025",
        "due_date": "15-May-2025",
        "contact_person": "John Smith",
        "sender_name": current_user.username or "Finance Team",
        "sender_email": "finance@company.com",
        "case_id": "CASE-2025-0001",
        "fiscal_year": "2024-25",
        "reminder_count": "1",
        "branch_name": "Head Office",
        "remarks": "",
    }

    # Render subject
    subject_template_str = template_data.get("subject", "")
    body_template_str = template_data.get("body", "")

    try:
        env = Environment(
            loader=BaseLoader(),
            variable_start_string="{{",
            variable_end_string="}}",
            autoescape=False,
        )

        subject_tpl = env.from_string(subject_template_str)
        rendered_subject = subject_tpl.render(**sample_data)

        body_tpl = env.from_string(body_template_str)
        rendered_body = body_tpl.render(**sample_data)
    except (TemplateSyntaxError, UndefinedError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template rendering error: {str(e)}",
        )

    # Convert newlines to HTML breaks for display
    rendered_html = rendered_body.replace("\n", "<br/>")

    return {
        "html": rendered_html,
        "subject": rendered_subject,
        "template_id": template_id,
        "template_name": template_data.get("name", ""),
    }


@router.get(
    "/meta/placeholders",
    response_model=list[str],
    summary="Get available placeholders",
    dependencies=[Depends(require_permission("vlr.settings.read"))],
)
async def get_placeholders(
    current_user: User = Depends(get_current_active_user),
) -> list[str]:
    return AVAILABLE_PLACEHOLDERS
