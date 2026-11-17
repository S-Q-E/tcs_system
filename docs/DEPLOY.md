# Deployment and operations

One container serves the API and the built SPA. The demo deployment guide for
Railway is `docs/tcs/RAILWAY_DEPLOY.md`; this document covers the general
mechanics.

## Image

`Dockerfile` is multi-stage: Node 20 builds `frontend/dist`, then a Python 3.12
image installs `requirements.txt`, copies the backend, scripts and the built
SPA, runs as an unprivileged user and starts
`scripts/docker-entrypoint.sh`, which:

1. runs `alembic -c backend/alembic.ini upgrade head` (idempotent; concurrent
   boots serialize on an advisory lock);
2. starts one uvicorn worker on `$PORT` (the realtime event bus is
   process-local, see D26).

`railway.json` configures the Dockerfile build, restart policy and the
`/api/health` healthcheck.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Postgres DSN (or the `PG*` parts) |
| `APP_ENV` / `LOG_LEVEL` | local / INFO | Logging and environment name |
| `COOKIE_SECURE` | true | Must be `true` behind HTTPS |
| `DEFAULT_TIMEZONE` / `DEFAULT_CURRENCY` | America/New_York / USD | UI and analytics defaults |
| `TRUSTED_PROXY_HOPS` | 1 | Trailing X-Forwarded-For entries added by proxies |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | — | Bootstrap the first admin once (≥10 chars) |
| `SECRET_KEY` | — | Signing/tooling secret; keep long and random |
| `ALLOWED_ORIGINS` | empty | Extra CORS origins (same-origin by default) |
| `N8N_SEND_WEBHOOK_URL` / `N8N_WEBHOOK_SECRET` | — | CRM → n8n message delivery |
| `SYNC_ENABLED` / `OUTBOX_ENABLED` / `NOTIFICATIONS_ENABLED` / `REALTIME_ENABLED` | true | Worker kill switches |
| `RATE_LIMIT_*`, `MAX_REQUEST_BODY_BYTES` | see `.env.example` | Hardening |
| `METRICS_TOKEN` | — | Enables `/api/metrics`; 404 without it |
| `SENTRY_DSN` | — | Optional error reporting |
| `PORT` | 8000 | Set by the platform |

Secrets live only in the platform environment; never commit them. For the demo
seed only, `DEMO_DB_CONFIRM=I_UNDERSTAND_THIS_IS_A_DEMO_DB` is required by
`scripts/seed_tcs_demo.py`.

## Database and migrations

- CRM tables (`crm_*`) are created only by Alembic; the version table is
  `crm_alembic_version`.
- Bot tables (`tcs_*`) belong to the bot/seed; migrations never create them.
  Backfills that read them are guarded with an existence check, so
  `alembic upgrade head` succeeds on a brand-new database.
- The single pipeline «TCS Leasing» with six stages is seeded by migration
  `0003_domain` through `services/funnel_seed.py`.
- Demo data: `scripts/seed_tcs_demo.py` (guardrails, `--reset` deletes only
  `source='demo'` rows). The seed applies the bot schema if it is missing.

## Workers

All workers are in-process asyncio tasks and use advisory locks:

| Worker | Flag | Cycle | Purpose |
|---|---|---|---|
| sync | `SYNC_ENABLED` | 5 s | bot leads → contacts/deals, stage moves, unread counts, handover |
| outbox | `OUTBOX_ENABLED` | 5 s | manager messages → n8n webhook, mirror to bot tables |
| notifications | `NOTIFICATIONS_ENABLED` | 60 s | task reminders, automations |
| realtime poller | `REALTIME_ENABLED` | 2 s | bot tables → SSE |

## Health and metrics

- `GET /api/health` — liveness (used by the platform).
- `GET /api/ready` — readiness (database reachable).
- `GET /api/metrics` — Prometheus text, guarded by `METRICS_TOKEN`.

## Backups and restore

See `docs/BACKUP.md` (single `pg_dump`, nightly rotation, restore steps).

## Rollback

Redeploy a previous Railway deployment. Database downgrades are not part of the
demo flow: the demo database can be recreated and re-seeded. Never restore a
newer database under older code without `alembic downgrade`.

## CI

`.github/workflows/ci.yml` runs lint, backend tests against a Postgres service,
frontend typecheck/lint/tests/build and a Docker build.

## Environments

Use two Railway environments with separate databases: **staging** for
rehearsals and **production** for the client. They run the same image and the
same variables; only values differ (`DATABASE_URL`, admin credentials, bot
token, n8n URLs). Never point staging at the production database.

## Least-privilege database role

The app reads the bot tables and writes only the columns it owns. Create a
dedicated role instead of using the database superuser:

```sql
CREATE ROLE crm_app LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE your_db TO crm_app;
GRANT USAGE ON SCHEMA public TO crm_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crm_app;
GRANT SELECT ON tcs_leads, tcs_messages, tcs_events, tcs_followups, tcs_units TO crm_app;
GRANT UPDATE (current_stage, previous_stage, updated_at) ON tcs_leads TO crm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crm_app;
```

The bot tables stay read-only except the mirror columns; a missing grant fails
loudly with `permission denied`, which is the intended behaviour. Migrations
run under the migration role (the owner), not under `crm_app`.

## Migration policy

Every schema change follows expand/contract: deploy additive columns and
backfills first (expand), switch the code, and only then remove the old
columns (contract). Migrations must stay safe to re-run and must not rewrite
bot tables; backfills that read `tcs_*` are guarded by an existence check.

## Smoke test and CI deploys

`scripts/smoke.sh` checks `/api/health`, login and the board after a deploy.
CI deploys use a project token: set `RAILWAY_TOKEN` as a repository secret and
call `railway up` for the `demo` service. The platform healthcheck is
`GET /api/health`; a failed healthcheck rolls the deployment back
automatically. Rollback manually via Railway → Deployments → Redeploy.
