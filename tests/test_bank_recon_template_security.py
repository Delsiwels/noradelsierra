"""Security regression checks for bank reconciliation template rendering."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "bank_recon_status.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_bank_recon_template_escapes_dynamic_values():
    source = _template_source()

    assert "function createAccountRow(account)" in source
    assert "function createUnreconciledRow(transaction)" in source
    assert "summaryStatus.appendChild(createOverallStatusBadge(result.overall_status));" in source
    assert "tr.innerHTML = `" not in source


def test_bank_recon_template_avoids_untrusted_inline_handlers_and_encodes_urls():
    source = _template_source()

    assert "onclick=\"showUnreconciled(" not in source
    assert "encodeURIComponent(asAtDate)" in source
