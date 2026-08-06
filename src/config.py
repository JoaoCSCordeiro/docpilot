import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_collection_name: str = os.getenv("QDRANT_COLLECTION_NAME", "docpilot")

    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )

    retrieval_top_k: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))


settings = Settings()
