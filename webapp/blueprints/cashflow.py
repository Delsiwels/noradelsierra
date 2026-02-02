"""
Cash Flow Blueprint

Page routes and REST API endpoints for cash flow analysis.

Endpoints:
- GET /cashflow - Cash flow dashboard page
- POST /api/cashflow/analyze - Analyze transactions and generate cash flow statement
- GET /api/cashflow/summary - Get cash flow summary for a period
- POST /api/cashflow/classify - Classify transactions into cash flow categories
"""

import logging
from datetime import UTC, datetime

from flask import Blueprint, jsonify, render_template, request

logger = logging.getLogger(__name__)

cashflow_bp = Blueprint("cashflow", __name__)

# Rate limiter (initialized after app setup)
limiter = None


def init_cashflow_limiter(app_limiter):
    """Initialize the rate limiter for cashflow endpoints."""
    global limiter
    limiter = app_limiter


def rate_limit(limit_string):
    """Apply per-user rate limit decorator if limiter is available."""

    def decorator(f):
        if limiter:
            return limiter.limit(limit_string)(f)
        return f

    return decorator


def get_current_user():
    """Get current authenticated user."""
    from flask import current_app

    if current_app.config.get("TESTING"):
        return None

    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return current_user
    except (ImportError, AttributeError):
        pass
    return None


def login_required(f):
    """Require login decorator. Bypassed in testing mode."""
    from functools import wraps

    from flask import current_app

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get("TESTING"):
            return f(*args, **kwargs)

        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return {"error": "Authentication required"}, 401
        except (ImportError, AttributeError):
            pass

        return f(*args, **kwargs)

    return decorated_function


# Transaction category mappings for cash flow classification
OPERATING_KEYWORDS = {
    "sales",
    "revenue",
    "income",
    "fees",
    "commission",
    "rent received",
    "cost of goods sold",
    "cogs",
    "wages",
    "salaries",
    "rent",
    "utilities",
    "insurance",
    "office expenses",
    "advertising",
    "marketing",
    "professional fees",
    "accounting",
    "legal",
    "repairs",
    "maintenance",
    "telephone",
    "internet",
    "subscriptions",
    "travel",
    "entertainment",
    "bank fees",
    "interest paid",
    "interest received",
    "tax paid",
    "gst collected",
    "gst paid",
    "payg withholding",
    "superannuation",
}

INVESTING_KEYWORDS = {
    "equipment purchase",
    "equipment sale",
    "vehicle purchase",
    "vehicle sale",
    "property purchase",
    "property sale",
    "investment purchase",
    "investment sale",
    "asset purchase",
    "asset sale",
    "computer equipment",
    "furniture",
    "plant and equipment",
}

FINANCING_KEYWORDS = {
    "loan received",
    "loan repayment",
    "owner contribution",
    "owner drawings",
    "drawings",
    "capital contribution",
    "dividend paid",
    "share issue",
    "lease payment",
}


def classify_transaction(description, account_name=""):
    """
    Classify a transaction into operating, investing, or financing activity.

    Args:
        description: Transaction description
        account_name: Account name/category from chart of accounts

    Returns:
        Tuple of (category, subcategory)
    """
    text = f"{description} {account_name}".lower().strip()

    for keyword in INVESTING_KEYWORDS:
        if keyword in text:
            return "investing", keyword

    for keyword in FINANCING_KEYWORDS:
        if keyword in text:
            return "financing", keyword

    for keyword in OPERATING_KEYWORDS:
        if keyword in text:
            return "operating", keyword

    return "operating", "other"


def build_cashflow_statement(transactions):
    """
    Build a cash flow statement from a list of transactions.

    Args:
        transactions: List of dicts with keys: date, description, amount, account

    Returns:
        Dict with structured cash flow statement data
    """
    operating = {"inflows": [], "outflows": []}
    investing = {"inflows": [], "outflows": []}
    financing = {"inflows": [], "outflows": []}

    categories = {
        "operating": operating,
        "investing": investing,
        "financing": financing,
    }

    for txn in transactions:
        amount = float(txn.get("amount", 0))
        description = str(txn.get("description", ""))
        account = str(txn.get("account", ""))
        date = txn.get("date", "")

        category, subcategory = classify_transaction(description, account)
        bucket = categories[category]

        entry = {
            "description": description,
            "amount": amount,
            "date": str(date),
            "subcategory": subcategory,
        }

        if amount >= 0:
            bucket["inflows"].append(entry)
        else:
            bucket["outflows"].append(entry)

    def section_totals(section):
        total_in = sum(e["amount"] for e in section["inflows"])
        total_out = sum(e["amount"] for e in section["outflows"])
        return {
            "inflows": section["inflows"],
            "outflows": section["outflows"],
            "total_inflows": round(total_in, 2),
            "total_outflows": round(total_out, 2),
            "net": round(total_in + total_out, 2),
        }

    operating_totals = section_totals(operating)
    investing_totals = section_totals(investing)
    financing_totals = section_totals(financing)

    net_cash_change = round(
        operating_totals["net"] + investing_totals["net"] + financing_totals["net"],
        2,
    )

    return {
        "operating": operating_totals,
        "investing": investing_totals,
        "financing": financing_totals,
        "net_cash_change": net_cash_change,
        "transaction_count": len(transactions),
    }


# =============================================================================
# Page Routes
# =============================================================================


@cashflow_bp.route("/cashflow")
@login_required
def cashflow_dashboard():
    """Render the cash flow dashboard page."""
    return render_template("cashflow.html")


# =============================================================================
# API Routes
# =============================================================================


@cashflow_bp.route("/api/cashflow/analyze", methods=["POST"])
@rate_limit("30 per hour")
@login_required
def api_analyze_cashflow():
    """
    Analyze transactions and generate a cash flow statement.

    Request (JSON):
        - transactions: List of transaction objects
            - date: Transaction date (YYYY-MM-DD)
            - description: Transaction description
            - amount: Amount (positive = inflow, negative = outflow)
            - account: Account name/category (optional)
        - opening_balance: Opening cash balance (optional, default 0)
        - period_label: Label for the period (optional)

    Response:
        - success: boolean
        - statement: Cash flow statement with operating/investing/financing
        - opening_balance: float
        - closing_balance: float
        - period_label: string
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        transactions = data.get("transactions", [])
        if not transactions:
            return jsonify({"error": "At least one transaction is required"}), 400

        if not isinstance(transactions, list):
            return jsonify({"error": "Transactions must be a list"}), 400

        if len(transactions) > 10000:
            return (
                jsonify({"error": "Maximum 10,000 transactions per analysis"}),
                400,
            )

        for i, txn in enumerate(transactions):
            if not isinstance(txn, dict):
                return jsonify({"error": f"Transaction {i} must be an object"}), 400
            if "amount" not in txn:
                return (
                    jsonify({"error": f"Transaction {i} missing 'amount' field"}),
                    400,
                )
            try:
                float(txn["amount"])
            except (ValueError, TypeError):
                return (
                    jsonify({"error": f"Transaction {i} has invalid 'amount'"}),
                    400,
                )
            if "description" not in txn:
                return (
                    jsonify({"error": f"Transaction {i} missing 'description' field"}),
                    400,
                )

        opening_balance = float(data.get("opening_balance", 0))
        period_label = str(data.get("period_label", ""))

        statement = build_cashflow_statement(transactions)
        closing_balance = round(opening_balance + statement["net_cash_change"], 2)

        return jsonify(
            {
                "success": True,
                "statement": statement,
                "opening_balance": opening_balance,
                "closing_balance": closing_balance,
                "period_label": period_label,
            }
        )

    except Exception as e:
        logger.exception(f"Error analyzing cash flow: {e}")
        return jsonify({"error": "Failed to analyze cash flow"}), 500


@cashflow_bp.route("/api/cashflow/summary", methods=["GET"])
@rate_limit("60 per hour")
@login_required
def api_cashflow_summary():
    """
    Get a cash flow summary structure for the current period.

    Query params:
        - period: Period label (default: current quarter)

    Response:
        - success: boolean
        - summary: Cash flow summary structure
    """
    try:
        now = datetime.now(UTC)
        quarter = (now.month - 1) // 3 + 1
        default_period = f"Q{quarter} {now.year}"
        period = request.args.get("period", default_period)

        summary = {
            "period": period,
            "operating": {"total_inflows": 0, "total_outflows": 0, "net": 0},
            "investing": {"total_inflows": 0, "total_outflows": 0, "net": 0},
            "financing": {"total_inflows": 0, "total_outflows": 0, "net": 0},
            "net_cash_change": 0,
            "opening_balance": 0,
            "closing_balance": 0,
        }

        return jsonify({"success": True, "summary": summary})

    except Exception as e:
        logger.exception(f"Error getting cash flow summary: {e}")
        return jsonify({"error": "Failed to get cash flow summary"}), 500


@cashflow_bp.route("/api/cashflow/classify", methods=["POST"])
@rate_limit("60 per hour")
@login_required
def api_classify_transaction():
    """
    Classify transactions into cash flow categories.

    Request (JSON):
        - transactions: List of objects with 'description' and optional 'account'

    Response:
        - success: boolean
        - classifications: List of classification results
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        transactions = data.get("transactions", [])
        if not transactions:
            return jsonify({"error": "At least one transaction is required"}), 400

        if not isinstance(transactions, list):
            return jsonify({"error": "Transactions must be a list"}), 400

        if len(transactions) > 1000:
            return jsonify({"error": "Maximum 1,000 transactions per request"}), 400

        classifications = []
        for txn in transactions:
            if not isinstance(txn, dict):
                continue
            description = str(txn.get("description", ""))
            account = str(txn.get("account", ""))
            category, subcategory = classify_transaction(description, account)
            classifications.append(
                {
                    "description": description,
                    "category": category,
                    "subcategory": subcategory,
                }
            )

        return jsonify({"success": True, "classifications": classifications})

    except Exception as e:
        logger.exception(f"Error classifying transactions: {e}")
        return jsonify({"error": "Failed to classify transactions"}), 500
