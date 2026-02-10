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

    # Deepseek Configuration (OpenAI-compatible API)
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

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

    # Session config
    PERMANENT_SESSION_LIFETIME = int(
        os.environ.get("PERMANENT_SESSION_LIFETIME", "86400")
    )  # 24 hours default
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Default system prompt
    DEFAULT_SYSTEM_PROMPT = os.environ.get(
        "DEFAULT_SYSTEM_PROMPT",
        "You are a helpful AI assistant.",
    )

    # Startup / readiness checks
    STARTUP_CONFIG_AUDIT_FAIL_FAST = (
        os.environ.get("STARTUP_CONFIG_AUDIT_FAIL_FAST", "false").lower() == "true"
    )
    ALEMBIC_SCRIPT_LOCATION = os.environ.get("ALEMBIC_SCRIPT_LOCATION", "migrations")

    # Background job runtime guardrails
    BACKGROUND_JOB_MAX_RUNTIME_SECONDS = int(
        os.environ.get("BACKGROUND_JOB_MAX_RUNTIME_SECONDS", "300")
    )
    BACKGROUND_JOB_MAX_RETRIES = int(os.environ.get("BACKGROUND_JOB_MAX_RETRIES", "1"))
    BACKGROUND_JOB_RETRY_BACKOFF_SECONDS = float(
        os.environ.get("BACKGROUND_JOB_RETRY_BACKOFF_SECONDS", "2.0")
    )

    # Operational alerts
    OP_ALERTS_ENABLED = os.environ.get("OP_ALERTS_ENABLED", "false").lower() == "true"
    OP_ALERT_WEBHOOK_URL = os.environ.get("OP_ALERT_WEBHOOK_URL")
    OP_ALERT_SLACK_WEBHOOK_URL = os.environ.get("OP_ALERT_SLACK_WEBHOOK_URL")
    OP_ALERT_EMAIL_TO = os.environ.get("OP_ALERT_EMAIL_TO")
    OP_ALERT_EMAIL_FROM = os.environ.get("OP_ALERT_EMAIL_FROM", "noreply@finql.ai")
    OP_ALERT_COOLDOWN_SECONDS = int(os.environ.get("OP_ALERT_COOLDOWN_SECONDS", "300"))

    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

    # Runtime health snapshot persistence
    RUNTIME_HEALTH_SNAPSHOT_ENABLED = (
        os.environ.get("RUNTIME_HEALTH_SNAPSHOT_ENABLED", "true").lower() == "true"
    )
    RUNTIME_HEALTH_SNAPSHOT_RETENTION_DAYS = int(
        os.environ.get("RUNTIME_HEALTH_SNAPSHOT_RETENTION_DAYS", "30")
    )
    RUNTIME_HEALTH_SNAPSHOT_MAX_ROWS = int(
        os.environ.get("RUNTIME_HEALTH_SNAPSHOT_MAX_ROWS", "2000")
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
