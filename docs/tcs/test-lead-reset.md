# Resetting the test Telegram lead

Use before a fresh bot test run. The procedure resets one lead only and also
clears the n8n chat memory, so the bot starts a genuinely new conversation.

```
DEMO_DB_CONFIRM=I_UNDERSTAND_THIS_IS_A_DEMO_DB \
  python scripts/reset_test_lead.py --whatsapp-id tg:563779188
```

What it does (single transaction, one `whatsapp_id`):

1. Cancels every active viewing via `tcs_crm_cancel_viewing(...)` (the slot
   becomes `open` again and a `trial_cancelled` event is written).
2. Resets `tcs_leads`: `status='ACTIVE'`, `current_stage='NEW_INQUIRY'`,
   `previous_stage=NULL`, `trial_datetime=NULL`, `reminder_sent=false`,
   `last_objection=NULL`, `lead_data='{}'`.
3. Sets `tcs_crm_conversation_state.bot_paused=false` (clears `paused_by` and
   `paused_at`).
4. Deletes the rows in `n8n_chat_histories` where `session_id = whatsapp_id`
   (the n8n Postgres Chat Memory). Without this the next dialog continues with
   the old history, including bedrooms/budget/pets from previous tests.

The script refuses to run without `DEMO_DB_CONFIRM` and never touches other
leads. History rows in `tcs_messages` / `tcs_events` are kept as an audit trail.
