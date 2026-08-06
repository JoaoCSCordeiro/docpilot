from src.agent.guardrail import confidence_score, is_confident
from src.retrieval.retriever import RetrievedChunk


def test_confidence_score_is_zero_for_empty_list() -> None:
    assert confidence_score([]) == 0.0


def test_confidence_score_high_positive_logit_yields_high_confidence() -> None:
    chunks = [RetrievedChunk(source="a.md", position=0, text="x", score=5.0)]

    assert confidence_score(chunks) > 0.9


def test_confidence_score_low_negative_logit_yields_low_confidence() -> None:
    chunks = [RetrievedChunk(source="a.md", position=0, text="x", score=-5.0)]

    assert confidence_score(chunks) < 0.1


def test_confidence_score_only_considers_top_chunk() -> None:
    chunks = [
        RetrievedChunk(source="a.md", position=0, text="x", score=5.0),
        RetrievedChunk(source="b.md", position=0, text="y", score=-5.0),
    ]

    assert confidence_score(chunks) > 0.9


def test_is_confident_respects_custom_threshold() -> None:
    chunks = [RetrievedChunk(source="a.md", position=0, text="x", score=0.0)]

    assert is_confident(chunks, threshold=0.4) is True
    assert is_confident(chunks, threshold=0.6) is False


def test_is_confident_uses_settings_threshold_by_default() -> None:
    well_covered = [RetrievedChunk(source="a.md", position=0, text="x", score=5.0)]
    out_of_domain = [RetrievedChunk(source="a.md", position=0, text="x", score=-5.0)]

    assert is_confident(well_covered) is True
    assert is_confident(out_of_domain) is False
