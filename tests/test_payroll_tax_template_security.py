"""Security regression checks for payroll tax template rendering."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "payroll_tax.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_payroll_tax_template_avoids_innerhtml_for_state_rate_rows():
    source = _template_source()

    assert "function createTextCell(className, value)" in source
    assert "tr.appendChild(createTextCell(" in source
    assert "tr.innerHTML = `" not in source


def test_payroll_tax_template_uses_urlsearchparams_for_query_strings():
    source = _template_source()

    assert "new URLSearchParams({" in source
    assert "params.toString()" in source
    assert "/payroll-tax/api/generate?" in source
    assert "/payroll-tax/api/download?" in source
