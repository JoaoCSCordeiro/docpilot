import pytest

from src.evaluation.metrics import precision_at_k, recall_at_k


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
