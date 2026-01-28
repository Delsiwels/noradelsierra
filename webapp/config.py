"""Application configuration."""

import os


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
    DEBUG = False
    TESTING = False

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    # Fix for Railway PostgreSQL URL format
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Cloudflare R2 Storage
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
    R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "skills-storage")

    # R2 storage toggle (for graceful degradation)
    R2_STORAGE_ENABLED = os.environ.get("R2_STORAGE_ENABLED", "true").lower() == "true"

    # AI Provider Configuration
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    AI_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-4-20250514")
    AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "2048"))

    # OpenAI Configuration
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4-turbo-preview")

    # Token Usage Limits
    DEFAULT_MONTHLY_TOKEN_LIMIT = int(
        os.environ.get("DEFAULT_MONTHLY_TOKEN_LIMIT", "100000")
    )
    TOKEN_LIMIT_ENFORCEMENT = (
        os.environ.get("TOKEN_LIMIT_ENFORCEMENT", "true").lower() == "true"
    )

    # Conversation Retention
    CONVERSATION_RETENTION_DAYS = int(
        os.environ.get("CONVERSATION_RETENTION_DAYS", "30")
    )

    # Default system prompt
    DEFAULT_SYSTEM_PROMPT = os.environ.get(
        "DEFAULT_SYSTEM_PROMPT",
        "You are a helpful AI assistant.",
    )


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    R2_STORAGE_ENABLED = False
    # Use mock AI client in tests
    ANTHROPIC_API_KEY = None
    AI_PROVIDER = "anthropic"
