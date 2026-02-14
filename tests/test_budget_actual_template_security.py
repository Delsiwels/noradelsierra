"""Security regression checks for budget vs actual template rendering."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "budget_actual.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_budget_actual_template_avoids_innerhtml_for_dynamic_rows():
    source = _template_source()

    assert "function createTextCell(className, value)" in source
    assert "function createStatusCell(status)" in source
    assert "tr.appendChild(createTextCell(" in source
    assert "tr.innerHTML = `" not in source


def test_budget_actual_template_uses_urlsearchparams_for_urls():
    source = _template_source()

    assert "new URLSearchParams({" in source
    assert "params.toString()" in source
    assert "/budget-actual/api/generate?" in source
    assert "/budget-actual/api/download?" in source
