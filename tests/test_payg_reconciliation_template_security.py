"""Security regression checks for PAYG reconciliation template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "payg_reconciliation.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_payg_template_escapes_warning_and_pay_run_text():
    source = _template_source()

    assert "function escapeHtml(value)" in source
    assert "const warningText = escapeHtml(warning);" in source
    assert "const paymentDate = escapeHtml(pr.payment_date);" in source
    assert "const payRunStatus = escapeHtml(pr.status ?? 'Unknown');" in source


def test_payg_template_url_params_are_encoded():
    source = _template_source()

    assert "encodeURIComponent(fromDate)" in source
    assert "encodeURIComponent(toDate)" in source
