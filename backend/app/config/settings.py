"""
Configuration Management

Handles environment variables and secrets for different deployment contexts:
- Development (local .env files)
- Production (environment variables)
- Streamlit Cloud (st.secrets)
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """
    Application configuration.
    
    Loads from environment variables with fallback to .env file.
    """
    
    # Database Configuration
    database_url: str = Field(
        ...,
        alias="DATABASE_URL",
        description="PostgreSQL connection string"
    )
    
    # AI Configuration
    gemini_api_key: str = Field(
        ...,
        alias="GEMINI_API_KEY",
        description="Google Gemini API key"
    )
    
    # Application Settings
    app_name: str = Field(
        default="Akcion",
        alias="APP_NAME"
    )
    
    app_version: str = Field(
        default="1.0.0",
        alias="APP_VERSION"
    )
    
    # API Settings (for FastAPI)
    api_host: str = Field(
        default="0.0.0.0",
        alias="API_HOST"
    )
    
    api_port: int = Field(
        default=8000,
        alias="API_PORT"
    )
    
    # CORS Settings
    cors_origins: str | list[str] = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:5174",
        alias="CORS_ORIGINS"
    )
    
    # Debug mode
    debug: bool = Field(
        default=False,
        alias="DEBUG"
    )
    
    @field_validator('cors_origins', mode='after')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # Try JSON first
            import json
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                # Fallback to comma-separated
                return [origin.strip() for origin in v.split(',')]
        return v
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


# ==============================================================================
# Singleton Instance
# ==============================================================================

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get application settings (singleton pattern).
    
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

def load_from_streamlit_secrets():
    """
    Load configuration from Streamlit secrets.
    
    For use in the existing Streamlit app during migration.
    Sets environment variables so Settings can load them.
    
    Usage:
        import streamlit as st
        from backend.app.config import load_from_streamlit_secrets
        
        load_from_streamlit_secrets()
        settings = get_settings()
    """
    try:
        import streamlit as st
        
        if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
            os.environ["DATABASE_URL"] = st.secrets["postgres"]["url"]
        
        # Gemini API key might be in secrets or set in Streamlit sidebar
        # This is a bridge function to help during migration
        
    except ImportError:
        # Streamlit not available - normal FastAPI mode
        pass
