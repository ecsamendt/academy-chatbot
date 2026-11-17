from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://coach:coach@localhost:5432/coach"

    openai_api_key: str = ""
    answer_model: str = "gpt-5"
    classify_model: str = "gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    transcribe_model: str = "whisper-1"

    member_token_secret: str = ""
    webhook_secret: str = ""
    wp_ingest_secret: str = ""
    admin_api_key: str = ""

    wp_base_url: str = "https://academy.susociodenegocios.com"
    vimeo_access_token: str = ""

    cors_origins: str = "https://academy.susociodenegocios.com"

    match_strong: float = 0.50
    match_partial: float = 0.35
    top_k: int = 6
    max_answer_tokens: int = 900

    work_dir: Path = Path("var")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
