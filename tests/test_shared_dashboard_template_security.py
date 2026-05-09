"""Security regression checks for shared dashboard template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "sharing"
        / "shared_dashboard.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_shared_dashboard_encodes_team_ids_for_navigation():
    source = _template_source()

    assert "encodeURIComponent(String(teamId ?? ''))" in source
    assert "window.location.href = `/chat?team=${encodeURIComponent(teamId)}`;" in source


def test_shared_dashboard_removes_inline_onclick_and_escapes_access_levels():
    source = _template_source()

    assert "onclick=\"window.location.href='/chat?team=" not in source
    assert "function createGridClientCard(sharedTeam, index)" in source
    assert "function createListClientRow(sharedTeam)" in source
    assert "badge.textContent = expiringSoon ? 'Expiring' : accessLevelLabel;" in source
    assert "grid.innerHTML = clients.map(" not in source
    assert "container.innerHTML = clients.map(" not in source
