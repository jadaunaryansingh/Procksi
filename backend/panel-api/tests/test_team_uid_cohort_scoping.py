"""
Regression guard for the cross-cohort team_uid misattribution bug.

Team numbers / slug suffixes T1..T125 exist in BOTH concurrently-active B.Tech
years. team_uid_map holds one uid per integer (all pointing at the 3rd-yr cohort
for that range), so the old resolve_team_uid(int) sent every 2nd-yr presentation
evaluation / result to the 3rd-yr team. resolve_team_uid must now resolve WITHIN
the supplied semester.
"""

import pytest

from app.cache import clear_all
from app.db_helpers import resolve_team_uid, _semester_team_uid_map


SEM_2ND = "7681fe4a-2nd-year"
SEM_3RD = "c1707ba6-3rd-year"

# uid layout: T5 exists in both cohorts with different uids; the 3rd-yr cohort
# also has a "900-series" drift team whose slug suffix (958) differs from its
# real team_number (184).
TEAMS_VALIDATION = [
    {"id": f"{SEM_2ND}-T5", "uid": "uid-2nd-t5", "team_number": 5, "semester_id": SEM_2ND},
    {"id": f"{SEM_2ND}-T7", "uid": "uid-2nd-t7", "team_number": 7, "semester_id": SEM_2ND},
    {"id": f"{SEM_3RD}-T5", "uid": "uid-3rd-t5", "team_number": 5, "semester_id": SEM_3RD},
    {"id": f"{SEM_3RD}-T7", "uid": "uid-3rd-t7", "team_number": 7, "semester_id": SEM_3RD},
    {"id": f"{SEM_3RD}-T958", "uid": "uid-3rd-t958", "team_number": 184, "semester_id": SEM_3RD},
]

# The legacy cross-cohort map — every low int points at the 3rd-yr cohort,
# exactly as production currently holds it.
TEAM_UID_MAP = [
    {"old_int_id": 5, "uid": "uid-3rd-t5"},
    {"old_int_id": 7, "uid": "uid-3rd-t7"},
]


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        return _Query([r for r in self._rows if r.get(col) == val])

    def in_(self, col, vals):
        vals = set(vals)
        return _Query([r for r in self._rows if r.get(col) in vals])

    def execute(self):
        return type("R", (), {"data": list(self._rows)})()


class FakeClient:
    def __init__(self):
        self._tables = {
            "teams_validation": TEAMS_VALIDATION,
            "team_uid_map": TEAM_UID_MAP,
        }

    def table(self, name):
        return _Query(self._tables.get(name, []))


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_all()
    yield
    clear_all()


def test_semester_map_keys_by_slug_number_and_team_number():
    m = _semester_team_uid_map(FakeClient(), SEM_2ND)
    assert m[f"{SEM_2ND}-T5"] == "uid-2nd-t5"   # exact slug
    assert m[5] == "uid-2nd-t5"                  # slug-suffix number (to_numeric_id)
    assert m[7] == "uid-2nd-t7"


def test_2nd_year_team_resolves_to_2nd_year_uid_not_the_map():
    c = FakeClient()
    # bare number, as slot_service derives it from the schedule slug
    assert resolve_team_uid(c, 5, semester_id=SEM_2ND) == "uid-2nd-t5"
    # full slug, as evaluation.py / results sync pass it
    assert resolve_team_uid(c, f"{SEM_2ND}-T5", semester_id=SEM_2ND) == "uid-2nd-t5"


def test_3rd_year_same_number_resolves_to_3rd_year_uid():
    c = FakeClient()
    assert resolve_team_uid(c, 5, semester_id=SEM_3RD) == "uid-3rd-t5"


def test_900_series_drift_resolves_by_slug_suffix():
    c = FakeClient()
    # schedule slug is "...-T958"; to_numeric_id -> 958; must find the T958 team
    assert resolve_team_uid(c, 958, semester_id=SEM_3RD) == "uid-3rd-t958"
    assert resolve_team_uid(c, f"{SEM_3RD}-T958", semester_id=SEM_3RD) == "uid-3rd-t958"
    # its real team_number still resolves too
    assert resolve_team_uid(c, 184, semester_id=SEM_3RD) == "uid-3rd-t958"


def test_semester_given_but_team_absent_returns_none_never_cross_cohort():
    c = FakeClient()
    # number 999 isn't in the 2nd-yr cohort — must NOT fall through to team_uid_map
    assert resolve_team_uid(c, 999, semester_id=SEM_2ND) is None


def test_no_semester_falls_back_to_legacy_map():
    c = FakeClient()
    # display-only callers with no semester context keep the old behaviour
    assert resolve_team_uid(c, 5) == "uid-3rd-t5"


def test_uuid_passthrough():
    # a real uuid is already canonical — returned as-is, no lookup
    assert (
        resolve_team_uid(FakeClient(), "3f4b1c2d-0000-4000-8000-000000000000")
        == "3f4b1c2d-0000-4000-8000-000000000000"
    )
    assert (
        resolve_team_uid(FakeClient(), "3f4b1c2d-0000-4000-8000-000000000000", semester_id=SEM_2ND)
        == "3f4b1c2d-0000-4000-8000-000000000000"
    )
