# DB schema (tcs_*) — TCS Leasing CRM demo

> Source: the bot schema in `tests/fixtures/tcs_schema.sql` (the demo seed
> creates `tcs_units` on top of it). The CRM never migrates these tables:
> they are owned by n8n and by `scripts/seed_tcs_demo.py`, and the CRM writes
> to them only through `bot_bridge.py`.

`whatsapp_id` is a historical column name: it stores the chat identifier
(`tg:<chat_id>` for Telegram), not a phone number.

Tables used by the CRM: `tcs_leads`, `tcs_messages`, `tcs_events`,
`tcs_followups`, `tcs_units` (read-only catalog for the bot).
CRM tables live in the same database under the `crm_` prefix and are created
only by Alembic (see `backend/alembic/versions`, version table
`tcs_crm_alembic_version`).
n8n-owned helper tables: `tcs_n8n_chat_histories` (agent memory) and
`tcs_n8n_processed_outbox` (dedupe for CRM → Telegram sends).
Other bot tables (not used by the CRM): `tcs_ai_metrics`,
`tcs_chat_history`, `bot_*`, `chat_status`, `reminders`, `Reminderai`, views
`tcs_*`.

**There are no foreign keys between tcs_* tables.** Rows are matched by
`whatsapp_id` (VARCHAR(50)). Deleting a lead does not delete its messages or events, so
tests and scripts must remove child rows explicitly.

## tcs_leads

PK `id` (integer, sequence). `whatsapp_id` is UNIQUE, not the primary key.
Trigger `update_tcs_leads_updated_at` sets `updated_at = now()` on every UPDATE.

| column | type | nullable | default |
|---|---|---|---|
| id | integer | NO | nextval(tcs_leads_id_seq) |
| whatsapp_id | varchar(50) | NO |  |
| name | varchar(100) | YES |  |
| status | varchar(30) | YES | 'new' |
| current_stage | varchar(50) | YES | 'NEW_INQUIRY' |
| previous_stage | varchar(50) | YES |  |
| direction | varchar(100) | YES |  |
| goal | varchar(200) | YES |  |
| experience_level | varchar(50) | YES |  |
| preferred_format | varchar(50) | YES |  |
| preferred_time | varchar(50) | YES |  |
| trial_datetime | timestamptz | YES |  |
| last_objection | text | YES |  |
| primary_objection | text | YES |  |
| confidence_last | numeric(3,2) | YES |  |
| reminder_sent | boolean | YES | false |
| lead_data | jsonb | YES | '{}' |
| source | varchar(100) | YES | 'telegram' |
| created_at | timestamptz | YES | CURRENT_TIMESTAMP |
| updated_at | timestamptz | YES | CURRENT_TIMESTAMP |
| last_message_at | timestamptz | YES | CURRENT_TIMESTAMP |
| last_interaction_at | timestamptz | YES | CURRENT_TIMESTAMP |
| client_name, phone, target_course, course_format, class_type, skill_level, student_category | varchar | YES |  |

The last group (`client_name` … `student_category`) comes from the legacy bot. The
TCS demo seed fills `client_name`; the bot workflow and the CRM use `name`.

## tcs_messages

PK `id` bigint (sequence). `direction` is `varchar(3)` with CHECK `in`/`out`. No FK.
Indexes: `(whatsapp_id)`, `(created_at)`. There is **no** composite `(whatsapp_id, created_at)`
index (a known perf note, not applied here).

| column | type | nullable | default |
|---|---|---|---|
| id | bigint | NO | sequence |
| whatsapp_id | varchar(50) | NO |  |
| direction | varchar(3) | NO |  |
| message_type | varchar(20) | YES | 'chat' |
| content | text | YES |  |
| stage_at_moment | varchar(50) | YES |  |
| tokens_used | integer | YES |  |
| response_time_ms | integer | YES |  |
| created_at | timestamptz | YES | CURRENT_TIMESTAMP |

## tcs_events

PK `id` bigint (sequence). No FK.

| column | type | nullable | default |
|---|---|---|---|
| id | bigint | NO | sequence |
| whatsapp_id | varchar(50) | NO |  |
| event_type | varchar(40) | NO |  |
| from_stage | varchar(50) | YES |  |
| to_stage | varchar(50) | YES |  |
| payload | jsonb | YES | '{}' |
| created_at | timestamptz | YES | CURRENT_TIMESTAMP |

## tcs_followups

PK `id` bigint (sequence). No FK. Written by the n8n workflow (`Insert Follow-up`); no consumer
is known (architecture §11.1).

| column | type | nullable | default |
|---|---|---|---|
| id | bigint | NO | sequence |
| whatsapp_id | varchar(50) | NO |  |
| kind | varchar(20) | NO | 'THINKING' |
| scheduled_at | timestamptz | NO |  |
| attempt_number | integer | NO | 1 |
| status | varchar(20) | NO | 'PENDING' |
| message | text | YES |  |
| created_at | timestamptz | YES | CURRENT_TIMESTAMP |
| sent_at | timestamptz | YES |  |

## tcs_units (demo catalog, created by the seed)

Owned by the demo seed (`scripts/seed_tcs_demo.py`), read-only for the CRM
and used by the bot tool `search_units`.

| column | type | nullable | default |
|---|---|---|---|
| id | serial | NO | sequence |
| building | text | YES |  |
| unit_number | text | YES |  |
| beds | int | YES |  |
| baths | numeric | YES |  |
| rent_usd | int | YES |  |
| deposit_usd | int | YES |  |
| available_from | date | YES |  |
| status | text | YES | 'available' |
| pets_policy | text | YES |  |
| description | text | YES |  |

UNIQUE `(building, unit_number)`. Demo rows: 14 units in
`Demo Residences A/B/C`, 2 of them `leased`.

## Distinct values

### tcs_leads.current_stage — TCS Leasing pipeline (bot keys)

Alembic seeds the single `TCS Leasing` pipeline (six stages, all board
columns):

| name | kind | bot_stage_key | bot_status_key |
|---|---|---|---|
| New inquiry | open | NEW_INQUIRY | — |
| Qualified | open | QUALIFIED | — |
| Viewing scheduled | open | VIEWING_SCHEDULED | — |
| Viewing done | open | VIEWING_DONE | — |
| Leased | won | — | LEASED |
| Lost | lost | — | LOST |

Bot meaning: NEW_INQUIRY = first message only; QUALIFIED = bedrooms or a unit
known AND move-in date or budget known; VIEWING_SCHEDULED = viewing booked;
VIEWING_DONE = viewing happened (a manager moves the card).

### tcs_leads.status

- ACTIVE
- VIEWING_BOOKED
- THINKING
- HANDOFF
- LEASED
- LOST

### tcs_events.event_type (from `frontend/app.js` EVENT_ICONS)
- stage_entered
- stage_exited
- objection_raised
- trial_booked
- transferred_to_manager
- followup_sent
- lead_lost
- sale_won
- (code also writes `manual_stage_change`, see D3)
