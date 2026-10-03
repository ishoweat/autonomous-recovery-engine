from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Autonomous Recovery Engine"
    environment: str = "development"

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/recovery_engine",
        validation_alias="DATABASE_URL",
    )

    github_webhook_secret: str = Field(
        default="",
        validation_alias="GITHUB_WEBHOOK_SECRET",
    )

    github_token: str = Field(
        default="",
        validation_alias="GITHUB_TOKEN",
    )

    github_client_id: str = Field(
        default="",
        validation_alias="GITHUB_CLIENT_ID",
    )

    github_client_secret: str = Field(
        default="",
        validation_alias="GITHUB_CLIENT_SECRET",
    )

    github_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/api/auth/github/callback",
        validation_alias="GITHUB_REDIRECT_URI",
    )

    # Mock mode disabled for evaluator – always run real pipelines.
    allow_mock_mode: bool = Field(
        default=False,
        validation_alias="ALLOW_MOCK_MODE",
    )

    enable_llm_cache: bool = Field(
        default=False,
        validation_alias="ENABLE_LLM_CACHE",
    )

    shadow_mode: bool = Field(
        default=True,
        validation_alias="SHADOW_MODE",
    )

    webhook_max_body_bytes: int = Field(
        default=2_000_000,
        validation_alias="WEBHOOK_MAX_BODY_BYTES",
    )

    sse_heartbeat_seconds: float = Field(
        default=15.0,
        validation_alias="SSE_HEARTBEAT_SECONDS",
    )

    sse_queue_size: int = Field(
        default=100,
        validation_alias="SSE_QUEUE_SIZE",
    )

    # Nebius Token Factory
    nebius_api_key: str = Field(
        default="",
        validation_alias="NEBIUS_API_KEY",
    )

    nebius_base_url: str = Field(
        default="https://api.tokenfactory.nebius.com/v1/",
        validation_alias="NEBIUS_BASE_URL",
    )

    nebius_model: str = Field(
        default="nvidia/Nemotron-3_5-Lightning",
        validation_alias="NEBIUS_MODEL",
    )

    nemotron_model: str | None = Field(
        default=None,
        validation_alias="NEMOTRON_MODEL",
    )

    nebius_fast_model: str | None = Field(
        default=None,
        validation_alias="NEBIUS_FAST_MODEL",
    )

    nebius_strong_model: str | None = Field(
        default=None,
        validation_alias="NEBIUS_STRONG_MODEL",
    )

    @property
    def active_nemotron_model(self) -> str:
        return self.nemotron_model or self.nebius_model
        
    @property
    def active_fast_model(self) -> str:
        return self.nebius_fast_model or self.active_nemotron_model

    @property
    def active_strong_model(self) -> str:
        return self.nebius_strong_model or self.active_nemotron_model

    price_per_mtok_fast: float | None = Field(
        default=None,
        validation_alias="PRICE_PER_MTOK_FAST",
    )

    price_per_mtok_strong: float | None = Field(
        default=None,
        validation_alias="PRICE_PER_MTOK_STRONG",
    )

    nebius_temperature: float = Field(
        default=0.1,
        validation_alias="NEBIUS_TEMPERATURE",
    )

    nebius_max_tokens: int = Field(
        default=8192,
        validation_alias="NEBIUS_MAX_TOKENS",
    )

    nebius_timeout_seconds: float = Field(
        default=90.0,
        validation_alias="NEBIUS_TIMEOUT_SECONDS",
    )

    # LangGraph
    langgraph_checkpoint_setup: bool = Field(
        default=True,
        validation_alias="LANGGRAPH_CHECKPOINT_SETUP",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings object."""

    return Settings()
