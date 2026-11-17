-- Test seed: covers all statuses/stages used by the CRM.
-- Stages come from the seeded TCS Leasing pipeline; statuses are the bot codes.

INSERT INTO tcs_leads (whatsapp_id, name, current_stage, previous_stage, status, direction, goal, experience_level, preferred_format, preferred_time, trial_datetime, last_objection, created_at, updated_at, last_message_at, confidence_last) VALUES
('77010000001@c.us', 'Alice Demo', 'NEW_INQUIRY', NULL, 'ACTIVE', 'in', 'Rent for myself', 'beginner', 'offline', 'evening', NULL, NULL, now() - interval '3 days', now() - interval '1 hour', now() - interval '1 hour', 0.91),
('77010000002@c.us', 'Bob Demo', 'VIEWING_SCHEDULED', 'QUALIFIED', 'VIEWING_BOOKED', 'in', 'Rent with a roommate', 'middle', 'online', 'morning', now() + interval '2 days', NULL, now() - interval '5 days', now() - interval '2 hours', now() - interval '2 hours', 0.87),
('77010000003@c.us', 'Cara Demo', 'QUALIFIED', 'QUALIFIED', 'THINKING', 'in', 'Move closer to work', 'beginner', 'online', 'afternoon', NULL, 'price', now() - interval '7 days', now() - interval '1 day', now() - interval '1 day', 0.62),
('77010000004@c.us', 'Dan Demo', 'QUALIFIED', 'QUALIFIED', 'HANDOFF', 'in', 'Relocation', 'advanced', 'offline', 'evening', NULL, 'wants to talk to a human', now() - interval '2 days', now() - interval '30 minutes', now() - interval '30 minutes', 0.55),
('77010000005@c.us', 'Eva Demo', 'VIEWING_DONE', 'VIEWING_SCHEDULED', 'LEASED', 'in', 'New job', 'middle', 'offline', 'morning', now() - interval '1 day', NULL, now() - interval '20 days', now() - interval '1 day', now() - interval '1 day', 0.99),
('77010000006@c.us', 'Frank Demo', 'VIEWING_DONE', 'VIEWING_DONE', 'LOST', 'in', 'Temporary stay', 'beginner', 'online', 'evening', NULL, 'no time', now() - interval '10 days', now() - interval '3 days', now() - interval '3 days', 0.41)
ON CONFLICT (whatsapp_id) DO NOTHING;

INSERT INTO tcs_messages (whatsapp_id, direction, message_type, content, stage_at_moment, tokens_used, response_time_ms, created_at) VALUES
('77010000001@c.us', 'in', 'chat', 'Hi! I want to rent a 1-bedroom', 'NEW_INQUIRY', 12, NULL, now() - interval '2 hours'),
('77010000001@c.us', 'out', 'chat', 'Hi Alice! What is your move-in date?', 'QUALIFIED', 45, 1200, now() - interval '2 hours' + interval '1 minute'),
('77010000001@c.us', 'in', 'chat', 'Around January 1st', 'QUALIFIED', 10, NULL, now() - interval '1 hour'),
('77010000002@c.us', 'in', 'chat', 'Please book me a viewing', 'QUALIFIED', 9, NULL, now() - interval '2 hours'),
('77010000002@c.us', 'out', 'chat', 'Booked! See you Thursday at 10:00', 'VIEWING_SCHEDULED', 30, 900, now() - interval '2 hours' + interval '2 minutes'),
('77010000003@c.us', 'in', 'chat', 'The price is a bit high for me', 'QUALIFIED', 8, NULL, now() - interval '1 day'),
('77010000004@c.us', 'in', 'chat', 'Please connect me with a manager', 'QUALIFIED', 7, NULL, now() - interval '30 minutes'),
('77010000005@c.us', 'out', 'chat', 'Congratulations on your new home!', 'VIEWING_DONE', 20, 800, now() - interval '1 day'),
('77010000006@c.us', 'in', 'chat', 'I cannot make it, no time', 'VIEWING_DONE', 11, NULL, now() - interval '3 days');

INSERT INTO tcs_events (whatsapp_id, event_type, from_stage, to_stage, payload, created_at) VALUES
('77010000001@c.us', 'stage_entered', NULL, 'NEW_INQUIRY', '{}', now() - interval '3 days'),
('77010000001@c.us', 'stage_entered', 'NEW_INQUIRY', 'QUALIFIED', '{}', now() - interval '2 hours'),
('77010000002@c.us', 'stage_entered', 'QUALIFIED', 'VIEWING_SCHEDULED', '{}', now() - interval '2 hours'),
('77010000002@c.us', 'trial_booked', NULL, NULL, '{"trial_datetime": "in 2 days"}', now() - interval '2 hours'),
('77010000003@c.us', 'objection_raised', NULL, NULL, '{"objection": "price"}', now() - interval '1 day'),
('77010000004@c.us', 'transferred_to_manager', NULL, NULL, '{"reason": "wants to talk to a human"}', now() - interval '30 minutes'),
('77010000005@c.us', 'sale_won', NULL, 'VIEWING_DONE', '{}', now() - interval '1 day'),
('77010000006@c.us', 'lead_lost', NULL, NULL, '{"reason": "no time"}', now() - interval '3 days');

INSERT INTO tcs_followups (whatsapp_id, kind, scheduled_at, attempt_number, status, message, created_at) VALUES
('77010000003@c.us', 'THINKING', now() + interval '2 days', 1, 'PENDING', 'follow-up: still thinking', now());
