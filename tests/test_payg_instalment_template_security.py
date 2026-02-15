"""Security regression checks for PAYG instalment template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "payg_instalment.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_payg_instalment_template_uses_url_search_params_for_queries():
    source = _template_source()

    assert "const params = new URLSearchParams({" in source
    assert "/payg-instalment/api/generate?" in source
    assert "/payg-instalment/api/download?" in source
