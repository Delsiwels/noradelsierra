"""Security regression checks for STP tracker template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "stp_tracker.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_stp_tracker_template_escapes_dynamic_labels():
    source = _template_source()

    assert "function escapeHtml(value)" in source
    assert "const quarterLabel = escapeHtml(q.quarter);" in source
    assert "const periodLabel = escapeHtml(q.period);" in source


def test_stp_tracker_template_encodes_financial_year_params():
    source = _template_source()

    assert "encodeURIComponent(fy)" in source
