# Bot behaviour cases (handoff & slots)

Reference cases for the TCS Telegram bot. They pin the behaviour that the
system prompt (`docs/tcs/bot-prompt.md`) and the tool descriptions must
produce. `backend/tests/test_tcs_workflows.py` checks that each phrase and its
expected behaviour stay documented and that the prompt/SQL still contain the
required guardrails.

Viewing hours: Monday-Friday, 10:00-17:00 America/New_York. No weekend slots.

| # | User phrase | Expected tool calls | Expected reply | Must NOT happen |
|---|---|---|---|---|
| 1 | "I want to see an apartment on Sunday, November 23" | `get_slots` with `from_date=2026-11-23` (returns Mon-Fri slots) | Says there are no weekend viewings and offers the nearest weekday slots (with date/time in ET) | `handoff_to_human`; inventing a Sunday slot |
| 2 | "I need an apartment" | none (no `search_units`/`get_slots` yet) | Asks ONE clarifying question (bedrooms, budget or pets) | `handoff_to_human`; asking three questions at once |
| 3 | "Can I speak to a manager, please?" | `handoff_to_human` | Says a team member will follow up | Booking/searching instead of handoff |
| 4 | "Show me viewings for next week" when `get_slots` returns `[]` | `get_slots` (perhaps retried with a later `from_date`) | Explains viewings are weekdays 10:00-17:00 ET and offers the next available slots | `handoff_to_human`; claiming there are no viewings at all |
| 5 | `get_slots` returns an error once, then again | `get_slots` retried once, then `handoff_to_human` after the second failure | Apologizes, retries, and only then transfers to the team | Silently stopping; handoff after the first error |

Notes:

- Case 1: the bot must never convert a weekend request into a fabricated
  weekend time. The 7-day window from `from_date` naturally returns the
  following weekdays.
- Case 2: a vague request is not a handoff trigger and not a reason to call
  `search_units` with empty filters.
- Case 3 is the only routine handoff trigger besides complaints.
- Case 4: an empty slot list is a scheduling explanation, not a transfer.
- Case 5: two consecutive tool errors is the escalation threshold.
