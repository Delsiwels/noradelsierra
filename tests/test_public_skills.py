"""Tests for public skills (tax_agent, accountant, ato_compliance, bas_review)."""

from pathlib import Path

import pytest

from webapp.app import create_app
from webapp.config import TestingConfig
from webapp.skills import SkillLoader, SkillRegistry


class TestPublicSkillsDirectory:
    """Tests for public skills directory structure."""

    @pytest.fixture
    def public_skills_dir(self):
        """Get the public skills directory path."""
        return Path(__file__).parent.parent / "webapp" / "skills" / "public"

    def test_public_skills_directory_exists(self, public_skills_dir):
        """Test that public skills directory exists."""
        assert public_skills_dir.exists()
        assert public_skills_dir.is_dir()

    def test_tax_agent_skill_exists(self, public_skills_dir):
        """Test that tax_agent skill exists."""
        tax_agent_dir = public_skills_dir / "tax_agent"
        assert tax_agent_dir.exists()
        assert (tax_agent_dir / "SKILL.md").exists()

    def test_accountant_skill_exists(self, public_skills_dir):
        """Test that accountant skill exists."""
        accountant_dir = public_skills_dir / "accountant"
        assert accountant_dir.exists()
        assert (accountant_dir / "SKILL.md").exists()

    def test_ato_compliance_skill_exists(self, public_skills_dir):
        """Test that ato_compliance skill exists."""
        ato_dir = public_skills_dir / "ato_compliance"
        assert ato_dir.exists()
        assert (ato_dir / "SKILL.md").exists()

    def test_bas_review_skill_exists(self, public_skills_dir):
        """Test that bas_review skill exists."""
        bas_review_dir = public_skills_dir / "bas_review"
        assert bas_review_dir.exists()
        assert (bas_review_dir / "SKILL.md").exists()


class TestTaxAgentSkill:
    """Tests for tax_agent skill."""

    @pytest.fixture
    def skill_path(self):
        """Get path to tax_agent skill."""
        return (
            Path(__file__).parent.parent
            / "webapp"
            / "skills"
            / "public"
            / "tax_agent"
            / "SKILL.md"
        )

    @pytest.fixture
    def loader(self):
        """Create skill loader."""
        return SkillLoader()

    def test_tax_agent_loads_successfully(self, loader, skill_path):
        """Test that tax_agent skill loads without errors."""
        skill = loader.load_from_path(skill_path)

        assert skill is not None
        assert skill.name == "tax_agent"

    def test_tax_agent_metadata(self, loader, skill_path):
        """Test tax_agent skill metadata."""
        skill = loader.load_from_path(skill_path)

        assert skill.metadata.name == "tax_agent"
        assert "tax" in skill.description.lower()
        assert skill.metadata.version == "1.1.0"
        assert skill.metadata.tax_agent_approved is True

    def test_tax_agent_triggers(self, loader, skill_path):
        """Test tax_agent skill triggers."""
        skill = loader.load_from_path(skill_path)

        triggers = skill.triggers
        assert len(triggers) > 0
        assert any("tax" in t.lower() for t in triggers)

    def test_tax_agent_industries(self, loader, skill_path):
        """Test tax_agent skill industries."""
        skill = loader.load_from_path(skill_path)

        assert "accounting" in skill.industries
        assert "finance" in skill.industries

    def test_tax_agent_content(self, loader, skill_path):
        """Test tax_agent skill content."""
        skill = loader.load_from_path(skill_path)

        content = skill.content.lower()
        assert "income tax" in content or "tax agent" in content
        assert len(skill.content) > 100  # Should have substantial content


class TestAccountantSkill:
    """Tests for accountant skill."""

    @pytest.fixture
    def skill_path(self):
        """Get path to accountant skill."""
        return (
            Path(__file__).parent.parent
            / "webapp"
            / "skills"
            / "public"
            / "accountant"
            / "SKILL.md"
        )

    @pytest.fixture
    def loader(self):
        """Create skill loader."""
        return SkillLoader()

    def test_accountant_loads_successfully(self, loader, skill_path):
        """Test that accountant skill loads without errors."""
        skill = loader.load_from_path(skill_path)

        assert skill is not None
        assert skill.name == "accountant"

    def test_accountant_metadata(self, loader, skill_path):
        """Test accountant skill metadata."""
        skill = loader.load_from_path(skill_path)

        assert skill.metadata.name == "accountant"
        assert (
            "accountant" in skill.description.lower()
            or "financial" in skill.description.lower()
        )
        assert skill.metadata.version == "1.1.0"

    def test_accountant_triggers(self, loader, skill_path):
        """Test accountant skill triggers."""
        skill = loader.load_from_path(skill_path)

        triggers = skill.triggers
        assert len(triggers) > 0
        assert any(
            "financial" in t.lower() or "accountant" in t.lower() for t in triggers
        )

    def test_accountant_content(self, loader, skill_path):
        """Test accountant skill content."""
        skill = loader.load_from_path(skill_path)

        content = skill.content.lower()
        assert "aasb" in content or "financial" in content
        assert len(skill.content) > 100


class TestBasReviewSkill:
    """Tests for bas_review skill."""

    @pytest.fixture
    def skill_path(self):
        """Get path to bas_review skill."""
        return (
            Path(__file__).parent.parent
            / "webapp"
            / "skills"
            / "public"
            / "bas_review"
            / "SKILL.md"
        )

    @pytest.fixture
    def loader(self):
        """Create skill loader."""
        return SkillLoader()

    def test_bas_review_loads_successfully(self, loader, skill_path):
        """Test that bas_review skill loads without errors."""
        skill = loader.load_from_path(skill_path)

        assert skill is not None
        assert skill.name == "bas_review"

    def test_bas_review_metadata(self, loader, skill_path):
        """Test bas_review skill metadata."""
        skill = loader.load_from_path(skill_path)

        assert skill.metadata.name == "bas_review"
        assert "bas" in skill.description.lower()
        assert skill.metadata.version == "1.0.0"

    def test_bas_review_triggers_include_bas(self, loader, skill_path):
        """Test bas_review triggers include BAS review phrases."""
        skill = loader.load_from_path(skill_path)

        triggers = [t.lower() for t in skill.triggers]
        assert "run bas review" in triggers
        assert "review bas" in triggers


class TestPublicSkillsDiscovery:
    """Tests for public skills discovery via registry."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        return app

    def test_registry_discovers_public_skills(self, app):
        """Test that registry discovers public skills."""
        with app.app_context():
            registry = SkillRegistry()
            skills = registry.discover_skills()

            skill_names = [s.name for s in skills]
            assert "tax_agent" in skill_names
            assert "accountant" in skill_names
            assert "ato_compliance" in skill_names
            assert "bas_review" in skill_names

    def test_get_public_skill_by_name(self, app):
        """Test getting public skill by name."""
        with app.app_context():
            registry = SkillRegistry()

            skill = registry.get_skill("tax_agent")
            assert skill is not None
            assert skill.name == "tax_agent"
            assert skill.source == "public"


class TestPublicSkillsTriggerDetection:
    """Tests for public skills trigger detection."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app(TestingConfig)

    def test_tax_advice_triggers_tax_agent(self, app):
        """Test that tax-related messages trigger tax_agent skill."""
        with app.app_context():
            from webapp.skills import get_injector

            injector = get_injector()

            matches = injector.detect_skill_triggers("I need tax advice")

            skill_names = [m.skill.name for m in matches]
            assert "tax_agent" in skill_names

    def test_financial_statements_triggers_accountant(self, app):
        """Test that accounting messages trigger accountant skill."""
        with app.app_context():
            from webapp.skills import get_injector

            injector = get_injector()

            matches = injector.detect_skill_triggers("review my financial statements")

            skill_names = [m.skill.name for m in matches]
            assert "accountant" in skill_names

    def test_ato_triggers_tax_agent(self, app):
        """Test that ATO mention triggers tax_agent."""
        with app.app_context():
            from webapp.skills import get_injector

            injector = get_injector()

            matches = injector.detect_skill_triggers("ATO compliance question")

            skill_names = [m.skill.name for m in matches]
            assert "tax_agent" in skill_names

    def test_ato_compliance_triggers_compliance_skill(self, app):
        """Test that compliance phrasing triggers ato_compliance skill."""
        with app.app_context():
            from webapp.skills import get_injector

            injector = get_injector()

            matches = injector.detect_skill_triggers("Need ATO compliance BAS review")

            skill_names = [m.skill.name for m in matches]
            assert "ato_compliance" in skill_names

    def test_bas_review_phrase_triggers_bas_review_skill(self, app):
        """Test that BAS review phrasing triggers bas_review skill."""
        with app.app_context():
            from webapp.skills import get_injector

            injector = get_injector()

            matches = injector.detect_skill_triggers("Please run bas review for this quarter")

            skill_names = [m.skill.name for m in matches]
            assert "bas_review" in skill_names

    def test_aasb_triggers_accountant(self, app):
        """Test that AASB mention triggers accountant."""
        with app.app_context():
            from webapp.skills import get_injector

            injector = get_injector()

            matches = injector.detect_skill_triggers("What does AASB 16 say?")

            skill_names = [m.skill.name for m in matches]
            assert "accountant" in skill_names
