import datetime as dt
import logging

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from src.config import settings

QUERY_TRACES_COLLECTION_NAME = "query_traces"
# O timeout por omissao do pymongo (30 s) bloquearia cada pedido quando o Mongo esta em
# baixo; o trace e opcional, por isso falha depressa.
MONGO_SERVER_SELECTION_TIMEOUT_MS = 2000

logger = logging.getLogger(__name__)


def get_mongo_client() -> MongoClient:
    return MongoClient(
        settings.mongo_uri, serverSelectionTimeoutMS=MONGO_SERVER_SELECTION_TIMEOUT_MS
    )


def get_query_traces_collection(client: MongoClient) -> Collection:
    return client[settings.mongo_db_name][QUERY_TRACES_COLLECTION_NAME]


def save_query_trace(
    collection: Collection, agent_state: dict, created_at: dt.datetime | None = None
) -> None:
    document = {
        "question": agent_state["query"],
        "retrieved_chunks": [chunk.summary() for chunk in agent_state.get("retrieved_chunks", [])],
        "reranked_chunks": [chunk.summary() for chunk in agent_state.get("reranked_chunks", [])],
        "confidence": agent_state.get("confidence"),
        "is_confident": agent_state.get("is_confident"),
        "answer": agent_state.get("answer"),
        "created_at": created_at or dt.datetime.now(dt.timezone.utc),
    }
    collection.insert_one(document)


def try_save_query_trace(collection: Collection, agent_state: dict) -> bool:
    # Quando o trace e gravado, a resposta ja foi gerada (e a chamada ao LLM ja foi paga):
    # uma falha do Mongo fica no log em vez de a deitar fora.
    try:
        save_query_trace(collection, agent_state)
    except PyMongoError as error:
        logger.warning("Query trace not saved to MongoDB: %s", type(error).__name__)
        return False
    return True


def get_recent_queries(collection: Collection, limit: int = 20) -> list[dict]:
    return list(collection.find().sort("created_at", -1).limit(limit))


def get_low_confidence_queries(collection: Collection, threshold: float) -> list[dict]:
    return list(collection.find({"confidence": {"$lt": threshold}}).sort("created_at", -1))
