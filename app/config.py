"""Application configuration and settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Configuration loaded from environment variables or defaults."""

    # Upstream Urja Portal credentials and endpoint
    urja_portal_url: str = Field(
        default="https://urja-ops.flockenergy.tech",
        description="Base URL of the Urja Meter Ops legacy portal",
    )
    urja_username: str = Field(
        default="operator@urja.local",
        description="Operator username for portal authentication",
    )
    urja_password: str = Field(
        default="urja-ops-2026",
        description="Operator password for portal authentication",
    )

    # API Server settings
    host: str = Field(default="0.0.0.0", description="Host address to bind")
    port: int = Field(default=8000, description="Port to listen on")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Cache & Sync settings
    cache_ttl_seconds: int = Field(
        default=300,
        description="Time-to-live for in-memory meter and transformer cache (seconds)",
    )
    auto_sync_on_startup: bool = Field(
        default=True,
        description="Whether to perform bulk sync from Urja portal upon service startup",
    )
    request_timeout_seconds: float = Field(
        default=30.0,
        description="HTTP client timeout for upstream portal requests",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
