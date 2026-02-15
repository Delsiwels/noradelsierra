"""Security regression checks for readiness history template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "readiness"
        / "history.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_readiness_history_renders_rows_with_dom_nodes():
    source = _template_source()

    assert "container.innerHTML = '';" in source
    assert "const card = document.createElement('div');" in source
    assert "period.textContent = String(h.period ?? '');" in source
    assert "count.textContent = `${completed}/${items.length} items`;" in source
