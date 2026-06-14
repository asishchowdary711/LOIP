"""Central runtime configuration, sourced from environment variables.

Mirrors the variables documented in ``.env.example``. Import ``get_settings()``
rather than reading ``os.environ`` directly so config is parsed and validated
once.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- MinIO / object storage ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"  # noqa: S105 - dev default, override via env
    minio_use_ssl: bool = False

    # --- PostgreSQL ---
    database_url: str = "postgresql+asyncpg://loip:changeme@localhost:5432/loip"

    # --- Kafka (async domain event pipeline) ---
    kafka_bootstrap_servers: str = "localhost:9092"

    # --- Neo4j (identity graph / graph fraud) ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"  # noqa: S105 - dev default, override via env

    # --- Data residency (RBI localization) ---
    data_region: str = "ap-south-1"
    enforce_data_residency: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
