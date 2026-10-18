import pytest

from src.evaluation.metrics import (
    mean,
    mean_by_group,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_metrics,
)


def test_recall_at_k_is_one_when_expected_source_is_retrieved() -> None:
    retrieved = ["a.md", "b.md", "c.md"]
    expected = ["a.md"]

    assert recall_at_k(retrieved, expected) == 1.0


def test_recall_at_k_is_zero_when_expected_source_is_missing() -> None:
    retrieved = ["b.md", "c.md"]
    expected = ["a.md"]

    assert recall_at_k(retrieved, expected) == 0.0


def test_recall_at_k_with_multiple_expected_sources_is_partial() -> None:
    retrieved = ["a.md", "c.md"]
    expected = ["a.md", "b.md"]

    assert recall_at_k(retrieved, expected) == 0.5


def test_recall_at_k_raises_for_empty_expected_sources() -> None:
    with pytest.raises(ValueError):
        recall_at_k(["a.md"], [])


def test_precision_at_k_counts_fraction_of_relevant_retrieved_chunks() -> None:
    retrieved = ["a.md", "a.md", "b.md", "c.md"]
    expected = ["a.md"]

    assert precision_at_k(retrieved, expected) == 0.5


def test_precision_at_k_is_zero_for_empty_retrieved_list() -> None:
    assert precision_at_k([], ["a.md"]) == 0.0


def test_precision_at_k_is_one_when_all_retrieved_are_relevant() -> None:
    retrieved = ["a.md", "a.md"]
    expected = ["a.md"]

    assert precision_at_k(retrieved, expected) == 1.0


def test_reciprocal_rank_uses_position_of_first_relevant_source() -> None:
    assert reciprocal_rank(["b.md", "a.md", "a.md"], ["a.md"]) == 0.5


def test_reciprocal_rank_is_zero_when_no_relevant_source_is_retrieved() -> None:
    assert reciprocal_rank(["b.md", "c.md"], ["a.md"]) == 0.0


def test_mean_of_empty_values_is_none() -> None:
    assert mean([]) is None


def test_mean_by_group_reports_count_and_mean_per_group() -> None:
    rows = [
        {"language": "pt", "recall": 1.0},
        {"language": "en", "recall": 0.0},
        {"language": "en", "recall": 1.0},
    ]

    assert mean_by_group(rows, "language", "recall") == {
        "en": {"n": 2, "mean": 0.5},
        "pt": {"n": 1, "mean": 1.0},
    }


def test_refusal_metrics_treats_refusing_as_the_positive_class() -> None:
    should_refuse = [True, True, False, False, False]
    refused = [True, False, True, False, False]

    metrics = refusal_metrics(should_refuse, refused)

    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["true_refusals"] == 1
    assert metrics["false_refusals"] == 1
    assert metrics["missed_refusals"] == 1


def test_refusal_precision_is_undefined_when_nothing_is_refused() -> None:
    metrics = refusal_metrics([True, False], [False, False])

    assert metrics["precision"] is None
    assert metrics["recall"] == 0.0


def test_percentile_uses_nearest_rank() -> None:
    values = [5.0, 1.0, 3.0, 2.0, 4.0]

    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 0.95) == 5.0
    assert percentile(values, 0.2) == 1.0


def test_percentile_of_empty_values_is_none() -> None:
    assert percentile([], 0.5) is None


def test_percentile_rejects_fraction_outside_range() -> None:
    with pytest.raises(ValueError):
        percentile([1.0], 0.0)
