"""Shared openpyxl styling for Excel exports.

Centralises the export colour palette so the brand scheme lives in one place.
Each factory returns a fresh style object per call to avoid any shared-state
surprises across cells and workbooks. openpyxl is imported lazily so importing
this module never hard-requires the optional dependency.
"""

HEADER_COLOR = "0066CC"
OK_COLOR = "D1FAE5"
WARNING_COLOR = "FEF3C7"
ERROR_COLOR = "FEE2E2"
HEADER_FONT_COLOR = "FFFFFF"


def _solid_fill(color: str):
    from openpyxl.styles import PatternFill

    return PatternFill(start_color=color, end_color=color, fill_type="solid")


def header_fill():
    """Header background fill (brand blue)."""
    return _solid_fill(HEADER_COLOR)


def ok_fill():
    """Green 'ok' status fill."""
    return _solid_fill(OK_COLOR)


def warning_fill():
    """Amber 'warning' status fill."""
    return _solid_fill(WARNING_COLOR)


def error_fill():
    """Red 'error/alert' status fill."""
    return _solid_fill(ERROR_COLOR)


def header_font():
    """Bold white header font."""
    from openpyxl.styles import Font

    return Font(bold=True, color=HEADER_FONT_COLOR)


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def sanitize_workbook(wb):
    """Neutralize formula injection in every string cell of a workbook.

    A leading ``=``, ``+``, ``-``, or ``@`` makes spreadsheet apps execute a
    cell as a formula (CSV/Excel formula injection). Since exports embed
    Xero-sourced text (contact/account names, descriptions, references), prefix
    any such string value with a single quote so it is stored and shown as
    text. Numeric cells are left untouched. Call once just before ``wb.save``.
    """
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if isinstance(value, str) and value[:1] in _FORMULA_PREFIXES:
                    cell.value = "'" + value
    return wb
