-- HoReCa One / Setu: Phase 3 cloud schema (PostgreSQL 16). Multi-tenant: every table carries hotel_id.
-- Isolation: row-level security (FORCED, so even the table owner is filtered when it acts as setu_app), hotel set per
-- transaction with set_config('setu.hotel', <id>, true). The service runs tenant work as role setu_app (no BYPASSRLS);
-- only admin / authentication lookups use setu_admin.
-- Records come from the counter (the authority for its hotel). src_version = the counter's saved version at which the
-- record last changed: a write is applied only when it is newer, so older data never overwrites newer.

CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS hotels (
  hotel_id TEXT PRIMARY KEY CHECK (hotel_id ~ '^[A-Za-z0-9_-]{2,40}$'),
  name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  doc_meta JSONB NOT NULL DEFAULT '{}',          -- the counter's key order and storage kinds (for recovery)
  meta_version BIGINT NOT NULL DEFAULT 0,
  synced_version BIGINT NOT NULL DEFAULT 0,      -- highest counter version acknowledged
  last_seen TIMESTAMPTZ
);

-- Counter credentials (sync key shown once, stored as sha256)
CREATE TABLE IF NOT EXISTS counters (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  counter_id TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (hotel_id, counter_id)
);

-- Bills: typed columns for owner reports and uniqueness; the exact record in data
CREATE TABLE IF NOT EXISTS bills (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  ord BIGINT NOT NULL DEFAULT 0,
  no BIGINT,
  date TEXT,
  total_p BIGINT,
  mode TEXT,
  phone TEXT,
  idem_key TEXT,
  imported BOOLEAN NOT NULL DEFAULT false,
  cancelled BOOLEAN NOT NULL DEFAULT false,
  deleted BOOLEAN NOT NULL DEFAULT false,
  src_version BIGINT NOT NULL,
  snap TEXT,
  data JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hotel_id, id)
);
CREATE INDEX IF NOT EXISTS bills_hotel_date ON bills (hotel_id, date);
CREATE INDEX IF NOT EXISTS bills_hotel_phone ON bills (hotel_id, phone);
CREATE UNIQUE INDEX IF NOT EXISTS bills_hotel_idem ON bills (hotel_id, idem_key) WHERE idem_key IS NOT NULL AND NOT deleted;
CREATE UNIQUE INDEX IF NOT EXISTS bills_hotel_no ON bills (hotel_id, no) WHERE no IS NOT NULL AND NOT imported AND NOT deleted;

-- Every other record: list records (k, id), map entries (k, key), whole values (k, '')
CREATE TABLE IF NOT EXISTS records (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  k TEXT NOT NULL,
  rid TEXT NOT NULL,
  ord BIGINT NOT NULL DEFAULT 0,
  deleted BOOLEAN NOT NULL DEFAULT false,
  src_version BIGINT NOT NULL,
  snap TEXT,
  data JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hotel_id, k, rid)
);

-- The counter's credential block (PBKDF2 hashes only, never plain values): used for the owner's remote login and for
-- recovering a counter. Never sent to any device, owner screen or guest.
CREATE TABLE IF NOT EXISTS owner_creds (
  hotel_id TEXT PRIMARY KEY REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  secure JSONB NOT NULL,
  src_version BIGINT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS owner_sessions (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  token_hash TEXT PRIMARY KEY,
  expires_at TIMESTAMPTZ NOT NULL
);

-- Sync bookkeeping
CREATE TABLE IF NOT EXISTS sync_batches (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  batch_id TEXT NOT NULL,
  from_v BIGINT, to_v BIGINT,
  result JSONB NOT NULL,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hotel_id, batch_id)
);
CREATE TABLE IF NOT EXISTS commands (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  seq BIGSERIAL,
  kind TEXT NOT NULL CHECK (kind IN ('licence_key', 'vendor_message', 'vendor_lock')),
  payload JSONB NOT NULL,
  created_by TEXT NOT NULL DEFAULT 'admin',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  acked_at TIMESTAMPTZ,
  result JSONB,
  PRIMARY KEY (hotel_id, seq)
);
CREATE TABLE IF NOT EXISTS conflicts (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  seq BIGSERIAL,
  k TEXT NOT NULL, rid TEXT, reason TEXT NOT NULL,
  stored JSONB, incoming JSONB,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hotel_id, seq)
);

-- QR self-ordering (same behaviour as the Worker's guestorder / guestcall)
CREATE TABLE IF NOT EXISTS qr_conf (
  hotel_id TEXT PRIMARY KEY REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  qr_on BOOLEAN NOT NULL DEFAULT false, auto BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS qr_tables (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  tbl TEXT NOT NULL, token TEXT NOT NULL UNIQUE, active BOOLEAN NOT NULL DEFAULT true, at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hotel_id, tbl)
);
CREATE TABLE IF NOT EXISTS guest_orders (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  id TEXT NOT NULL, tbl TEXT NOT NULL, items JSONB NOT NULL, note TEXT, name TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'done')),
  at BIGINT NOT NULL, by TEXT, decided BIGINT, reason TEXT, kot TEXT,
  PRIMARY KEY (hotel_id, id)
);
CREATE TABLE IF NOT EXISTS guest_calls (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  id TEXT NOT NULL, tbl TEXT NOT NULL, kind TEXT NOT NULL, at BIGINT NOT NULL, done BOOLEAN NOT NULL DEFAULT false, by TEXT,
  PRIMARY KEY (hotel_id, id)
);

-- Cloud backups (files outside the database; manifest here)
CREATE TABLE IF NOT EXISTS backups (
  hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id) ON DELETE CASCADE,
  id TEXT NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT now(), file TEXT NOT NULL, bytes BIGINT, sha256 TEXT, content_sha256 TEXT,
  bills BIGINT, records BIGINT, synced_version BIGINT, verified BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (hotel_id, id)
);

-- Failed logins (rate limit; not tenant data)
CREATE TABLE IF NOT EXISTS login_fails (key TEXT PRIMARY KEY, n INTEGER NOT NULL, first_at TIMESTAMPTZ NOT NULL);

-- ---------------- Row-level security ----------------
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['hotels', 'counters', 'bills', 'records', 'owner_creds', 'owner_sessions', 'sync_batches', 'commands', 'conflicts',
                           'qr_conf', 'qr_tables', 'guest_orders', 'guest_calls', 'backups'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant ON %I', t);
    -- No hotel set = no rows (current_setting(..., true) returns NULL or '')
    EXECUTE format($p$CREATE POLICY tenant ON %I USING (hotel_id = current_setting('setu.hotel', true)) WITH CHECK (hotel_id = current_setting('setu.hotel', true))$p$, t);
  END LOOP;
END $$;

INSERT INTO schema_migrations (version, name) VALUES (1, 'Phase 3: multi-tenant cloud schema with row-level security') ON CONFLICT DO NOTHING;
