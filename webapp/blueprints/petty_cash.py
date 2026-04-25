"""Petty Cash Manager Blueprint."""

import html
import logging
from datetime import date
from functools import wraps

from flask import Blueprint, current_app, jsonify, render_template, request

logger = logging.getLogger(__name__)

petty_cash_bp = Blueprint("petty_cash", __name__, url_prefix="/petty-cash")

VALID_CATEGORIES = [
    "Office Supplies",
    "Travel",
    "Meals & Entertainment",
    "Postage",
    "Cleaning",
    "Minor Equipment",
    "Other",
]


def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_app.config.get("TESTING"):
            return f(*args, **kwargs)
        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
        except (ImportError, AttributeError):
            pass
        return f(*args, **kwargs)

    return decorated


def _get_team_id() -> str | None:
    try:
        from flask_login import current_user

        team_id: str | None = current_user.team_id
        return team_id
    except Exception:
        return None


@petty_cash_bp.get("/")
@_login_required
def index():
    return render_template("petty_cash.html")


@petty_cash_bp.get("/api/transactions")
@_login_required
def list_transactions():
    from webapp.models import PettyCashTransaction

    team_id = _get_team_id()
    if not team_id:
        return jsonify({"error": "No team"}), 400

    txns = (
        PettyCashTransaction.query.filter_by(team_id=team_id)
        .order_by(
            PettyCashTransaction.date.desc(), PettyCashTransaction.created_at.desc()
        )
        .limit(200)
        .all()
    )
    return jsonify({"transactions": [t.to_dict() for t in txns]})


@petty_cash_bp.post("/api/transactions")
@_login_required
def add_transaction():
    from flask_login import current_user

    from webapp.models import PettyCashTransaction, db

    team_id = _get_team_id()
    if not team_id:
        return jsonify({"error": "No team"}), 400

    data = request.get_json(silent=True) or {}

    txn_type = data.get("transaction_type", "").strip()
    if txn_type not in ("in", "out"):
        return jsonify({"error": "transaction_type must be 'in' or 'out'"}), 400

    try:
        amount = round(float(data.get("amount", 0)), 2)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "amount must be a positive number"}), 400

    description = html.escape((data.get("description") or "").strip())
    if not description:
        return jsonify({"error": "description is required"}), 400
    if len(description) > 255:
        description = description[:255]

    category = (data.get("category") or "Other").strip()
    if category not in VALID_CATEGORIES:
        category = "Other"

    reference = html.escape((data.get("reference") or "").strip())[:100]

    try:
        txn_date = date.fromisoformat(data.get("date", ""))
    except (ValueError, TypeError):
        txn_date = date.today()

    txn = PettyCashTransaction(
        team_id=team_id,
        user_id=current_user.id,
        date=txn_date,
        transaction_type=txn_type,
        amount=amount,
        description=description,
        category=category,
        reference=reference or None,
    )
    db.session.add(txn)
    db.session.commit()

    return jsonify({"success": True, "transaction": txn.to_dict()}), 201


@petty_cash_bp.delete("/api/transactions/<txn_id>")
@_login_required
def delete_transaction(txn_id: str):
    from webapp.models import PettyCashTransaction, db

    team_id = _get_team_id()
    if not team_id:
        return jsonify({"error": "No team"}), 400

    txn = PettyCashTransaction.query.filter_by(id=txn_id, team_id=team_id).first()
    if not txn:
        return jsonify({"error": "Not found"}), 404

    db.session.delete(txn)
    db.session.commit()
    return jsonify({"success": True})
