from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMOODIE_", env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+asyncpg://smoodie:smoodie@localhost:5432/smoodie"
    # Review-gate thresholds: config, never exposed to clients (see docs/review-system.html §4).
    tier1_scoring_floor: float = 0.35
    tier2_offer_floor: float = 0.65
    audit_flag_ceiling: float = 0.20
    session_ttl_hours: int = 72


@lru_cache
def get_settings() -> Settings:
    return Settings()
