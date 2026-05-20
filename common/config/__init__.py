from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    url: str
    pool_size: int = 10
    max_overflow: int = 20


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"


class AdapterSettings(BaseModel):
    event_bus: str = "redis_streams"
    object_store: str = "local_fs"
    secret_store: str = "env"
    metrics: str = "prometheus"


class SentinelSettings(BaseModel):
    enabled: bool = True
    run_mode: Literal["sync", "async", "shadow"] = "async"


class RetentionSettings(BaseModel):
    hot_days: int = 30
    warm_days: int = 90
    cold_days: int = 365
    delete_after_days: int = 730


class PlatformSettings(BaseModel):
    signing_key_private: str = ""
    signing_key_public: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOX_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    secret_key: str = "change-me"
    database: DatabaseSettings
    redis: RedisSettings = RedisSettings()
    adapters: AdapterSettings = AdapterSettings()
    sentinel: SentinelSettings = SentinelSettings()
    retention: RetentionSettings = RetentionSettings()
    platform: PlatformSettings = PlatformSettings()


settings = Settings()
