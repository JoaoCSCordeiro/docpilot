import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.graph import build_graph, run_agent  # noqa: E402
from src.agent.llm import AZURE_OPENAI, get_llm  # noqa: E402
from src.config import settings  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

DATASET = Path(__file__).resolve().parents[1] / "data" / "evaluation" / "qa_dataset_v2.json"
# PT e EN respondiveis e uma fora do corpus; a recusa nao chega a chamar o LLM.
CASE_IDS = [13, 33, 42]


def main() -> None:
    if not (settings.azure_openai_endpoint and settings.azure_openai_api_key):
        sys.exit("Definir AZURE_OPENAI_ENDPOINT e AZURE_OPENAI_API_KEY")

    cases = {case["id"]: case for case in json.loads(DATASET.read_text(encoding="utf-8"))}
    llm = get_llm(provider=AZURE_OPENAI)
    graph = build_graph(get_client(), llm)
    print(f"Provider {llm.provider}, deployment {llm.model_name}, {settings.azure_openai_endpoint}")

    # O ultimo caso repete o primeiro: deve vir da cache sem nova chamada ao Azure.
    for case_id in [*CASE_IDS, CASE_IDS[0]]:
        case = cases[case_id]
        calls_before = llm.call_count
        started = time.perf_counter()
        result = run_agent(graph, case["question"], entrypoint="cli")
        elapsed = time.perf_counter() - started
        print(f"\ncaso {case_id} ({case['language']}, {case['category']}) em {elapsed:.2f}s")
        print(f"  pergunta: {case['question']}")
        print(
            f"  confianca: {result['confidence']:.3f}  respondeu: {result['is_confident']}  "
            f"chamadas ao Azure: {llm.call_count - calls_before}"
        )
        print(f"  resposta: {result['answer'][:300]}")

    print(f"\nTotal de chamadas ao Azure OpenAI: {llm.call_count}")


if __name__ == "__main__":
    main()
