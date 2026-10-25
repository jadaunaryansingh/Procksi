"""Evaluation harness for the roster Validation Agent.

Treats roster validation as a binary detection problem:

    positive ("flag")  = the row is a duplicate / near-duplicate of an existing
                          roster person and should land in `duplicates` or `review`.
    negative ("allow") = the row is a genuinely new, clean person -> `valid`.

It reports precision / recall / F1 on a small hand-labelled set and sweeps the
`review_min` threshold so the chosen default can be justified with evidence.

Run standalone:   python -m tests.eval_roster
Run as a test:    pytest tests/eval_roster.py
"""
from __future__ import annotations

from app.validators.roster_validator import RosterThresholds, RosterValidator

EXISTING = [
    {"student_id": "GLA2021001", "name": "Rohit Sharma", "email": "rohit.sharma@gla.ac.in"},
    {"student_id": "GLA2021002", "name": "Anita Verma", "email": "anita.verma@gla.ac.in"},
    {"student_id": "GLA2021003", "name": "Lakshmi Nair", "email": "lakshmi.nair@gla.ac.in"},
    {"student_id": "GLA2021004", "name": "Mohammed Irfan", "email": "mohammed.irfan@gla.ac.in"},
    {"student_id": "BCA1234", "name": "Suresh Kumar", "email": "suresh.kumar@gla.ac.in"},
]

# (row, expected_label). "flag" = should be caught (dup/near-dup); "allow" = clean new.
LABELED: list[tuple[dict, str]] = [
    # --- genuinely new, clean people (allow) ---
    ({"student_id": "GLA2021050", "name": "Vikram Rao", "email": "vikram.rao@gla.ac.in"}, "allow"),
    ({"student_id": "GLA2021051", "name": "Priya Menon", "email": "priya.menon@gla.ac.in"}, "allow"),
    ({"student_id": "GLA2021052", "name": "Arjun Reddy", "email": "arjun.reddy@gla.ac.in"}, "allow"),
    ({"student_id": "GLA2021053", "name": "Sneha Pillai", "email": "sneha.pillai@gla.ac.in"}, "allow"),
    ({"student_id": "GLA2021054", "name": "Karan Mehta", "email": "karan.mehta@gla.ac.in"}, "allow"),
    # Common surname, different person — must NOT false-flag against Suresh Kumar.
    ({"student_id": "GLA2021055", "name": "Anil Kumar", "email": "anil.kumar@gla.ac.in"}, "allow"),
    # --- duplicates / near-duplicates (flag) ---
    ({"student_id": "GLA2021001", "name": "Rohit Sharma", "email": "new1@gla.ac.in"}, "flag"),   # exact id
    ({"student_id": "NEW9001", "name": "Someone", "email": "anita.verma@gla.ac.in"}, "flag"),      # exact email
    ({"student_id": "NEW9002", "name": "Rohith Sharma", "email": "rohith.sharma@gla.ac.in"}, "flag"),  # typo name
    ({"student_id": "NEW9003", "name": "Anitha Verma", "email": "anitha.verma@gla.ac.in"}, "flag"),    # translit
    ({"student_id": "NEW9004", "name": "Laxmi Nair", "email": "laxmi.nair@gla.ac.in"}, "flag"),        # translit
    ({"student_id": "NEW9005", "name": "Rohit Sharma", "email": "rohit.s.alt@gla.ac.in"}, "flag"),     # same person, new id
    ({"student_id": "BCA1243", "name": "Suresh Kumar", "email": "suresh.k2@gla.ac.in"}, "flag"),       # id typo + name
]


def evaluate(review_min: float) -> dict:
    thresholds = RosterThresholds(review_min=review_min)
    validator = RosterValidator(thresholds=thresholds)

    tp = fp = tn = fn = 0
    for row, label in LABELED:
        res = validator.validate_batch([row], EXISTING)
        flagged = bool(res["duplicates"] or res["review"])
        if label == "flag":
            if flagged:
                tp += 1
            else:
                fn += 1
        else:  # allow
            if flagged:
                fp += 1
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "review_min": review_min,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
    }


def sweep(thresholds=(0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.95)) -> list[dict]:
    return [evaluate(t) for t in thresholds]


def format_report(rows: list[dict]) -> str:
    lines = [
        "review_min |  TP  FP  TN  FN | precision  recall    f1",
        "-----------+-----------------+---------------------------",
    ]
    for r in rows:
        lines.append(
            f"   {r['review_min']:.2f}    | {r['tp']:>3} {r['fp']:>3} {r['tn']:>3} {r['fn']:>3} "
            f"|   {r['precision']:.3f}   {r['recall']:.3f}  {r['f1']:.3f}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# pytest entry points
# --------------------------------------------------------------------------- #
def test_default_threshold_has_perfect_recall_and_high_precision():
    """At the shipped default we must catch every true duplicate (recall=1.0)
    and keep false alarms low (precision >= 0.8)."""
    metrics = evaluate(RosterThresholds().review_min)
    assert metrics["recall"] == 1.0, metrics
    assert metrics["precision"] >= 0.8, metrics


def test_sweep_shows_recall_holding_then_degrading():
    """The sweep documents the safe operating band: perfect recall at/below the
    default, degrading as the threshold gets too strict."""
    rows = {round(r["review_min"], 2): r for r in sweep()}
    assert len(rows) == 8
    # At and below the shipped default, every true duplicate is still caught.
    assert all(rows[t]["recall"] == 1.0 for t in (0.80, 0.82, 0.84, 0.86, 0.88, 0.90))
    # Too strict -> we start missing transliteration-style near-duplicates.
    assert rows[0.95]["recall"] < 1.0
    # No false positives anywhere in the sweep (precision stays perfect on fixture).
    assert all(r["precision"] == 1.0 for r in rows.values())


if __name__ == "__main__":
    report = sweep()
    print("\nRoster Validation Agent — threshold sweep on labelled fixture\n")
    print(format_report(report))
    best = max(report, key=lambda r: (round(r["f1"], 3), r["recall"]))
    print(f"\nBest F1 at review_min={best['review_min']:.2f} "
          f"(precision={best['precision']:.3f}, recall={best['recall']:.3f}, f1={best['f1']:.3f})\n")
