"""Security regression checks for dashboard template rendering."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "dashboard.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_dashboard_template_uses_dom_nodes_for_deadline_rows():
    source = _template_source()

    assert "const row = document.createElement('div');" in source
    assert "labelNode.textContent = String(label);" in source
    assert "dueNode.textContent = `Due ${String(d.due_date_str ?? '')}`;" in source


def test_dashboard_template_encodes_export_date_params():
    source = _template_source()

    assert "encodeURIComponent(from)" in source
    assert "encodeURIComponent(to)" in source
