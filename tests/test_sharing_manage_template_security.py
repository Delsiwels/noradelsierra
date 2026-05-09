"""Security regression checks for sharing manage template."""

from pathlib import Path


def _template_source() -> str:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "webapp"
        / "templates"
        / "sharing"
        / "manage.html"
    )
    return template_path.read_text(encoding="utf-8")


def test_sharing_manage_uses_dom_builders_for_group_and_client_lists():
    source = _template_source()

    assert "function createGroupTab(group)" in source
    assert "function createGroupMenuItem(group)" in source
    assert "function createClientListItem(client)" in source
    assert "button.dataset.addToGroup = String(group.id ?? '');" in source
    assert "item.dataset.id = clientId;" in source
    assert "container.innerHTML = html;" not in source
    assert "container.innerHTML = clientGroups.map(" not in source
    assert "list.innerHTML = filtered.map(" not in source
