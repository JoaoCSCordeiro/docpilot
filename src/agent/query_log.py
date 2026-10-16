import datetime as dt

from pymongo import MongoClient
from pymongo.collection import Collection

from src.config import settings

QUERY_TRACES_COLLECTION_NAME = "query_traces"


def get_mongo_client() -> MongoClient:
    return MongoClient(settings.mongo_uri)


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


def get_recent_queries(collection: Collection, limit: int = 20) -> list[dict]:
    return list(collection.find().sort("created_at", -1).limit(limit))


def get_low_confidence_queries(collection: Collection, threshold: float) -> list[dict]:
    return list(collection.find({"confidence": {"$lt": threshold}}).sort("created_at", -1))
