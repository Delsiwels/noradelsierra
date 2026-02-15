"""Security regression checks for payroll review template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "payroll_review.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_payroll_review_template_escapes_dynamic_html_values():
    source = _template_source()

    assert "function escapeHtml(value)" in source
    assert "const employeeName = escapeHtml(row.name);" in source
    assert "const errorTitle = escapeHtml((emp.errors || []).join('; '));" in source
    assert "const resultError = escapeHtml(result.error);" in source


def test_payroll_review_template_encodes_query_params():
    source = _template_source()

    assert "encodeURIComponent(draftId)" in source
    assert "encodeURIComponent(payRunId)" in source
