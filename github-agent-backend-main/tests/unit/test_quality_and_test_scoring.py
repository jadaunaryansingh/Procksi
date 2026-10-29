from src.detectors.quality_metrics import aggregate_quality_metrics
from src.detectors.test_coverage_analyzer import estimate_test_coverage_from_analysis


def test_test_coverage_rewards_large_mature_suite():
    test_stats = {
        "total_test_files": 21,
        "total_test_lines": 2199,
    }
    frameworks = {"python": ["pytest"]}

    score = estimate_test_coverage_from_analysis(test_stats, 0.0512, frameworks)

    assert score >= 90


def test_quality_aggregate_applies_scale_bonus_for_large_repo():
    language_results = {
        "python": {
            "files": 190,
            "complexity": 14.0,
            "maintainability": 62.0,
            "loc": 42900,
            "comments": 4607,
        }
    }

    metrics = aggregate_quality_metrics(language_results)

    assert metrics["scale_bonus"] >= 8.0
    assert metrics["maintainability_index"] >= 85.0
    assert metrics["complexity_score"] > 80.0
