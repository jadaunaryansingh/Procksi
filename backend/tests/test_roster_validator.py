"""Cascade tests for RosterValidator — one assertion per kickoff scenario."""
import pytest

from app.validators.roster_validator import RosterValidator

EXISTING = [
    {"student_id": "UNI2021001", "name": "Rohit Sharma", "email": "rohit.sharma@example.edu"},
    {"student_id": "UNI2021002", "name": "Anita Verma", "email": "anita.verma@example.edu"},
    {"student_id": "BCA1234", "name": "Suresh Kumar", "email": "suresh.kumar@example.edu"},
]


@pytest.fixture
def validator():
    return RosterValidator()


def run(validator, *rows):
    return validator.validate_batch(list(rows), EXISTING)


def bucket_of(result):
    """Return the single non-empty bucket name for a one-row batch."""
    for name in ("valid", "duplicates", "invalid", "review"):
        if result[name]:
            return name
    return None


def test_clean_new_row_is_valid(validator):
    row = {"student_id": "UNI2021099", "name": "Vikram Rao", "email": "vikram.rao@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "valid"
    assert res["summary"]["valid"] == 1


def test_exact_id_collision_is_duplicate(validator):
    row = {"student_id": "UNI2021001", "name": "Rohit Sharma", "email": "brand.new@example.edu"}
    assert bucket_of(run(validator, row)) == "duplicates"


def test_exact_email_collision_is_duplicate(validator):
    row = {"student_id": "UNI2099999", "name": "Totally Different", "email": "rohit.sharma@example.edu"}
    assert bucket_of(run(validator, row)) == "duplicates"


def test_same_person_different_id_routes_to_review(validator):
    row = {"student_id": "ZZ7777", "name": "Rohit Sharma", "email": "rohit.s2@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "review"
    item = res["review"][0]
    assert item["candidate"]["student_id"] == "UNI2021001"
    assert item["match_type"] == "name"


def test_typo_name_new_id_routes_to_review(validator):
    row = {"student_id": "MNO5555", "name": "Rohith Sharma", "email": "rohith.sharma@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "review"
    assert res["review"][0]["candidate"]["name"] == "Rohit Sharma"


def test_transliteration_variant_routes_to_review(validator):
    row = {"student_id": "PQR6666", "name": "Anitha Verma", "email": "anitha.verma@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "review"
    assert res["review"][0]["candidate"]["student_id"] == "UNI2021002"


def test_same_name_with_typod_roll_number_is_flagged_as_id_near(validator):
    # Same person, transposed roll digits -> caught by NAME match, annotated id_near.
    row = {"student_id": "BCA1243", "name": "Suresh Kumar", "email": "suresh.k2@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "review"
    item = res["review"][0]
    assert item["candidate"]["student_id"] == "BCA1234"
    assert item["match_type"] == "id_near"  # name matched AND roll is 1 edit away


def test_adjacent_roll_number_with_different_person_is_not_flagged(validator):
    # Sequential roll numbers are legitimately 1 edit apart: must NOT false-flag.
    row = {"student_id": "BCA1243", "name": "Pooja Singh", "email": "pooja.singh@example.edu"}
    assert bucket_of(run(validator, row)) == "valid"


def test_malformed_email_is_invalid(validator):
    row = {"student_id": "UNI2030001", "name": "New Person", "email": "not-an-email"}
    res = run(validator, row)
    assert bucket_of(res) == "invalid"
    assert "email" in res["invalid"][0]["reason"].lower()


def test_missing_field_is_invalid(validator):
    row = {"student_id": "UNI2030002", "name": "", "email": "x@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "invalid"
    assert "name" in res["invalid"][0]["reason"].lower()


def test_bad_roll_number_is_invalid(validator):
    row = {"student_id": "A1", "name": "Short Roll", "email": "short.roll@example.edu"}
    res = run(validator, row)
    assert bucket_of(res) == "invalid"
    assert "roll" in res["invalid"][0]["reason"].lower()


def test_within_file_duplicate_detected(validator):
    r1 = {"student_id": "UNI2055001", "name": "Neha Gupta", "email": "neha.gupta@example.edu"}
    r2 = {"student_id": "UNI2055001", "name": "Neha Gupta", "email": "neha.g@example.edu"}
    res = validator.validate_batch([r1, r2], EXISTING)
    assert res["summary"]["valid"] == 1
    assert res["summary"]["duplicates"] == 1


def test_contract_keys_present_and_additive(validator):
    res = run(validator, {"student_id": "UNI2021100", "name": "A B", "email": "a.b@example.edu"})
    # Existing contract preserved; review/summary added.
    for key in ("valid", "duplicates", "invalid", "review", "summary"):
        assert key in res
