"""Security regression checks for fuel tax credits template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "fuel_tax_credits.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_fuel_tax_template_uses_safe_cell_rendering():
    source = _template_source()

    assert "function createTextCell(className, value)" in source
    assert "tr.appendChild(createTextCell('px-4 py-3 text-sm text-gray-900', inv.date));" in source
    assert "tr.appendChild(createTextCell('px-4 py-3 text-sm text-gray-900', inv.contact));" in source


def test_fuel_tax_template_uses_url_search_params_for_generate_and_download():
    source = _template_source()

    assert "const params = new URLSearchParams({" in source
    assert "/fuel-tax-credits/api/generate?" in source
    assert "/fuel-tax-credits/api/download?" in source
