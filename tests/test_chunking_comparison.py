from src.evaluation.chunking_comparison import compute_stats, format_report
from src.ingestion.chunking_fixed import Chunk


def test_compute_stats_calculates_expected_metrics() -> None:
    chunks = [
        Chunk(source="doc.md", position=0, text="a" * 10),
        Chunk(source="doc.md", position=1, text="a" * 20),
    ]

    stats = compute_stats("fixed-size", chunks)

    assert stats.strategy == "fixed-size"
    assert stats.num_chunks == 2
    assert stats.mean_size == 15.0
    assert stats.variance_size == 25.0
    assert stats.min_size == 10
    assert stats.max_size == 20


def test_format_report_lists_all_strategies() -> None:
    chunks = [Chunk(source="doc.md", position=0, text="a" * 10)]
    stats = [compute_stats("fixed-size", chunks), compute_stats("semantic", chunks)]

    report = format_report(stats)

    assert "fixed-size" in report
    assert "semantic" in report
