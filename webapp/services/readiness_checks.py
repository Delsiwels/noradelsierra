"""
Readiness Checks Service

Provides month-end close and EOFY checklists for Australian businesses.
Australian financial year: July 1 - June 30.
"""

from datetime import date, datetime

from webapp.models import ChecklistProgress, db

MONTH_END_CHECKLIST = [
    {
        "key": "bank_rec",
        "label": "Bank reconciliation",
        "description": "Reconcile all bank accounts to statements",
    },
    {
        "key": "ar_review",
        "label": "Accounts receivable review",
        "description": "Review outstanding invoices and follow up overdue",
    },
    {
        "key": "ap_review",
        "label": "Accounts payable review",
        "description": "Review and process outstanding bills",
    },
    {
        "key": "gst_rec",
        "label": "GST reconciliation",
        "description": "Reconcile GST collected vs paid",
    },
    {
        "key": "payroll_rec",
        "label": "Payroll reconciliation",
        "description": "Verify payroll processed correctly and super paid",
    },
    {
        "key": "cc_rec",
        "label": "Credit card reconciliation",
        "description": "Reconcile credit card transactions",
    },
    {
        "key": "petty_cash",
        "label": "Petty cash count",
        "description": "Count and reconcile petty cash",
    },
    {
        "key": "prepayments",
        "label": "Review prepayments",
        "description": "Adjust prepaid expenses for the month",
    },
    {
        "key": "accruals",
        "label": "Process accruals",
        "description": "Accrue expenses incurred but not yet billed",
    },
    {
        "key": "depreciation",
        "label": "Depreciation entry",
        "description": "Process monthly depreciation for fixed assets",
    },
    {
        "key": "review_pnl",
        "label": "Review P&L",
        "description": "Review profit and loss for unusual items",
    },
    {
        "key": "review_bs",
        "label": "Review balance sheet",
        "description": "Check balance sheet accounts for accuracy",
    },
]

EOFY_CHECKLIST = [
    {
        "key": "stp_final",
        "label": "STP finalisation",
        "description": "Finalise Single Touch Payroll for all employees",
    },
    {
        "key": "super_guarantee",
        "label": "Super guarantee review",
        "description": "Ensure all super guarantee obligations are met (due 28 Jul)",
    },
    {
        "key": "stocktake",
        "label": "Stocktake",
        "description": "Complete physical stocktake and adjust inventory",
    },
    {
        "key": "asset_depreciation",
        "label": "Asset depreciation",
        "description": "Calculate annual depreciation and instant asset write-offs",
    },
    {
        "key": "bad_debts",
        "label": "Write off bad debts",
        "description": "Review and write off uncollectable debts before 30 June",
    },
    {
        "key": "prepayments_eofy",
        "label": "Prepayment review",
        "description": "Review and adjust all prepaid expenses",
    },
    {
        "key": "accruals_eofy",
        "label": "Year-end accruals",
        "description": "Accrue all expenses and revenue for the year",
    },
    {
        "key": "bank_rec_eofy",
        "label": "Final bank reconciliation",
        "description": "Reconcile all bank accounts as at 30 June",
    },
    {
        "key": "gst_annual",
        "label": "GST annual reconciliation",
        "description": "Reconcile annual GST position",
    },
    {
        "key": "bas_q4",
        "label": "Lodge Q4 BAS",
        "description": "Prepare and lodge final quarter BAS",
    },
    {
        "key": "fbt_review",
        "label": "FBT review",
        "description": "Review fringe benefits tax obligations",
    },
    {
        "key": "trustee_res",
        "label": "Trustee resolutions",
        "description": "Complete trust distribution resolutions before 30 June (if applicable)",
    },
    {
        "key": "div7a",
        "label": "Division 7A review",
        "description": "Review shareholder loans and Division 7A compliance",
    },
    {
        "key": "payg_summary",
        "label": "PAYG summary review",
        "description": "Verify PAYG withholding and instalments",
    },
    {
        "key": "backup",
        "label": "Accounting data backup",
        "description": "Create backup of all accounting data",
    },
    {
        "key": "tax_planning",
        "label": "Tax planning items",
        "description": "Complete any year-end tax planning strategies",
    },
]


def get_month_end_checklist() -> list[dict]:
    """Return the standard month-end checklist items."""
    return [dict(item, completed=False) for item in MONTH_END_CHECKLIST]


def get_eofy_checklist() -> list[dict]:
    """Return the EOFY checklist items."""
    return [dict(item, completed=False) for item in EOFY_CHECKLIST]


def get_current_checklist(
    team_id: str,
    reference_date: date | None = None,
) -> dict:
    """
    Get the context-appropriate checklist with any saved progress.

    Returns EOFY checklist in May-July, month-end otherwise.

    Args:
        team_id: Team ID
        reference_date: Optional reference date

    Returns:
        Dict with checklist_type, period, items, and progress stats
    """
    today = reference_date or date.today()

    # Use EOFY checklist in May, June, July
    if today.month in (5, 6, 7):
        checklist_type = "eofy"
        items = get_eofy_checklist()
        # EOFY period is the FY ending June 30
        fy_year = today.year if today.month <= 6 else today.year
        period = f"{fy_year}-06"
    else:
        checklist_type = "month_end"
        items = get_month_end_checklist()
        period = today.strftime("%Y-%m")

    # Load saved progress
    progress = ChecklistProgress.query.filter_by(
        team_id=team_id,
        checklist_type=checklist_type,
        period=period,
    ).first()

    if progress and progress.items:
        saved_items = {
            item["key"]: item.get("completed", False) for item in progress.items
        }
        for item in items:
            if item["key"] in saved_items:
                item["completed"] = saved_items[item["key"]]

    completed_count = sum(1 for item in items if item["completed"])

    return {
        "checklist_type": checklist_type,
        "period": period,
        "items": items,
        "total": len(items),
        "completed": completed_count,
        "percentage": round((completed_count / len(items)) * 100, 1) if items else 0,
        "is_complete": completed_count == len(items),
    }


def save_checklist_progress(
    team_id: str,
    user_id: str,
    checklist_type: str,
    period: str,
    items: list[dict],
) -> ChecklistProgress:
    """
    Save checklist progress.

    Args:
        team_id: Team ID
        user_id: User ID saving the progress
        checklist_type: "month_end" or "eofy"
        period: Period string (YYYY-MM)
        items: List of item dicts with key and completed status
    """
    progress = ChecklistProgress.query.filter_by(
        team_id=team_id,
        checklist_type=checklist_type,
        period=period,
    ).first()

    if not progress:
        progress = ChecklistProgress(
            team_id=team_id,
            user_id=user_id,
            checklist_type=checklist_type,
            period=period,
        )
        db.session.add(progress)

    progress.items = items
    progress.user_id = user_id

    # Check if all items completed
    all_completed = all(item.get("completed", False) for item in items)
    if all_completed and not progress.completed_at:
        progress.completed_at = datetime.utcnow()
    elif not all_completed:
        progress.completed_at = None

    db.session.commit()
    return progress  # type: ignore[no-any-return]


def get_checklist_progress(
    team_id: str,
    checklist_type: str,
    period: str,
) -> ChecklistProgress | None:
    """Retrieve saved progress for a specific checklist and period."""
    return ChecklistProgress.query.filter_by(  # type: ignore[no-any-return]
        team_id=team_id,
        checklist_type=checklist_type,
        period=period,
    ).first()


def get_checklist_history(
    team_id: str,
    limit: int = 12,
) -> list[dict]:
    """
    Get past completed checklists for a team.

    Args:
        team_id: Team ID
        limit: Max number of results

    Returns:
        List of checklist progress dicts
    """
    progress_list = (
        ChecklistProgress.query.filter_by(team_id=team_id)
        .order_by(ChecklistProgress.period.desc())
        .limit(limit)
        .all()
    )

    return [p.to_dict() for p in progress_list]
