# Railway Runtime Ops Environment Checklist

Last updated: 2026-02-11

## Core App

| Variable | Required | Recommended Value | Notes |
|---|---|---|---|
| `SECRET_KEY` | Yes | Long random string | Must not use the dev default in production. |
| `DATABASE_URL` | Yes | Railway Postgres URL | App auto-normalizes `postgres://` to `postgresql://`. |
| `AI_PROVIDER` | Yes | `anthropic` / `openai` / `deepseek` | Must match the API key you provide. |
| `ANTHROPIC_API_KEY` | Conditional | `<secret>` | Required if `AI_PROVIDER=anthropic`. |
| `OPENAI_API_KEY` | Conditional | `<secret>` | Required if `AI_PROVIDER=openai`. |
| `DEEPSEEK_API_KEY` | Conditional | `<secret>` | Required if `AI_PROVIDER=deepseek`. |

## Scheduler + Guardrails

| Variable | Required | Recommended Value | Notes |
|---|---|---|---|
| `ENABLE_BACKGROUND_JOBS` | Yes | `true` | Set `false` for one-off smoke checks. |
| `CLEANUP_CONVERSATIONS_CRON` | No | `0 * * * *` | Avoid invalid values like `*/60`. |
| `CLEANUP_CONVERSATIONS_MINUTES` | No | `60` | Used if cron is not set; safely falls back. |
| `BACKGROUND_JOB_MAX_RUNTIME_SECONDS` | No | `300` | Per-run timeout cap. |
| `BACKGROUND_JOB_MAX_RETRIES` | No | `1` | Retry count for non-timeout failures. |
| `BACKGROUND_JOB_RETRY_BACKOFF_SECONDS` | No | `2.0` | Exponential retry base delay. |
| `RUNTIME_HEALTH_SNAPSHOT_MINUTES` | No | `15` | Snapshot schedule when cron is not set. |
| `RUNTIME_HEALTH_SNAPSHOT_CRON` | No | `5,20,35,50 * * * *` | Optional explicit schedule. |

## Health Snapshot Persistence

| Variable | Required | Recommended Value | Notes |
|---|---|---|---|
| `RUNTIME_HEALTH_SNAPSHOT_ENABLED` | No | `true` | Stores trend records in DB. |
| `RUNTIME_HEALTH_SNAPSHOT_RETENTION_DAYS` | No | `30` | Deletes older snapshots. |
| `RUNTIME_HEALTH_SNAPSHOT_MAX_ROWS` | No | `2000` | Hard cap after retention trimming. |

## Startup Audit / Fail-Fast

| Variable | Required | Recommended Value | Notes |
|---|---|---|---|
| `STARTUP_CONFIG_AUDIT_FAIL_FAST` | No | `true` (prod) | Blocks startup when audit finds blocking config issues. |
| `ALEMBIC_SCRIPT_LOCATION` | No | `migrations` | Used by readiness checks to validate DB head revision alignment. |

## Operational Alerts

| Variable | Required | Recommended Value | Notes |
|---|---|---|---|
| `OP_ALERTS_ENABLED` | No | `true` | Enables webhook/Slack/email alerts. |
| `OP_ALERT_COOLDOWN_SECONDS` | No | `300` | Dedupe cooldown for repeated events. |
| `OP_ALERT_WEBHOOK_URL` | Conditional | `<https webhook>` | Generic webhook channel. |
| `OP_ALERT_SLACK_WEBHOOK_URL` | Conditional | `<slack webhook>` | Optional Slack channel. |
| `OP_ALERT_EMAIL_TO` | Conditional | `ops@yourdomain.com` | Optional email recipient. |
| `OP_ALERT_EMAIL_FROM` | No | `noreply@yourdomain.com` | Sender address for SMTP alerts. |
| `SMTP_HOST` | Conditional | `smtp.yourprovider.com` | Needed for email alerts. |
| `SMTP_PORT` | No | `587` | SMTP port. |
| `SMTP_USERNAME` | Conditional | `<smtp-user>` | Needed if SMTP auth enabled. |
| `SMTP_PASSWORD` | Conditional | `<smtp-pass>` | Needed if SMTP auth enabled. |
| `SMTP_USE_TLS` | No | `true` | Enable TLS for SMTP. |

## R2 Storage (If Enabled)

| Variable | Required | Recommended Value | Notes |
|---|---|---|---|
| `R2_STORAGE_ENABLED` | No | `true` | If true, credentials should be complete. |
| `R2_ACCOUNT_ID` | Conditional | `<account-id>` | Required when R2 is enabled. |
| `R2_ACCESS_KEY_ID` | Conditional | `<access-key>` | Required when R2 is enabled. |
| `R2_SECRET_ACCESS_KEY` | Conditional | `<secret>` | Required when R2 is enabled. |
| `R2_BUCKET_NAME` | No | `skills-storage` | Bucket used for skills artifacts. |

## Quick Verification

1. `GET /health` returns `200`.
2. `GET /health/ready` returns `200` (or `503` with actionable checks).
3. `GET /health/runtime` includes scheduler + queue + startup audit data.
4. `GET /ops/runtime-health` loads for owner/admin users.
5. `POST /ops/runtime-health/actions` works for owner/admin (`snapshot`, `cleanup`).
6. `GET /ops/runtime-health/incidents.csv` exports degraded snapshot incidents.
