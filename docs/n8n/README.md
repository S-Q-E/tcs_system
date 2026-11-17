# n8n integration

The CRM never stores provider tokens. Two directions:

## 1. CRM → client (send workflow)

File: `docs/n8n/tcs-send-message-telegram.workflow.json` (generated, do not
edit by hand).

```
POST /webhook/crm-send-message
  {outbox_id, whatsapp_id, text} + header X-CRM-Secret
    → 401 {ok:false} when the secret does not match
    → dedupe on outbox_id in n8n_processed_outbox (repeat = 200 deduped, no send)
    → Telegram sendMessage (chat id = whatsapp_id without the tg: prefix)
    → success output → Mark Sent → 200 {ok:true, provider_message_id:null}
    → error output → 502 {ok:false, error:"provider send failed"} (no dedupe row,
      so a CRM retry delivers again)
```

The CRM contract (`workers/outbox_worker.py::post_to_n8n`):

- `POST $N8N_SEND_WEBHOOK_URL`
- `X-CRM-Secret: $N8N_WEBHOOK_SECRET`
- body `{"outbox_id": "<uuid>", "whatsapp_id": "<tg:...>", "text": "..."}`
- success: HTTP 200 + `{"ok": true, ...}`; anything else marks the row failed.

### Dedupe table

```sql
CREATE TABLE IF NOT EXISTS n8n_processed_outbox (
  outbox_id uuid PRIMARY KEY,
  provider_message_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

## 2. Client → CRM (bot workflow)

`workflows/tcs_bot.json` listens to Telegram and writes to the bot tables
(`tcs_leads`, `tcs_messages`, `tcs_events`). The CRM reads them every 5 seconds
and mirrors leads into contacts/deals. Pause state is read from
`crm_conversation_state.bot_paused`: a manager reply in the CRM pauses the bot
automatically, and the bot skips replies while paused.

The bot has four tools (SQL/JS in `docs/tcs/tools-spec.md`):

| Tool | Effect |
|---|---|
| `search_units` | available units from `tcs_units` |
| `get_slots` | up to three 30-minute viewing slots, weekdays 09:00–17:00 New York |
| `book_viewing` | transactional capacity check, `trial_datetime`, status `VIEWING_BOOKED`, `trial_booked` event |
| `handoff_to_human` | status `HANDOFF` + `transferred_to_manager` event; the CRM raises a task and notification |

## 3. Reminders

`workflows/tcs_reminders.json` runs every 15 minutes, selects leads with a
viewing in the next 24 hours (`reminder_sent = false`, bot not paused), sends
the reminder and marks the row in one statement.

## Registration

1. Credentials in n8n: `Postgres account` (CRM database), `Telegram account`
   (the demo bot), `OpenRouter account` (LLM key).
2. Import the three JSON files and attach the credentials.
3. Set `N8N_WEBHOOK_SECRET` in the n8n environment (same value as the CRM).
4. Activate the workflows; Telegram registers the webhook automatically.

Manual, version-dependent steps are listed in `HUMAN_TODO.md`.
