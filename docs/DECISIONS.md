# Decisions

Architecture decisions for the TCS Leasing CRM. Numbers are stable because
code comments reference them.

## D1. Sessions, not JWT

Opaque random session tokens in `tcs_crm_sessions`, stored as SHA-256 hashes, sent
in an HttpOnly cookie; CSRF is a double-submit token for unsafe methods.
14-day sliding TTL.

## D2. One bot lead = one contact + one deal by default

The sync worker creates a contact and a deal per bot lead (`whatsapp_id` is the
join key). A deal is never duplicated for the same lead.

## D3. Two-way stage sync

The bot moves deals by `bot_stage_key`; managers move deals in the CRM and the
move is written back to the bot lead through `services/bot_bridge.py`, the only
writer to bot tables. A locked stage blocks bot moves and logs an activity.

## D4. Realtime without triggers

No Postgres triggers or logical replication. A poller reads bot tables by id
and fans out on a process-local event bus; SSE clients consume it at
`GET /api/stream`.

## D5. Bot autopause

Settings control pausing the bot on handover (`auto_pause_on_manager`) and on a
manual manager reply (`auto_pause_on_manual_reply`). The pause flag lives in
`tcs_crm_conversation_state` and the bot checks it before replying.

## D6. Manager outbound messages go through outbox + n8n webhook

The CRM stores no provider keys. A manager message is queued in `tcs_crm_outbox`;
the outbox worker POSTs `{outbox_id, whatsapp_id, text}` with `X-CRM-Secret` to
`N8N_SEND_WEBHOOK_URL`; n8n sends via Telegram and dedupes on `outbox_id`.
A mirrored row is written to `tcs_messages` by `bot_bridge.py`.

## D7. Soft delete

Contacts and deals are soft-deleted (`deleted_at`); restore is supported.
Bot tables are never modified for deletion.

## D8. Step 1 skeleton notes

FastAPI + SQLAlchemy 2.0 async + Alembic baseline; errors are uniform
`{error:{code,message,details}}`; request-id middleware and JSON logs; the
health endpoints are `/api/health` and `/api/ready`.

## D9. Step 2 auth notes

Argon2 password hashes; login rate limits are in-memory (single process) with
per-IP and per-email windows; the first admin is bootstrapped from
`ADMIN_EMAIL`/`ADMIN_PASSWORD` only when no admin exists; the last active
admin cannot be demoted or deactivated.

## D10. Step 3 domain and bot sync notes

CRM tables use the `crm_` prefix and are created only by Alembic. Bot tables
are read-only for the CRM except `bot_bridge.py`. The sync worker runs every
5 seconds under a Postgres advisory lock, backfills in batches, and updates
contacts, deals, stage history, unread counts and dialog cache.

## D11. Step 4 domain REST API notes

Pipelines/stages CRUD is admin-only; contacts support search and filters;
deals expose board (per-column cursors) and list views; notes use fractional
positions; tags, custom fields and lost reasons have role-aware CRUD; every
mutation writes an activity log entry.

## D12. Step 5 frontend scaffold notes

Vite + React 18 + TypeScript strict + Tailwind; TanStack Query; an API client
with cookies, automatic CSRF and 401 redirects; openapi-typescript types
(`npm run gen:api`); amoCRM-like layout, light/dark theme; backend serves the
built SPA with SPA fallback.

## D13. Step 6 kanban notes

Drag-and-drop with dnd-kit and optimistic updates with rollback; per-column
cursor pagination; column sums; card shows contact, amount, owner, tags,
viewing time, lock and last activity; list view supports sorting, column
toggles and bulk actions; saved views keep filters in the URL.

## D14. Step 7 card, timeline, and dialogs notes

The deal card combines overview, chat and history; the timeline merges bot
messages/events, stage history, notes, tasks and activity; dialogs support
search, filters, unread counters and the unanswered flag.

## D15. Step 8 tasks and notifications notes

Tasks have types, assignees, due dates and done/undone state; a worker creates
due-soon and overdue notifications; automations create tasks from rules;
notification delivery is deduplicated per user and entity.

## D16. Step 10 realtime notes

SSE with heartbeats; the poller keeps cursors in `tcs_crm_settings` and overlaps
windows to avoid gaps; events are deduplicated by id; the client falls back to
polling when the stream is unavailable.

## D17. Step 11 contacts and data notes

Contact merge moves deals, notes, tasks, tags and dialogs to the target and
marks the source as deleted; CSV/XLSX import and export use the same
normalization as the API; duplicate groups are computed by phone/e-mail keys.

## D18. Step 9C visibility rule for dialogs, chats and SSE

Managers with `restrict_managers_to_own` see only dialogs/contacts whose
effective owner is themselves or empty; admins and users without the
restriction see everything. The rule is applied in SQL, not in the UI.

## D19. Step 9C debt-closure notes

Unassign uses `PATCH` with an explicit `null` distinct from an absent field;
assignment changes are mirrored to deal, contact and dialog; the dialog list
caches the last message for sorting.

## D20. Step 12 analytics notes

The overview returns funnel, summary, dynamics, managers, sources, tags and bot
sections for a date range; the funnel cohort is deals created in the range;
lost reasons are grouped with a fallback label; CSV export mirrors the API
sections.

## D21. Step 13 settings notes

Settings are key/value JSONB: analytics visibility for managers, pause policy,
deal assignment mode, unanswered threshold, paused-alert hours and sync
cursors. Profile preferences (timezone, sound) live in the browser.

## D22. Step 14 hardening notes

Per-IP request limiting, per-user send limiting, body size limits, security
headers, SSE connection limits, CSV injection protection and XSS-safe rendering
of imported content; production requires HTTPS and secure cookies.

## D23. Step 9D part B notes (n8n send workflow + targeted hardening)

The CRM sends through the n8n webhook only; the workflow checks the shared
secret, dedupes on `outbox_id`, and answers 200/401/502. Telegram has no
success field, so the Telegram output is the source of truth.

## D24. Step 15 production deploy notes

One container: Node builds the SPA, Python serves API and static files. The
entrypoint runs migrations, then one uvicorn worker (the realtime bus is
process-local). Healthcheck `/api/health`; Railway sets `PORT`.

## D25. Step 16a security-audit closure notes

Audit findings were closed with tests: session revocation, CSRF on all unsafe
methods, login limits, IDOR checks on every entity, import validation and
safe error messages. The remaining items are tracked in the improvement plan.

## D26. Single uvicorn worker until the realtime bus is cross-process (P1-1)

The event bus lives in process memory, so two workers would split SSE clients.
Keep `--workers 1` until LISTEN/NOTIFY is implemented.

## D27. Operational gauges on /api/metrics (P1-11)

Prometheus text metrics are available when `METRICS_TOKEN` is set; the endpoint
returns 404 otherwise. Gauges cover outbox queue, paused bots and unanswered
dialogs.

## D28. Unanswered dialogs (P0-5)

One definition (`services/unanswered.py`) is shared by the list filter, the
per-row flag, the notification worker and the gauge: last message incoming,
older than the threshold, bot not paused. A dialog can be paused deliberately
and then it is not «unanswered».

## D29. Realtime poller cursor: overlap, dedupe, restart (P2-2) and header status (P3-6)

Cursors persist in settings and restart from a small overlap; duplicates are
dropped by id; the UI shows Online / Fallback polling / Offline.

## D30. Long bot pause alert (P3-2)

A paused dialog older than `paused_alert_hours` raises one notification per
episode, so managers notice a bot that nobody resumed.

## D31. Full conversation capture (research, no code yet)

Capturing every provider message (including manager messages sent from the
phone) requires a provider webhook with echo events; the reference design is
kept outside the repository. Not part of the demo.

## D32. Handover once per deal (B-01, audit fix)

The handover notification and task are created once per deal and deduplicated;
a later handover on the same deal does not spam managers.

## D33. Contact merge and chat (B-09, audit fix)

Merging contacts moves conversations and mirrors the newest state to the
surviving contact; the chat key stays `whatsapp_id`.

## D34. Event stream re-checks its session (B-13, B-14 related)

SSE connections re-validate the session and user scope periodically; a revoked
session or a role change closes the stream.

## D35. Notify cycle isolation (B-06)

One failing notification rule does not abort the whole cycle; each rule runs in
its own savepoint and errors are logged.

## D36. Outgoing messages from the manager's phone (no CRM code change)

Messages sent outside the CRM are captured by the bot workflow and written to
(the bot tables; the CRM mirrors them as manager messages. No CRM change is
required for this.

## D37. Deal/contact timeline labels manager outgoing as manager

Outgoing rows with `message_type='manager'` are rendered as manager messages
with the manager's name; bot rows keep the assistant label.

## D38. Mobile A: breakpoints, list → chat, 16px/44px

Lists become a single-column master-detail below `md`; the chat replaces the
list; inputs keep 16px and touch targets 44px to avoid iOS zoom.

## D39. New deals appear on top of their kanban column

New cards get `position = min(position) - 1` inside their stage, so bot-created
deals land on top; the backfill migration aligns existing first-open columns
only.

## D40. One responsible manager: deal is the source of truth

The deal owner is authoritative and mirrored to the contact, the dialog and
existing deals. Assignment is edited in the deal card; other screens show it
read-only.

## D41. TCS demo seed and its guardrails

`scripts/seed_tcs_demo.py` fills the demo slice (never the pipeline), refuses
without `DEMO_DB_CONFIRM`, refuses production-looking bot data and deletes only
`source='demo'` rows. Bot field text lands in fields the CRM already shows;
`whatsapp_id` is historical and stores `tg:<chat_id>`. Assumptions in the
savings card are labelled as estimates.

## D42. n8n workflows are generated, not hand-edited

`scripts/build_tcs_workflows.py` produces the send workflow, the bot and the
reminders; node parameters come from the original exports (bot template is
supplied via `TCS_BOT_TEMPLATE`), SQL/JS from `docs/tcs/tools-spec.md`, the
prompt from `docs/tcs/bot-prompt.md`. `scripts/validate_workflow.py` and the
static tests check ids, names, connections and key contracts. New projects
must not hand-edit generated JSON.
