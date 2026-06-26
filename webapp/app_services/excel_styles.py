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
