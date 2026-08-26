"""
Unit tests for email template rendering + resolution.

Covers the fix for outbound vendor emails hardcoding "Emcure Pharmaceuticals
Limited" regardless of which company entity a request was actually created
under, and for the Email Templates screen being disconnected from the real
outbound invite email (a template could be created/edited but was never
actually used to render anything sent).
"""

from src.api.v1.endpoints.vlr.email_template_controller import (
    DEFAULT_TEMPLATES,
    get_template_for_category,
    render_email_template,
)


class FakeSetting:
    def __init__(self, value: str):
        self.value = value


class FakeSettingRepo:
    """Minimal stand-in for SettingRepositoryImpl.get_by_key for these tests."""

    def __init__(self, stored: dict[str, str] | None = None):
        self._stored = stored or {}

    async def get_by_key(self, company_code: str, key: str):
        value = self._stored.get(key)
        return FakeSetting(value) if value is not None else None


class TestRenderEmailTemplate:
    def test_renders_placeholders_and_heading(self):
        template = next(t for t in DEFAULT_TEMPLATES if t["id"] == "tpl-ledger-request")
        subject, html = render_email_template(template, {
            "vendor_name": "Acme Pvt Ltd",
            "vendor_code": "V-001",
            "company_name": "Gennova Biopharmaceuticals Ltd",
            "portal_link": "http://portal.example.com/access/token123",
            "period_start": "01-Apr-2025",
            "period_end": "31-Mar-2026",
            "remarks": "",
        })

        assert "01-Apr-2025 to 31-Mar-2026" in subject
        assert "Gennova Biopharmaceuticals Ltd" in html
        assert "Emcure" not in html
        assert "Acme Pvt Ltd" in html
        assert "V-001" in html
        assert "Vendor Ledger Reconciliation Request" in html

    def test_portal_link_button_and_footer_shown_once_each(self):
        """The auto-appended section shows both a clickable button AND a
        plain-text footer link (matching the original hardcoded template) —
        so the URL legitimately appears twice: once in the button's href,
        once in the footer's href+text. Never a THIRD occurrence, which
        would mean the button/footer got duplicated."""
        template = next(t for t in DEFAULT_TEMPLATES if t["id"] == "tpl-ledger-request")
        _, html = render_email_template(template, {
            "vendor_name": "Acme",
            "vendor_code": "V-1",
            "company_name": "Test Co",
            "portal_link": "http://portal.example.com/access/abc",
            "period_start": "01-Apr-2025",
            "period_end": "31-Mar-2026",
            "remarks": "",
        })
        assert html.count('href="http://portal.example.com/access/abc"') == 2
        assert "Upload Statement" in html
        assert "Portal Link:" in html

    def test_reminder_template_inline_link_not_duplicated_as_button(self):
        template = next(t for t in DEFAULT_TEMPLATES if t["id"] == "tpl-reminder-1")
        _, html = render_email_template(template, {
            "contact_person": "John",
            "company_name": "Test Co",
            "period_start": "01-Apr-2025",
            "period_end": "31-Mar-2026",
            "portal_link": "http://portal.example.com/access/xyz",
            "due_date": "15-May-2025",
            "sender_name": "Finance",
            "reminder_count": "1",
        })
        # The reminder template embeds {{portal_link}} directly in its body
        # (linkified into a single anchor), so the auto-appended
        # button/footer section must be skipped entirely — no "Upload
        # Statement" button should appear for this category.
        assert html.count('href="http://portal.example.com/access/xyz"') == 1
        assert "Upload Statement" not in html

    def test_remarks_placeholder_omitted_when_blank(self):
        template = next(t for t in DEFAULT_TEMPLATES if t["id"] == "tpl-ledger-request")
        _, html = render_email_template(template, {
            "vendor_name": "Acme",
            "vendor_code": "V-1",
            "company_name": "Test Co",
            "portal_link": "http://portal.example.com/access/abc",
            "period_start": "01-Apr-2025",
            "period_end": "31-Mar-2026",
            "remarks": "",
        })
        assert "<p></p>" not in html

    def test_malformed_template_falls_back_without_crashing(self):
        broken = {
            "subject": "Hello {{unclosed",
            "body": "Body {{also unclosed",
            "category": "ledger_request",
            "include_portal_link": True,
        }
        subject, html = render_email_template(broken, {"portal_link": ""})
        assert subject == "Hello {{unclosed"
        assert "also unclosed" in html


class TestGetTemplateForCategory:
    async def test_returns_default_template_for_category(self):
        repo = FakeSettingRepo()  # no stored templates -> falls back to DEFAULT_TEMPLATES
        template = await get_template_for_category(repo, "1000", "ledger_request")
        assert template is not None
        assert template["id"] == "tpl-ledger-request"

    async def test_explicit_template_id_overrides_category_default(self):
        repo = FakeSettingRepo()
        template = await get_template_for_category(
            repo, "1000", "ledger_request", template_id="tpl-reminder-1",
        )
        assert template is not None
        assert template["id"] == "tpl-reminder-1"

    async def test_missing_category_returns_none(self):
        import json
        custom = [{
            "id": "tpl-custom",
            "name": "Custom",
            "subject": "s",
            "body": "b",
            "category": "general",
            "include_portal_link": True,
            "is_default": True,
        }]
        repo = FakeSettingRepo({"email_templates.1000": json.dumps(custom)})
        template = await get_template_for_category(repo, "1000", "ledger_request")
        assert template is None
