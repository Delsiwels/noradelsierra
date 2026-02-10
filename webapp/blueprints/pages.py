"""Public pages blueprint."""

from collections import Counter

from flask import Blueprint, current_app, redirect, render_template, url_for
from flask_login import current_user, login_required

from webapp.services.runtime_health import runtime_health
from webapp.services.runtime_health_persistence import list_runtime_health_snapshots

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def home():
    """Home page — redirects authenticated users to dashboard."""
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    return render_template("home.html")


@pages_bp.route("/dashboard")
@login_required
def dashboard():
    """Authenticated user dashboard."""
    return render_template("dashboard.html")


def _build_runtime_ops_view_model() -> dict:
    """Build summary and trend data for runtime operations dashboard."""
    current = runtime_health.build_report(current_app)
    snapshots = list_runtime_health_snapshots(limit=120)

    status_counts = Counter(snapshot.get("status", "unknown") for snapshot in snapshots)
    degraded_reason_counts: Counter[str] = Counter()
    for snapshot in snapshots:
        for reason in snapshot.get("degraded_reasons", []):
            degraded_reason_counts[reason] += 1

    return {
        "current": current,
        "snapshots": snapshots,
        "summary": {
            "total_snapshots": len(snapshots),
            "healthy_count": status_counts.get("healthy", 0),
            "degraded_count": status_counts.get("degraded", 0),
            "top_reasons": degraded_reason_counts.most_common(8),
        },
    }


@pages_bp.route("/ops/runtime-health")
@login_required
def runtime_health_page():
    """Operational runtime health dashboard (owner/admin only)."""
    if not getattr(current_user, "is_admin", False):
        return render_template("ops/runtime_health_denied.html"), 403

    context = _build_runtime_ops_view_model()
    return render_template("ops/runtime_health.html", **context)


@pages_bp.route("/chat")
@login_required
def chat_page():
    """Chat interface page."""
    return render_template("chat.html")


@pages_bp.route("/pricing")
def pricing():
    """Pricing page."""
    return render_template("pricing.html")


@pages_bp.route("/features")
def features():
    """Features page."""
    return render_template("features.html")


@pages_bp.route("/contact")
def contact():
    """Contact page."""
    return render_template("contact.html")


@pages_bp.route("/book-setup")
def book_setup():
    """Book setup call page."""
    return render_template("book_setup.html")
