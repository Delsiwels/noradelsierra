"""Security regression checks for skills index template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "skills"
        / "index.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_skills_index_template_sanitizes_ids_and_css_tokens():
    source = _template_source()

    assert "const skillId = encodeURIComponent(String(skill.owner_id || ''));" in source
    assert "const sourceClass = sanitizeCssToken(skill.source || currentTab);" in source
    assert "function sanitizeCssToken(value)" in source


def test_skills_index_template_escapes_display_values():
    source = _template_source()

    assert "const safeSkillName = escapeHtml(skill.name || '');" in source
    assert "const safeSkillDescription = escapeHtml(skill.description || 'No description');" in source
    assert "const safeSkillVersion = escapeHtml(skill.version || '1.0.0');" in source
