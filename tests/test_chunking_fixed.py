import pytest

from src.ingestion.chunking_fixed import chunk_documents_fixed_size, chunk_fixed_size
from src.ingestion.loader import Document


def test_chunk_fixed_size_respects_chunk_size() -> None:
    document = Document(source="doc.md", content="a" * 100)

    chunks = chunk_fixed_size(document, chunk_size=30, overlap=0)

    assert [len(chunk.text) for chunk in chunks] == [30, 30, 30, 10]


def test_chunk_fixed_size_overlap_repeats_boundary_text() -> None:
    document = Document(source="doc.md", content="0123456789")

    chunks = chunk_fixed_size(document, chunk_size=4, overlap=2)

    texts = [chunk.text for chunk in chunks]
    assert texts == ["0123", "2345", "4567", "6789", "89"]


def test_chunk_fixed_size_assigns_incrementing_positions_and_source() -> None:
    document = Document(source="doc.md", content="a" * 25)

    chunks = chunk_fixed_size(document, chunk_size=10, overlap=0)

    assert [chunk.position for chunk in chunks] == [0, 1, 2]
    assert all(chunk.source == "doc.md" for chunk in chunks)


def test_chunk_fixed_size_rejects_overlap_greater_or_equal_to_chunk_size() -> None:
    document = Document(source="doc.md", content="conteudo")

    with pytest.raises(ValueError):
        chunk_fixed_size(document, chunk_size=5, overlap=5)


def test_chunk_fixed_size_rejects_non_positive_chunk_size() -> None:
    document = Document(source="doc.md", content="conteudo")

    with pytest.raises(ValueError):
        chunk_fixed_size(document, chunk_size=0, overlap=0)


def test_chunk_documents_fixed_size_aggregates_all_documents() -> None:
    documents = [
        Document(source="a.md", content="a" * 10),
        Document(source="b.md", content="b" * 10),
    ]

    chunks = chunk_documents_fixed_size(documents, chunk_size=5, overlap=0)

    sources = [chunk.source for chunk in chunks]
    assert sources == ["a.md", "a.md", "b.md", "b.md"]
