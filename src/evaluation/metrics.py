from collections import defaultdict
from typing import Iterable


def recall_at_k(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    if not expected_sources:
        raise ValueError("expected_sources nao pode ser vazio")

    unique_expected = set(expected_sources)
    unique_retrieved = set(retrieved_sources)
    return len(unique_expected & unique_retrieved) / len(unique_expected)


def precision_at_k(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    if not retrieved_sources:
        return 0.0

    unique_expected = set(expected_sources)
    relevant_count = sum(1 for source in retrieved_sources if source in unique_expected)
    return relevant_count / len(retrieved_sources)


def reciprocal_rank(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    unique_expected = set(expected_sources)
    for rank, source in enumerate(retrieved_sources, start=1):
        if source in unique_expected:
            return 1.0 / rank
    return 0.0


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def mean_by_group(rows: list[dict], group_key: str, value_key: str) -> dict[str, dict]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        groups[row[group_key]].append(row[value_key])
    return {
        group: {"n": len(values), "mean": mean(values)} for group, values in sorted(groups.items())
    }


def refusal_metrics(should_refuse: list[bool], refused: list[bool]) -> dict:
    # A classe positiva e "recusar": precision = das recusas, quantas eram devidas;
    # recall = das perguntas a recusar, quantas foram de facto recusadas.
    if len(should_refuse) != len(refused):
        raise ValueError("should_refuse e refused devem ter o mesmo tamanho")

    pairs = list(zip(should_refuse, refused))
    true_refusals = sum(1 for expected, actual in pairs if expected and actual)
    false_refusals = sum(1 for expected, actual in pairs if not expected and actual)
    missed_refusals = sum(1 for expected, actual in pairs if expected and not actual)

    predicted = true_refusals + false_refusals
    expected_total = true_refusals + missed_refusals
    return {
        "precision": true_refusals / predicted if predicted else None,
        "recall": true_refusals / expected_total if expected_total else None,
        "true_refusals": true_refusals,
        "false_refusals": false_refusals,
        "missed_refusals": missed_refusals,
        "n": len(pairs),
    }
