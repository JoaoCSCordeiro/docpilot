import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_collection_name: str = os.getenv("QDRANT_COLLECTION_NAME", "docpilot_v2")

    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name: str = os.getenv("MONGO_DB_NAME", "docpilot")

    # Defaults escolhidos pela ablation do Bloco 19 (docs/hybrid-retrieval.md).
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
    reranker_model_name: str = os.getenv(
        "RERANKER_MODEL_NAME", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    )

    # dense | sparse | hybrid; todos usam a mesma coleccao com named vectors (Bloco 19).
    retrieval_mode: str = os.getenv("RETRIEVAL_MODE", "hybrid")
    # Lingua do stemmer/stopwords do BM25 (fastembed), ou "none" para os desligar. O
    # portugues mediu melhor do que o ingles mesmo com metade dos documentos em ingles.
    bm25_language: str = os.getenv("BM25_LANGUAGE", "portuguese")

    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    # Limiar mais baixo da ablation que mantem as 8 recusas certas de antes (eram 21 recusas
    # erradas a 0.5 com o setup antigo, 4 aqui); escolhido sobre o mesmo dataset que mede.
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.1"))

    # groq | azure_openai. O juiz da avaliacao fica sempre na Groq (ver judge.py).
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_max_calls_per_minute: int = int(os.getenv("GROQ_MAX_CALLS_PER_MINUTE", "20"))
    groq_max_tokens: int = int(os.getenv("GROQ_MAX_TOKENS", "1024"))
    # Preco publico por milhao de tokens de openai/gpt-oss-120b, em USD
    # (console.groq.com/docs/model/openai/gpt-oss-120b, consultado a 2026-10-16).
    # Usado so para estimar custo no tracing: no free tier o custo real e zero.
    groq_price_input_per_million: float = float(os.getenv("GROQ_PRICE_INPUT_PER_MILLION", "0.15"))
    groq_price_output_per_million: float = float(os.getenv("GROQ_PRICE_OUTPUT_PER_MILLION", "0.60"))

    # Azure OpenAI (Bloco 21). O deployment tem o nome que lhe foi dado no Terraform; a
    # api_version e a GA usada pelo langchain-openai 0.3.
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    azure_openai_max_calls_per_minute: int = int(
        os.getenv("AZURE_OPENAI_MAX_CALLS_PER_MINUTE", "10")
    )
    azure_openai_max_tokens: int = int(os.getenv("AZURE_OPENAI_MAX_TOKENS", "1024"))

    # Juiz LLM da avaliacao (Bloco 18). Modelo diferente do gerador, mas da mesma familia:
    # o qwen/qwen3.8-27b (outro fornecedor, preferivel contra o self-preference bias) teve
    # 9/26 veredictos rejeitados em modo strict e ignorou o schema em modo nao-strict.
    judge_model: str = os.getenv("JUDGE_MODEL", "openai/gpt-oss-20b")
    # Inclui os tokens de raciocinio do gpt-oss: com 1024, um veredicto foi cortado antes
    # de o JSON terminar (Groq 400, "max completion tokens reached").
    judge_max_tokens: int = int(os.getenv("JUDGE_MAX_TOKENS", "2048"))
    # Vazio = parametro omitido (raciocinio por omissao do modelo).
    judge_reasoning_effort: str = os.getenv("JUDGE_REASONING_EFFORT", "")

    # Redis partilhado entre replicas (Bloco 20). Com "sqlite" e "memory" o comportamento e
    # o de antes; com "redis" e o Redis em baixo, cai-se nesses mesmos backends.
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    llm_cache_backend: str = os.getenv("LLM_CACHE_BACKEND", "sqlite")
    # 0 = sem expiracao. As respostas sao deterministicas (temperature 0) mas o modelo da
    # Groq pode mudar por baixo do mesmo nome; 7 dias limita o tempo de uma resposta velha.
    llm_cache_ttl_seconds: int = int(os.getenv("LLM_CACHE_TTL_SECONDS", "604800"))
    rate_limiter_backend: str = os.getenv("RATE_LIMITER_BACKEND", "memory")

    max_question_length: int = int(os.getenv("MAX_QUESTION_LENGTH", "2000"))

    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_base_url: str = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")

    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    mcp_http_host: str = os.getenv("MCP_HTTP_HOST", "127.0.0.1")
    mcp_http_port: int = int(os.getenv("MCP_HTTP_PORT", "8001"))


settings = Settings()
