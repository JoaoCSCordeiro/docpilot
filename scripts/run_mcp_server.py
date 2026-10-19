import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from src.agent.graph import build_graph  # noqa: E402
from src.agent.llm import get_llm, missing_llm_settings  # noqa: E402
from src.agent.query_log import get_mongo_client, get_query_traces_collection  # noqa: E402
from src.config import settings  # noqa: E402
from src.mcp_server.server import build_server  # noqa: E402
from src.observability.tracing import get_langfuse  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="DocPilot MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default=settings.mcp_http_host)
    parser.add_argument("--port", type=int, default=settings.mcp_http_port)
    args = parser.parse_args()

    # Inicializado antes do primeiro pedido: o middleware OpenTelemetry do SDK MCP abre o
    # span de tools/call antes de a tool correr, e esse span so e exportado se o
    # TracerProvider do Langfuse ja estiver registado.
    get_langfuse()
    client = get_client()

    def graph_factory():
        missing = missing_llm_settings()
        if missing:
            raise ToolError(
                f"{', '.join(missing)} not set on the DocPilot server; ask_docpilot needs "
                f"it with LLM_PROVIDER={settings.llm_provider}."
            )
        return build_graph(client, get_llm())

    server = build_server(
        client, graph_factory, query_log=get_query_traces_collection(get_mongo_client())
    )

    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
