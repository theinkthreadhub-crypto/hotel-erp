-- After schema.sql (as setu_admin): tenant role permissions. setu_app may read / write tenant rows only (RLS).
GRANT USAGE ON SCHEMA public TO setu_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON bills, records, owner_creds, owner_sessions, sync_batches, commands, conflicts,
  qr_conf, qr_tables, guest_orders, guest_calls, backups, counters TO setu_app;
GRANT SELECT, UPDATE ON hotels TO setu_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO setu_app;
