"""Regression tests for security-hardening fixes (see security-audit-ledger)."""

import pytest


@pytest.fixture
def client():
    from webapp.app import create_app
    from webapp.config import TestingConfig

    app = create_app(TestingConfig)
    return app.test_client()


class TestSecurityHeaders:
    """F4: baseline security response headers on every response."""

    def test_headers_present_on_health(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert "frame-ancestors 'none'" in resp.headers.get(
            "Content-Security-Policy", ""
        )
        assert "max-age=" in resp.headers.get("Strict-Transport-Security", "")


_PRIVATE_SKILL_MD = """---
name: idor_probe_skill
description: A private skill used to test page-route access control
version: 1.0.0
author: Owner
triggers:
  - "idor probe"
industries:
  - general
tags:
  - test
---

# IDOR Probe Skill

Private content that must not be readable cross-user.
"""


class TestSkillPageIDOR:
    """F2: skill detail/edit pages must enforce private-skill ownership."""

    def _app_with_private_skill(self):
        from unittest.mock import MagicMock

        from webapp.app import create_app
        from webapp.config import TestingConfig
        from webapp.models import db
        from webapp.skills.custom_skill_service import CustomSkillService
        from webapp.skills.r2_skill_loader import R2SkillLoader

        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
            mock_r2 = MagicMock(spec=R2SkillLoader)
            mock_r2.is_enabled = False
            skill = CustomSkillService(r2_loader=mock_r2).create_skill(
                content=_PRIVATE_SKILL_MD,
                scope="private",
                user_id="owner-id",
                created_by="owner-id",
            )
            return app, skill.id

    def test_non_owner_blocked_on_detail_and_edit(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        app, skill_id = self._app_with_private_skill()
        client = app.test_client()
        attacker = SimpleNamespace(id="attacker-id")

        with patch(
            "webapp.blueprints.skills.get_current_user", return_value=attacker
        ):
            assert client.get(f"/skills/{skill_id}").status_code == 403
            assert client.get(f"/skills/{skill_id}/edit").status_code == 403

    def test_owner_allowed_on_detail(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        app, skill_id = self._app_with_private_skill()
        client = app.test_client()
        owner = SimpleNamespace(id="owner-id")

        with patch("webapp.blueprints.skills.get_current_user", return_value=owner):
            assert client.get(f"/skills/{skill_id}").status_code == 200


_SHARED_SKILL_MD = """---
name: shared_team_skill
description: A shared skill used to test cross-team mutation control
version: 1.0.0
author: TeamA
triggers:
  - "shared probe"
industries:
  - general
tags:
  - test
---

# Shared Team Skill

Team-scoped content that only the owning team may modify.
"""


def _make_shared_skill_for_team_a():
    """Within an app context: create team-A/team-B users + a team-A shared skill."""
    from unittest.mock import MagicMock

    from webapp.models import User, db
    from webapp.skills.custom_skill_service import CustomSkillService
    from webapp.skills.r2_skill_loader import R2SkillLoader

    db.create_all()
    owner = User(
        email="owner@a.com", password_hash="h", name="O", role="owner",
        team_id="team-A",
    )
    attacker = User(
        email="atk@b.com", password_hash="h", name="A", role="owner",
        team_id="team-B",
    )
    db.session.add_all([owner, attacker])
    db.session.commit()

    mock_r2 = MagicMock(spec=R2SkillLoader)
    mock_r2.is_enabled = False
    svc = CustomSkillService(r2_loader=mock_r2)
    skill = svc.create_skill(
        content=_SHARED_SKILL_MD,
        scope="shared",
        team_id="team-A",
        created_by=owner.id,
    )
    return svc, skill.id, owner.id, attacker.id


class TestSharedSkillTeamIsolation:
    """F3: shared-skill update/delete restricted to the owning team."""

    def test_cross_team_mutation_denied(self):
        from webapp.app import create_app
        from webapp.config import TestingConfig
        from webapp.skills.custom_skill_service import PermissionDeniedError

        app = create_app(TestingConfig)
        with app.app_context():
            svc, skill_id, _owner_id, attacker_id = _make_shared_skill_for_team_a()
            with pytest.raises(PermissionDeniedError):
                svc.delete_skill(skill_id, user_id=attacker_id)
            with pytest.raises(PermissionDeniedError):
                svc.update_skill(skill_id, _SHARED_SKILL_MD, user_id=attacker_id)

    def test_same_team_delete_allowed(self):
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        with app.app_context():
            svc, skill_id, owner_id, _attacker_id = _make_shared_skill_for_team_a()
            assert svc.delete_skill(skill_id, user_id=owner_id) is True


class TestSessionCookieSecure:
    """F5: session cookie must be Secure in production, not forced elsewhere."""

    def test_production_forces_secure_cookie(self):
        from webapp.config import ProductionConfig

        assert ProductionConfig.SESSION_COOKIE_SECURE is True

    def test_base_and_testing_do_not_force_secure(self):
        # Local HTTP and the test client rely on Secure NOT being forced here.
        from webapp.config import Config, TestingConfig

        assert getattr(Config, "SESSION_COOKIE_SECURE", False) is False
        assert getattr(TestingConfig, "SESSION_COOKIE_SECURE", False) is False
