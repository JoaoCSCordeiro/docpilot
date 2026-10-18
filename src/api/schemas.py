from pydantic import BaseModel, Field

from src.config import settings


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=settings.max_question_length)


class SourceChunk(BaseModel):
    source: str
    position: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    is_confident: bool
    confidence: float
    sources: list[SourceChunk] = []
