import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_collection_name: str = os.getenv("QDRANT_COLLECTION_NAME", "docpilot")

    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name: str = os.getenv("MONGO_DB_NAME", "docpilot")

    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )
    reranker_model_name: str = os.getenv(
        "RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )

    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_max_calls_per_minute: int = int(os.getenv("GROQ_MAX_CALLS_PER_MINUTE", "20"))
    groq_max_tokens: int = int(os.getenv("GROQ_MAX_TOKENS", "1024"))
    # Preco publico por milhao de tokens de openai/gpt-oss-120b, em USD
    # (console.groq.com/docs/model/openai/gpt-oss-120b, consultado a 2026-10-16).
    # Usado so para estimar custo no tracing: no free tier o custo real e zero.
    groq_price_input_per_million: float = float(os.getenv("GROQ_PRICE_INPUT_PER_MILLION", "0.15"))
    groq_price_output_per_million: float = float(os.getenv("GROQ_PRICE_OUTPUT_PER_MILLION", "0.60"))

    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_base_url: str = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")

    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    mcp_http_host: str = os.getenv("MCP_HTTP_HOST", "127.0.0.1")
    mcp_http_port: int = int(os.getenv("MCP_HTTP_PORT", "8001"))


settings = Settings()
