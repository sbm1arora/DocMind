from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    app_secret_key: str
    encryption_key: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "docmind"
    postgres_user: str = "docmind"
    postgres_password: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    redis_url: str = "redis://localhost:6379/0"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "doc_chunks"
    github_client_id: str
    github_client_secret: str
    github_callback_url: str = "http://localhost:8000/api/v1/auth/github/callback"
    openai_api_key: str
    anthropic_api_key: str
    cohere_api_key: str
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    frontend_url: str = "http://localhost:3000"
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
