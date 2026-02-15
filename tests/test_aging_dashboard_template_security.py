"""Security regression checks for aging dashboard template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "aging_dashboard.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_aging_dashboard_uses_safe_dom_nodes_for_dynamic_contact_text():
    source = _template_source()

    assert "name.textContent = String(alert.contact_name ?? '');" in source
    assert "tr.appendChild(createTextCell('px-4 py-3 text-sm font-medium text-gray-900', contact.contact_name));" in source
    assert "function createTextCell(className, value)" in source


def test_aging_dashboard_encodes_as_at_date_in_requests():
    source = _template_source()

    assert "new URLSearchParams({ as_at_date: asAtDate })" in source
    assert "/aging-dashboard/api/generate?" in source
    assert "/aging-dashboard/api/download?" in source
