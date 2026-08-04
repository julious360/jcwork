"""Typed runtime settings.

Every secret arrives via environment variable; nothing is read from a checked-in file.
Nested settings use a ``__`` delimiter, e.g. ``ADAGENT_CLICKHOUSE__HOST``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path(__file__).parent


class ClickHouseSettings(BaseModel):
    host: str = "localhost"
    port: int = 8123
    database: str = "adagent"
    user: str = "adagent"
    password: SecretStr = SecretStr("adagent")
    secure: bool = False


class PostgresSettings(BaseModel):
    dsn: SecretStr = SecretStr("postgresql://adagent:adagent@localhost:5432/adagent")
    pool_min: int = 1
    pool_max: int = 8


class MetaSettings(BaseModel):
    """Meta Marketing API — used for mutations only.

    ``dry_run`` defaults to True so that a misconfigured deploy cannot spend money.
    """

    dry_run: bool = True
    access_token: SecretStr = SecretStr("")
    ad_account_id: str = "act_000000000000"
    app_secret: SecretStr = SecretStr("")
    api_version: str = "v25.0"
    access_tier: Literal["limited", "full"] = "limited"

    # Rate governor. Meta meters per ad account: reads cost 1 point, writes cost 3.
    # "limited" (the default developer tier) is documented by Meta as unsuitable for
    # production traffic, so we assume the small bucket unless told otherwise.
    points_per_read: int = 1
    points_per_write: int = 3
    rate_window_seconds: int = 300
    soft_utilization_pct: float = 75.0
    hard_utilization_pct: float = 90.0

    # Post-write verification is the only read path. Capped hard; see meta/write_client.py.
    allow_status_verification: bool = True
    verification_budget_pct: float = 5.0

    @property
    def window_points(self) -> int:
        return 60 if self.access_tier == "limited" else 9000

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}"


class LLMSettings(BaseModel):
    anthropic_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    text_model: str = "claude-opus-5"
    vision_model: str = "claude-opus-5"
    image_model: str = "gemini-2.5-flash-image"
    max_tokens: int = 4096
    request_timeout_seconds: float = 120.0


class ResearchSettings(BaseModel):
    perplexity_api_key: SecretStr = SecretStr("")
    reddit_client_id: SecretStr = SecretStr("")
    reddit_client_secret: SecretStr = SecretStr("")
    reddit_user_agent: str = "adagent/0.1"
    cache_ttl_hours: int = 168


class CreativeSettings(BaseModel):
    heygen_api_key: SecretStr = SecretStr("")
    seedance_api_key: SecretStr = SecretStr("")
    artifact_dir: Path = Path("artifacts")
    max_validation_attempts: int = 3
    ffmpeg_binary: str = "ffmpeg"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADAGENT_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    meta: MetaSettings = Field(default_factory=MetaSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    creative: CreativeSettings = Field(default_factory=CreativeSettings)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.llm.anthropic_api_key.get_secret_value())

    @property
    def has_gemini(self) -> bool:
        return bool(self.llm.gemini_api_key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
