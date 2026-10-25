"""Parsing of the free-text teams_validation.domain column.

Two real defects motivated these cases, both observed in live data:

  1. "A, B, & C" split on commas alone left a bare "& C" in the picker.
     Ten such fragments were being offered as selectable domains.
  2. "Artifical Intelligence" was offered alongside the correct spelling.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.domain_catalog import parse_domain_field, collect_domains


class TestAmpersandSplitting:
    def test_oxford_ampersand_does_not_leave_a_fragment(self):
        # The exact shape that produced "& HR Operations" in production.
        got = parse_domain_field("Enterprise IT Operations, Customer Service, & HR Operations")
        assert got == ["Enterprise IT Operations", "Customer Service", "HR Operations"]

    def test_ampersand_without_comma_is_also_a_separator(self):
        got = parse_domain_field("Cloud Native Infrastructure, DevOps & Autonomous Systems")
        assert got == ["Cloud Native Infrastructure", "DevOps", "Autonomous Systems"]

    def test_no_label_begins_with_a_separator(self):
        for raw in [
            "Home Safety, Commercial Kitchens, & Asset Management",
            "Precision Farming, Crop Protection, & Mobile AI",
            "FinTech, Computational Economics & Intelligent Automation",
        ]:
            for label in parse_domain_field(raw):
                assert not label.startswith(("&", ",")), f"fragment from {raw!r}: {label!r}"

    def test_ampersand_inside_a_real_label_is_preserved(self):
        # "Identity & Access Management" is one domain, not two. It is split —
        # accepted cost: splitting is the only way to remove the fragments, and
        # both halves remain meaningful, whereas "& X" never is.
        got = parse_domain_field("Identity & Access Management")
        assert "&" not in " ".join(got)


class TestMisspellings:
    def test_artifical_is_corrected(self):
        assert parse_domain_field("Artifical Intelligence") == ["Artificial Intelligence"]

    def test_correction_applies_within_a_list(self):
        got = parse_domain_field("Artifical Intelligence, Machine Learning, Information Retrieval")
        assert got == ["Artificial Intelligence", "Machine Learning", "Information Retrieval"]

    def test_correct_spelling_is_untouched(self):
        assert parse_domain_field("Artificial Intelligence") == ["Artificial Intelligence"]

    def test_misspelling_collapses_into_one_entry(self):
        rows = [{"domain": "Artifical Intelligence"}, {"domain": "Artificial Intelligence"}]
        assert collect_domains(rows) == ["Artificial Intelligence"]


class TestExistingBehaviourPreserved:
    def test_json_array_still_parses(self):
        assert parse_domain_field('["Software", "Web Development"]') == ["Software", "Web Development"]

    def test_plain_comma_list_still_parses(self):
        assert parse_domain_field("Artificial Intelligence, Computer Vision") == [
            "Artificial Intelligence", "Computer Vision"]

    def test_single_label_unchanged(self):
        assert parse_domain_field("Cybersecurity") == ["Cybersecurity"]

    def test_empty_and_none(self):
        assert parse_domain_field(None) == []
        assert parse_domain_field("") == []

    def test_placeholders_still_dropped(self):
        assert collect_domains([{"domain": "General"}, {"domain": "N/A"}]) == []


class TestJsonArrayElementsAreAlsoSplit:
    """A JSON array element can itself hold a separated list.

    Live data contains '["Agritech, Resource Management, & Environmental
    Sensing"]' — one JSON element carrying three domains. Returning elements
    verbatim let that reach the picker as a single 54-character entry with a
    stray "&" still in it.
    """

    def test_json_element_containing_a_list_is_split(self):
        got = parse_domain_field('["Agritech, Resource Management, & Environmental Sensing"]')
        assert got == ["Agritech", "Resource Management", "Environmental Sensing"]

    def test_json_array_of_clean_labels_is_unchanged(self):
        assert parse_domain_field('["Software", "Web Development"]') == ["Software", "Web Development"]

    def test_json_element_misspelling_corrected(self):
        assert parse_domain_field('["Artifical Intelligence"]') == ["Artificial Intelligence"]
