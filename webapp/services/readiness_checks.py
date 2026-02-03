"""
Readiness Checks Service

Provides month-end close and EOFY checklists for Australian businesses.
Australian financial year: July 1 - June 30.
"""

import html
from collections import defaultdict
from datetime import date, datetime

from webapp.models import ChecklistComment, ChecklistProgress, db

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

# All valid item keys for validation
_ALL_ITEM_KEYS = {item["key"] for item in MONTH_END_CHECKLIST + EOFY_CHECKLIST}


def get_month_end_checklist() -> list[dict]:
    """Return the standard month-end checklist items."""
    return [dict(item, completed=False) for item in MONTH_END_CHECKLIST]


def get_eofy_checklist() -> list[dict]:
    """Return the EOFY checklist items."""
    return [dict(item, completed=False) for item in EOFY_CHECKLIST]


def _load_progress_record(
    team_id: str,
    checklist_type: str,
    period: str,
    tenant_id: str | None = None,
) -> ChecklistProgress | None:
    """Load the ORM progress record, filtered by tenant when provided."""
    query = ChecklistProgress.query.filter_by(
        team_id=team_id,
        checklist_type=checklist_type,
        period=period,
    )
    if tenant_id:
        query = query.filter_by(tenant_id=tenant_id)
    else:
        query = query.filter(ChecklistProgress.tenant_id.is_(None))
    return query.first()  # type: ignore[no-any-return]


def get_current_checklist(
    team_id: str,
    reference_date: date | None = None,
    tenant_id: str | None = None,
    tenant_name: str | None = None,
) -> dict:
    """
    Get the context-appropriate checklist with any saved progress.

    Returns EOFY checklist in May-July, month-end otherwise.

    Args:
        team_id: Team ID
        reference_date: Optional reference date
        tenant_id: Optional Xero tenant ID for per-org progress
        tenant_name: Optional Xero tenant display name

    Returns:
        Dict with checklist_type, period, items, progress stats,
        and checklist_progress_id when saved progress exists.
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
    progress = _load_progress_record(team_id, checklist_type, period, tenant_id)

    if progress and progress.items:
        saved_items = {
            item["key"]: item.get("completed", False) for item in progress.items
        }
        for item in items:
            if item["key"] in saved_items:
                item["completed"] = saved_items[item["key"]]

    completed_count = sum(1 for item in items if item["completed"])

    result: dict = {
        "checklist_type": checklist_type,
        "period": period,
        "items": items,
        "total": len(items),
        "completed": completed_count,
        "percentage": round((completed_count / len(items)) * 100, 1) if items else 0,
        "is_complete": completed_count == len(items),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "checklist_progress_id": progress.id if progress else None,
    }
    return result


def save_checklist_progress(
    team_id: str,
    user_id: str,
    checklist_type: str,
    period: str,
    items: list[dict],
    tenant_id: str | None = None,
    tenant_name: str | None = None,
) -> ChecklistProgress:
    """
    Save checklist progress.

    Args:
        team_id: Team ID
        user_id: User ID saving the progress
        checklist_type: "month_end" or "eofy"
        period: Period string (YYYY-MM)
        items: List of item dicts with key and completed status
        tenant_id: Optional Xero tenant ID
        tenant_name: Optional Xero tenant display name
    """
    progress = _load_progress_record(team_id, checklist_type, period, tenant_id)

    if not progress:
        progress = ChecklistProgress(
            team_id=team_id,
            user_id=user_id,
            checklist_type=checklist_type,
            period=period,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )
        db.session.add(progress)

    progress.items = items
    progress.user_id = user_id
    if tenant_name:
        progress.tenant_name = tenant_name

    # Check if all items completed
    all_completed = all(item.get("completed", False) for item in items)
    if all_completed and not progress.completed_at:
        progress.completed_at = datetime.utcnow()
    elif not all_completed:
        progress.completed_at = None

    db.session.commit()
    return progress


def get_checklist_progress(
    team_id: str,
    checklist_type: str,
    period: str,
    tenant_id: str | None = None,
) -> ChecklistProgress | None:
    """Retrieve saved progress for a specific checklist and period."""
    return _load_progress_record(team_id, checklist_type, period, tenant_id)


def get_checklist_history(
    team_id: str,
    limit: int = 12,
    tenant_id: str | None = None,
) -> list[dict]:
    """
    Get past completed checklists for a team.

    Args:
        team_id: Team ID
        limit: Max number of results
        tenant_id: Optional Xero tenant ID to filter by

    Returns:
        List of checklist progress dicts
    """
    query = ChecklistProgress.query.filter_by(team_id=team_id)
    if tenant_id:
        query = query.filter_by(tenant_id=tenant_id)
    progress_list = query.order_by(ChecklistProgress.period.desc()).limit(limit).all()

    return [p.to_dict() for p in progress_list]


# ---------------------------------------------------------------------------
# Comment CRUD
# ---------------------------------------------------------------------------

MAX_COMMENT_LENGTH = 2000


def add_checklist_comment(
    checklist_progress_id: str,
    item_key: str,
    user_id: str,
    content: str,
    assigned_to: str | None = None,
) -> ChecklistComment:
    """
    Add a comment/note to a checklist item.

    Args:
        checklist_progress_id: FK to ChecklistProgress
        item_key: Which checklist item this note is for
        user_id: Author's user ID
        content: The note text (max 2000 chars, HTML-escaped)
        assigned_to: Optional user ID to assign the item to

    Returns:
        The created ChecklistComment

    Raises:
        ValueError: If item_key is invalid or content is empty/too long
    """
    if item_key not in _ALL_ITEM_KEYS:
        raise ValueError(f"Invalid item_key: {item_key}")

    content = (content or "").strip()
    if not content:
        raise ValueError("Comment content cannot be empty")
    if len(content) > MAX_COMMENT_LENGTH:
        content = content[:MAX_COMMENT_LENGTH]

    # Escape HTML to prevent stored XSS
    content = html.escape(content)

    comment = ChecklistComment(
        checklist_progress_id=checklist_progress_id,
        item_key=item_key,
        user_id=user_id,
        content=content,
        assigned_to=assigned_to,
    )
    db.session.add(comment)
    db.session.commit()
    return comment


def get_checklist_comments(
    checklist_progress_id: str,
) -> dict[str, list[dict]]:
    """
    Get all comments for a checklist, grouped by item_key.

    Args:
        checklist_progress_id: The checklist progress record ID

    Returns:
        Dict mapping item_key to list of comment dicts
    """
    comments = (
        ChecklistComment.query.filter_by(checklist_progress_id=checklist_progress_id)
        .order_by(ChecklistComment.created_at.asc())
        .all()
    )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for c in comments:
        grouped[c.item_key].append(c.to_dict())
    return dict(grouped)
