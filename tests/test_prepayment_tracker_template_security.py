"""Security regression checks for prepayment tracker template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "prepayment_tracker.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_prepayment_tracker_uses_safe_cell_rendering():
    source = _template_source()

    assert "function createTextCell(className, value)" in source
    assert "tr.appendChild(createTextCell('px-4 py-3 text-sm font-medium text-gray-900', item.account_name));" in source
    assert "tr.appendChild(createStatusCell(item.status));" in source


def test_prepayment_tracker_encodes_query_params():
    source = _template_source()

    assert "new URLSearchParams({ as_at_date: asAtDate })" in source
    assert "/prepayment-tracker/api/download?" in source
