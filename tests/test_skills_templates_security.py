"""Security regression checks for skills create/edit templates."""

from pathlib import Path


def _read_template(name: str) -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "skills"
        / name
    )
    return template_path.read_text(encoding="utf-8")


def test_skills_create_template_escapes_validation_and_uses_safe_message_rendering():
    source = _read_template("create.html")

    assert "function escapeHtml(value)" in source
    assert "const metadataName = escapeHtml(data.metadata?.name || '');" in source
    assert "validationResult.innerHTML = `<div class=\"validation-result invalid\">${escapeHtml(data.error)}</div>`;" in source
    assert "container.textContent = String(text ?? '');" in source


def test_skills_edit_template_escapes_validation_and_uses_safe_message_rendering():
    source = _read_template("edit.html")

    assert "function escapeHtml(value)" in source
    assert "const metadataName = escapeHtml(data.metadata?.name || '');" in source
    assert "validationResult.innerHTML = `<div class=\"validation-result invalid\">${escapeHtml(data.error)}</div>`;" in source
    assert "container.textContent = String(text ?? '');" in source
