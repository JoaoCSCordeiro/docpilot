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
