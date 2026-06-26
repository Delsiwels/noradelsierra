"""Tests for rate-limit storage backend selection (Redis when available)."""

from webapp.extensions import _resolve_storage_uri


def test_defaults_to_in_memory(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert _resolve_storage_uri() == "memory://"


def test_uses_redis_url_when_set(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://default:pw@host:6379")
    assert _resolve_storage_uri() == "redis://default:pw@host:6379"


def test_explicit_storage_uri_takes_precedence(monkeypatch):
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "redis://explicit:6379")
    monkeypatch.setenv("REDIS_URL", "redis://fallback:6379")
    assert _resolve_storage_uri() == "redis://explicit:6379"
