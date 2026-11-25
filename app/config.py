"""Centralize application settings. Deployment secrets come from the environment or .env."""

from functools import lru_cache
from typing import Final, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PUBLIC_OWNER_ID: Final = "public"


class Settings(BaseSettings):
    """Load and validate the service's environment-backed configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    postgres_user: str
    postgres_password: str = Field(repr=False)
    postgres_db: str
    database_url: str = Field(repr=False)

    ollama_base_url: str = "http://localhost:11434"
    embed_model: str = "bge-m3"
    embed_dimensions: int = 1024
    embedding_batch_size: int = Field(default=16, gt=0)
    fallback_llm_model: str = "qwen2.5:3b"

    llm_provider: str = "groq"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: SecretStr
    llm_model: str = "openai/gpt-oss-20b"
    judge_model: str = "qwen/qwen3.8-27b"
    guard_model: str = "meta-llama/llama-prompt-guard-2-86m"
    llm_max_tokens: int = 400
    jwt_secret: SecretStr

    chunk_strategy: Literal["fixed", "structure"] = "structure"
    chunk_size_words: int = 120
    chunk_overlap_words: int = 25
    chunk_max_words: int = 200
    top_k: int = 4
    retrieval_mode: Literal["dense", "hybrid"] = "hybrid"
    candidate_k: int = Field(default=20, gt=0)
    rrf_k: int = Field(default=60, ge=0)
    min_similarity: float = Field(default=0.45, ge=-1, le=1)
    max_question_chars: int = Field(default=1000, gt=0)
    llm_temperature: float = 0.1
    rate_limit_ask: str = "20/minute"
    rate_limit_upload: str = "30/minute"
    # Groq free tier. Set actual prices for paid tiers.
    cost_per_million_input_tokens: float = Field(default=0.0, ge=0)
    cost_per_million_output_tokens: float = Field(default=0.0, ge=0)
    max_upload_mb: int = 10
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    database_timeout_seconds: float = Field(default=30.0, gt=0)
    cors_allowed_origin: str = "http://localhost:5173"

    @property
    def max_upload_bytes(self) -> int:
        """Return the configured upload limit in bytes."""

        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
