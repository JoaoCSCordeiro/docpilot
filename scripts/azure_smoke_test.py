import argparse
import json
import sys
import time
from pathlib import Path

import httpx

DATASET = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "qa_dataset_v2.json"
# Duas perguntas respondiveis (PT e EN) e duas fora do corpus que devem ser recusadas.
DEFAULT_CASE_IDS = [13, 33, 41, 42]


def load_cases(case_ids: list[int]) -> list[dict]:
    cases = {case["id"]: case for case in json.loads(DATASET.read_text(encoding="utf-8"))}
    return [cases[case_id] for case_id in case_ids]


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test da API publicada no Azure")
    parser.add_argument("base_url")
    parser.add_argument("--case-ids", type=int, nargs="+", default=DEFAULT_CASE_IDS)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=120.0) as client:
        started = time.perf_counter()
        health = client.get("/health")
        print(
            f"GET /health -> {health.status_code} {health.json()} "
            f"({time.perf_counter() - started:.2f}s)"
        )

        failures = 0
        for case in load_cases(args.case_ids):
            started = time.perf_counter()
            response = client.post("/query", json={"question": case["question"]})
            elapsed = time.perf_counter() - started
            body = response.json()
            refused = not body["is_confident"]
            ok = response.status_code == 200 and refused == case["should_refuse"]
            failures += not ok
            sources = sorted({source["source"] for source in body.get("sources", [])})
            print(
                f"\n[{'OK' if ok else 'FALHA'}] caso {case['id']} ({case['language']}, "
                f"{case['category']}) -> {response.status_code} em {elapsed:.2f}s"
            )
            print(f"  pergunta: {case['question']}")
            print(
                f"  confianca: {body['confidence']:.3f}  recusada: {refused}  "
                f"esperado recusar: {case['should_refuse']}"
            )
            print(f"  fontes: {', '.join(sources) or '-'}")
            print(f"  resposta: {body['answer'][:300]}")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
