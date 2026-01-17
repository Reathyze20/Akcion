"""
Configuration Management

Handles environment variables and secrets for different deployment contexts:
- Development (local .env files)
- Production (environment variables)
- Streamlit Cloud (st.secrets)

Clean Code Principles Applied:
- Single Responsibility: Configuration only
- Singleton pattern for settings
- Type-safe with Pydantic validation
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.
    
    Loads from environment variables with fallback to .env file.
    All sensitive values should be set via environment variables.
    """
    
    # Database Configuration
    database_url: str = Field(
        ...,
        alias="DATABASE_URL",
        description="PostgreSQL connection string",
    )
    
    # AI Configuration
    gemini_api_key: str = Field(
        ...,
        alias="GEMINI_API_KEY",
        description="Google Gemini API key",
    )
    
    # Market Data API
    massive_api_key: str | None = Field(
        default=None,
        alias="MASSIVE_API_KEY",
        description="Massive.com (Polygon.io) API key for US market data",
    )
    
    finnhub_api_key: str | None = Field(
        default=None,
        alias="FINNHUB_API_KEY",
        description="Finnhub.io API key for global market data (non-US stocks)",
    )
    
    # Application Settings
    app_name: str = Field(default="Akcion", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    
    # API Settings (for FastAPI)
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    
    # CORS Settings
    cors_origins: str | list[str] = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:5174",
        alias="CORS_ORIGINS",
    )
    
    # Debug mode
    debug: bool = Field(default=False, alias="DEBUG")
    
    @field_validator("cors_origins", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return [origin.strip() for origin in v.split(",")]
        return v
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# ==============================================================================
# Singleton Instance
# ==============================================================================

_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get application settings (singleton pattern).
    
    Uses module-level caching to avoid repeated environment reads.
    
    Returns:
        Settings object loaded from environment
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# ==============================================================================
# Streamlit Integration Helper
# ==============================================================================

def load_from_streamlit_secrets() -> None:
    """
    Load configuration from Streamlit secrets.
    
    For use in the existing Streamlit app during migration.
    Sets environment variables so Settings can load them.
    
    Usage:
        from backend.app.config import load_from_streamlit_secrets
        
        load_from_streamlit_secrets()
        settings = get_settings()
    """
    try:
        import streamlit as st
        
        if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
            os.environ["DATABASE_URL"] = st.secrets["postgres"]["url"]
        
    except ImportError:
        # Streamlit not available - normal FastAPI mode
        pass
