"""Unit tests for the Communication Agent's scheduling helpers (pure, no DB)."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.communication_scheduler import (
    build_sequence,
    effective_segment,
    is_due,
    serialize,
    to_send_kwargs,
    utcnow,
    validate_target,
)

UTC = timezone.utc


# --- is_due ----------------------------------------------------------------- #
def test_is_due_for_past_and_future():
    assert is_due(utcnow() - timedelta(minutes=1)) is True
    assert is_due(utcnow() + timedelta(days=1)) is False


def test_is_due_treats_naive_datetime_as_utc():
    # Naive datetime far in the past must not raise and must be due.
    assert is_due(datetime(2000, 1, 1)) is True


# --- segment resolution ----------------------------------------------------- #
def test_effective_segment_prefers_explicit_then_template_default():
    assert effective_segment("mentors", "kickoff") == "mentors"
    assert effective_segment(None, "kickoff") == "all_students"
    assert effective_segment(None, None) is None


def test_validate_target_accepts_valid_and_rejects_bad():
    assert validate_target(None, "kickoff") == "all_students"
    assert validate_target("mentors", None) == "mentors"
    with pytest.raises(ValueError):
        validate_target(None, None)
    with pytest.raises(ValueError):
        validate_target("not_a_segment", None)
    with pytest.raises(ValueError):
        validate_target(None, "not_a_template")


# --- build_sequence --------------------------------------------------------- #
def test_build_sequence_computes_offsets_and_strips_offset_key():
    base = datetime(2026, 6, 10, 9, 0, tzinfo=UTC)
    steps = [
        {"template_code": "kickoff", "offset_days": 0},
        {"template_code": "team_formation", "offset_days": 3},
    ]
    plans = build_sequence(steps, base=base)
    assert plans[0]["send_at"] == base
    assert plans[1]["send_at"] == base + timedelta(days=3)
    assert plans[0]["template_code"] == "kickoff"
    assert "offset_days" not in plans[0]


def test_build_sequence_defaults_base_to_now():
    plans = build_sequence([{"template_code": "kickoff", "offset_days": 0}])
    assert (utcnow() - plans[0]["send_at"]).total_seconds() < 5


# --- mapping / serialization ------------------------------------------------ #
def test_to_send_kwargs_maps_fields_and_defaults_context():
    sched = SimpleNamespace(
        segment="mentors", template_code=None, subject="S", body="B",
        context=None, team_id=None, semester_id=None,
    )
    kw = to_send_kwargs(sched)
    assert kw["segment"] == "mentors"
    assert kw["subject"] == "S"
    assert kw["context"] == {}


def test_serialize_renders_iso_timestamps():
    sid = uuid.uuid4()
    sched = SimpleNamespace(
        id=sid, segment="mentors", template_code="kickoff", subject="S",
        send_at=datetime(2026, 6, 10, tzinfo=UTC), status="pending",
        sent_at=None, result=None,
    )
    out = serialize(sched)
    assert out["id"] == str(sid)
    assert out["status"] == "pending"
    assert out["send_at"].startswith("2026-06-10")
