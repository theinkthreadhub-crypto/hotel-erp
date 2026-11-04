-- HoReCa One / Setu — local SQLite schema, version 1
-- Generated from setu_sqlite.SCHEMA (the program applies exactly this text). One file per hotel: setu.sqlite.
-- Connection settings used by the program on every connection:
--   PRAGMA journal_mode = WAL;  PRAGMA synchronous = FULL;  PRAGMA foreign_keys = ON;
--   PRAGMA busy_timeout = 30000;  PRAGMA wal_autocheckpoint = 1000;
-- Columns declared without a type keep the exact JSON value (integer stays integer, 290.0 stays real, text stays text).
-- *_p columns are integer paise used for exact sums; they are derived, never used to rebuild a record.
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS database_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS hotels (hotel_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL);

-- Small configuration objects of the data (settings, auth, secure hashes, subscription, saas, ...): one row each
CREATE TABLE IF NOT EXISTS hotel_settings (k TEXT PRIMARY KEY, v TEXT NOT NULL);
-- Running numbers (bill, kot, token, cn, ...). Text values (tokenDate) in t.
CREATE TABLE IF NOT EXISTS sequences (name TEXT PRIMARY KEY, n, t TEXT, ord INTEGER NOT NULL DEFAULT 0);

-- ---------------- Billing & POS ----------------
CREATE TABLE IF NOT EXISTS bills (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL,
  no, kot, date, time, "table", channel, mode, sub, disc, tax, taxable, total, round, cust, phone, idemKey, mv, imported, cancelled,
  total_p INTEGER, is_cancelled INTEGER NOT NULL DEFAULT 0, arrays TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS bills_date ON bills(date);
CREATE INDEX IF NOT EXISTS bills_no ON bills(no);
CREATE INDEX IF NOT EXISTS bills_phone ON bills(phone);
CREATE INDEX IF NOT EXISTS bills_ord ON bills(ord);
CREATE UNIQUE INDEX IF NOT EXISTS bills_idem ON bills(idemKey) WHERE idemKey IS NOT NULL;
CREATE TABLE IF NOT EXISTS bill_items (
  bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  mid, name, price, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (bill_id, line));
CREATE INDEX IF NOT EXISTS bill_items_mid ON bill_items(mid);
-- Payment lines: the bill's split tenders, or one synthetic line (mode, total) for a single-mode bill
CREATE TABLE IF NOT EXISTS bill_payments (
  bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  mode, amt, amount_p INTEGER, synthetic INTEGER NOT NULL DEFAULT 0, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (bill_id, line));
CREATE INDEX IF NOT EXISTS bill_payments_mode ON bill_payments(mode);
-- Recipe consumption recorded on the bill (legacy bills[].used)
CREATE TABLE IF NOT EXISTS bill_used (
  bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  sid, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (bill_id, line));
CREATE TABLE IF NOT EXISTS bill_cancellations (
  bill_id TEXT PRIMARY KEY REFERENCES bills(id) ON DELETE CASCADE, cancelled_by TEXT, recorded_at INTEGER NOT NULL);
-- Every change to an existing bill (edit, cancel, delete) with the old and new record
CREATE TABLE IF NOT EXISTS bill_modifications (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, bill_id TEXT NOT NULL, action TEXT NOT NULL, at INTEGER NOT NULL,
  doc_version INTEGER, old TEXT, new TEXT);
CREATE INDEX IF NOT EXISTS bill_modifications_bill ON bill_modifications(bill_id);
CREATE TABLE IF NOT EXISTS credit_notes (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, no, billId, date, total, total_p INTEGER, extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS table_orders (tbl TEXT PRIMARY KEY, ord INTEGER NOT NULL, data TEXT NOT NULL);

-- ---------------- KOT & kitchen ----------------
CREATE TABLE IF NOT EXISTS kots (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, no, date, time, "table", channel, status, arrays TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS kots_date ON kots(date);
CREATE TABLE IF NOT EXISTS kot_items (
  kot_id TEXT NOT NULL REFERENCES kots(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  mid, name, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (kot_id, line));
CREATE TABLE IF NOT EXISTS kot_status_history (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, kot_id TEXT NOT NULL, old_status TEXT, new_status TEXT, at INTEGER NOT NULL);

-- ---------------- Menu & recipes ----------------
CREATE TABLE IF NOT EXISTS menu_items (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name, cat, price, arrays TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS recipe_ingredients (
  menu_id TEXT NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  sid, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (menu_id, line));

-- ---------------- Inventory ----------------
CREATE TABLE IF NOT EXISTS stock_items (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name, unit, qty, rate, cat, extra TEXT NOT NULL DEFAULT '{}');
-- The movement ledger. source = move (D.moves: open, waste, issue, return, adjust, del, merge),
-- purchase (vouchers with mv), sale / cancel (bills with mv). Ids follow the app's own stockMoves() ids,
-- so a bill or purchase can only ever produce its movements once.
CREATE TABLE IF NOT EXISTS stock_movements (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, ref TEXT, sid TEXT NOT NULL, qty REAL NOT NULL, type TEXT, date TEXT, time TEXT);
CREATE INDEX IF NOT EXISTS stock_movements_sid ON stock_movements(sid, date);
CREATE INDEX IF NOT EXISTS stock_movements_ref ON stock_movements(source, ref);
-- D.moves rows themselves (lossless copy of the app's movement records; the ledger above is built from them)
CREATE TABLE IF NOT EXISTS stock_move_records (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, sid, qty, type, date, time, extra TEXT NOT NULL DEFAULT '{}');
-- Current balance per stock id, kept by triggers in the same transaction as every movement
CREATE TABLE IF NOT EXISTS stock_balances (sid TEXT PRIMARY KEY, qty REAL NOT NULL DEFAULT 0);
CREATE TRIGGER IF NOT EXISTS stock_movements_ai AFTER INSERT ON stock_movements BEGIN
  INSERT INTO stock_balances(sid, qty) VALUES (NEW.sid, NEW.qty) ON CONFLICT(sid) DO UPDATE SET qty = qty + NEW.qty; END;
CREATE TRIGGER IF NOT EXISTS stock_movements_ad AFTER DELETE ON stock_movements BEGIN
  UPDATE stock_balances SET qty = qty - OLD.qty WHERE sid = OLD.sid; END;

-- ---------------- Vouchers: purchases, supplier payments, expenses, income ----------------
CREATE TABLE IF NOT EXISTS vouchers (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, type, date, time, head, party, amount, mode, sid, qty, mv,
  amount_p INTEGER, inv_id TEXT, extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS vouchers_date ON vouchers(type, date);
CREATE INDEX IF NOT EXISTS vouchers_party ON vouchers(party);
CREATE INDEX IF NOT EXISTS vouchers_inv ON vouchers(inv_id);
-- Purchase invoice headers (projection of the inv object every purchase line carries)
CREATE TABLE IF NOT EXISTS purchases (inv_id TEXT PRIMARY KEY, no TEXT, party TEXT, date TEXT, total_p INTEGER, paid_p INTEGER, lines INTEGER);
CREATE VIEW IF NOT EXISTS purchase_items AS SELECT * FROM vouchers WHERE type = 'Purchase';
CREATE VIEW IF NOT EXISTS supplier_payments AS SELECT * FROM vouchers WHERE type = 'Expense' AND head = 'Supplier Payment';
CREATE VIEW IF NOT EXISTS expenses AS SELECT * FROM vouchers WHERE type = 'Expense' AND COALESCE(head, '') <> 'Supplier Payment';
CREATE VIEW IF NOT EXISTS income_transactions AS SELECT * FROM vouchers WHERE type = 'Receipt';
CREATE TABLE IF NOT EXISTS purchase_orders (id TEXT PRIMARY KEY, ord INTEGER NOT NULL, party, date, status, extra TEXT NOT NULL DEFAULT '{}');

-- ---------------- Staff, customers, accounting maps ----------------
CREATE TABLE IF NOT EXISTS staff (id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name, role, access, extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS attendance (date TEXT NOT NULL, staff_key TEXT NOT NULL, ord INTEGER NOT NULL, v TEXT NOT NULL, PRIMARY KEY (date, staff_key));
CREATE TABLE IF NOT EXISTS cash_drawer_sessions (date TEXT PRIMARY KEY, ord INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS salary_records (month TEXT PRIMARY KEY, ord INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, at, date, action, user, amount, ref, extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS audit_logs_date ON audit_logs(date);
CREATE VIEW IF NOT EXISTS customer_loyalty AS
  SELECT phone, COUNT(*) AS bills, SUM(total_p) AS spent_p FROM bills WHERE is_cancelled = 0 AND phone IS NOT NULL AND phone <> '' GROUP BY phone;

-- Lists and maps without a dedicated table (customers list, recurring-expense templates, reservations, assets,
-- gas log, QR log, WhatsApp messages, online orders, error sync, ...): one row per record / entry
CREATE TABLE IF NOT EXISTS ext_records (list TEXT NOT NULL, id TEXT NOT NULL, ord INTEGER NOT NULL, noid INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL, PRIMARY KEY (list, id));
CREATE INDEX IF NOT EXISTS ext_records_ord ON ext_records(list, ord);
CREATE TABLE IF NOT EXISTS kv_maps (map TEXT NOT NULL, k TEXT NOT NULL, ord INTEGER NOT NULL, v TEXT NOT NULL, PRIMARY KEY (map, k));
CREATE VIEW IF NOT EXISTS customers AS SELECT id, ord, data FROM ext_records WHERE list = 'custList';
CREATE VIEW IF NOT EXISTS recurring_expense_templates AS SELECT id, ord, data FROM ext_records WHERE list = 'expTpl';

-- ---------------- Reliability ----------------
CREATE TABLE IF NOT EXISTS operation_idempotency (
  key TEXT PRIMARY KEY, op TEXT NOT NULL, ref TEXT, request_sha TEXT, actor TEXT, at INTEGER NOT NULL, result TEXT);
CREATE TABLE IF NOT EXISTS sync_outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL, ref TEXT, doc_version INTEGER, payload TEXT, at INTEGER NOT NULL, sent_at INTEGER);
CREATE TABLE IF NOT EXISTS sync_inbox_deduplication (key TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sync_checkpoints (name TEXT PRIMARY KEY, value TEXT, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS backup_manifest (
  file TEXT PRIMARY KEY, at INTEGER NOT NULL, doc_version INTEGER, bytes INTEGER, sha256 TEXT, bills INTEGER, verified INTEGER NOT NULL DEFAULT 0, note TEXT);
