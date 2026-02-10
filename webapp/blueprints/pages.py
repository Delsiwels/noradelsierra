"""Public pages blueprint."""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from webapp.services.maintenance import (
    cleanup_expired_conversations,
    snapshot_runtime_health,
)
from webapp.services.runtime_health import runtime_health
from webapp.services.runtime_health_persistence import list_runtime_health_snapshots

pages_bp = Blueprint("pages", __name__)

_ALLOWED_STATUS_FILTERS = {"all", "healthy", "degraded"}
_ALLOWED_AUTO_REFRESH_SECONDS = {0, 15, 30, 60, 120}


@dataclass(frozen=True)
class RuntimeOpsFilters:
    """Runtime operations dashboard filter set."""

    status: str = "all"
    reason: str = ""
    limit: int = 120
    auto_refresh_seconds: int = 0


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


def _parse_runtime_filters(values: Mapping[str, object]) -> RuntimeOpsFilters:
    raw_status = str(values.get("status", "all")).strip().lower()
    status = raw_status if raw_status in _ALLOWED_STATUS_FILTERS else "all"

    reason = str(values.get("reason", "")).strip()
    if len(reason) > 80:
        reason = reason[:80]

    limit = _safe_int(values.get("limit"), default=120)
    limit = max(10, min(limit, 200))

    auto_refresh_seconds = _safe_int(values.get("auto_refresh"), default=0)
    if auto_refresh_seconds not in _ALLOWED_AUTO_REFRESH_SECONDS:
        auto_refresh_seconds = 0

    return RuntimeOpsFilters(
        status=status,
        reason=reason,
        limit=limit,
        auto_refresh_seconds=auto_refresh_seconds,
    )


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _filter_snapshots(
    snapshots: list[dict],
    *,
    status: str,
    reason: str,
) -> list[dict]:
    filtered = snapshots
    if status in {"healthy", "degraded"}:
        filtered = [
            snapshot for snapshot in filtered if snapshot.get("status") == status
        ]

    normalized_reason = reason.strip().lower()
    if normalized_reason:
        filtered = [
            snapshot
            for snapshot in filtered
            if any(
                normalized_reason in str(item).lower()
                for item in snapshot.get("degraded_reasons", [])
            )
        ]
    return filtered


def _build_runtime_ops_view_model(filters: RuntimeOpsFilters) -> dict:
    """Build summary and trend data for runtime operations dashboard."""
    current = runtime_health.build_report(current_app)
    snapshots = list_runtime_health_snapshots(limit=filters.limit)
    filtered_snapshots = _filter_snapshots(
        snapshots,
        status=filters.status,
        reason=filters.reason,
    )

    status_counts = Counter(
        snapshot.get("status", "unknown") for snapshot in filtered_snapshots
    )
    degraded_reason_counts: Counter[str] = Counter()
    for snapshot in filtered_snapshots:
        for reason in snapshot.get("degraded_reasons", []):
            degraded_reason_counts[reason] += 1

    return {
        "current": current,
        "snapshots": filtered_snapshots,
        "summary": {
            "total_snapshots": len(filtered_snapshots),
            "available_snapshots": len(snapshots),
            "healthy_count": status_counts.get("healthy", 0),
            "degraded_count": status_counts.get("degraded", 0),
            "top_reasons": degraded_reason_counts.most_common(8),
        },
        "filters": {
            "status": filters.status,
            "reason": filters.reason,
            "limit": filters.limit,
            "auto_refresh": filters.auto_refresh_seconds,
        },
        "action_result": request.args.get("action_result", "").strip(),
    }


def _runtime_filters_to_query(filters: RuntimeOpsFilters) -> dict[str, str]:
    return {
        "status": filters.status,
        "reason": filters.reason,
        "limit": str(filters.limit),
        "auto_refresh": str(filters.auto_refresh_seconds),
    }


def _runtime_admin_forbidden_response():
    if (
        request.accept_mimetypes.accept_json
        and not request.accept_mimetypes.accept_html
    ):
        return jsonify({"error": "Access denied"}), 403
    return render_template("ops/runtime_health_denied.html"), 403


def _build_incident_rows(snapshots: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for snapshot in snapshots:
        if snapshot.get("status") != "degraded":
            continue

        reasons = snapshot.get("degraded_reasons", [])
        if reasons:
            for reason in reasons:
                rows.append(
                    {
                        "snapshot_id": snapshot.get("id", ""),
                        "timestamp_utc": snapshot.get("created_at", ""),
                        "status": snapshot.get("status", ""),
                        "reason": str(reason),
                    }
                )
        else:
            rows.append(
                {
                    "snapshot_id": snapshot.get("id", ""),
                    "timestamp_utc": snapshot.get("created_at", ""),
                    "status": snapshot.get("status", ""),
                    "reason": "",
                }
            )
    return rows


@pages_bp.route("/ops/runtime-health")
@login_required
def runtime_health_page():
    """Operational runtime health dashboard (owner/admin only)."""
    if not getattr(current_user, "is_admin", False):
        return _runtime_admin_forbidden_response()

    filters = _parse_runtime_filters(request.args)
    context = _build_runtime_ops_view_model(filters)
    return render_template("ops/runtime_health.html", **context)


@pages_bp.route("/ops/runtime-health/actions", methods=["POST"])
@login_required
def runtime_health_action():
    """Run admin runtime maintenance actions."""
    if not getattr(current_user, "is_admin", False):
        return _runtime_admin_forbidden_response()

    payload = request.get_json(silent=True) if request.is_json else None
    action = str(
        (payload or {}).get("action") or request.form.get("action", "")
    ).strip()

    result: dict[str, object]
    if action == "snapshot":
        snapshot_id = snapshot_runtime_health(current_app)
        result = {"action": action, "snapshot_id": snapshot_id}
    elif action in {"cleanup", "cleanup_conversations"}:
        deleted_count = cleanup_expired_conversations(current_app)
        result = {"action": "cleanup_conversations", "deleted_count": deleted_count}
    else:
        return jsonify({"error": "Unsupported action"}), 400

    if request.is_json:
        return jsonify({"success": True, **result})

    filters = _parse_runtime_filters(request.form)
    query = _runtime_filters_to_query(filters)
    if action == "snapshot":
        query[
            "action_result"
        ] = f"Snapshot captured ({result.get('snapshot_id', 'unavailable')})."
    else:
        query["action_result"] = (
            "Conversation cleanup completed "
            f"({result.get('deleted_count', 0)} deleted)."
        )
    return redirect(url_for("pages.runtime_health_page", **query))


@pages_bp.route("/ops/runtime-health/incidents.csv")
@login_required
def runtime_health_incidents_csv():
    """Export degraded runtime incidents as CSV."""
    if not getattr(current_user, "is_admin", False):
        return jsonify({"error": "Access denied"}), 403

    filters = _parse_runtime_filters(request.args)
    snapshots = list_runtime_health_snapshots(limit=filters.limit)
    filtered_snapshots = _filter_snapshots(
        snapshots,
        status=filters.status,
        reason=filters.reason,
    )
    incident_rows = _build_incident_rows(filtered_snapshots)

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["snapshot_id", "timestamp_utc", "status", "reason"])
    for row in incident_rows:
        writer.writerow(
            [row["snapshot_id"], row["timestamp_utc"], row["status"], row["reason"]]
        )

    response = Response(csv_buffer.getvalue(), mimetype="text/csv")
    response.headers[
        "Content-Disposition"
    ] = "attachment; filename=runtime-health-incidents.csv"
    return response


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
