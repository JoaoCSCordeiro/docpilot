import statistics
from dataclasses import dataclass
from pathlib import Path

from src.ingestion.chunking_fixed import Chunk, chunk_documents_fixed_size
from src.ingestion.chunking_semantic import chunk_documents_semantic
from src.ingestion.loader import load_documents

DEFAULT_RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

FIXED_CHUNK_SIZE = 500
FIXED_OVERLAP = 50
SEMANTIC_MAX_CHUNK_SIZE = 500
SEMANTIC_OVERLAP_SENTENCES = 1


@dataclass
class ChunkingStats:
    strategy: str
    num_chunks: int
    mean_size: float
    variance_size: float
    min_size: int
    max_size: int


def compute_stats(strategy: str, chunks: list[Chunk]) -> ChunkingStats:
    sizes = [len(chunk.text) for chunk in chunks]
    return ChunkingStats(
        strategy=strategy,
        num_chunks=len(chunks),
        mean_size=statistics.mean(sizes),
        variance_size=statistics.pvariance(sizes),
        min_size=min(sizes),
        max_size=max(sizes),
    )


def compare_chunking_strategies(raw_dir: Path = DEFAULT_RAW_DIR) -> list[ChunkingStats]:
    documents = load_documents(raw_dir)

    fixed_chunks = chunk_documents_fixed_size(
        documents, chunk_size=FIXED_CHUNK_SIZE, overlap=FIXED_OVERLAP
    )
    semantic_chunks = chunk_documents_semantic(
        documents,
        max_chunk_size=SEMANTIC_MAX_CHUNK_SIZE,
        overlap_sentences=SEMANTIC_OVERLAP_SENTENCES,
    )

    return [
        compute_stats("fixed-size", fixed_chunks),
        compute_stats("semantic", semantic_chunks),
    ]


def format_report(stats: list[ChunkingStats]) -> str:
    header = (
        f"{'strategy':<12}{'num_chunks':>12}{'mean_size':>12}"
        f"{'variance':>14}{'min_size':>10}{'max_size':>10}"
    )
    rows = [header]
    for s in stats:
        rows.append(
            f"{s.strategy:<12}{s.num_chunks:>12}{s.mean_size:>12.1f}"
            f"{s.variance_size:>14.1f}{s.min_size:>10}{s.max_size:>10}"
        )
    return "\n".join(rows)


if __name__ == "__main__":
    print(format_report(compare_chunking_strategies()))
