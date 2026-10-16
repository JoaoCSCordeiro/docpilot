import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from src.agent.graph import build_graph  # noqa: E402
from src.agent.llm import get_llm  # noqa: E402
from src.agent.query_log import get_query_traces_collection  # noqa: E402
from src.config import settings  # noqa: E402
from src.mcp_server.server import build_server  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

# O timeout por omissao do pymongo (30 s) bloquearia cada ask_docpilot quando o Mongo
# esta em baixo; o trace e opcional, por isso falha depressa.
MONGO_SERVER_SELECTION_TIMEOUT_MS = 2000


def main() -> None:
    parser = argparse.ArgumentParser(description="DocPilot MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default=settings.mcp_http_host)
    parser.add_argument("--port", type=int, default=settings.mcp_http_port)
    args = parser.parse_args()

    client = get_client()

    def graph_factory():
        if not settings.groq_api_key:
            raise ToolError(
                "GROQ_API_KEY is not set on the DocPilot server; ask_docpilot needs it."
            )
        return build_graph(client, get_llm())

    mongo_client = MongoClient(
        settings.mongo_uri, serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS
    )
    server = build_server(
        client, graph_factory, query_log=get_query_traces_collection(mongo_client)
    )

    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
