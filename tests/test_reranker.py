from src.retrieval.reranker import rerank
from src.retrieval.retriever import RetrievedChunk


def test_rerank_promotes_most_relevant_chunk_to_top() -> None:
    query = "How many people live in Berlin?"
    chunks = [
        RetrievedChunk(
            source="berlin.md", position=0, text="Berlin is well known for its museums.", score=0.9
        ),
        RetrievedChunk(
            source="berlin.md",
            position=1,
            text="Berlin is the capital and largest city of Germany.",
            score=0.85,
        ),
        RetrievedChunk(
            source="berlin.md",
            position=2,
            text="Berlin has a population of 3,850,809 registered inhabitants.",
            score=0.8,
        ),
    ]

    reranked = rerank(query, chunks)

    assert reranked[0].text == "Berlin has a population of 3,850,809 registered inhabitants."
    assert [chunk.text for chunk in reranked] != [chunk.text for chunk in chunks]


def test_rerank_returns_empty_list_for_no_chunks() -> None:
    assert rerank("query sem resultados", []) == []


def test_rerank_preserves_chunk_metadata() -> None:
    chunks = [
        RetrievedChunk(source="doc.md", position=0, text="Paris is the capital of France.", score=0.5)
    ]

    reranked = rerank("What is the capital of France?", chunks)

    assert reranked[0].source == "doc.md"
    assert reranked[0].position == 0
