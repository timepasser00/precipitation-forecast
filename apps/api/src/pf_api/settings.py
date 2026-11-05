"""Runtime settings, read from ``PF_API_*`` environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PF_API_", env_file=".env", extra="ignore")

    storage_url: str = "data/processed/store"
    """Where the pipeline publishes: a directory, or ``s3://bucket/prefix?endpoint_url=...``."""

    data_base_url: str = "/data"
    """Public base URL clients use to fetch tiles and cubes (the CDN in production)."""

    serve_data: bool = False
    """Serve ``/data/*`` from storage. For local development only; production uses the CDN."""

    config_path: str | None = None
    """Registry file for source metadata; defaults to ``config/sources.yaml``."""

    cors_origins: list[str] = ["http://localhost:4200"]
    manifest_ttl_s: float = 30.0
    cube_cache_size: int = 6
