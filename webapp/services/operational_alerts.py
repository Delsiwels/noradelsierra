"""Operational alert hooks (webhook/slack/email)."""

from __future__ import annotations

import json
import logging
import smtplib
import threading
import time
from collections import deque
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from urllib import request

from flask import Flask

logger = logging.getLogger(__name__)

_ALERT_LOCK = threading.Lock()
_LAST_ALERT_BY_KEY: dict[str, float] = {}
_ALERT_TELEMETRY_LOCK = threading.Lock()
_ALERT_TELEMETRY_RECENT_LIMIT = 40
_ALERT_TELEMETRY: dict[str, Any] = {
    "counts": {
        "attempted": 0,
        "delivered": 0,
        "failed": 0,
        "suppressed": 0,
    },
    "channels": {
        "webhook": {"attempted": 0, "delivered": 0, "failed": 0},
        "slack": {"attempted": 0, "delivered": 0, "failed": 0},
        "email": {"attempted": 0, "delivered": 0, "failed": 0},
    },
}
_ALERT_TELEMETRY_RECENT: deque[dict[str, Any]] = deque(
    maxlen=_ALERT_TELEMETRY_RECENT_LIMIT
)


def send_operational_alert(
    app: Flask,
    *,
    event_type: str,
    severity: str,
    message: str,
    details: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    """Send an operational alert if channels are configured."""
    if not app.config.get("OP_ALERTS_ENABLED"):
        _record_alert_suppressed(event_type, severity, reason="alerts_disabled")
        return False

    cooldown_seconds = int(app.config.get("OP_ALERT_COOLDOWN_SECONDS", 300))
    effective_dedupe_key = dedupe_key or f"{event_type}:{severity}:{message}"
    if _is_suppressed(effective_dedupe_key, cooldown_seconds):
        _record_alert_suppressed(event_type, severity, reason="cooldown")
        return False

    payload = {
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "details": details or {},
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }

    delivered = False
    channel_results: dict[str, bool] = {}
    webhook_url = app.config.get("OP_ALERT_WEBHOOK_URL")
    slack_webhook = app.config.get("OP_ALERT_SLACK_WEBHOOK_URL")
    email_to = app.config.get("OP_ALERT_EMAIL_TO")

    if webhook_url:
        webhook_delivered = _post_json(webhook_url, payload)
        channel_results["webhook"] = webhook_delivered
        delivered = webhook_delivered or delivered

    if slack_webhook:
        slack_text = (
            f"[{severity.upper()}] {event_type}\n"
            f"{message}\n"
            f"details={json.dumps(details or {}, sort_keys=True)}"
        )
        slack_delivered = _post_json(slack_webhook, {"text": slack_text})
        channel_results["slack"] = slack_delivered
        delivered = slack_delivered or delivered

    if email_to:
        email_delivered = _send_email_alert(
            app,
            to_address=email_to,
            subject=f"[{severity.upper()}] {event_type}",
            body=f"{message}\n\n{json.dumps(payload, indent=2, sort_keys=True)}",
        )
        channel_results["email"] = email_delivered
        delivered = email_delivered or delivered

    _record_alert_attempt(
        event_type=event_type,
        severity=severity,
        delivered=delivered,
        channel_results=channel_results,
    )

    if not delivered:
        logger.warning(
            "Operational alert could not be delivered for event %s", event_type
        )
    return delivered


def get_operational_alert_telemetry() -> dict[str, Any]:
    """Return alert delivery telemetry snapshot."""
    with _ALERT_TELEMETRY_LOCK:
        return {
            "counts": {
                "attempted": int(_ALERT_TELEMETRY["counts"]["attempted"]),
                "delivered": int(_ALERT_TELEMETRY["counts"]["delivered"]),
                "failed": int(_ALERT_TELEMETRY["counts"]["failed"]),
                "suppressed": int(_ALERT_TELEMETRY["counts"]["suppressed"]),
            },
            "channels": {
                channel: {
                    "attempted": int(metrics["attempted"]),
                    "delivered": int(metrics["delivered"]),
                    "failed": int(metrics["failed"]),
                }
                for channel, metrics in _ALERT_TELEMETRY["channels"].items()
            },
            "recent": list(_ALERT_TELEMETRY_RECENT),
        }


def reset_operational_alert_telemetry() -> None:
    """Reset in-memory alert telemetry and dedupe state (test helper)."""
    with _ALERT_LOCK:
        _LAST_ALERT_BY_KEY.clear()

    with _ALERT_TELEMETRY_LOCK:
        _ALERT_TELEMETRY["counts"] = {
            "attempted": 0,
            "delivered": 0,
            "failed": 0,
            "suppressed": 0,
        }
        _ALERT_TELEMETRY["channels"] = {
            "webhook": {"attempted": 0, "delivered": 0, "failed": 0},
            "slack": {"attempted": 0, "delivered": 0, "failed": 0},
            "email": {"attempted": 0, "delivered": 0, "failed": 0},
        }
        _ALERT_TELEMETRY_RECENT.clear()


def _is_suppressed(key: str, cooldown_seconds: int) -> bool:
    now = time.time()
    with _ALERT_LOCK:
        last = _LAST_ALERT_BY_KEY.get(key)
        if last is not None and (now - last) < cooldown_seconds:
            return True
        _LAST_ALERT_BY_KEY[key] = now
        return False


def _record_alert_suppressed(event_type: str, severity: str, *, reason: str) -> None:
    with _ALERT_TELEMETRY_LOCK:
        _ALERT_TELEMETRY["counts"]["suppressed"] += 1
        _ALERT_TELEMETRY_RECENT.appendleft(
            {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                "severity": severity,
                "status": "suppressed",
                "reason": reason,
                "channels": [],
            }
        )


def _record_alert_attempt(
    *,
    event_type: str,
    severity: str,
    delivered: bool,
    channel_results: dict[str, bool],
) -> None:
    with _ALERT_TELEMETRY_LOCK:
        _ALERT_TELEMETRY["counts"]["attempted"] += 1
        if delivered:
            _ALERT_TELEMETRY["counts"]["delivered"] += 1
            status = "delivered"
        else:
            _ALERT_TELEMETRY["counts"]["failed"] += 1
            status = "failed"

        for channel, result in channel_results.items():
            if channel not in _ALERT_TELEMETRY["channels"]:
                continue
            _ALERT_TELEMETRY["channels"][channel]["attempted"] += 1
            if result:
                _ALERT_TELEMETRY["channels"][channel]["delivered"] += 1
            else:
                _ALERT_TELEMETRY["channels"][channel]["failed"] += 1

        _ALERT_TELEMETRY_RECENT.appendleft(
            {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                "severity": severity,
                "status": status,
                "reason": "",
                "channels": [
                    {"name": channel, "delivered": result}
                    for channel, result in channel_results.items()
                ],
            }
        )


def _post_json(url: str, payload: dict[str, Any]) -> bool:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(  # noqa: S310
        url=url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=5) as resp:  # noqa: S310  # nosec B310
            return bool(200 <= int(resp.status) < 300)
    except Exception as exc:
        logger.warning("Webhook alert delivery failed: %s", exc)
        return False


def _send_email_alert(
    app: Flask,
    *,
    to_address: str,
    subject: str,
    body: str,
) -> bool:
    host = app.config.get("SMTP_HOST")
    if not host:
        return False

    port = int(app.config.get("SMTP_PORT", 587))
    username = app.config.get("SMTP_USERNAME")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = bool(app.config.get("SMTP_USE_TLS", True))
    from_address = app.config.get("OP_ALERT_EMAIL_FROM", "noreply@finql.ai")

    msg = EmailMessage()
    msg["From"] = from_address
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=8) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("Email alert delivery failed: %s", exc)
        return False
