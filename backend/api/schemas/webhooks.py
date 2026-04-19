from pydantic import BaseModel


class GitHubCommit(BaseModel):
    id: str
    message: str
    added: list[str] = []
    removed: list[str] = []
    modified: list[str] = []


class GitHubRepository(BaseModel):
    full_name: str


class GitHubPushPayload(BaseModel):
    ref: str
    before: str
    after: str
    repository: GitHubRepository
    commits: list[GitHubCommit] = []
    head_commit: GitHubCommit | None = None
