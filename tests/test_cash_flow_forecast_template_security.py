"""Security regression checks for cash flow forecast template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "cash_flow_forecast.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_cash_flow_forecast_uses_safe_dom_builders_for_dynamic_values():
    source = _template_source()

    assert "function createTextNode(tagName, className, value)" in source
    assert "function createTableCell(className, value)" in source
    assert "row.appendChild(createTextNode('span', 'text-sm text-gray-700', acct.name));" in source
    assert "tr.appendChild(createTableCell('px-4 py-3 text-sm font-medium text-gray-900', m.month));" in source


def test_cash_flow_forecast_encodes_deadline_query_params():
    source = _template_source()

    assert "new URLSearchParams({ lodge_method: currentLodgeMethod })" in source
    assert "/api/forecast/deadlines?" in source
