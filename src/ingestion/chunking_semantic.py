import re

from src.ingestion.chunking_fixed import Chunk
from src.ingestion.loader import Document

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_into_units(text: str, max_chunk_size: int) -> list[str]:
    units = []
    for paragraph in _PARAGRAPH_SPLIT.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chunk_size:
            units.append(paragraph)
        else:
            units.extend(s for s in _SENTENCE_SPLIT.split(paragraph) if s.strip())
    return units


def chunk_semantic(document: Document, max_chunk_size: int, overlap_sentences: int) -> list[Chunk]:
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size deve ser positivo")
    if overlap_sentences < 0:
        raise ValueError("overlap_sentences deve ser >= 0")

    units = _split_into_units(document.content, max_chunk_size)

    chunks: list[Chunk] = []
    position = 0
    current_units: list[str] = []

    def flush() -> None:
        nonlocal position
        text = "\n\n".join(current_units)
        chunks.append(Chunk(source=document.source, position=position, text=text))
        position += 1

    for unit in units:
        candidate = current_units + [unit]
        if current_units and len("\n\n".join(candidate)) > max_chunk_size:
            flush()
            current_units = current_units[-overlap_sentences:] if overlap_sentences else []
        current_units.append(unit)

    if current_units:
        flush()

    return chunks


def chunk_documents_semantic(
    documents: list[Document], max_chunk_size: int, overlap_sentences: int
) -> list[Chunk]:
    all_chunks = []
    for document in documents:
        all_chunks.extend(chunk_semantic(document, max_chunk_size, overlap_sentences))
    return all_chunks
