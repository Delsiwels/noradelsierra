"""Regression tests for Excel export structural integrity and shared styling.

These exports previously had no direct test coverage. They are exercised with
empty input (which every service tolerates, producing an empty-but-valid
workbook) so a structural break surfaces here, and the shared style palette is
asserted against webapp.app_services.excel_styles.
"""

import importlib

import pytest

pytest.importorskip("openpyxl")
from openpyxl import load_workbook  # noqa: E402

from webapp.app_services import excel_styles  # noqa: E402

EXPORT_SERVICES = [
    "aging_dashboard",
    "bank_recon_status",
    "budget_actual",
    "depreciation_calc",
    "fuel_tax_credits",
    "payg_instalment",
    "payg_reconciliation",
    "payroll_tax",
    "prepayment_tracker",
    "stp_tracker",
]


@pytest.mark.parametrize("service_name", EXPORT_SERVICES)
def test_export_to_excel_produces_valid_workbook(service_name):
    module = importlib.import_module(f"webapp.app_services.{service_name}_service")
    workbook = load_workbook(module.export_to_excel({}))
    assert workbook.sheetnames  # at least one sheet, file opens cleanly


def test_style_factories_use_brand_palette():
    assert str(excel_styles.header_fill().fgColor.rgb).endswith(excel_styles.HEADER_COLOR)
    assert str(excel_styles.ok_fill().fgColor.rgb).endswith(excel_styles.OK_COLOR)
    assert str(excel_styles.warning_fill().fgColor.rgb).endswith(
        excel_styles.WARNING_COLOR
    )
    assert str(excel_styles.error_fill().fgColor.rgb).endswith(excel_styles.ERROR_COLOR)

    font = excel_styles.header_font()
    assert font.bold is True
    assert str(font.color.rgb).endswith(excel_styles.HEADER_FONT_COLOR)
