"""Application configuration via Pydantic Settings.

Environment variables prefixed with ZENITH_ override defaults.
Config file at ~/.zenith/config.toml is loaded on startup.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ZenithSettings(BaseSettings):
    """Global configuration for Zenith Unified."""

    model_config = SettingsConfigDict(
        env_prefix="ZENITH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Paths --
    config_dir: Path = Field(default_factory=lambda: Path.home() / ".zenith")
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2] / "data")
    log_dir: Path = Field(default_factory=lambda: Path.home() / ".zenith" / "logs")
    backup_dir: Path = Field(default_factory=lambda: Path.home() / ".zenith" / "backups")

    # -- ATLAS Knowledge Base --
    atlas_path: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "data" / "DEEP_ATLAS.md")

    # -- ADB --
    adb_path: str | None = None
    adb_timeout: int = 30

    # -- Safety --
    dry_run: bool = False
    require_consent: bool = True
    auto_backup: bool = True

    # -- AI Provider --
    ai_provider: str = "local"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "mistral-7b-instruct"
    mistral_api_key: str | None = None

    # -- ChromaDB --
    chroma_path: Path = Field(default_factory=lambda: Path.home() / ".zenith" / "chroma_db")
    chroma_collection: str = "zenith_knowledge"

    # -- Server --
    server_host: str = "127.0.0.1"
    server_port: int = 8089

    # -- Logging --
    log_level: str = "INFO"
    log_retention: str = "7 days"

    # -- GUI --
    gui_theme: str = "catppuccin_mocha"
    gui_framework: str = "pyside6"

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        for d in (self.config_dir, self.log_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)


_settings: ZenithSettings | None = None


def get_settings() -> ZenithSettings:
    """Get the global settings singleton."""
    global _settings
    if _settings is None:
        _settings = ZenithSettings()
        _settings.ensure_dirs()
    return _settings
