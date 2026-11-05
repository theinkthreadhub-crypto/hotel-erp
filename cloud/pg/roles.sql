-- Roles for the Phase 3 cloud database (run once by a superuser, before schema.sql as setu_admin).
-- setu_admin: owns the tables, used for admin and authentication lookups (BYPASSRLS).
-- setu_app:   tenant work; no BYPASSRLS, so row-level security always applies. The service switches to it per
--             transaction (SET LOCAL ROLE setu_app) after setting setu.hotel.
-- Passwords are set by the operator (never in git): ALTER ROLE setu_admin PASSWORD '...';
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'setu_admin') THEN CREATE ROLE setu_admin LOGIN BYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'setu_app') THEN CREATE ROLE setu_app NOLOGIN NOBYPASSRLS; END IF;
END $$;
GRANT setu_app TO setu_admin;
