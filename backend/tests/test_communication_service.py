"""Unit tests for the Communication Agent.

The pure helpers and the injected-mailer ``send()`` path need no DB or SMTP, so
these run without the full backend stack. Async methods are driven with
``asyncio.run`` to avoid a pytest-asyncio dependency.
"""
import asyncio

import pytest

from app.services.communication_service import (
    TEMPLATES,
    CommunicationService,
    dedupe_emails,
    list_segments,
    list_templates,
    prepare_message,
    render_template,
    resolve_message_fields,
)


class FakeMailer:
    """Records send calls instead of hitting SMTP."""

    def __init__(self):
        self.calls = []

    async def __call__(self, *, subject, recipients, body):
        self.calls.append({"subject": subject, "recipients": recipients, "body": body})


# --- render_template -------------------------------------------------------- #
def test_render_template_substitutes_known_placeholders():
    assert render_template("Hi {name}, welcome", {"name": "Riya"}) == "Hi Riya, welcome"


def test_render_template_leaves_unknown_placeholders_visible():
    assert render_template("Due {deadline}", {}) == "Due {deadline}"


def test_render_template_handles_empty_and_none():
    assert render_template("", {"a": 1}) == ""
    assert render_template(None) == ""


# --- dedupe_emails ---------------------------------------------------------- #
def test_dedupe_emails_is_case_insensitive_order_preserving_and_filters_invalid():
    recs = [
        {"email": "a@x.com"},
        {"email": "A@x.com"},   # dup of a@x.com (case-insensitive)
        {"email": "bad-no-at"}, # invalid, dropped
        {"email": "b@x.com"},
        {"email": ""},          # empty, dropped
    ]
    assert dedupe_emails(recs) == ["a@x.com", "b@x.com"]


# --- prepare_message -------------------------------------------------------- #
def test_prepare_message_renders_and_collapses_recipients():
    msg = prepare_message(
        subject="Hello {name}",
        body="Body {name}",
        context={"name": "All"},
        recipients=[{"email": "a@x.com"}, {"email": "a@x.com"}],
    )
    assert msg == {"subject": "Hello All", "body": "Body All", "emails": ["a@x.com"]}


# --- resolve_message_fields ------------------------------------------------- #
def test_resolve_message_fields_uses_template_defaults():
    subject, body, segment = resolve_message_fields(
        template_code="kickoff", subject=None, body=None, segment=None
    )
    assert subject == TEMPLATES["kickoff"]["subject"]
    assert body == TEMPLATES["kickoff"]["body"]
    assert segment == "all_students"


def test_resolve_message_fields_lets_explicit_values_override():
    subject, body, segment = resolve_message_fields(
        template_code="kickoff", subject="Custom", body="Custom body", segment="mentors"
    )
    assert subject == "Custom"
    assert segment == "mentors"


# --- registries ------------------------------------------------------------- #
def test_segment_registry_shape():
    segs = list_segments()
    assert any(s["key"] == "all_students" for s in segs)
    assert any(s["key"] == "unassigned_students" for s in segs)
    assert all("label" in s and "requires_team" in s for s in segs)
    # specific_team is the only team-scoped segment
    assert next(s for s in segs if s["key"] == "specific_team")["requires_team"] is True


def test_template_registry_shape():
    tmpls = list_templates()
    assert any(t["code"] == "kickoff" for t in tmpls)
    assert all({"code", "subject", "body", "default_segment"} <= set(t) for t in tmpls)


def test_all_templates_render_with_their_declared_params():
    for code, t in TEMPLATES.items():
        ctx = {p: f"<{p}>" for p in t["params"]}
        out = render_template(t["body"], ctx)
        for p in t["params"]:
            assert f"<{p}>" in out, f"{code}: param {p} not substituted"
            assert "{" + p + "}" not in out, f"{code}: leftover placeholder {p}"


# --- send() orchestration (fake mailer, no DB) ------------------------------ #
def test_send_with_recipients_calls_mailer_with_rendered_message():
    mailer = FakeMailer()
    result = asyncio.run(
        CommunicationService.send(
            None,
            subject="Hi {name}",
            body="Welcome {name}",
            context={"name": "Everyone"},
            recipients=[
                {"name": "A", "email": "a@x.com"},
                {"name": "B", "email": "B@X.com"},
                {"name": "C", "email": "a@x.com"},  # dup
            ],
            mailer=mailer,
        )
    )
    assert result["sent"] == 2
    assert len(mailer.calls) == 1
    assert mailer.calls[0]["subject"] == "Hi Everyone"
    assert mailer.calls[0]["body"] == "Welcome Everyone"
    assert mailer.calls[0]["recipients"] == ["a@x.com", "B@X.com"]


def test_send_with_no_valid_recipients_does_not_call_mailer():
    mailer = FakeMailer()
    result = asyncio.run(
        CommunicationService.send(None, subject="X", body="Y", recipients=[], mailer=mailer)
    )
    assert result["sent"] == 0
    assert mailer.calls == []


def test_send_with_template_code_fills_subject_body_and_renders_context():
    mailer = FakeMailer()
    asyncio.run(
        CommunicationService.send(
            None,
            template_code="team_add_request",
            context={"team_name": "Alpha", "student_name": "Riya Sharma"},
            recipients=[{"name": "Lead", "email": "lead@x.com"}],
            mailer=mailer,
        )
    )
    body = mailer.calls[0]["body"]
    assert "Alpha" in body and "Riya Sharma" in body
    assert "{team_name}" not in body and "{student_name}" not in body


def test_send_requires_recipients_or_db():
    with pytest.raises(ValueError):
        asyncio.run(
            CommunicationService.send(None, subject="x", body="y", segment="all_students")
        )
