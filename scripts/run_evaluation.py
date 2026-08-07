import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.evaluation.metrics import precision_at_k, recall_at_k  # noqa: E402
from src.retrieval.reranker import rerank  # noqa: E402
from src.retrieval.retriever import retrieve  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "qa_dataset.json"


def load_dataset() -> list[dict]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> None:
    dataset = load_dataset()
    client = get_client()
    top_k = settings.retrieval_top_k

    results = []
    for example in dataset:
        expected_sources = example["expected_sources"]

        retrieved = retrieve(client, settings.qdrant_collection_name, example["question"], top_k)
        retrieved_sources = [chunk.source for chunk in retrieved]

        reranked = rerank(example["question"], retrieved)
        reranked_sources = [chunk.source for chunk in reranked]

        results.append(
            {
                "id": example["id"],
                "question": example["question"],
                "expected_sources": expected_sources,
                "retrieved_sources": retrieved_sources,
                "recall_at_k": recall_at_k(retrieved_sources, expected_sources),
                "precision_at_k": precision_at_k(retrieved_sources, expected_sources),
                "precision_at_1_before_rerank": precision_at_k(retrieved_sources[:1], expected_sources),
                "precision_at_1_after_rerank": precision_at_k(reranked_sources[:1], expected_sources),
            }
        )

    print(f"Dataset: {len(results)} perguntas, top_k={top_k}\n")
    print(f"Recall@{top_k}:                       {mean([r['recall_at_k'] for r in results]):.4f}")
    print(f"Precision@{top_k}:                     {mean([r['precision_at_k'] for r in results]):.4f}")
    print(f"Precision@1 (antes do reranking):    {mean([r['precision_at_1_before_rerank'] for r in results]):.4f}")
    print(f"Precision@1 (depois do reranking):   {mean([r['precision_at_1_after_rerank'] for r in results]):.4f}")

    failures = [r for r in results if r["recall_at_k"] < 1.0]
    print(f"\nFalhas de recall ({len(failures)}/{len(results)}):")
    for failure in failures:
        print(f"  [{failure['id']}] {failure['question']!r}")
        print(f"      esperado: {failure['expected_sources']}")
        print(f"      recuperado: {failure['retrieved_sources']}")


if __name__ == "__main__":
    main()
