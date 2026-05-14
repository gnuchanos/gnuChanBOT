"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration; override via `.env` or process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str = Field(..., alias="DISCORD_TOKEN")
    discord_admin_ids: str = Field(default="", alias="DISCORD_ADMIN_IDS")
    discord_banned_ids: str = Field(default="", alias="DISCORD_BANNED_IDS")
    discord_guild_id: int | None = Field(default=None, alias="DISCORD_GUILD_ID")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db",
        alias="DATABASE_URL",
    )

    follow_check_interval_seconds: int = Field(
        default=120,
        ge=10,
        alias="FOLLOW_CHECK_INTERVAL_SECONDS",
    )
    roblox_http_timeout_seconds: float = Field(
        default=25.0,
        gt=0,
        alias="ROBLOX_HTTP_TIMEOUT_SECONDS",
    )
    roblox_max_retries: int = Field(default=4, ge=1, alias="ROBLOX_MAX_RETRIES")
    roblox_cache_ttl_seconds: float = Field(
        default=45.0,
        ge=0,
        alias="ROBLOX_CACHE_TTL_SECONDS",
    )

    follow_reward_points: int = Field(default=5, alias="FOLLOW_REWARD_POINTS")
    follow_penalty_points: int = Field(default=5, alias="FOLLOW_PENALTY_POINTS")

    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        alias="RATE_LIMIT_WINDOW_SECONDS",
    )
    rate_limit_max_commands: int = Field(
        default=15,
        ge=1,
        alias="RATE_LIMIT_MAX_COMMANDS",
    )

    cooldown_register_seconds: int = Field(
        default=30,
        ge=0,
        alias="COOLDOWN_REGISTER_SECONDS",
    )
    cooldown_tasks_seconds: int = Field(default=10, ge=0, alias="COOLDOWN_TASKS_SECONDS")
    cooldown_leaderboard_seconds: int = Field(
        default=15,
        ge=0,
        alias="COOLDOWN_LEADERBOARD_SECONDS",
    )
    cooldown_check_seconds: int = Field(default=25, ge=0, alias="COOLDOWN_CHECK_SECONDS")
    cooldown_redemption_seconds: int = Field(default=120, ge=0, alias="COOLDOWN_REDEMPTION_SECONDS")
    cooldown_taleplerim_seconds: int = Field(default=12, ge=0, alias="COOLDOWN_TALEPLERIM_SECONDS")

    bot_command_prefix: str = Field(default="$", alias="BOT_COMMAND_PREFIX")

    max_single_redemption: int = Field(
        default=50_000,
        ge=0,
        alias="MAX_SINGLE_REDEMPTION",
    )
    max_pending_redemptions_per_user: int = Field(
        default=2,
        ge=1,
        alias="MAX_PENDING_REDEMPTIONS_PER_USER",
    )

    ffmpeg_path: str | None = Field(default=None, alias="FFMPEG_PATH")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @staticmethod
    def _parse_csv_int_ids(raw: str) -> set[int]:
        out: set[int] = set()
        for part in (raw or "").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.add(int(part))
            except ValueError:
                continue
        return out

    def admin_id_set(self) -> set[int]:
        return self._parse_csv_int_ids(self.discord_admin_ids)

    def banned_id_set(self) -> set[int]:
        """Discord kullanıcı ID’leri — sunucuda slash ve prefix komutlarında engellenir."""

        return self._parse_csv_int_ids(self.discord_banned_ids)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton suitable for import-time use."""

    return Settings()  # type: ignore[call-arg]
