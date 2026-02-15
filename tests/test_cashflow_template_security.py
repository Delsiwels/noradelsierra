"""Security regression checks for cashflow statement template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "cashflow.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_cashflow_template_uses_text_nodes_for_grouped_line_items():
    source = _template_source()

    assert "const labelSpan = document.createElement('span');" in source
    assert "labelSpan.textContent = String(label ?? '');" in source
    assert "const amountSpan = document.createElement('span');" in source
