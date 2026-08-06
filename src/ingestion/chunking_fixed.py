from dataclasses import dataclass

from src.ingestion.loader import Document


@dataclass
class Chunk:
    source: str
    position: int
    text: str


def chunk_fixed_size(document: Document, chunk_size: int, overlap: int) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size deve ser positivo")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap deve ser >= 0 e menor que chunk_size")

    text = document.content
    step = chunk_size - overlap

    chunks = []
    position = 0
    start = 0
    while start < len(text):
        chunk_text = text[start : start + chunk_size]
        chunks.append(Chunk(source=document.source, position=position, text=chunk_text))
        position += 1
        start += step
    return chunks


def chunk_documents_fixed_size(
    documents: list[Document], chunk_size: int, overlap: int
) -> list[Chunk]:
    all_chunks = []
    for document in documents:
        all_chunks.extend(chunk_fixed_size(document, chunk_size, overlap))
    return all_chunks
