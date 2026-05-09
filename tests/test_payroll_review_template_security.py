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


def test_payroll_review_template_uses_dom_builders_for_dynamic_rows_and_results():
    source = _template_source()

    assert "function createComparisonRow(row)" in source
    assert "function createLeaveFlagRow(employee)" in source
    assert "function createUploadPreviewRow(employee)" in source
    assert "function createCreationResultRow(result)" in source
    assert "tr.innerHTML = `" not in source
    assert "summary.innerHTML =" not in source


def test_payroll_review_template_encodes_query_params():
    source = _template_source()

    assert "encodeURIComponent(draftId)" in source
    assert "encodeURIComponent(payRunId)" in source
