"""
BAS Deadline Service

Provides ATO BAS deadline calculations for Australian businesses.

Quarterly deadlines: 28th of month after quarter end
Monthly deadlines: 21st of following month
Special: December quarter due 28 Feb, GST annual due 28 Feb
"""

from datetime import date, timedelta

# Quarterly BAS due dates (quarter_end_month -> due_month, due_day)
QUARTERLY_DEADLINES = {
    9: (10, 28),  # Q1: Jul-Sep -> 28 Oct
    12: (2, 28),  # Q2: Oct-Dec -> 28 Feb (special)
    3: (4, 28),  # Q3: Jan-Mar -> 28 Apr
    6: (
        7,
        28,
    ),  # Q4: Apr-Jun -> 28 Jul (note: if lodging electronically, may get extra time)
}

# Agent-lodged quarterly BAS due dates (extended deadlines for tax agents)
QUARTERLY_DEADLINES_AGENT = {
    9: (11, 25),  # Q1: Jul-Sep -> 25 Nov
    12: (2, 28),  # Q2: Oct-Dec -> 28 Feb (same as self-lodge)
    3: (5, 26),  # Q3: Jan-Mar -> 26 May
    6: (8, 25),  # Q4: Apr-Jun -> 25 Aug
}

# Month names for display
QUARTER_LABELS = {
    9: "Q1 (Jul-Sep)",
    12: "Q2 (Oct-Dec)",
    3: "Q3 (Jan-Mar)",
    6: "Q4 (Apr-Jun)",
}


def _get_quarterly_deadlines_for_year(
    fy_start_year: int, lodge_method: str = "self"
) -> list[dict]:
    """
    Get all quarterly BAS deadlines for a financial year.

    Args:
        fy_start_year: The calendar year the FY starts in (e.g., 2025 for FY 2025-26)
        lodge_method: "self" for self-lodger dates, "agent" for tax agent dates
    """
    table = (
        QUARTERLY_DEADLINES_AGENT if lodge_method == "agent" else QUARTERLY_DEADLINES
    )
    deadlines = []

    # Q1: Jul-Sep of fy_start_year
    due_month, due_day = table[9]
    deadlines.append(
        {
            "quarter": "Q1 (Jul-Sep)",
            "period_end": date(fy_start_year, 9, 30),
            "due_date": date(fy_start_year, due_month, due_day),
            "type": "quarterly",
        }
    )

    # Q2: Oct-Dec of fy_start_year
    due_month, due_day = table[12]
    deadlines.append(
        {
            "quarter": "Q2 (Oct-Dec)",
            "period_end": date(fy_start_year, 12, 31),
            "due_date": date(fy_start_year + 1, due_month, due_day),
            "type": "quarterly",
        }
    )

    # Q3: Jan-Mar of fy_start_year+1
    due_month, due_day = table[3]
    deadlines.append(
        {
            "quarter": "Q3 (Jan-Mar)",
            "period_end": date(fy_start_year + 1, 3, 31),
            "due_date": date(fy_start_year + 1, due_month, due_day),
            "type": "quarterly",
        }
    )

    # Q4: Apr-Jun of fy_start_year+1
    due_month, due_day = table[6]
    deadlines.append(
        {
            "quarter": "Q4 (Apr-Jun)",
            "period_end": date(fy_start_year + 1, 6, 30),
            "due_date": date(fy_start_year + 1, due_month, due_day),
            "type": "quarterly",
        }
    )

    return deadlines


def _get_monthly_deadline(year: int, month: int) -> date:
    """Get the monthly BAS due date (21st of following month)."""
    if month == 12:
        return date(year + 1, 1, 21)
    return date(year, month + 1, 21)


def _get_monthly_deadlines_for_period(
    start_date: date, months_ahead: int = 3
) -> list[dict]:
    """Get monthly BAS deadlines for a range of months."""
    deadlines = []
    current = date(start_date.year, start_date.month, 1)

    for _ in range(months_ahead + 2):
        import calendar

        last_day = calendar.monthrange(current.year, current.month)[1]
        period_end = date(current.year, current.month, last_day)
        due = _get_monthly_deadline(current.year, current.month)

        deadlines.append(
            {
                "period": current.strftime("%B %Y"),
                "period_end": period_end,
                "due_date": due,
                "type": "monthly",
            }
        )

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return deadlines


def get_upcoming_deadlines(
    frequency: str = "quarterly",
    days_ahead: int = 90,
    reference_date: date | None = None,
    lodge_method: str = "self",
) -> list[dict]:
    """
    Get upcoming BAS deadlines.

    Args:
        frequency: "quarterly" or "monthly"
        days_ahead: Number of days to look ahead
        reference_date: Reference date (defaults to today)
        lodge_method: "self" for self-lodger dates, "agent" for tax agent dates

    Returns:
        List of deadline dicts with quarter/period, period_end, due_date, days_remaining
    """
    today = reference_date or date.today()
    cutoff = today + timedelta(days=days_ahead)

    if frequency == "monthly":
        # Get monthly deadlines for the period
        all_deadlines = _get_monthly_deadlines_for_period(today, months_ahead=6)
    else:
        # Get quarterly deadlines for prior, current, and next FY
        # to catch tail-end deadlines (e.g. Q4 due in Jul at start of new FY)
        fy_start = today.year if today.month >= 7 else today.year - 1
        all_deadlines = _get_quarterly_deadlines_for_year(fy_start - 1, lodge_method)
        all_deadlines += _get_quarterly_deadlines_for_year(fy_start, lodge_method)
        all_deadlines += _get_quarterly_deadlines_for_year(fy_start + 1, lodge_method)

    upcoming = []
    for dl in all_deadlines:
        due = dl["due_date"]
        if today <= due <= cutoff:
            days_remaining = (due - today).days
            dl["days_remaining"] = days_remaining
            dl["due_date_str"] = due.strftime("%d %b %Y")
            dl["status"] = _get_status(days_remaining)
            upcoming.append(dl)
        elif due < today and (today - due).days <= 30:
            # Overdue within last 30 days
            days_overdue = (today - due).days
            dl["days_remaining"] = -days_overdue
            dl["due_date_str"] = due.strftime("%d %b %Y")
            dl["status"] = "overdue"
            upcoming.append(dl)

    upcoming.sort(key=lambda x: x["due_date"])
    return upcoming


def _get_status(days_remaining: int) -> str:
    """Get deadline status based on days remaining."""
    if days_remaining < 0:
        return "overdue"
    elif days_remaining <= 7:
        return "due_soon"
    elif days_remaining <= 30:
        return "upcoming"
    else:
        return "clear"


def get_next_deadline(
    frequency: str = "quarterly",
    reference_date: date | None = None,
    lodge_method: str = "self",
) -> dict | None:
    """
    Get the single next upcoming deadline.

    Returns:
        Deadline dict or None
    """
    upcoming = get_upcoming_deadlines(
        frequency=frequency,
        days_ahead=120,
        reference_date=reference_date,
        lodge_method=lodge_method,
    )
    # Find first non-overdue, or the most recent overdue
    for dl in upcoming:
        if dl["days_remaining"] >= 0:
            return dl
    return upcoming[0] if upcoming else None


def get_deadline_status(
    frequency: str = "quarterly",
    reference_date: date | None = None,
    lodge_method: str = "self",
) -> str:
    """
    Get overall deadline status.

    Returns: "overdue", "due_soon", "upcoming", or "clear"
    """
    next_dl = get_next_deadline(
        frequency=frequency, reference_date=reference_date, lodge_method=lodge_method
    )
    if not next_dl:
        return "clear"
    return next_dl["status"]  # type: ignore[no-any-return]


def get_reminders_for_user(
    user_id: str,
    reference_date: date | None = None,
) -> list[dict]:
    """
    Get personalized BAS reminders for a user.

    Args:
        user_id: User ID to get preferences from
        reference_date: Optional reference date

    Returns:
        List of reminder dicts
    """
    from webapp.models import User

    user = User.query.get(user_id)
    if not user or not user.bas_reminders_enabled:
        return []

    frequency = user.bas_frequency or "quarterly"
    lodge_method = getattr(user, "bas_lodge_method", "self") or "self"
    return get_upcoming_deadlines(
        frequency=frequency,
        days_ahead=90,
        reference_date=reference_date,
        lodge_method=lodge_method,
    )


def get_bas_context_for_prompt(
    user_id: str,
    reference_date: date | None = None,
) -> str | None:
    """
    Get BAS deadline context string for injection into AI system prompt.

    Returns context string if deadline is within 14 days, else None.
    """
    from webapp.models import User

    user = User.query.get(user_id)
    if not user:
        return None

    frequency = user.bas_frequency or "quarterly"
    lodge_method = getattr(user, "bas_lodge_method", "self") or "self"
    next_dl = get_next_deadline(
        frequency=frequency, reference_date=reference_date, lodge_method=lodge_method
    )

    if not next_dl:
        return None

    days = next_dl["days_remaining"]
    if days < 0:
        return (
            f"IMPORTANT: The user's BAS was due on {next_dl['due_date_str']} "
            f"and is now {abs(days)} days overdue. Remind them to lodge urgently."
        )
    elif days <= 14:
        return (
            f"Heads up: The user's next BAS is due in {days} days "
            f"({next_dl['due_date_str']}). Be proactive about reminding them."
        )

    return None


def get_deadlines_for_forecast(
    frequency: str = "quarterly",
    lodge_method: str = "self",
    months_ahead: int = 12,
    reference_date: date | None = None,
) -> list[dict]:
    """
    Get BAS deadlines for a forecast window (default 12 months).

    Args:
        frequency: "quarterly" or "monthly"
        lodge_method: "self" or "agent"
        months_ahead: Number of months to look ahead
        reference_date: Reference date (defaults to today)

    Returns:
        List of deadline dicts with quarter/period, period_end, due_date,
        days_remaining, due_date_str
    """
    return get_upcoming_deadlines(
        frequency=frequency,
        days_ahead=months_ahead * 31,
        reference_date=reference_date,
        lodge_method=lodge_method,
    )
