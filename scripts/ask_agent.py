import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.graph import build_default_graph, run_agent  # noqa: E402
from src.agent.query_log import (  # noqa: E402
    get_mongo_client,
    get_query_traces_collection,
    save_query_trace,
)
from src.config import settings  # noqa: E402
from src.observability.tracing import flush  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: python scripts/ask_agent.py "a tua pergunta aqui"')
        sys.exit(1)

    if not settings.groq_api_key:
        print("GROQ_API_KEY nao esta definida. Cria um .env com base no .env.example.")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    graph = build_default_graph()
    result = run_agent(graph, query, entrypoint="cli")
    flush()

    query_log = get_query_traces_collection(get_mongo_client())
    save_query_trace(query_log, result)

    print(f"QUERY: {query}")
    print(f"Confianca: {result['confidence']:.4f} (threshold={settings.confidence_threshold})")
    print(f"Respondeu: {result['is_confident']}")
    print(f"\nRESPOSTA:\n{result['answer']}")


if __name__ == "__main__":
    main()
