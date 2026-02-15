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


def test_sharing_manage_escapes_group_ids_in_data_attributes():
    source = _template_source()

    assert "const safeGroupId = escapeHtml(String(group.id ?? ''));" in source
    assert 'data-group="${safeGroupId}"' in source
    assert 'data-delete="${safeGroupId}"' in source
    assert 'data-add-to-group="${escapeHtml(String(group.id ?? \'\'))}"' in source
    assert "const safeClientId = escapeHtml(String(client.id ?? ''));" in source
    assert 'data-id="${safeClientId}"' in source
