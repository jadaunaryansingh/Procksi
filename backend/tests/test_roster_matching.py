"""Unit tests for the pure normalization + comparison primitives."""
from app.validators.roster_matching import (
    RapidFuzzNameComparator,
    canonical_email,
    canonical_student_id,
    id_similarity,
    normalize_name,
)


def test_normalize_name_casefold_accents_punctuation():
    assert normalize_name("  José  D'Souza! ") == "jose d souza"
    assert normalize_name("ROHIT   sharma") == "rohit sharma"
    assert normalize_name(None) == ""


def test_canonical_email_gmail_dots_and_tags_stripped():
    assert canonical_email("Rohit.Sharma+gla@gmail.com") == "rohitsharma@gmail.com"
    assert canonical_email("a.b.c@googlemail.com") == "abc@gmail.com"
    # Non-gmail domains keep dots (institutional addresses).
    assert canonical_email("rohit.sharma@gla.ac.in") == "rohit.sharma@gla.ac.in"


def test_canonical_student_id_strips_separators_and_uppercases():
    assert canonical_student_id("gla-2021/001") == "GLA2021001"
    assert canonical_student_id(" bca_1234 ") == "BCA1234"
    assert canonical_student_id(None) == ""


def test_name_comparator_in_unit_range_and_symmetric():
    cmp = RapidFuzzNameComparator()
    score = cmp.score(normalize_name("Rohith Sharma"), normalize_name("Rohit Sharma"))
    assert 0.0 <= score <= 1.0
    assert score > 0.85  # one-letter typo should score high
    # token order swap absorbed by token-sort
    swapped = cmp.score(normalize_name("Sharma Rohit"), normalize_name("Rohit Sharma"))
    assert swapped > 0.9
    # empty inputs are safe
    assert cmp.score("", "anything") == 0.0


def test_id_similarity_catches_transposition():
    assert id_similarity("BCA1234", "BCA1243") > 0.88
    assert id_similarity("GLA2021001", "ZZ7777") < 0.7
