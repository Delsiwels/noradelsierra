"""Tests for optional blueprint registration behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Blueprint, Flask

import webapp.app as app_module


def test_register_optional_blueprint_success(monkeypatch):
    app = Flask(__name__)
    module = SimpleNamespace(optional_bp=Blueprint("optional_bp", __name__))

    monkeypatch.setattr(app_module.importlib, "import_module", lambda _path: module)

    assert app_module._register_optional_blueprint(
        app, "webapp.blueprints.optional_mod", "optional_bp"
    )
    assert "optional_bp" in app.blueprints


def test_register_optional_blueprint_missing_module_logs_warning(monkeypatch):
    app = Flask(__name__)
    warning_mock = MagicMock()
    exception_mock = MagicMock()

    missing_exc = ModuleNotFoundError(
        "No module named 'webapp.blueprints.missing_optional'"
    )
    missing_exc.name = "webapp.blueprints.missing_optional"

    def _raise_missing(_path: str):
        raise missing_exc

    monkeypatch.setattr(app_module.importlib, "import_module", _raise_missing)
    monkeypatch.setattr(app_module.logger, "warning", warning_mock)
    monkeypatch.setattr(app_module.logger, "exception", exception_mock)

    result = app_module._register_optional_blueprint(
        app, "webapp.blueprints.missing_optional", "missing_bp"
    )

    assert result is False
    warning_mock.assert_called_once()
    exception_mock.assert_not_called()


def test_register_optional_blueprint_missing_dependency_logs_exception(monkeypatch):
    app = Flask(__name__)
    warning_mock = MagicMock()
    exception_mock = MagicMock()

    dependency_exc = ModuleNotFoundError("No module named 'third_party_lib'")
    dependency_exc.name = "third_party_lib"

    def _raise_dependency_error(_path: str):
        raise dependency_exc

    monkeypatch.setattr(app_module.importlib, "import_module", _raise_dependency_error)
    monkeypatch.setattr(app_module.logger, "warning", warning_mock)
    monkeypatch.setattr(app_module.logger, "exception", exception_mock)

    result = app_module._register_optional_blueprint(
        app, "webapp.blueprints.optional_with_dependency", "ask_fin_bp"
    )

    assert result is False
    exception_mock.assert_called_once()
    warning_mock.assert_not_called()


def test_register_optional_blueprint_missing_symbol_logs_warning(monkeypatch):
    app = Flask(__name__)
    warning_mock = MagicMock()
    exception_mock = MagicMock()
    module = SimpleNamespace()

    monkeypatch.setattr(app_module.importlib, "import_module", lambda _path: module)
    monkeypatch.setattr(app_module.logger, "warning", warning_mock)
    monkeypatch.setattr(app_module.logger, "exception", exception_mock)

    result = app_module._register_optional_blueprint(
        app, "webapp.blueprints.optional_without_symbol", "ask_fin_bp"
    )

    assert result is False
    warning_mock.assert_called_once()
    exception_mock.assert_not_called()
