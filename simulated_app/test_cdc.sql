-- Test CDC
-- Insert command
INSERT INTO test.users (
    name, is_active, address, email, phone_number, date_of_birth,
    national_id, kyc_status, risk_profile, account_tier, referral_code, last_login_at
)
VALUES
    ('Nguyen Van XYZ', TRUE,
     '{"province": "Ho Chi Minh", "ward": "Phuong An Khanh", "detail": "12 Nguyen Long"}'::jsonb,
     'aghjaaf.nguyen@example.com', '0901234567', '1995-05-20', '079095000423',
     'verified', 'moderate', 'premium', 'REF1000', now() - INTERVAL '2 hours')
ON CONFLICT DO NOTHING;

-- Update data
update test.users
set is_active = 'False'
where id = '1000'

-- Check cdc
select * from information_schema."tables" t where table_name = 'changes' order by table_name
select * from pg_catalog.pg_logical_slot_peek_changes
SELECT pg_logical_emit_message(true, 'wal2json', 'this message will be delivered');
SELECT pg_logical_emit_message(true, 'pgoutput', 'this message will be filtered');
SELECT pg_logical_emit_message(false, 'wal2json', 'this non-transactional message will be delivered even if you rollback the transaction');
SELECT lsn::text, data FROM pg_logical_slot_peek_changes('cdc_users_slot', NULL, 2, 'include-timestamp', '1')