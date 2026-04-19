from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    channel: str = "web"


class QueryResponse(BaseModel):
    answer: str
    citations: list[str]
    confidence: float
    follow_ups: list[str]
    latency_ms: int
