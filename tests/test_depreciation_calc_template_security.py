"""Security regression checks for depreciation calculator template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "depreciation_calc.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_depreciation_template_avoids_dynamic_tfoot_innerhtml():
    source = _template_source()

    assert "function renderTotalsRow(tfoot, totals)" in source
    assert "tfoot.replaceChildren();" in source
    assert "tfoot.innerHTML = `" not in source


def test_depreciation_template_uses_encoded_query_params_for_download():
    source = _template_source()

    assert "new URLSearchParams({" in source
    assert "params.toString()" in source
    assert "/depreciation-calc/api/download?" in source
