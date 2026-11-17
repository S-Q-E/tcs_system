# CHANGES

All work is committed directly to `main` of the TCS repository
(`https://github.com/S-Q-E/tcs_system`). This document summarises the current
state of the project.

## Product

- TCS Leasing CRM demo for TCS Property Management (Philadelphia): English UI,
  USD, `America/New_York`, permanent «DEMO — fictional data» banner,
  product name «TCS Leasing CRM».
- Telegram bot through n8n: answers instantly, books viewings, hands off to a
  manager; the CRM mirrors the bot tables, shows dialogs/deals/tasks and lets a
  manager take over (pausing the bot automatically).
- Analytics: funnel, bot metrics, after-hours KPI and an «Estimated savings»
  card with editable assumptions (labelled as an estimate).

## Backend

- `models/pipelines.py`: five bot status constants are now English
  (`VIEWING_BOOKED`, `THINKING`, `HANDOFF`, `LEASED`, `LOST`) plus `ACTIVE`.
- `services/funnel_seed.py`: the only pipeline is «TCS Leasing» with exactly six
  stages (New inquiry, Qualified, Viewing scheduled, Viewing done, Leased,
  Lost) and five English lost reasons; seeded by migration `0003_domain`.
- `services/analytics.py`: status comparisons use the constants; new
  `after_hours_leads` / `after_hours_share` in the bot section.
- `schemas/analytics.py`: the new fields in `BotOut`.
- `services/normalize.py`: `tg:<chat_id>` is not treated as a phone number.
- `alembic/versions/0010_outbox.py`: English quick-reply templates
  (Greeting, Viewing reminder, Thank you).
- `alembic/versions/0015_dialogs_list.py`: the backfill is guarded by a
  table-existence check, so migrations succeed on a brand-new database.
- `workers/sync_worker.py`, `services/assignment.py`, `services/timeline.py`:
  English constants/docstrings; no legacy stage names.
- `backend/tests/**`: new funnel/status expectations, `test_funnel_seed.py`
  (fresh DB: one pipeline, six stages), `test_seed_tcs_demo.py`,
  `test_tcs_workflows.py`; the bot-tables contract constant was renamed.

## Demo data

- `scripts/seed_tcs_demo.py`: never creates the pipeline (only verifies the six
  stages), guardrails unchanged; 30 leads distributed 4 / 6 / 4 / 8 / 3 / 5
  across the six stages, 8 past viewings + 4 upcoming, 3 missed/cancelled
  returned to Qualified, 2 `HANDOFF`, one unanswered dialog in New inquiry.
- `tcs_units` catalog (14 units, 2 leased) created by the seed.
- `tests/fixtures/tcs_schema.sql` defaults use `NEW_INQUIRY`; the fixture seed
  is English and covers all statuses.

## Frontend

- Full English interface; USD and US date formats; timezones New York,
  Chicago, Denver, Los Angeles, UTC.
- Deal card bot fields: «Unit of interest», «Move-in & budget», «Bedrooms»,
  «Viewing preference», «Objection»; `experience_level` and `lead_data` extras
  are not shown.
- `lib/savings.ts` + `savings.test.ts`: `estimateSavings()`.
- Analytics page: «Estimated savings» card with three editable assumptions
  (localStorage, `try/catch`), after-hours KPI.
- `api/types.ts` regenerated with `npm run gen:api`.

## n8n

- `scripts/build_tcs_workflows.py` generates:
  - `docs/n8n/tcs-send-message-telegram.workflow.json` (CRM outbox → Telegram,
    same secret/dedupe/contract, 502 on failure);
  - `workflows/tcs_bot.json` (Telegram trigger, pause check, agent with four
    tools, reply first, logging, agent-error handoff);
  - `workflows/tcs_reminders.json` (15-minute viewing reminders).
- Workflows use the six TCS stages and English statuses; there is no Google
  Sheets node and no Cloud knowledge base — the bot only uses `tcs_units`.
- `docs/tcs/tools-spec.md`: SQL/JS for `search_units`, `get_slots`,
  `book_viewing` (stores `lead_data.unit`, status `VIEWING_BOOKED`),
  `handoff_to_human` (status `HANDOFF`).
- `docs/tcs/bot-prompt.md`: the English prompt plus the stage values.
- `scripts/validate_workflow.py` + static tests guard ids, names, connections.

## Documentation

- `README.md`, `docs/db_schema.md`, `docs/DEPLOY.md`, `docs/DECISIONS.md`,
  `docs/BACKUP.md`, `docs/n8n/README.md`, `DEMO_SCRIPT.md`, `HUMAN_TODO.md`,
  `docs/tcs/RAILWAY_DEPLOY.md`, `docs/tcs/IMPROVEMENT_PLAN.md` are English.
- Old research/history files and the original template exports were moved out
  of the repository (kept in the author's local `notes/` directory, not
  committed).

## Naming exception

`whatsapp_id` is a historical column/API name kept for compatibility with the
bot tables; it stores the chat identifier (`tg:<chat_id>`), not a phone number.
