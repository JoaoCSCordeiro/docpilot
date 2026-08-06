import pytest

from src.ingestion.chunking_semantic import chunk_documents_semantic, chunk_semantic
from src.ingestion.loader import Document


def test_chunk_semantic_splits_at_paragraph_boundaries() -> None:
    content = "para one text\n\npara two text"
    document = Document(source="doc.md", content=content)

    chunks = chunk_semantic(document, max_chunk_size=13, overlap_sentences=0)

    assert [chunk.text for chunk in chunks] == ["para one text", "para two text"]


def test_chunk_semantic_splits_oversized_paragraph_at_sentence_boundaries() -> None:
    content = "First sentence. Second sentence."
    document = Document(source="doc.md", content=content)

    chunks = chunk_semantic(document, max_chunk_size=20, overlap_sentences=0)

    assert [chunk.text for chunk in chunks] == ["First sentence.", "Second sentence."]


def test_chunk_semantic_never_splits_a_sentence_in_half() -> None:
    content = "First sentence. Second sentence. Third sentence."
    document = Document(source="doc.md", content=content)

    chunks = chunk_semantic(document, max_chunk_size=25, overlap_sentences=0)

    reconstructed = " ".join(chunks[i].text for i in range(len(chunks)))
    assert "First sentence." in reconstructed
    assert "Second sentence." in reconstructed
    assert "Third sentence." in reconstructed
    for chunk in chunks:
        assert chunk.text.strip().endswith((".", "!", "?"))


def test_chunk_semantic_overlap_repeats_trailing_unit() -> None:
    content = "AAA\n\nBBB\n\nCCC"
    document = Document(source="doc.md", content=content)

    chunks = chunk_semantic(document, max_chunk_size=3, overlap_sentences=1)

    assert [chunk.text for chunk in chunks] == ["AAA", "AAA\n\nBBB", "BBB\n\nCCC"]


def test_chunk_semantic_assigns_incrementing_positions_and_source() -> None:
    content = "para one\n\npara two\n\npara three"
    document = Document(source="doc.md", content=content)

    chunks = chunk_semantic(document, max_chunk_size=8, overlap_sentences=0)

    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.source == "doc.md" for chunk in chunks)


def test_chunk_semantic_rejects_non_positive_max_chunk_size() -> None:
    document = Document(source="doc.md", content="conteudo.")

    with pytest.raises(ValueError):
        chunk_semantic(document, max_chunk_size=0, overlap_sentences=0)


def test_chunk_semantic_rejects_negative_overlap() -> None:
    document = Document(source="doc.md", content="conteudo.")

    with pytest.raises(ValueError):
        chunk_semantic(document, max_chunk_size=10, overlap_sentences=-1)


def test_chunk_documents_semantic_aggregates_all_documents() -> None:
    documents = [
        Document(source="a.md", content="a para\n\nb para"),
        Document(source="b.md", content="c para\n\nd para"),
    ]

    chunks = chunk_documents_semantic(documents, max_chunk_size=6, overlap_sentences=0)

    sources = [chunk.source for chunk in chunks]
    assert sources == ["a.md", "a.md", "b.md", "b.md"]
