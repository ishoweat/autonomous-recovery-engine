from __future__ import annotations

import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtFlags(BaseSettings):
    """Typed feature flags for Autonomous Recovery Engine extension modules."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    enable_persistence: bool = Field(
        default=False,
        validation_alias="ENABLE_PERSISTENCE",
    )
    enable_webhook_ingress: bool = Field(
        default=False,
        validation_alias="ENABLE_WEBHOOK_INGRESS",
    )
    enable_approval_gate: bool = Field(
        default=False,
        validation_alias="ENABLE_APPROVAL_GATE",
    )
    enable_block_escalation: bool = Field(
        default=False,
        validation_alias="ENABLE_BLOCK_ESCALATION",
    )
    enable_sandbox_hardening: bool = Field(
        default=False,
        validation_alias="ENABLE_SANDBOX_HARDENING",
    )
    enable_auto_merge: bool = Field(
        default=False,
        validation_alias="ENABLE_AUTO_MERGE",
    )
    enable_post_merge_verify: bool = Field(
        default=False,
        validation_alias="ENABLE_POST_MERGE_VERIFY",
    )
    enable_demo_scenarios: bool = Field(
        default=False,
        validation_alias="ENABLE_DEMO_SCENARIOS",
    )
    enable_benchmark_view: bool = Field(
        default=False,
        validation_alias="ENABLE_BENCHMARK_VIEW",
    )
    enable_tavily_research: bool = Field(
        default=False,
        validation_alias="ENABLE_TAVILY_RESEARCH",
    )
    enable_rate_limiting: bool = Field(
        default=False,
        validation_alias="ENABLE_RATE_LIMITING",
    )
    public_demo_mode: bool = Field(
        default=False,
        validation_alias="PUBLIC_DEMO_MODE",
    )
    enable_fork_and_pr: bool = Field(
        default=False,
        validation_alias="ENABLE_FORK_AND_PR",
    )



@lru_cache
def get_flags() -> ExtFlags:
    """Return cached extension feature flags."""
    return ExtFlags()
