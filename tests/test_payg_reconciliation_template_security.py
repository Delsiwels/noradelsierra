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


def test_payg_template_uses_dom_builders_for_warnings_and_pay_runs():
    source = _template_source()

    assert "function createWarningBannerItem(warning)" in source
    assert "function createPayRunRow(payRun)" in source
    assert "statusEl.appendChild(createSummaryStatusBadge(result.status));" in source
    assert "tr.innerHTML = `" not in source
    assert "tfoot.innerHTML = `" not in source


def test_payg_template_url_params_are_encoded():
    source = _template_source()

    assert "encodeURIComponent(fromDate)" in source
    assert "encodeURIComponent(toDate)" in source
