from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class RepoItem(BaseModel):
    name: str
    full_name: str
    private: bool
    language: str | None
    updated_at: str


class ProjectCreate(BaseModel):
    repo_full_name: str
    branch: str = "main"


class ProjectOut(BaseModel):
    id: UUID
    repo_full_name: str
    repo_name: str
    repo_owner: str
    default_branch: str
    status: str
    file_count: int
    chunk_count: int
    doc_coverage_score: float | None
    last_indexed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
