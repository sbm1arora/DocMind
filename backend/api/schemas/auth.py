from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class UserOut(BaseModel):
    id: UUID
    github_id: int
    github_username: str
    email: str | None
    github_avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours


class GithubCallbackQuery(BaseModel):
    code: str
    state: str
