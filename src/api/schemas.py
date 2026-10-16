from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)


class SourceChunk(BaseModel):
    source: str
    position: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    is_confident: bool
    confidence: float
    sources: list[SourceChunk] = []
