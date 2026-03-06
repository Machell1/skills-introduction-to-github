"""
FNID Application Configuration

Environment-based configuration with sensible defaults for development
and strict requirements for production.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("FNID_SECRET_KEY")
    DB_PATH = os.environ.get(
        "FNID_DB_PATH",
        str(BASE_DIR / "data" / "fnid.db"),
    )
    UPLOAD_DIR = os.environ.get(
        "FNID_UPLOAD_DIR",
        str(BASE_DIR / "data" / "uploads"),
    )
    EXPORT_DIR = os.environ.get(
        "FNID_EXPORT_DIR",
        str(BASE_DIR / "data" / "exports"),
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    SECRET_KEY = os.environ.get("FNID_SECRET_KEY", "fnid-dev-key-not-for-production")


class ProductionConfig(Config):
    """Production configuration - SECRET_KEY must be set via env var."""

    DEBUG = False

    def __init__(self):
        if not self.SECRET_KEY:
            raise RuntimeError(
                "FNID_SECRET_KEY environment variable must be set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    SECRET_KEY = "test-secret-key-not-for-production"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
