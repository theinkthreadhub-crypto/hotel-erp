"""HoReCa One / Setu — local SQLite storage for the counter PC (Phase 2).

One SQLite file per hotel (`setu.sqlite` in the hotel's data folder, Hotel ID fixed in `meta`), WAL journal,
synchronous=FULL, foreign keys on, busy timeout, schema versioning. Every business list is stored as rows:
bills / bill_items / bill_payments / bill_used, KOTs, vouchers (purchases, expenses, income, supplier
payments), stock items and a stock movement ledger with transactional balances, menu + recipes, staff,
attendance, audit log, credit notes, purchase orders, customers, cash drawer, salary records.

Lossless: a record's known fields go into typed columns with their exact JSON value (SQLite keeps int / float /
text as given); everything else stays in the row's `extra` JSON. `export_document()` rebuilds exactly the data
object the app has always used, so the existing UI keeps working while storage is incremental:

* `write(doc)` (the existing whole-document upload) runs ONE transaction that touches only records that
  changed (compared in memory with the last committed copy), not the whole database.
* `settle_bill()` / `cancel_bill()` are native transactions: number, rows, stock movements, idempotency
  record and sync-outbox entry commit together or not at all.

Not here (Phase 3): cloud incremental sync. The outbox is written so Phase 3 can send it; nothing sends it yet.
"""
import gzip
import hashlib
import json
import random
import urllib.request
import urllib.error
import os
import shutil
import sqlite3
import threading
import time
import secrets
from contextlib import nullcontext
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from horeca_license_verify import verify_signed_license, InvalidLicence, TRUSTED_PUBLIC_KEYS

SCHEMA_VERSION = 6
DB_FILE = 'setu.sqlite'
FLAG_FILE = 'setu-storage.json'

# ---------------------------------------------------------------------------------------------------------
# Schema. Value columns without a declared type keep the exact JSON scalar (int stays int, 290.0 stays float).
# *_p columns are integer paise for exact money sums; they are projections, never used to rebuild records.
# ---------------------------------------------------------------------------------------------------------
SCHEMA = r"""
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
CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending ON sync_outbox(sent_at, seq);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_ref ON sync_outbox(ref);
CREATE TABLE IF NOT EXISTS sync_inbox_deduplication (key TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sync_checkpoints (name TEXT PRIMARY KEY, value TEXT, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS backup_manifest (
  file TEXT PRIMARY KEY, at INTEGER NOT NULL, doc_version INTEGER, bytes INTEGER, sha256 TEXT, bills INTEGER, verified INTEGER NOT NULL DEFAULT 0, note TEXT);

-- ---------------- Schema 2 (Phase 2b): incremental saves ----------------
-- Which records changed in which saved version: devices fetch only these (GET /api/changes), never the whole data
CREATE TABLE IF NOT EXISTS change_log (seq INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL, k TEXT NOT NULL, rid TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS change_log_version ON change_log(version);
CREATE INDEX IF NOT EXISTS change_log_krid ON change_log(k, rid, version);
-- Totals of older sales per stock item without reading every movement
CREATE INDEX IF NOT EXISTS stock_movements_src_date ON stock_movements(source, date);

-- ---------------- Schema 3: conflicts kept for review (never silently dropped) ----------------
-- Two copies of one record with different content, or one sale key with different amounts: the stored /
-- first copy stays in the books, every other copy is kept here for a Manager to review
CREATE TABLE IF NOT EXISTS sync_conflicts (seq INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL, k TEXT NOT NULL, rid TEXT, reason TEXT NOT NULL,
  kept TEXT, other TEXT, device TEXT, resolved INTEGER NOT NULL DEFAULT 0);

-- ---------------- Schema 4 (Phase 3.4): Cloud Change Feed Inbound Sync ----------------
CREATE TABLE IF NOT EXISTS inbound_events_applied (
  id TEXT PRIMARY KEY, seq INTEGER NOT NULL, event_type TEXT NOT NULL,
  entity_id TEXT, applied_at INTEGER NOT NULL, acked_at INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inbound_applied_seq ON inbound_events_applied(seq);
CREATE TABLE IF NOT EXISTS inbound_cursor_state (
  name TEXT PRIMARY KEY, seq INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS inbound_event_failures (
  event_id TEXT PRIMARY KEY, seq INTEGER, reason TEXT NOT NULL,
  occurred_at INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS inbound_qr_orders (
  order_id TEXT PRIMARY KEY, tbl TEXT NOT NULL, items_json TEXT NOT NULL,
  guest_name TEXT, note TEXT, status TEXT NOT NULL DEFAULT 'pending',
  kot_id TEXT, created_at INTEGER, updated_at INTEGER, cloud_applied_at INTEGER);
CREATE INDEX IF NOT EXISTS idx_inbound_qr_pending ON inbound_qr_orders(status, created_at);
"""

# ---------------------------------------------------------------------------------------------------------
# Mapping of the app's data object to tables
# ---------------------------------------------------------------------------------------------------------
MONEY = lambda v: int((Decimal(str(v)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


class Child:
    def __init__(self, key, table, fk, cols):
        self.key, self.table, self.fk, self.cols = key, table, fk, cols


class Spec:
    def __init__(self, key, table, cols, children=(), proj=None):
        self.key, self.table, self.cols, self.children, self.proj = key, table, cols, list(children), proj or {}


def _bill_proj(r):
    tot = r.get('total')
    return {'total_p': MONEY(tot) if _num(tot) else None, 'is_cancelled': 1 if r.get('cancelled') else 0}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


SPECS = [
    Spec('bills', 'bills', ['no', 'kot', 'date', 'time', 'table', 'channel', 'mode', 'sub', 'disc', 'tax', 'taxable', 'total', 'round', 'cust', 'phone', 'idemKey', 'mv', 'imported', 'cancelled'],
         [Child('items', 'bill_items', 'bill_id', ['mid', 'name', 'price', 'qty']),
          Child('pays', 'bill_payments', 'bill_id', ['mode', 'amt']),
          Child('used', 'bill_used', 'bill_id', ['sid', 'qty'])], {'bills': _bill_proj}),
    Spec('kots', 'kots', ['no', 'date', 'time', 'table', 'channel', 'status'],
         [Child('items', 'kot_items', 'kot_id', ['mid', 'name', 'qty'])]),
    Spec('menu', 'menu_items', ['name', 'cat', 'price'], [Child('recipe', 'recipe_ingredients', 'menu_id', ['sid', 'qty'])]),
    Spec('stock', 'stock_items', ['name', 'unit', 'qty', 'rate', 'cat']),
    Spec('moves', 'stock_move_records', ['sid', 'qty', 'type', 'date', 'time']),
    Spec('txns', 'vouchers', ['type', 'date', 'time', 'head', 'party', 'amount', 'mode', 'sid', 'qty', 'mv']),
    Spec('staff', 'staff', ['name', 'role', 'access']),
    Spec('audit', 'audit_logs', ['at', 'date', 'action', 'user', 'amount', 'ref']),
    Spec('cnotes', 'credit_notes', ['no', 'billId', 'date', 'total']),
    Spec('orders', 'purchase_orders', ['party', 'date', 'status']),
]
SPEC_BY_KEY = {s.key: s for s in SPECS}
# Maps with their own table: key -> (table, key column)
MAP_TABLES = {'kaccha': ('table_orders', 'tbl'), 'cash': ('cash_drawer_sessions', 'date'), 'salarySheets': ('salary_records', 'month')}
CONFIG_KEYS = ('settings', 'auth', 'secure', 'subscription', 'saas', 'vendor_notices')
GUARDED_FOR_DELETE_LOG = ('bills',)


def _scalar(v):
    return isinstance(v, (str, int, float)) and not isinstance(v, bool)


def _dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def split_record(cols, rec):
    """(column values, extra dict): known scalar fields move to columns with their exact value; the rest stays."""
    vals, extra = [], {}
    for c in cols:
        v = rec.get(c, None) if c in rec else None
        vals.append(v if c in rec and _scalar(v) else None)
    for k, v in rec.items():
        if k in cols and _scalar(v):
            continue
        extra[k] = v
    return vals, extra


def join_record(cols, vals, extra_text):
    rec = json.loads(extra_text) if extra_text and extra_text != '{}' else {}
    for c, v in zip(cols, vals):
        if v is not None:
            rec[c] = v
    return rec


class StoreError(Exception):
    pass


class SqliteDoc:
    """The SQLite database of one hotel. Thread-safe: one write at a time (`self.wlock`), readers use WAL."""

    def __init__(self, path, hotel_id=None, create=False):
        self.path = path
        self.wlock = threading.RLock()
        self._local = threading.local()
        exists = os.path.exists(path)
        if not exists and not create:
            raise StoreError(f'database not found: {path}')
        con = self.con()
        if exists:
            ok = con.execute('PRAGMA quick_check').fetchone()[0]
            if ok != 'ok':
                raise StoreError(f'database failed its integrity check: {ok}')
        con.executescript(SCHEMA)
        # Upgrade existing Phase 3.4 installs without deleting event history.
        prior_cols = {r[1] for r in con.execute('PRAGMA table_info(inbound_events_applied)')}
        if 'acked_at' not in prior_cols:
            con.execute('ALTER TABLE inbound_events_applied ADD COLUMN acked_at INTEGER')
        qr_cols = {r[1] for r in con.execute('PRAGMA table_info(inbound_qr_orders)')}
        if 'cloud_applied_at' not in qr_cols:
            con.execute('ALTER TABLE inbound_qr_orders ADD COLUMN cloud_applied_at INTEGER')
        cur = self.meta('schema_version')
        if cur is not None and int(cur) > SCHEMA_VERSION:
            raise StoreError(f'database schema {cur} is newer than this program ({SCHEMA_VERSION})')
        if cur is None or int(cur) < SCHEMA_VERSION:
            # The new tables / indexes were created by the script above (IF NOT EXISTS); record each step once
            names = {1: 'initial relational schema', 2: 'change log for incremental saves; stock movement (source, date) index',
                     3: 'sync_conflicts: differing copies kept for review',
                     4: 'inbound_events_applied: change feed and QR / licence sync',
                     5: 'contiguous inbound cursor, pending ACK, QR approval staging',
                     6: 'cloud KOT applied confirmation retry state'}
            with self.tx() as c:
                for v in range(1 if cur is None else int(cur) + 1, SCHEMA_VERSION + 1):
                    c.execute('INSERT OR IGNORE INTO database_migrations VALUES (?, ?, ?)', (v, names[v], int(time.time() * 1000)))
                c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        hid = self.meta('hotel_id')
        if hotel_id and hid and hid != hotel_id:
            raise StoreError(f'this database belongs to hotel {hid}, not {hotel_id}')

    # ---- connections ----
    def con(self):
        # One connection for the whole process, used under self.wlock (writes) / self.rlock() (reads).
        # The HTTP server starts a thread per request: a connection per thread meant a new connection with a cold
        # page cache on every request (measured: 25+ ms per bill and a collapse at 100 clients on a year of data).
        c = getattr(self, '_con', None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=FULL')        # financial records: a commit is on disk before we answer
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA busy_timeout=30000')
            # Checkpoints (copying the write log back into the database file): inside a commit every 1,000 pages
            # (SQLite's default), or - SETU_CHECKPOINT=background - by a separate thread so no bill waits for one.
            # Durability is the same either way: every commit is flushed to the log (synchronous=FULL).
            c.execute('PRAGMA wal_autocheckpoint=1000')   # the server's start_checkpointer() turns this off
            c.execute('PRAGMA cache_size=-65536')       # 64 MB page cache
            self._con = c
        return c

    @staticmethod
    def _bg_ckpt():
        # Default: SQLite's own checkpoints inside commits (measured faster at 365,000 bills: 245 vs 175 saves/s at
        # 100 clients); background checkpoints only when asked for (SETU_CHECKPOINT=background)
        return os.environ.get('SETU_CHECKPOINT', 'commit') == 'background'

    def start_checkpointer(self, every=1.0, wal_mb=16, idle_truncate=30):
        """Background checkpoints on an own connection: PASSIVE (never blocks a writer) when the log passes `wal_mb`
        or every 30 s; TRUNCATE (shrinks the log file) after `idle_truncate` s without a commit."""
        if not self._bg_ckpt() or getattr(self, '_ckpt', None):
            return
        with self.wlock:
            self.con().execute('PRAGMA wal_autocheckpoint=0')
        self.ckpt_stats = {'mode': 'background', 'runs': 0, 'pages': 0, 'busy': 0, 'maxMs': 0, 'totalMs': 0, 'truncates': 0, 'lastAt': 0, 'error': ''}
        self._ckpt = threading.Thread(target=self._ckpt_loop, args=(every, wal_mb, idle_truncate), daemon=True)
        self._ckpt.start()

    def _ckpt_loop(self, every, wal_mb, idle_truncate):
        wal = self.path + '-wal'
        c = None
        last_run, last_size, quiet_since, truncated = time.time(), -1, time.time(), False
        try:
            c = sqlite3.connect(self.path, timeout=5, isolation_level=None, check_same_thread=False)
            c.execute('PRAGMA busy_timeout=5000')
            while not getattr(self, '_ckpt_stop', False):
                time.sleep(every)
                try:
                    size = os.path.getsize(wal) if os.path.exists(wal) else 0
                except OSError:
                    continue
                now = time.time()
                if size != last_size:
                    quiet_since, truncated, last_size = now, False, size
                mode = None
                if size > wal_mb * 1048576 or (size and now - last_run > 30):
                    mode = 'PASSIVE'
                elif size and not truncated and now - quiet_since > idle_truncate:
                    mode = 'TRUNCATE'
                if not mode:
                    continue
                t0 = time.perf_counter()
                busy, log_pages, done = c.execute(f'PRAGMA wal_checkpoint({mode})').fetchone()
                ms = (time.perf_counter() - t0) * 1000
                st = self.ckpt_stats
                st['runs'] += 1
                st['pages'] += max(0, done or 0)
                st['busy'] += 1 if busy else 0
                st['maxMs'] = round(max(st['maxMs'], ms), 1)
                st['totalMs'] = round(st['totalMs'] + ms, 1)
                st['lastAt'] = int(now * 1000)
                if mode == 'TRUNCATE' and not busy:
                    st['truncates'] += 1
                    truncated = True
                last_run = now
        except Exception as e:
            # Never leave the log growing: fall back to SQLite's own checkpoints
            self.ckpt_stats['error'] = repr(e)[:200]
            try:
                with self.wlock:
                    self.con().execute('PRAGMA wal_autocheckpoint=1000')
            except Exception:
                pass
        finally:
            if c is not None:
                c.close()

    def stop_checkpointer(self):
        self._ckpt_stop = True

    def rlock(self):
        return self.wlock

    class _Reader:
        """A separate read-only connection in one read transaction: a consistent snapshot of the last commit
        (WAL) for long reads, without taking the write lock, so billing never waits for a report or a device load."""
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            # Plain path (a URI would need escaping for spaces in Windows user folders); query_only = read only
            self.c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            self.c.execute('PRAGMA query_only=1')
            self.c.execute('PRAGMA busy_timeout=30000')
            self.c.execute('PRAGMA cache_size=-16384')
            self.c.execute('BEGIN')
            return self.c

        def __exit__(self, et, ev, tb):
            try:
                self.c.execute('COMMIT')
            finally:
                self.c.close()
            return False

    def reader(self):
        return SqliteDoc._Reader(self.path)

    class _Tx:
        def __init__(self, doc):
            self.doc = doc

        def __enter__(self):
            self.doc.wlock.acquire()
            self.c = self.doc.con()
            self.c.execute('BEGIN IMMEDIATE')
            return self.c

        def __exit__(self, et, ev, tb):
            try:
                self.c.execute('COMMIT' if et is None else 'ROLLBACK')
            finally:
                self.doc.wlock.release()
            return False

    def tx(self):
        return SqliteDoc._Tx(self)

    def meta(self, k):
        with self.wlock:
            r = self.con().execute('SELECT v FROM meta WHERE k = ?', (k,)).fetchone()
        return r[0] if r else None

    def close(self):
        self.stop_checkpointer()
        with self.wlock:            # never while another thread is using the shared connection
            c = getattr(self, '_con', None)
            if c is not None:
                c.close()
                self._con = None

    # ---- import (one record) ----
    def _put_record(self, c, spec, rec, ordn):
        cols = spec.cols
        vals, extra = split_record(cols, rec)
        rid = rec.get('id')
        arrays = []
        children = []
        for ch in spec.children:
            if ch.key in rec and isinstance(rec[ch.key], list) and all(isinstance(x, dict) for x in rec[ch.key]):
                arrays.append(ch.key)
                extra.pop(ch.key, None)
                children.append((ch, rec[ch.key]))
        names = ['id', 'ord'] + cols + ['extra']
        args = [rid, ordn] + vals + [_dump(extra)]
        has_arrays = spec.table in ('bills', 'kots', 'menu_items')
        if has_arrays:
            names.append('arrays'); args.append(','.join(arrays))
        if spec.table == 'bills':
            p = _bill_proj(rec)
            names += ['total_p', 'is_cancelled']; args += [p['total_p'], p['is_cancelled']]
        if spec.table == 'vouchers':
            inv = rec.get('inv') if isinstance(rec.get('inv'), dict) else {}
            names += ['amount_p', 'inv_id']; args += [MONEY(rec['amount']) if _num(rec.get('amount')) else None, inv.get('id')]
        if spec.table == 'credit_notes':
            names.append('total_p'); args.append(MONEY(rec['total']) if _num(rec.get('total')) else None)
        q = ','.join('"%s"' % n for n in names)
        c.execute(f'INSERT OR REPLACE INTO {spec.table} ({q}) VALUES ({",".join("?" * len(names))})', args)
        for ch in spec.children:
            c.execute(f'DELETE FROM {ch.table} WHERE {ch.fk} = ?', (rid,))
        for ch, rows in children:
            extra_cols = ['synthetic', 'amount_p'] if ch.table == 'bill_payments' else []
            for i, x in enumerate(rows):
                v, ex = split_record(ch.cols, x)
                more = [0, MONEY(x['amt']) if _num(x.get('amt')) else None] if extra_cols else []
                cn = ','.join([ch.fk, 'line'] + ['"%s"' % k for k in ch.cols] + extra_cols + ['extra'])
                c.execute(f'INSERT INTO {ch.table} ({cn}) VALUES ({",".join("?" * (len(ch.cols) + 3 + len(extra_cols)))})', [rid, i] + v + more + [_dump(ex)])
        if spec.table == 'bills':
            self._bill_side(c, rec)
        elif spec.table == 'vouchers':
            self._voucher_side(c, rec)
        elif spec.table == 'stock_move_records':
            self._move_side(c, rec)

    def _bill_side(self, c, b):
        bid = b['id']
        # Same rule as the app's payParts(): split tenders only for a Split bill that has them, otherwise one
        # synthetic line (bill mode, total) so payments can always be summed by mode
        if not (b.get('mode') == 'Split' and isinstance(b.get('pays'), list) and b.get('pays')):
            c.execute('DELETE FROM bill_payments WHERE bill_id = ? AND synthetic = 1', (bid,))
            if _num(b.get('total')):
                c.execute('INSERT INTO bill_payments (bill_id, line, mode, amt, amount_p, synthetic) VALUES (?, -1, ?, ?, ?, 1)',
                          (bid, b.get('mode') or 'Cash', b.get('total'), MONEY(b['total'])))
        # Stock ledger: exactly the movements the app's stockMoves() derives from this bill
        c.execute("DELETE FROM stock_movements WHERE source IN ('sale', 'cancel') AND ref = ?", (bid,))
        if b.get('mv'):
            seen = set()
            for u in b.get('used') or []:
                if not isinstance(u, dict):
                    continue
                sid = str(u.get('sid')) if u.get('sid') is not None else ''
                q = float(u.get('qty') or 0)
                mid = 's-' + bid + '-' + sid
                if mid in seen:
                    mid += '#' + str(len(seen))
                seen.add(mid)
                c.execute("INSERT INTO stock_movements VALUES (?, 'sale', ?, ?, ?, 'sale', ?, ?)", (mid, bid, sid, -q, b.get('date'), b.get('time') or ''))
                if b.get('cancelled'):
                    c.execute("INSERT INTO stock_movements VALUES (?, 'cancel', ?, ?, ?, 'cancel', ?, ?)", ('x' + mid[1:], bid, sid, q, b.get('date'), b.get('time') or ''))
        if b.get('cancelled'):
            c.execute('INSERT OR IGNORE INTO bill_cancellations VALUES (?, ?, ?)', (bid, str(b.get('cancelledBy') or ''), int(time.time() * 1000)))
        else:
            c.execute('DELETE FROM bill_cancellations WHERE bill_id = ?', (bid,))

    def _voucher_side(self, c, t):
        tid = t['id']
        c.execute("DELETE FROM stock_movements WHERE source = 'purchase' AND ref = ?", (tid,))
        if t.get('type') == 'Purchase' and t.get('mv') and t.get('sid') and _num(t.get('qty')) and t.get('qty'):
            c.execute("INSERT INTO stock_movements VALUES (?, 'purchase', ?, ?, ?, 'purchase', ?, ?)", ('p-' + tid, tid, str(t['sid']), float(t['qty']), t.get('date'), t.get('time') or ''))
        inv = t.get('inv')
        if t.get('type') == 'Purchase' and isinstance(inv, dict) and inv.get('id'):
            c.execute('INSERT OR REPLACE INTO purchases VALUES (?, ?, ?, ?, ?, ?, ?)', (inv['id'], str(inv.get('no') or ''), t.get('party'), t.get('date'),
                      MONEY(inv['total']) if _num(inv.get('total')) else None, MONEY(inv['paid']) if _num(inv.get('paid')) else None, inv.get('n')))

    def _move_side(self, c, m):
        c.execute("DELETE FROM stock_movements WHERE source = 'move' AND ref = ?", (m['id'],))
        if m.get('sid') is not None:
            c.execute("INSERT INTO stock_movements VALUES (?, 'move', ?, ?, ?, ?, ?, ?)",
                      ('m-' + m['id'], m['id'], str(m['sid']), float(m.get('qty') or 0), m.get('type'), m.get('date'), m.get('time') or ''))

    def _del_record(self, c, spec, rid):
        for ch in spec.children:
            c.execute(f'DELETE FROM {ch.table} WHERE {ch.fk} = ?', (rid,))
        if spec.table == 'bills':
            c.execute("DELETE FROM stock_movements WHERE source IN ('sale', 'cancel') AND ref = ?", (rid,))
            c.execute('DELETE FROM bill_cancellations WHERE bill_id = ?', (rid,))
        elif spec.table == 'vouchers':
            c.execute("DELETE FROM stock_movements WHERE source = 'purchase' AND ref = ?", (rid,))
        elif spec.table == 'stock_move_records':
            c.execute("DELETE FROM stock_movements WHERE source = 'move' AND ref = ?", (rid,))
        c.execute(f'DELETE FROM {spec.table} WHERE id = ?', (rid,))

    # ---- whole document in / out ----
    @staticmethod
    def kind_of(k, v):
        """Where a top-level key of the data object lives."""
        spec = SPEC_BY_KEY.get(k)
        if spec and isinstance(v, list) and all(isinstance(x, dict) and isinstance(x.get('id'), str) and x.get('id') for x in v) \
                and len({x['id'] for x in v}) == len(v):
            return 'spec'
        if k == 'seq' and isinstance(v, dict):
            return 'seq'
        if k in MAP_TABLES and isinstance(v, dict):
            return 'maptable'
        if k == 'att' and isinstance(v, dict) and all(isinstance(x, dict) for x in v.values()):
            return 'att'
        if isinstance(v, list) and k not in CONFIG_KEYS:
            return 'extlist'
        if isinstance(v, dict) and k not in CONFIG_KEYS:
            return 'kvmap'
        return 'setting'

    def _clear_key(self, c, k, kind):
        if kind == 'spec':
            spec = SPEC_BY_KEY[k]
            for rid, in c.execute(f'SELECT id FROM {spec.table}').fetchall():
                self._del_record(c, spec, rid)
        elif kind == 'seq':
            c.execute('DELETE FROM sequences')
        elif kind == 'maptable':
            c.execute(f'DELETE FROM {MAP_TABLES[k][0]}')
        elif kind == 'att':
            c.execute('DELETE FROM attendance')
        elif kind == 'extlist':
            c.execute('DELETE FROM ext_records WHERE list = ?', (k,))
        elif kind == 'kvmap':
            c.execute('DELETE FROM kv_maps WHERE map = ?', (k,))
        else:
            c.execute('DELETE FROM hotel_settings WHERE k = ?', (k,))

    def commit_document(self, c, old, new, version, saved_at):
        """Write the difference between two data objects inside the caller's transaction (`c`).
        `old` = the last committed object ({} for a fresh import). Returns the number of top-level keys written."""
        kinds = json.loads(self.meta('doc_kinds') or '{}') if old else {}
        changed = 0
        for k, v in new.items():
            nk = self.kind_of(k, v)
            ok = kinds.get(k)
            if ok == nk and k in old and old[k] == v:
                continue
            if ok is not None and ok != nk:
                self._clear_key(c, k, ok)
                ov = None
            else:
                ov = old.get(k) if ok == nk else None
            self._put_key(c, k, nk, v, ov)
            kinds[k] = nk
            changed += 1
        for k in list(old.keys()):
            if k not in new and k in kinds:
                self._clear_key(c, k, kinds.pop(k))
                changed += 1
        keys = list(new.keys())
        if not old or list(old.keys()) != keys or changed:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_keys', ?)", (_dump(keys),))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_kinds', ?)", (_dump(kinds),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_version', ?)", (str(int(version)),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('saved_at', ?)", (str(int(saved_at or 0)),))
        return changed

    def import_document(self, c, doc, version=1, saved_at=0, hotel_id=None):
        """Fresh import (migration), inside the caller's transaction."""
        self.commit_document(c, {}, doc, version, saved_at)
        hid = hotel_id or _hotel_of(doc)
        if hid:
            c.execute("INSERT OR IGNORE INTO meta VALUES ('hotel_id', ?)", (hid,))
            c.execute('INSERT OR IGNORE INTO hotels VALUES (?, ?)', (hid, int(time.time() * 1000)))

    def _put_key(self, c, k, kind, v, old):
        if kind == 'spec':
            self._put_list(c, SPEC_BY_KEY[k], v, old if isinstance(old, list) else [])
        elif kind == 'seq':
            c.execute('DELETE FROM sequences')
            for i, (n, x) in enumerate(v.items()):
                num = _scalar(x) and not isinstance(x, str)
                c.execute('INSERT INTO sequences VALUES (?, ?, ?, ?)', (n, x if num else None, None if num else _dump(x), i))
        elif kind == 'maptable':
            table, kc = MAP_TABLES[k]
            self._put_map_rows(c, table, kc, v, old if isinstance(old, dict) else {})
        elif kind == 'att':
            self._put_att(c, v, old if isinstance(old, dict) else {})
        elif kind == 'extlist':
            self._put_ext_list(c, k, v, old if isinstance(old, list) else None)
        elif kind == 'kvmap':
            self._put_kv_map(c, k, v, old if isinstance(old, dict) else {})
        else:
            c.execute('INSERT OR REPLACE INTO hotel_settings VALUES (?, ?)', (k, _dump(v)))

    def _put_list(self, c, spec, new, old):
        om = {x['id']: (i, x) for i, x in enumerate(old) if isinstance(x, dict) and x.get('id')}
        nids = set()
        now = int(time.time() * 1000)
        for i, x in enumerate(new):
            rid = x['id']
            nids.add(rid)
            o = om.get(rid)
            if o is None:
                self._put_record(c, spec, x, i)
            elif o[1] != x:
                if spec.table == 'bills':
                    c.execute('INSERT INTO bill_modifications (bill_id, action, at, old, new) VALUES (?, ?, ?, ?, ?)',
                              (rid, 'cancel' if x.get('cancelled') and not o[1].get('cancelled') else 'edit', now, _dump(o[1]), _dump(x)))
                if spec.table == 'kots' and o[1].get('status') != x.get('status'):
                    c.execute('INSERT INTO kot_status_history (kot_id, old_status, new_status, at) VALUES (?, ?, ?, ?)', (rid, o[1].get('status'), x.get('status'), now))
                self._put_record(c, spec, x, i)
            elif o[0] != i:
                c.execute(f'UPDATE {spec.table} SET ord = ? WHERE id = ?', (i, rid))
        for rid, (i, x) in om.items():
            if rid not in nids:
                if spec.table == 'bills':
                    c.execute('INSERT INTO bill_modifications (bill_id, action, at, old, new) VALUES (?, ?, ?, ?, NULL)', (rid, 'delete', now, _dump(x)))
                self._del_record(c, spec, rid)

    def _put_map_rows(self, c, table, kc, new, old):
        pos = {k: i for i, k in enumerate(old)}
        for i, (k, v) in enumerate(new.items()):
            if k not in old or old[k] != v or pos[k] != i:
                c.execute(f'INSERT OR REPLACE INTO {table} ({kc}, ord, data) VALUES (?, ?, ?)', (k, i, _dump(v)))
        for k in old:
            if k not in new:
                c.execute(f'DELETE FROM {table} WHERE {kc} = ?', (k,))

    def _put_att(self, c, new, old):
        pos = {k: i for i, k in enumerate(old)}
        for di, (d, m) in enumerate(new.items()):
            if d in old and old[d] == m and pos[d] == di:
                continue
            c.execute('DELETE FROM attendance WHERE date = ?', (d,))
            if not m:
                c.execute("INSERT INTO attendance VALUES (?, '', ?, '__empty__')", (d, di * 100000))
            for si, (sk, v) in enumerate(m.items()):
                c.execute('INSERT INTO attendance VALUES (?, ?, ?, ?)', (d, sk, di * 100000 + si, _dump(v)))
        for d in old:
            if d not in new:
                c.execute('DELETE FROM attendance WHERE date = ?', (d,))

    def _put_ext_list(self, c, k, new, old):
        ids_ok = all(isinstance(x, dict) and isinstance(x.get('id'), str) and x.get('id') for x in new) and len({x['id'] for x in new}) == len(new)
        old_ok = old is not None and all(isinstance(x, dict) and isinstance(x.get('id'), str) for x in old)
        if not ids_ok or not old_ok:
            c.execute('DELETE FROM ext_records WHERE list = ?', (k,))
            for i, x in enumerate(new):
                rid = x['id'] if ids_ok else '#%d' % i
                c.execute('INSERT INTO ext_records VALUES (?, ?, ?, ?, ?)', (k, rid, i, 0 if ids_ok else 1, _dump(x)))
            return
        om = {x['id']: (i, x) for i, x in enumerate(old)}
        for i, x in enumerate(new):
            o = om.get(x['id'])
            if o is None or o[1] != x or o[0] != i:
                c.execute('INSERT OR REPLACE INTO ext_records VALUES (?, ?, ?, 0, ?)', (k, x['id'], i, _dump(x)))
        nids = {x['id'] for x in new}
        for rid in om:
            if rid not in nids:
                c.execute('DELETE FROM ext_records WHERE list = ? AND id = ?', (k, rid))

    def _put_kv_map(self, c, name, new, old):
        if not old or list(old.keys()) != list(new.keys()):
            c.execute('DELETE FROM kv_maps WHERE map = ?', (name,))
            for i, (k, v) in enumerate(new.items()):
                c.execute('INSERT INTO kv_maps VALUES (?, ?, ?, ?)', (name, k, i, _dump(v)))
            return
        for i, (k, v) in enumerate(new.items()):
            if old.get(k) != v:
                c.execute('INSERT OR REPLACE INTO kv_maps VALUES (?, ?, ?, ?)', (name, k, i, _dump(v)))

    def export_document(self):
        with self.wlock:
            return self._export_document()

    def _export_document(self, skip=()):
        c = self.con()
        keys = json.loads(self.meta('doc_keys') or '[]')
        kinds = json.loads(self.meta('doc_kinds') or '{}')
        out = {}
        for k in keys:
            if k in skip:
                continue
            kind = kinds.get(k, 'setting')
            if kind == 'spec':
                out[k] = self._export_list(c, SPEC_BY_KEY[k])
            elif kind == 'seq':
                out[k] = {n: (json.loads(t) if t is not None else v) for n, v, t in c.execute('SELECT name, n, t FROM sequences ORDER BY ord')}
            elif kind == 'maptable':
                table, kc = MAP_TABLES[k]
                out[k] = {r[0]: json.loads(r[1]) for r in c.execute(f'SELECT {kc}, data FROM {table} ORDER BY ord')}
            elif kind == 'att':
                att = {}
                for d, sk, v in c.execute('SELECT date, staff_key, v FROM attendance ORDER BY ord'):
                    m = att.setdefault(d, {})
                    if v != '__empty__':
                        m[sk] = json.loads(v)
                out[k] = att
            elif kind == 'extlist':
                out[k] = [json.loads(r[0]) for r in c.execute('SELECT data FROM ext_records WHERE list = ? ORDER BY ord', (k,))]
            elif kind == 'kvmap':
                out[k] = {r[0]: json.loads(r[1]) for r in c.execute('SELECT k, v FROM kv_maps WHERE map = ? ORDER BY ord', (k,))}
            else:
                r = c.execute('SELECT v FROM hotel_settings WHERE k = ?', (k,)).fetchone()
                out[k] = json.loads(r[0]) if r else None
        return out

    def _export_list(self, c, spec):
        return self._export_rows(c, spec)

    def _export_rows(self, c, spec, where='', args=()):
        """Records of one list, in stored order; `where` (on the parent table) limits parents and children alike."""
        cols = spec.cols
        has_arrays = spec.table in ('bills', 'kots', 'menu_items')
        sel = ','.join(['id'] + ['"%s"' % x for x in cols] + ['extra'] + (['arrays'] if has_arrays else []))
        rows = c.execute(f'SELECT {sel} FROM {spec.table} {where} ORDER BY ord', args).fetchall()
        kids = {}
        sub = f' WHERE {{fk}} IN (SELECT id FROM {spec.table} {where})' if where else ''
        for ch in spec.children:
            m = {}
            if not rows:
                kids[ch.key] = m
                continue
            for r in c.execute(f'SELECT {ch.fk}, {",".join(chr(34) + x + chr(34) for x in ch.cols)}, extra' + (', synthetic' if ch.table == 'bill_payments' else '') + f' FROM {ch.table}' + sub.format(fk=ch.fk) + f' ORDER BY {ch.fk}, line', args):
                if ch.table == 'bill_payments' and r[-1]:
                    continue
                m.setdefault(r[0], []).append(join_record(ch.cols, r[1:1 + len(ch.cols)], r[1 + len(ch.cols)]))
            kids[ch.key] = m
        out = []
        for r in rows:
            rid = r[0]
            rec = join_record(cols, r[1:1 + len(cols)], r[1 + len(cols)])
            rec['id'] = rid
            arrays = (r[2 + len(cols)] or '').split(',') if has_arrays else []
            for ch in spec.children:
                if ch.key in arrays:
                    rec[ch.key] = kids[ch.key].get(rid, [])
            out.append(rec)
        return out

    # ---- record-level operations (Phase 2b: a save sends only the records that changed) ----
    def kinds(self):
        return json.loads(self.meta('doc_kinds') or '{}')

    def doc_keys(self):
        return json.loads(self.meta('doc_keys') or '[]')

    def register_key(self, c, k, kind):
        """A top-level key and the place it is stored (doc_keys / doc_kinds), inside the caller's transaction."""
        keys, kinds = self.doc_keys(), self.kinds()
        old = kinds.get(k)
        if k in keys and old == kind:
            return old
        if old is not None and old != kind:
            self._clear_key(c, k, old)
        if k not in keys:
            keys.append(k)
        kinds[k] = kind
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_keys', ?)", (_dump(keys),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_kinds', ?)", (_dump(kinds),))
        return old

    def get_records(self, c, key, ids):
        """{id: record} for the given ids of a list stored in its own table."""
        spec, out = SPEC_BY_KEY[key], {}
        ids = [str(i) for i in ids]
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            for r in self._export_rows(c, spec, f'WHERE id IN ({",".join("?" * len(chunk))})', chunk):
                out[r['id']] = r
        return out

    def get_ext_records(self, c, key, ids):
        out = {}
        for rid in ids:
            r = c.execute('SELECT data FROM ext_records WHERE list = ? AND id = ?', (key, str(rid))).fetchone()
            if r:
                out[str(rid)] = json.loads(r[0])
        return out

    @staticmethod
    def _next_ord(c, table, where='', args=()):
        return c.execute(f'SELECT COALESCE(MAX(ord), -1) + 1 FROM {table} {where}', args).fetchone()[0]

    def upsert(self, c, key, kind, rec, old=None):
        """Insert or replace one record of a list; a new record goes to the end, an existing one keeps its place."""
        now = int(time.time() * 1000)
        if kind == 'spec':
            spec = SPEC_BY_KEY[key]
            r = c.execute(f'SELECT ord FROM {spec.table} WHERE id = ?', (rec['id'],)).fetchone()
            if r is not None and old is not None and old != rec:
                if spec.table == 'bills':
                    c.execute('INSERT INTO bill_modifications (bill_id, action, at, old, new) VALUES (?, ?, ?, ?, ?)',
                              (rec['id'], 'cancel' if rec.get('cancelled') and not old.get('cancelled') else 'edit', now, _dump(old), _dump(rec)))
                if spec.table == 'kots' and old.get('status') != rec.get('status'):
                    c.execute('INSERT INTO kot_status_history (kot_id, old_status, new_status, at) VALUES (?, ?, ?, ?)', (rec['id'], old.get('status'), rec.get('status'), now))
            self._put_record(c, spec, rec, r[0] if r is not None else self._next_ord(c, spec.table))
        elif kind == 'extlist':
            r = c.execute('SELECT ord FROM ext_records WHERE list = ? AND id = ?', (key, rec['id'])).fetchone()
            c.execute('INSERT OR REPLACE INTO ext_records VALUES (?, ?, ?, 0, ?)',
                      (key, rec['id'], r[0] if r is not None else self._next_ord(c, 'ext_records', 'WHERE list = ?', (key,)), _dump(rec)))
        else:
            raise StoreError(f'{key}: records cannot be saved one by one ({kind})')

    def remove(self, c, key, kind, rid, old=None):
        if kind == 'spec':
            spec = SPEC_BY_KEY[key]
            if spec.table == 'bills' and old is not None:
                c.execute('INSERT INTO bill_modifications (bill_id, action, at, old, new) VALUES (?, ?, ?, ?, NULL)', (rid, 'delete', int(time.time() * 1000), _dump(old)))
            self._del_record(c, spec, rid)
        elif kind == 'extlist':
            c.execute('DELETE FROM ext_records WHERE list = ? AND id = ?', (key, rid))
        else:
            raise StoreError(f'{key}: records cannot be removed one by one ({kind})')

    def map_set(self, c, key, kind, mk, v):
        """One entry of a map (running table orders, cash drawer, salary sheets, attendance day, other maps)."""
        if kind == 'maptable':
            table, kc = MAP_TABLES[key]
            r = c.execute(f'SELECT ord FROM {table} WHERE {kc} = ?', (mk,)).fetchone()
            c.execute(f'INSERT OR REPLACE INTO {table} ({kc}, ord, data) VALUES (?, ?, ?)', (mk, r[0] if r else self._next_ord(c, table), _dump(v)))
        elif kind == 'kvmap':
            r = c.execute('SELECT ord FROM kv_maps WHERE map = ? AND k = ?', (key, mk)).fetchone()
            c.execute('INSERT OR REPLACE INTO kv_maps VALUES (?, ?, ?, ?)', (key, mk, r[0] if r else self._next_ord(c, 'kv_maps', 'WHERE map = ?', (key,)), _dump(v)))
        elif kind == 'att':
            if not isinstance(v, dict):
                raise StoreError('attendance day must be an object')
            r = c.execute('SELECT MIN(ord) FROM attendance WHERE date = ?', (mk,)).fetchone()
            if r and r[0] is not None:
                base = r[0] - r[0] % 100000
            else:
                top = c.execute('SELECT MAX(ord) FROM attendance').fetchone()[0]
                base = 0 if top is None else (top // 100000 + 1) * 100000
            c.execute('DELETE FROM attendance WHERE date = ?', (mk,))
            if not v:
                c.execute("INSERT INTO attendance VALUES (?, '', ?, '__empty__')", (mk, base))
            for si, (sk, x) in enumerate(v.items()):
                c.execute('INSERT INTO attendance VALUES (?, ?, ?, ?)', (mk, sk, base + si, _dump(x)))
        else:
            raise StoreError(f'{key}: not a map ({kind})')

    def map_del(self, c, key, kind, mk):
        if kind == 'maptable':
            table, kc = MAP_TABLES[key]
            c.execute(f'DELETE FROM {table} WHERE {kc} = ?', (mk,))
        elif kind == 'kvmap':
            c.execute('DELETE FROM kv_maps WHERE map = ? AND k = ?', (key, mk))
        elif kind == 'att':
            c.execute('DELETE FROM attendance WHERE date = ?', (mk,))
        else:
            raise StoreError(f'{key}: not a map ({kind})')

    def set_value(self, c, key, kind, v, old):
        """Replace a whole top-level value (settings, sequences, staff, a small list), writing only what differs."""
        prev = self.register_key(c, key, kind)
        self._put_key(c, key, kind, v, old if prev == kind else None)

    @staticmethod
    def log_change(c, version, k, rid=''):
        c.execute('INSERT INTO change_log (version, k, rid) VALUES (?, ?, ?)', (int(version), k, str(rid)))

    @staticmethod
    def set_version(c, version, saved_at):
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_version', ?)", (str(int(version)),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('saved_at', ?)", (str(int(saved_at or 0)),))

    @staticmethod
    def append_outbox(c, op, ref, doc_version, payload_obj_or_str, at=None):
        if at is None:
            at = int(time.time() * 1000)
        p_str = json.dumps(payload_obj_or_str, ensure_ascii=False) if isinstance(payload_obj_or_str, (dict, list)) else str(payload_obj_or_str or '{}')
        cur = c.execute('INSERT INTO sync_outbox (op, ref, doc_version, payload, at) VALUES (?, ?, ?, ?, ?)',
                  (str(op), str(ref) if ref else None, int(doc_version), p_str, int(at)))
        return cur.lastrowid

    def get_pending_outbox(self, con=None, limit=100, include_legacy=True):
        if con is None:
            con = self.con()
        rows = con.execute(
            "SELECT seq, op, ref, doc_version, payload, at, sent_at FROM sync_outbox WHERE sent_at IS NULL ORDER BY seq ASC LIMIT ?",
            (int(limit),)
        ).fetchall()
        result = []
        for seq, op, ref, dv, p_raw, at, sent_at in rows:
            try:
                p_obj = json.loads(p_raw or '{}')
            except Exception:
                p_obj = {}
            is_leg = is_legacy_outbox(p_obj)
            if not include_legacy and is_leg:
                continue
            result.append({
                'seq': seq,
                'op': op,
                'ref': ref,
                'doc_version': dv,
                'payload': p_obj,
                'at': at,
                'sent_at': sent_at,
                'is_legacy': is_leg
            })
        return result

    def ack_outbox(self, con, confirmed_acks, now=None):
        """
        Acknowledge ONLY confirmed operations by verifying (op_id, hotel_id, checksum).
        Never allows acknowledgment by unrelated sequence or ref aliases.
        """
        if not confirmed_acks:
            return 0
        if now is None:
            now = int(time.time() * 1000)

        valid_acks = {}
        for ack in confirmed_acks:
            if isinstance(ack, dict):
                oid = str(ack.get('op_id') or '').strip()
                hid = str(ack.get('hotel_id') or '').strip().upper()
                cs = str(ack.get('checksum') or '').strip().lower()
                if oid and hid and cs:
                    valid_acks[oid] = (hid, cs)
            # Strict acknowledgment: string-only or alias acks permanently removed from production

        if not valid_acks:
            return 0

        pending = con.execute("SELECT seq, ref, payload FROM sync_outbox WHERE sent_at IS NULL").fetchall()
        matched = []
        for seq, ref, p_str in pending:
            try:
                p = json.loads(p_str or '{}')
            except Exception:
                continue
            env_op_id = str(p.get('op_id') or '').strip()
            if env_op_id in valid_acks:
                req_hid, req_cs = valid_acks[env_op_id]
                env_hid = str(p.get('hotel_id') or '').strip().upper()
                env_cs = str(p.get('integrity', {}).get('checksum') or '').strip().lower()
                norm_req_cs = req_cs.replace('sha256:', '')
                norm_env_cs = env_cs.replace('sha256:', '')
                if env_hid == req_hid and norm_env_cs == norm_req_cs and norm_req_cs != '':
                    matched.append(seq)

        if matched:
            q = ','.join('?' * len(matched))
            con.execute(f"UPDATE sync_outbox SET sent_at = ? WHERE seq IN ({q})", [int(now)] + matched)
        return len(matched)

    @staticmethod
    def record_conflict(c, k, rid, reason, kept=None, other=None, device=None, now=None):
        if now is None:
            now = int(time.time() * 1000)
        # Record conflicts once: check if unresolved conflict already exists for this rid
        existing = c.execute("SELECT seq FROM sync_conflicts WHERE rid = ? AND resolved = 0", (str(rid or ''),)).fetchone()
        if existing:
            return existing[0]

        kept_str = json.dumps(kept, ensure_ascii=False) if isinstance(kept, (dict, list)) else str(kept or '')
        other_str = json.dumps(other, ensure_ascii=False) if isinstance(other, (dict, list)) else str(other or '')
        c.execute(
            "INSERT INTO sync_conflicts (at, k, rid, reason, kept, other, device, resolved) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (int(now), str(k), str(rid or ''), str(reason), kept_str, other_str, str(device or 'counter'))
        )
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    def changed_since(self, c, since, upto):
        """[(key, record id, version)] changed after version `since` up to `upto`, or None when the log no longer
        reaches back that far (the device then loads again)."""
        lo = c.execute('SELECT MIN(version) FROM change_log').fetchone()[0]
        if since >= upto:
            return []
        if lo is None or since < lo - 1:
            return None
        return c.execute('SELECT k, rid, MAX(version) FROM change_log WHERE version > ? AND version <= ? GROUP BY k, rid ORDER BY MAX(version)', (int(since), int(upto))).fetchall()

    @staticmethod
    def last_change(c, k, rid=''):
        r = c.execute('SELECT MAX(version) FROM change_log WHERE k = ? AND rid = ?', (k, str(rid))).fetchone()
        return r[0] if r and r[0] is not None else 0

    @staticmethod
    def prune_change_log(c, keep=100000):
        c.execute('DELETE FROM change_log WHERE seq <= (SELECT MAX(seq) FROM change_log) - ?', (int(keep),))

    # ---- what the server keeps in memory, and what devices load ----
    def export_except(self, skip=('bills',)):
        """The data object without the long history lists (they are read from the tables when needed)."""
        with self.wlock:
            return self._export_document(skip)

    def export_window(self, frm):
        """Bills from `frm` (YYYY-MM-DD) on, in stored order, rebuilt exactly (own read connection)."""
        with self.reader() as c:
            return self._export_rows(c, SPEC_BY_KEY['bills'], 'WHERE date >= ?', (frm,))

    def bill_page(self, frm, to, after, limit):
        """(count in range, records, last ord) of bills in a date range after stored position `after`."""
        with self.reader() as c:
            n = c.execute('SELECT COUNT(*) FROM bills WHERE date >= ? AND date <= ?', (frm, to)).fetchone()[0]
            ids = c.execute('SELECT id, ord FROM bills WHERE date >= ? AND date <= ? AND ord > ? ORDER BY ord LIMIT ?', (frm, to, int(after), int(limit))).fetchall()
            recs = self.get_records(c, 'bills', [i for i, _ in ids])
            return n, [recs[i] for i, _ in ids if i in recs], (ids[-1][1] if ids else after)

    def iter_bills(self, page=5000):
        """Every bill in stored order, `page` at a time (keyset paging; one snapshot for the whole run)."""
        with self.reader() as c:
            last = -1
            while True:
                ids = c.execute('SELECT id, ord FROM bills WHERE ord > ? ORDER BY ord LIMIT ?', (last, page)).fetchall()
                if not ids:
                    return
                recs = self.get_records(c, 'bills', [i for i, _ in ids])
                yield [recs[i] for i, _ in ids if i in recs]
                last = ids[-1][1]

    def history_totals(self, frm):
        """Totals of the bills before `frm`, for the values the app derives from every bill ever made:
        stock (sale / cancel movements per item), and per customer: visits, spend, first / last visit,
        loyalty points, wallet spend and favourite dishes. Same rules as the app's customers(), ptsBal(),
        walletBal() and stockMoves()."""
        with self.reader() as c:
            stock = {sid: q for sid, q in c.execute("SELECT sid, SUM(qty) FROM stock_movements WHERE source IN ('sale', 'cancel') AND date < ? GROUP BY sid", (frm,))}
            n = c.execute('SELECT COUNT(*) FROM bills WHERE date < ?', (frm,)).fetchone()[0]
            cust = self._cust_totals(c, frm)
            # Sales per day (not cancelled), for charts of older months: [bills, total in paise]
            days = {d: [k, p or 0] for d, k, p in c.execute('SELECT date, COUNT(*), SUM(total_p) FROM bills WHERE date < ? AND is_cancelled = 0 GROUP BY date', (frm,)) if d}
            # Last day each dish was sold (Slow Movers report)
            item_last = {nm: d for nm, d in c.execute('SELECT i.name, MAX(b.date) FROM bill_items i JOIN bills b ON b.id = i.bill_id WHERE b.date < ? AND b.is_cancelled = 0 GROUP BY i.name', (frm,)) if nm}
        return {'from': frm, 'bills': n, 'stock': stock, 'cust': cust, 'days': days, 'itemLast': item_last}

    def cust_totals(self, frm, phones):
        """history_totals()['cust'] for some customers only (10-digit numbers), recounted from the tables."""
        with self.reader() as c:
            out = {}
            for p in phones:
                out.update({k: v for k, v in self._cust_totals(c, frm, p).items() if k == p})
            return out

    @staticmethod
    def _cust_totals(c, frm, phone=None):
        cust = {}
        flt, args = ('AND phone LIKE ?', (frm, '%' + phone)) if phone else ('', (frm,))
        for phone_, name, channel, mode, total, date, extra, canc in c.execute(
                f'SELECT phone, cust, channel, mode, total, date, extra, is_cancelled FROM bills WHERE date < ? {flt} ORDER BY ord', args):
            if canc:
                continue
            p = norm_ph(phone_)
            if len(p) != 10:
                continue
            ex = json.loads(extra) if extra and extra != '{}' else {}
            e = cust.get(p)
            if e is None:
                e = cust[p] = {'visits': 0, 'spend': 0, 'pts': 0, 'pa': 0, 'ws': 0, 'name': '', 'first': '', 'last': '', 'fav': {}}
            pts = jsnum(ex.get('ptsEarned')) - jsnum(ex.get('ptsUsed'))
            e['pa'] += pts
            if mode == 'Wallet':
                e['ws'] += jsnum(total)
            if channel in ('Zomato', 'Swiggy'):
                continue
            if name:
                e['name'] = name
            if not e['visits']:
                e['first'] = date
            e['visits'] += 1
            e['spend'] += jsnum(total)
            e['last'] = date
            e['pts'] += pts
        for phone_, iname, qty in c.execute(f"""SELECT b.phone, i.name, i.qty FROM bill_items i JOIN bills b ON b.id = i.bill_id
                WHERE b.date < ? {flt.replace('phone', 'b.phone')} AND b.is_cancelled = 0 AND COALESCE(b.phone, '') <> '' AND COALESCE(b.channel, '') NOT IN ('Zomato', 'Swiggy')
                ORDER BY b.ord, i.line""", args):
            e = cust.get(norm_ph(phone_))
            if e is not None and iname:
                e['fav'][iname] = e['fav'].get(iname, 0) + (jsnum(qty) or 1)
        # Every dish a customer ordered, in first-ordered order (no cap: a cap changes which dish is the favourite
        # once recent orders are added; the app breaks ties by that order)
        return cust

    # ---- stock ----
    def stock_balances(self, aliases=None):
        """Quantity per stock item from the ledger, with merged items folded into their target (the app's sidOf)."""
        aliases = aliases or {}

        def root(s):
            n = 0
            while s in aliases and n < 6:
                s, n = aliases[s], n + 1
            return s
        tot = {}
        with self.wlock:
            rows = self.con().execute('SELECT sid, qty FROM stock_balances').fetchall()
        for sid, q in rows:
            r = root(sid)
            tot[r] = tot.get(r, 0) + q
        return tot

    def rebuild_balances(self, c):
        c.execute('DELETE FROM stock_balances')
        c.execute('INSERT INTO stock_balances (sid, qty) SELECT sid, SUM(qty) FROM stock_movements GROUP BY sid')

    # ---- backups ----
    def backup_to(self, dest_gz, doc_version=None, keep=60, verify=True):
        """Online backup (VACUUM INTO from a separate read connection: a consistent snapshot while transactions run),
        gzip, verify, record in the manifest."""
        tmp = dest_gz + '.part.sqlite'
        for p in (tmp, tmp + '-wal', tmp + '-shm'):
            if os.path.exists(p):
                os.remove(p)
        t0 = time.time()
        # Own read connection + VACUUM INTO: a consistent snapshot of the last commit, while billing keeps writing (WAL).
        # (Holding the write lock for the whole copy stopped billing for ~65 s on a year of data.)
        src = sqlite3.connect(self.path, timeout=30)
        try:
            src.execute('VACUUM INTO ?', (tmp,))
        finally:
            src.close()
        h = hashlib.sha256()
        with open(tmp, 'rb') as f, gzip.open(dest_gz + '.part', 'wb', compresslevel=6) as g:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
                g.write(chunk)
        bills = None
        ok = 0
        if verify:
            v = sqlite3.connect(tmp)
            ok = 1 if v.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' else 0
            bills = v.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
            v.close()
        os.replace(dest_gz + '.part', dest_gz)
        os.remove(tmp)
        size = os.path.getsize(dest_gz)
        with self.tx() as c:
            c.execute('INSERT OR REPLACE INTO backup_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                      (os.path.basename(dest_gz), int(time.time() * 1000), doc_version, size, h.hexdigest(), bills, ok, f'{time.time() - t0:.2f}s'))
        if keep:
            d = os.path.dirname(dest_gz)
            files = sorted(x for x in os.listdir(d) if x.startswith('setu-') and x.endswith('.sqlite.gz'))
            for old in files[:-keep]:
                os.remove(os.path.join(d, old))
        return {'file': dest_gz, 'bytes': size, 'sha256': h.hexdigest(), 'bills': bills, 'verified': bool(ok), 'seconds': round(time.time() - t0, 2)}


def restore_backup(backup_gz, dest_db, expected_hotel_id=None):
    """Verify and restore a backup to a *new/empty* SQLite path, offline only.

    Never replace a live hotel database or WAL file. Use a new data folder,
    verify hotel identity, and swap client paths through the offline upgrade
    runbook only after all checks pass. No cloud or network writes are made.
    """
    if not expected_hotel_id:
        # Existing test/demo copies may omit this, but real hotel restores
        # must supply the identity to prevent accidental cross-hotel imports.
        expected_hotel_id = None
    if any(os.path.exists(dest_db + ext) for ext in ('', '-wal', '-shm', '.restore')):
        raise StoreError("restore requires an empty destination; stop the counter and use a new folder")
    parent = os.path.dirname(os.path.abspath(dest_db))
    if not os.path.isdir(parent):
        raise StoreError("restore destination directory does not exist")
    tmp = dest_db + '.restore'
    try:
        with gzip.open(backup_gz, 'rb') as g, open(tmp, 'xb') as out:
            shutil.copyfileobj(g, out)
            out.flush()
            os.fsync(out.fileno())
        # Do not trust a backup simply because it can be decompressed.
        con = sqlite3.connect(f'file:{tmp}?mode=ro', uri=True)
        try:
            integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                raise StoreError('backup failed its integrity check: ' + str(integrity))
            hotel_row = con.execute(
                "SELECT value FROM meta WHERE key='hotel_id'"
            ).fetchone()
            # schema uses meta(k,v); support the actual installed layout below
        except sqlite3.OperationalError as exc:
            if 'no such column' not in str(exc):
                raise
            hotel_row = con.execute(
                "SELECT v FROM meta WHERE k='hotel_id'"
            ).fetchone()
        finally:
            con.close()

        con = sqlite3.connect(f'file:{tmp}?mode=ro', uri=True)
        try:
            bills = con.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
            hotel = str(hotel_row[0] or '').strip().upper() if hotel_row else ''
        finally:
            con.close()
        if expected_hotel_id and hotel != str(expected_hotel_id).strip().upper():
            raise StoreError('backup Hotel ID does not match intended installation')
        if not hotel:
            raise StoreError('backup missing Hotel ID; unsafe to restore')
        os.replace(tmp, dest_db)
        return {'bills': bills, 'integrity': 'ok', 'hotel_id': hotel}
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def norm_ph(p):
    """The app's normPh(): digits only, the last 10 of a longer number."""
    d = ''.join(ch for ch in str(p if p is not None else '') if ch in '0123456789')   # JS \D: ASCII digits only
    return d[-10:] if len(d) > 10 else d


def jsnum(x):
    """JavaScript `+x || 0`."""
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x if x == x else 0
    if x is None:
        return 0
    try:
        s = str(x).strip()
        v = float(s) if s else 0
        return int(v) if float(v).is_integer() else v
    except (TypeError, ValueError):
        return 0


def _hotel_of(doc):
    for part in ('settings', 'auth'):
        v = (doc.get(part) or {}).get('hotelId') if isinstance(doc.get(part), dict) else None
        if v:
            return str(v)
    return None


def canonical_hash(doc):
    """sha256 of the canonical form, built record by record (no single huge string for big databases)."""
    h = hashlib.sha256()

    def feed(v):
        if isinstance(v, dict):
            h.update(b'{')
            for k in sorted(v):
                h.update(json.dumps(k, ensure_ascii=False).encode() + b':')
                feed(v[k])
                h.update(b',')
            h.update(b'}')
        elif isinstance(v, list):
            h.update(b'[')
            for x in v:
                feed(x) if isinstance(x, (dict, list)) else h.update(json.dumps(x, ensure_ascii=False).encode())
                h.update(b',')
            h.update(b']')
        else:
            h.update(json.dumps(v, ensure_ascii=False).encode())
    for k in sorted(doc):
        h.update(json.dumps(k, ensure_ascii=False).encode() + b'=')
        feed(doc[k])
    return h.hexdigest()


def canonical(doc):
    """Text used to prove two data objects are identical (key order inside objects does not matter)."""
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def read_flag(data_dir):
    try:
        with open(os.path.join(data_dir, FLAG_FILE), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_flag(data_dir, obj):
    p = os.path.join(data_dir, FLAG_FILE)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(p + '.tmp', p)


# ---------------------------------------------------------------------------------------------------------
# Phase 3.0: Reliable Sync Foundation & Operation Envelopes
# ---------------------------------------------------------------------------------------------------------

def is_legacy_outbox(payload):
    """Returns True if an outbox payload is a legacy summary-only record."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return True
    if not isinstance(payload, dict):
        return True
    return payload.get('envelope_version') != 1


def get_envelope_entities(env):
    """Returns a set of (module, id) tuples touched by the envelope."""
    entities = set()
    payload = env.get('payload') or {}
    recs = payload.get('records') or {}
    for mod, v in recs.items():
        if isinstance(v, dict):
            for r in v.get('ups') or []:
                if isinstance(r, dict) and r.get('id'):
                    entities.add((mod, str(r['id'])))
            for rm_id in v.get('rm') or []:
                entities.add((mod, str(rm_id)))
    maps = payload.get('maps') or {}
    for mod, v in maps.items():
        if isinstance(v, dict):
            for tbl in (v.get('set') or {}).keys():
                entities.add((mod, str(tbl)))
            for tbl in v.get('del') or []:
                entities.add((mod, str(tbl)))
    return entities


def _normalize_numbers(obj):
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: _normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_numbers(v) for v in obj]
    return obj


def make_sync_envelope(
    op_id,
    hotel_id,
    device_id,
    doc_version,
    timestamp,
    event_type='ops',
    actor=None,
    writes_rec=None,
    writes_map=None,
    writes_whole=None,
    conflicts=None
):
    """
    Constructs an immutable, durable Phase 3.0 operation sync envelope.
    Contains the complete business records and mutations needed to reproduce
    the committed transaction deterministically on the cloud or another replica.
    Strictly sanitizes all credentials, passwords, and PIN hashes.
    """
    clean_rec = {}
    total_records = 0
    if writes_rec:
        for k, val in writes_rec.items():
            if isinstance(val, (list, tuple)) and len(val) == 3:
                kind, ups, rms = val
            elif isinstance(val, dict):
                kind = val.get('kind', 'rec')
                ups = val.get('ups') or []
                rms = val.get('rm') or []
            else:
                continue

            clean_ups = []
            for r in ups:
                if isinstance(r, dict):
                    # Strip any potential secrets/PINs from staff or users
                    cr = {rk: rv for rk, rv in r.items() if not any(x in rk.lower() for x in ('pin', 'pass', 'hash', 'secret'))}
                    clean_ups.append(cr)
                else:
                    clean_ups.append(r)
            clean_rms = [str(x) for x in rms]
            total_records += len(clean_ups) + len(clean_rms)
            clean_rec[k] = {
                'kind': kind,
                'ups': clean_ups,
                'rm': clean_rms
            }

    clean_map = {}
    if writes_map:
        for k, val in writes_map.items():
            if isinstance(val, (list, tuple)) and len(val) == 3:
                kind, s_, d_ = val
            elif isinstance(val, dict):
                kind = val.get('kind', 'map')
                s_ = val.get('set') or {}
                d_ = val.get('del') or []
            else:
                continue
            clean_map[k] = {
                'kind': kind,
                'set': dict(s_),
                'del': [str(x) for x in d_]
            }

    clean_values = {}
    if writes_whole:
        for k, v in writes_whole.items():
            if k in ('secure', 'adminPin', 'password', 'token'):
                continue
            if k == 'settings' and isinstance(v, dict):
                clean_values[k] = {sk: sv for sk, sv in v.items() if not any(x in sk.lower() for x in ('pin', 'pass', 'hash', 'secret', 'key'))}
            elif k == 'auth' and isinstance(v, dict):
                clean_values[k] = {ak: av for ak, av in v.items() if not any(x in ak.lower() for x in ('pin', 'pass', 'hash', 'secret'))}
            else:
                clean_values[k] = v

    payload = {
        'records': clean_rec,
        'maps': clean_map,
        'values': clean_values
    }
    payload = _normalize_numbers(payload)

    payload_canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    checksum = hashlib.sha256(payload_canonical.encode('utf-8')).hexdigest()

    clean_conflicts = []
    if conflicts:
        for c in conflicts:
            if isinstance(c, (list, tuple)) and len(c) >= 3:
                clean_conflicts.append({'k': c[0], 'id': str(c[1]), 'reason': str(c[2])})
            elif isinstance(c, dict):
                clean_conflicts.append({'k': c.get('k'), 'id': str(c.get('id') or ''), 'reason': str(c.get('reason') or '')})

    actor_info = {}
    if isinstance(actor, dict):
        actor_info = {'role': str(actor.get('role') or 'local'), 'name': str(actor.get('name') or '')}
    elif actor:
        actor_info = {'role': str(actor), 'name': ''}
    else:
        actor_info = {'role': 'local', 'name': ''}

    envelope = {
        'envelope_version': 1,
        'op_id': str(op_id),
        'hotel_id': str(hotel_id or 'UNKNOWN'),
        'device_id': str(device_id or 'counter'),
        'doc_version': int(doc_version),
        'timestamp': int(timestamp),
        'event_type': str(event_type),
        'actor': actor_info,
        'payload': payload,
        'conflicts': clean_conflicts,
        'integrity': {
            'checksum': f'sha256:{checksum}',
            'record_count': total_records,
            'keys': sorted(set(clean_rec) | set(clean_map) | set(clean_values))
        }
    }
    return envelope



class OutboxSyncDispatcher:
    """
    Phase 3.2 Reliable Background Counter-to-Cloud Sync Dispatcher.

    Guarantees:
    - Reads pending full Phase 3.0 envelopes in ascending sequence order.
    - Never sends legacy summary-only rows as normal transactions.
    - Sends bounded batches with timeouts over authenticated HTTPS (X-Setu-Sync / X-Setu-Hotel).
    - Sync credentials stay strictly server-side, never exposed to clients or browser.
    - Never holds SQLite write locks during HTTP network roundtrips.
    - Accepts ONLY explicit, individual per-operation committed acknowledgments.
    - Preserves unacknowledged operations across restarts and transient network failures.
    - Quarantines permanent conflicts in sync_conflicts for Manager review without dropping payloads.
    - Kept disabled by default; activates only when explicitly configured and safely validated.
    """
    def __init__(self, store, url=None, hotel=None, key=None, enabled=False,
                 batch_size=50, poll_interval=5.0, max_backoff=30.0, http_post_fn=None):
        self.store = store
        self.url = (url or '').rstrip('/')
        self.hotel = (hotel or '').strip().upper()
        self.key = (key or '').strip()
        self.enabled = bool(enabled)
        self.batch_size = max(1, min(100, int(batch_size)))
        self.poll_interval = float(poll_interval)
        self.max_backoff = float(max_backoff)
        self.http_post_fn = http_post_fn or self._default_http_post

        self._running = False
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self.inbound = InboundSyncReceiver(
            store=self.store,
            url=self.url,
            hotel=self.hotel,
            key=self.key,
            enabled=self.enabled,
            batch_size=self.batch_size,
            poll_interval=self.poll_interval,
            max_backoff=self.max_backoff,
            http_post_fn=self.http_post_fn
        )
        self.stats = {
            'sent_batches': 0,
            'sent_ops': 0,
            'acked_ops': 0,
            'conflicts': 0,
            'errors': 0,
            'last_sync_at': 0,
            'last_error': '',
            'state': 'stopped'
        }

    @staticmethod
    def _default_http_post(url, path, body_bytes, headers, timeout=15):
        full_url = url.rstrip('/') + path
        req = urllib.request.Request(full_url, data=body_bytes, method='POST', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        except urllib.error.URLError as e:
            raise OSError(f'Network connection failed: {e.reason}')

    def get_pending_count(self):
        with self.store.rlock():
            row = self.store.con().execute("SELECT COUNT(*) FROM sync_outbox WHERE sent_at IS NULL").fetchone()
            return row[0] if row else 0

    def get_operational_status(self):
        with self.store.rlock():
            outbox_pending = self.get_pending_count()
        inbound_status = self.inbound.get_operational_status() if hasattr(self, 'inbound') and self.inbound else {}
        return {
            'connection_status': self.stats.get('state', 'offline') if self.stats.get('state') != 'stopped' else (inbound_status.get('connection_status') or 'offline'),
            'outbox_pending_ops': outbox_pending,
            'pending_inbound_qr_orders': inbound_status.get('pending_inbound_qr_orders', 0),
            'pending_licence_updates': inbound_status.get('pending_licence_updates', 0),
            'last_inbound_sync': inbound_status.get('last_inbound_sync', 0),
            'last_outbox_sync': self.stats.get('last_sync_at', 0),
            'failed_ops': self.stats.get('errors', 0) + inbound_status.get('failed_inbound_ops', 0),
            'conflicts': self.stats.get('conflicts', 0),
            'inbound_cursor': inbound_status.get('inbound_cursor', 0)
        }

    def is_activation_safe(self):
        """
        Activation safety check:
        Phase 3 sync is disabled by default.
        Allowed only for explicitly configured isolated test hotels after verifying:
        1. Explicitly enabled (self.enabled == True)
        2. Configured credentials (url, hotel, key)
        3. Hotel code matches local database identity
        4. No unresolved legacy summary outbox rows pending
        """
        if not self.enabled:
            return False, 'Phase 3 cloud sync is disabled by default.'
        if not self.url or not self.hotel or not self.key:
            return False, 'Missing cloud sync credentials (url, hotel code, or sync key).'

        sdb = getattr(self.store, 'sdb', self.store)
        doc_hotel = sdb.meta('hotel_id')
        if doc_hotel and doc_hotel.strip().upper() != self.hotel:
            return False, f'Hotel identity mismatch: database belongs to {doc_hotel}, configured for {self.hotel}.'

        with sdb.rlock():
            pending_raw = sdb.con().execute("SELECT payload FROM sync_outbox WHERE sent_at IS NULL").fetchall()
            for (p_raw,) in pending_raw:
                if is_legacy_outbox(p_raw):
                    return False, 'Unresolved legacy summary outbox records found. Baseline migration must be reconciled before Phase 3 activation.'

        return True, 'OK'

    def dispatch_once(self):
        """
        Executes a single non-blocking dispatch pass:
        1. Checks activation safety.
        2. Reads pending Phase 3 envelopes via read-only query (NO write lock held during network).
        3. Sends batch over authenticated HTTPS.
        4. Acknowledges ONLY confirmed operations and quarantines conflicts.
        """
        safe, reason = self.is_activation_safe()
        if not safe:
            self.stats['state'] = 'inactive'
            self.stats['last_error'] = reason
            return {'status': 'inactive', 'reason': reason, 'processed': 0}

        sdb = getattr(self.store, 'sdb', self.store)

        # 1. Read pending envelopes without holding write locks
        with sdb.rlock():
            pending = sdb.get_pending_outbox(sdb.con(), limit=self.batch_size, include_legacy=False)
            # Find entities with unresolved active conflicts
            blocked_entities = set()
            active_conflicts = sdb.con().execute("SELECT other FROM sync_conflicts WHERE resolved = 0").fetchall()
            for (c_raw,) in active_conflicts:
                try:
                    c_obj = json.loads(c_raw or '{}')
                    blocked_entities.update(get_envelope_entities(c_obj))
                except Exception:
                    pass

        if not pending:
            self.stats['state'] = 'idle'
            return {'status': 'idle', 'processed': 0}

        envelopes = []
        for item in pending:
            p = item.get('payload')
            if isinstance(p, dict) and p.get('envelope_version') == 1 and p.get('op_id'):
                env_entities = get_envelope_entities(p)
                # If dependent on an unresolved conflicted entity, hold back
                if env_entities & blocked_entities:
                    continue
                # Attach exact outbox row metadata for precise quarantine indexing
                p_with_meta = dict(p)
                p_with_meta['_outbox_seq'] = item['seq']
                p_with_meta['_outbox_ref'] = item.get('ref') or p.get('op_id')
                envelopes.append(p_with_meta)

        if not envelopes:
            state = 'blocked_on_dependency' if (pending and blocked_entities) else 'idle'
            self.stats['state'] = state
            return {'status': state, 'processed': 0, 'acked': 0, 'conflicts': 0}

        # 2. Build HTTP request
        req_headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'X-Setu-Hotel': self.hotel,
            'X-Setu-Sync': self.key,
            'X-Setu-Caps': 'secure1',
            'User-Agent': 'Setu-Main-Counter/1.0'
        }
        wire_envelopes = []
        for env in envelopes:
            clean_env = {k: v for k, v in env.items() if not k.startswith('_outbox_')}
            wire_envelopes.append(clean_env)
        req_body = json.dumps({'batch': wire_envelopes}, ensure_ascii=False).encode('utf-8')

        # 3. Network roundtrip (isolated from SQLite write locks)
        try:
            code, text = self.http_post_fn(self.url, '/api/sync/ops', req_body, req_headers, timeout=15)
        except Exception as e:
            self._consecutive_failures += 1
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            self.stats['state'] = 'error'
            return {'status': 'network_error', 'error': str(e), 'processed': 0}

        if code == 401:
            self._consecutive_failures += 1
            self.stats['errors'] += 1
            self.stats['last_error'] = 'Invalid sync credentials (HTTP 401)'
            self.stats['state'] = 'auth_error'
            return {'status': 'auth_error', 'http_code': 401, 'error': 'Invalid sync credentials'}

        if code == 402:
            self._consecutive_failures += 1
            self.stats['errors'] += 1
            self.stats['last_error'] = 'Hotel account suspended or subscription expired (HTTP 402)'
            self.stats['state'] = 'payment_required'
            return {'status': 'payment_required', 'http_code': 402, 'error': 'Subscription expired'}

        if code == 403:
            self._consecutive_failures += 1
            self.stats['errors'] += 1
            self.stats['last_error'] = 'Hotel tenant mismatch or forbidden (HTTP 403)'
            self.stats['state'] = 'forbidden'
            return {'status': 'forbidden', 'http_code': 403, 'error': 'Tenant mismatch'}

        if code != 200:
            self._consecutive_failures += 1
            self.stats['errors'] += 1
            self.stats['last_error'] = f'Cloud returned HTTP {code}: {text[:150]}'
            self.stats['state'] = 'server_error'
            return {'status': 'server_error', 'http_code': code, 'error': text[:150]}

        # 4. Process individual acknowledgments
        try:
            resp_data = json.loads(text or '{}')
        except Exception as e:
            self._consecutive_failures += 1
            self.stats['errors'] += 1
            self.stats['last_error'] = f'Malformed JSON response from cloud: {e}'
            return {'status': 'response_parse_error', 'error': str(e)}

        results = resp_data.get('results') or {}
        confirmed_acks = []
        confirmed_op_ids = []
        conflicts = []

        for env in envelopes:
            op_id = env.get('op_id')
            op_res = results.get(op_id)
            if not isinstance(op_res, dict):
                # Missing or malformed ack: unconfirmed
                continue

            status = op_res.get('status')
            if status == 'committed':
                ack_op_id = str(op_res.get('op_id') or '').strip()
                ack_hotel_id = str(op_res.get('hotel_id') or '').strip().upper()
                ack_checksum = str(op_res.get('checksum') or '').strip().lower()

                env_op_id = str(op_id or '').strip()
                env_hotel_id = str(env.get('hotel_id') or self.hotel).strip().upper()
                env_checksum = str(env.get('integrity', {}).get('checksum') or '').strip().lower()

                norm_ack_cs = ack_checksum.replace('sha256:', '')
                norm_env_cs = env_checksum.replace('sha256:', '')

                # Verify all three: op_id, hotel_id, and committed payload checksum
                if ack_op_id == env_op_id and ack_hotel_id == env_hotel_id and norm_ack_cs == norm_env_cs and norm_ack_cs != '':
                    confirmed_acks.append({
                        'op_id': env_op_id,
                        'hotel_id': env_hotel_id,
                        'checksum': env_checksum
                    })
                    confirmed_op_ids.append(env_op_id)
                else:
                    # Mismatched ack: treat as unconfirmed
                    continue
            elif status == 'rejected':
                err = op_res.get('error')
                if err in ('CONFLICT_OP_ID_PAYLOAD_MISMATCH', 'CONFLICT_STALE_RECORD'):
                    conflicts.append({'op_id': op_id, 'reason': err, 'payload': env})

        # 5. Persist acknowledgments and conflicts atomically in local SQLite
        now_ms = int(time.time() * 1000)
        with sdb.tx() as write_con:
            if confirmed_acks:
                sdb.ack_outbox(write_con, confirmed_acks, now=now_ms)
            for conf in conflicts:
                op_id = conf['op_id']
                sdb.record_conflict(
                    write_con,
                    k=conf['payload'].get('event_type') or 'ops',
                    rid=op_id,
                    reason=conf['reason'],
                    kept=None,
                    other=conf['payload'],
                    device=conf['payload'].get('device_id'),
                    now=now_ms
                )
                # Exact indexed quarantine: match by primary key seq or indexed ref!
                outbox_seq = conf['payload'].get('_outbox_seq')
                if outbox_seq:
                    write_con.execute(
                        "UPDATE sync_outbox SET sent_at = ? WHERE seq = ? AND sent_at IS NULL",
                        (-now_ms, outbox_seq)
                    )
                else:
                    write_con.execute(
                        "UPDATE sync_outbox SET sent_at = ? WHERE ref = ? AND sent_at IS NULL",
                        (-now_ms, op_id)
                    )

        self._consecutive_failures = 0
        self.stats['sent_batches'] += 1
        self.stats['sent_ops'] += len(envelopes)
        self.stats['acked_ops'] += len(confirmed_acks)
        self.stats['conflicts'] += len(conflicts)
        self.stats['last_sync_at'] = now_ms
        self.stats['last_error'] = ''
        self.stats['state'] = 'active'

        return {
            'status': 'ok',
            'processed': len(envelopes),
            'acked': len(confirmed_acks),
            'conflicts': len(conflicts),
            'confirmed_ids': confirmed_op_ids
        }

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._wake_event.clear()
            self.stats['state'] = 'running'
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name='SetuOutboxDispatcher')
            self._thread.start()
            safe, _ = self.is_activation_safe()
            if safe:
                self.inbound.start()

    def stop(self, timeout=5.0):
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            self._wake_event.set()
            self.stats['state'] = 'stopped'
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self.inbound.stop(timeout=timeout)

    def wake(self):
        self._wake_event.set()

    def _run_loop(self):
        attempt = 0
        while not self._stop_event.is_set():
            try:
                res = self.dispatch_once()
                status = res.get('status')
                if status == 'ok':
                    attempt = 0
                    if res.get('processed', 0) >= self.batch_size:
                        if self._stop_event.wait(0.05):
                            break
                        continue
                    self._wake_event.wait(self.poll_interval)
                    self._wake_event.clear()
                elif status in ('idle', 'inactive'):
                    attempt = 0
                    self._wake_event.wait(self.poll_interval)
                    self._wake_event.clear()
                else:
                    attempt += 1
                    backoff = min(self.max_backoff, 1.0 * (2 ** min(attempt - 1, 6)))
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = max(0.5, backoff * jitter)
                    self._wake_event.wait(sleep_time)
                    self._wake_event.clear()
            except Exception as e:
                attempt += 1
                backoff = min(self.max_backoff, 1.0 * (2 ** min(attempt - 1, 6)))
                jitter = random.uniform(0.8, 1.2)
                sleep_time = max(0.5, backoff * jitter)
                self.stats['errors'] += 1
                self.stats['last_error'] = str(e)
                self._wake_event.wait(sleep_time)
                self._wake_event.clear()



class InboundApplyError(ValueError):
    """Permanent invalid inbound event: never commit or ACK."""
    pass


class InboundSyncReceiver:
    """
    Phase 3.4 Inbound Cloud Change Feed Sync Receiver.

    Guarantees:
    - Fetches paginated inbound change events (since=cursor, limit=50) strictly in ascending seq order.
    - Idempotent execution: verifies each event against `inbound_events_applied`.
    - QR Orders: updates `table_orders` (kaccha) and inserts running `kots` + `kot_items` atomically.
    - Never auto-charges, auto-settles, or creates bills/payments for inbound QR orders.
    - Zero inventory movement or stock balance modification on KOT reception.
    - Preserves existing offline POS billing and receipt printing under all conditions.
    - Licence updates: verifies hotel_id and installation_id, prevents downgrades, updates `subscription`.
    - Vendor notices: deduplicates and records into settings.
    - Sends durable ACKs to cloud only after local SQLite transaction commits.
    - Supports exponential backoff and offline reconnection recovery.
    """
    def __init__(self, store, url=None, hotel=None, key=None, enabled=False,
                 batch_size=50, poll_interval=5.0, max_backoff=30.0,
                 http_get_fn=None, http_post_fn=None):
        # SqliteSetuStore (live counter) wraps SqliteDoc (tests).
        # Keep the wrapper to publish committed inbound changes to LAN clients.
        self.live_store = store if hasattr(store, '_reload_after_inbound') else None
        self.store = getattr(store, 'sdb', store)
        self.url = (url or '').rstrip('/')
        self.hotel = (hotel or '').strip().upper()
        self.key = (key or '').strip()
        self.enabled = bool(enabled)
        self.batch_size = max(1, min(100, int(batch_size)))
        self.poll_interval = float(poll_interval)
        self.max_backoff = float(max_backoff)
        self.http_get_fn = http_get_fn or self._default_http_get
        self.http_post_fn = http_post_fn or self._default_http_post

        self._running = False
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self.stats = {
            'applied_events': 0,
            'acked_events': 0,
            'last_sync_at': 0,
            'errors': 0,
            'last_error': '',
            'state': 'stopped'
        }

    @staticmethod
    def _default_http_get(url, path, headers, timeout=15):
        full_url = url.rstrip('/') + path
        req = urllib.request.Request(full_url, method='GET', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        except urllib.error.URLError as e:
            raise OSError(f'Network connection failed: {e.reason}')

    @staticmethod
    def _default_http_post(url, path, body_bytes, headers, timeout=15):
        full_url = url.rstrip('/') + path
        req = urllib.request.Request(full_url, data=body_bytes, method='POST', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        except urllib.error.URLError as e:
            raise OSError(f'Network connection failed: {e.reason}')

    def is_activation_safe(self):
        if not self.enabled:
            return False
        if not self.url or not self.hotel or not self.key:
            return False
        return True

    def get_last_applied_seq(self):
        """Durable contiguous cursor, not MAX(seq): never hide missing events."""
        with self.store.tx() as c:
            row = c.execute("SELECT seq FROM inbound_cursor_state WHERE name = 'inbound'").fetchone()
            if row:
                return int(row[0])
            expected = 1
            # One-time migration for Phase 3.4 databases; stop at first gap.
            for (seq,) in c.execute("SELECT seq FROM inbound_events_applied ORDER BY seq ASC"):
                if int(seq) != expected:
                    break
                expected += 1
            cursor = expected - 1
            c.execute("INSERT OR IGNORE INTO inbound_cursor_state(name,seq) VALUES('inbound',?)", (cursor,))
            return cursor

    def get_pending_qr_count(self):
        with self.store.rlock():
            row = self.store.con().execute(
                "SELECT COUNT(*) FROM inbound_qr_orders WHERE status = 'pending'"
            ).fetchone()
            return int(row[0]) if row else 0

    def get_pending_licence_count(self):
        with self.store.rlock():
            row = self.store.con().execute("SELECT v FROM hotel_settings WHERE k = 'subscription'").fetchone()
            if not row or not row[0]:
                return 0
            try:
                sub = json.loads(row[0])
                cloud_keys = sub.get('cloudKeys', [])
                used_keys = sub.get('usedKeys', [])
                return max(0, len(cloud_keys) - len(used_keys))
            except Exception:
                return 0

    def get_operational_status(self):
        return {
            'connection_status': self.stats.get('state', 'offline'),
            'pending_inbound_qr_orders': self.get_pending_qr_count(),
            'pending_licence_updates': self.get_pending_licence_count(),
            'last_inbound_sync': self.stats.get('last_sync_at', 0),
            'failed_inbound_ops': self.stats.get('errors', 0),
            'inbound_cursor': self.get_last_applied_seq()
        }

    def _ack_pending(self):
        """Resend committed event ACKs until cloud confirms exact event IDs."""
        with self.store.rlock():
            ids = [r[0] for r in self.store.con().execute(
                "SELECT id FROM inbound_events_applied WHERE acked_at IS NULL "
                "ORDER BY seq ASC LIMIT ?", (self.batch_size,)
            ).fetchall()]
        if not ids:
            return 0
        payload = json.dumps({'hotel_id': self.hotel, 'event_ids': ids}).encode('utf-8')
        headers = {
            'X-Setu-Hotel': self.hotel, 'X-Setu-Sync': self.key,
            'Content-Type': 'application/json'
        }
        try:
            status, response = self.http_post_fn(self.url, '/api/sync/inbound/ack', payload, headers)
            if status != 200:
                raise OSError('Inbound ACK HTTP ' + str(status))
            parsed = json.loads(response)
            if not isinstance(parsed, dict) or parsed.get('ok') is not True:
                raise ValueError('invalid ACK response')
            if parsed.get('hotel') != self.hotel:
                raise ValueError('ACK tenant mismatch')
            confirmed = set(parsed.get('acked_ids') or [])
            confirmed.intersection_update(ids)
            if not confirmed:
                raise ValueError('No event IDs confirmed by cloud ACK')
            now = int(time.time() * 1000)
            with self.store.tx() as c:
                for evt_id in confirmed:
                    c.execute(
                        "UPDATE inbound_events_applied SET acked_at = ? "
                        "WHERE id = ? AND acked_at IS NULL", (now, evt_id)
                    )
            return len(confirmed)
        except (OSError, ValueError, TypeError) as exc:
            self.stats['errors'] += 1
            self.stats['last_error'] = 'Inbound ACK pending retry: ' + str(exc)
            return 0

    def _report_cloud_applied(self):
        """Tell the guest cloud *only after* an accepted KOT is durable locally.

        Cloud may be offline or the HTTP response lost. Unconfirmed orders
        remain in inbound_qr_orders and are retried on later poll/restarts.
        This is independent of inbound event ACK and never affects bills.
        """
        with self.store.rlock():
            rows = self.store.con().execute("""
                SELECT q.order_id, CAST(k.no AS TEXT)
                FROM inbound_qr_orders q
                JOIN kots k ON k.id = q.kot_id
                WHERE q.status='accepted' AND q.cloud_applied_at IS NULL
                ORDER BY q.created_at, q.order_id
                LIMIT ?
            """, (self.batch_size,)).fetchall()
        done = 0
        headers = {
            'X-Setu-Hotel': self.hotel, 'X-Setu-Sync': self.key,
            'Content-Type': 'application/json'
        }
        for order_id, kot_no in rows:
            try:
                status, raw = self.http_post_fn(
                    self.url, '/api/qr/applied',
                    json.dumps({'id': order_id, 'kot': kot_no}).encode('utf-8'),
                    headers
                )
                if status != 200:
                    raise OSError('QR applied cloud HTTP ' + str(status))
                reply = json.loads(raw)
                if not isinstance(reply, dict) or reply.get('ok') is not True or \
                   reply.get('id') != order_id or str(reply.get('kot')) != kot_no:
                    raise ValueError('cloud did not confirm this QR/KOT pair')
                with self.store.tx() as c:
                    c.execute(
                        "UPDATE inbound_qr_orders SET cloud_applied_at=? "
                        "WHERE order_id=? AND status='accepted' AND kot_id IN "
                        "(SELECT id FROM kots WHERE CAST(no AS TEXT)=?) "
                        "AND cloud_applied_at IS NULL",
                        (int(time.time()*1000), order_id, kot_no)
                    )
                done += 1
            except (OSError, ValueError, TypeError) as exc:
                # Keep pending; do not ack, delete or change the kitchen KOT.
                self.stats['last_error'] = 'QR cloud KOT confirmation pending: ' + str(exc)
        return done

    def _record_inbound_failure(self, event_id, seq, reason):
        self.stats['errors'] += 1
        self.stats['last_error'] = str(reason)
        with self.store.tx() as c:
            c.execute(
                "INSERT INTO inbound_event_failures(event_id,seq,reason,occurred_at,resolved) "
                "VALUES (?,?,?,?,0) ON CONFLICT(event_id) DO UPDATE SET "
                "reason=excluded.reason, occurred_at=excluded.occurred_at",
                (str(event_id or 'unknown')[:128],
                 int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else 0,
                 str(reason)[:400], int(time.time()*1000))
            )

    def fetch_and_apply_once(self):
        if not self.is_activation_safe():
            self.stats['state'] = 'inactive'
            return {'status': 'inactive'}

        self.stats['state'] = 'syncing'
        # Retry unconfirmed ACKs even when the previously committed event
        # is outside the GET cursor window. Lost HTTP responses cannot strand ACKs.
        pre_acked = self._ack_pending()
        self._report_cloud_applied()
        last_seq = self.get_last_applied_seq()
        headers = {
            'X-Setu-Hotel': self.hotel, 'X-Setu-Sync': self.key,
            'Accept': 'application/json'
        }
        path = f'/api/sync/inbound?since={last_seq}&limit={self.batch_size}'
        try:
            http_status, response = self.http_get_fn(self.url, path, headers)
        except OSError as exc:
            self.stats['errors'] += 1
            self.stats['last_error'] = str(exc)
            self.stats['state'] = 'offline'
            return {'status': 'network_error', 'error': str(exc), 'acked': pre_acked}

        if http_status != 200:
            self.stats['errors'] += 1
            self.stats['last_error'] = f'Inbound HTTP {http_status}'
            self.stats['state'] = 'offline'
            return {
                'status': 'payment_required' if http_status == 402 else
                          'unauthorized' if http_status in (401, 403) else 'http_error',
                'http_code': http_status, 'acked': pre_acked
            }

        try:
            body = json.loads(response)
            if not isinstance(body, dict) or body.get('ok') is not True:
                raise ValueError('invalid inbound response')
            if body.get('hotel') and str(body['hotel']).upper() != self.hotel:
                raise ValueError('wrong hotel in inbound response')
            events = body.get('events')
            if not isinstance(events, list) or len(events) > self.batch_size:
                raise ValueError('invalid event batch')
        except (TypeError, ValueError) as exc:
            self.stats['errors'] += 1
            self.stats['last_error'] = str(exc)
            self.stats['state'] = 'offline'
            return {'status': 'invalid_response', 'error': str(exc), 'acked': pre_acked}

        applied_count = 0
        for evt in events:
            evt_id = evt.get('id') if isinstance(evt, dict) else None
            evt_seq = evt.get('seq') if isinstance(evt, dict) else None
            try:
                if not isinstance(evt_id, str) or not evt_id or len(evt_id) > 128:
                    raise InboundApplyError('INVALID_EVENT_ID')
                if type(evt_seq) is not int or evt_seq != last_seq + 1:
                    raise InboundApplyError(f'INBOUND_CURSOR_GAP expected {last_seq + 1}, got {evt_seq}')
                evt_type = evt.get('event_type')
                if evt_type not in ('qr_order', 'qr_status', 'licence_update', 'vendor_message'):
                    raise InboundApplyError('UNKNOWN_INBOUND_EVENT_TYPE')
                if evt.get('hotel_id') and str(evt['hotel_id']).upper() != self.hotel:
                    raise InboundApplyError('INBOUND_HOTEL_MISMATCH')
                payload = evt.get('payload')
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if not isinstance(payload, dict):
                    raise InboundApplyError('INVALID_EVENT_PAYLOAD')

                # Counter writes hold store.lock before SqliteDoc.wlock. Use
                # the same lock order to prevent an outbound edit overwriting
                # a cloud event while server memory is being refreshed.
                app_lock = self.live_store.lock if self.live_store else nullcontext()
                with app_lock:
                    dirty_keys = []
                    with self.store.tx() as c:
                        existing = c.execute(
                            "SELECT seq FROM inbound_events_applied WHERE id = ?", (evt_id,)
                        ).fetchone()
                        if existing:
                            if int(existing[0]) != evt_seq:
                                raise InboundApplyError('REPLAYED_EVENT_ID_NEW_SEQUENCE')
                        else:
                            if evt_type == 'qr_order':
                                self._apply_qr_order(c, payload)
                                # Pending QR orders have their own review endpoint.
                            elif evt_type == 'qr_status':
                                self._apply_qr_status(c, payload)
                                ordrow = c.execute(
                                    "SELECT tbl,status,kot_id FROM inbound_qr_orders WHERE order_id=?",
                                    (str(payload.get('order_id') or ''),)
                                ).fetchone()
                                if ordrow and ordrow[1] == 'accepted':
                                    dirty_keys = [
                                        ('kaccha', ordrow[0]), ('kots', ordrow[2]), ('seq', '')
                                    ]
                            elif evt_type == 'licence_update':
                                self._apply_licence_update(c, payload)
                                dirty_keys = [('subscription', '')]
                            elif evt_type == 'vendor_message':
                                self._apply_vendor_message(c, payload)
                                dirty_keys = [('vendor_notices', '')]
                            now_ms = int(time.time() * 1000)
                            # Phase 2b LAN /api/changes uses doc_version as its
                            # notification clock. Update it atomically with the
                            # inbound business data AND durable applied marker.
                            next_version = int(self.store.meta('doc_version') or 0) + 1
                            self.store.set_version(c, next_version, now_ms)
                            if dirty_keys:
                                for key, rid in dirty_keys:
                                    self.store.log_change(c, next_version, key, rid)
                            else:
                                self.store.log_change(c, next_version, 'inbound_qr', '')
                            c.execute(
                                "INSERT INTO inbound_events_applied"
                                "(id,seq,event_type,entity_id,applied_at,acked_at) "
                                "VALUES(?,?,?,?,?,NULL)",
                                (evt_id, evt_seq, evt_type, str(evt.get('entity_id') or ''),
                                 now_ms)
                            )
                            applied_count += 1
                        changed = c.execute(
                            "UPDATE inbound_cursor_state SET seq=? "
                            "WHERE name='inbound' AND seq=?",
                            (evt_seq, last_seq)
                        ).rowcount
                        if changed != 1:
                            raise InboundApplyError('CONCURRENT_INBOUND_CURSOR_CHANGE')
                    if self.live_store and not existing:
                        self.live_store._reload_after_inbound()
                last_seq = evt_seq
            except (InboundApplyError, ValueError, TypeError) as exc:
                self._record_inbound_failure(evt_id, evt_seq, str(exc))
                self.stats['state'] = 'blocked'
                acked = pre_acked + self._ack_pending()
                return {
                    'status': 'blocked', 'processed': applied_count,
                    'applied': applied_count, 'failed_event': evt_id,
                    'error': str(exc), 'acked': acked, 'cursor': last_seq
                }

        acked = pre_acked + self._ack_pending()
        self._report_cloud_applied()
        self.stats['applied_events'] += applied_count
        self.stats['acked_events'] += acked
        self.stats['last_sync_at'] = int(time.time()*1000)
        self.stats['state'] = 'connected'
        return {
            'status': 'ok' if events else 'idle',
            'processed': len(events), 'applied': applied_count,
            'acked': acked, 'cursor': last_seq
        }

    def _apply_qr_order(self, c, payload):
        """Stage guest order for approval. NEVER add pending items to bill cart."""
        order_id = str(payload.get('order_id') or '').strip()
        tbl = str(payload.get('table') or '').strip()
        items = payload.get('items')
        if not order_id or len(order_id) > 90 or not tbl or len(tbl) > 90:
            raise InboundApplyError('QR_ORDER_ID_OR_TABLE_INVALID')
        if not isinstance(items, list) or not 1 <= len(items) <= 40:
            raise InboundApplyError('QR_ORDER_ITEMS_INVALID')
        clean_items = []
        for it in items:
            if not isinstance(it, dict) or not str(it.get('mid') or ''):
                raise InboundApplyError('QR_ORDER_ITEM_INVALID')
            qty = float(it.get('qty', 0))
            price = float(it.get('price', 0))
            if not 0 < qty <= 50 or not 0 <= price <= 1000000:
                raise InboundApplyError('QR_ORDER_QUANTITY_OR_PRICE_INVALID')
            clean_items.append({
                'mid': str(it['mid'])[:90], 'name': str(it.get('name') or '')[:120],
                'price': price, 'qty': qty
            })
        # Duplicate order IDs may arrive via retry; conflicting content must
        # never be silently ignored under a reused ID.
        prior = c.execute(
            "SELECT tbl,items_json FROM inbound_qr_orders WHERE order_id=?",
            (order_id,)
        ).fetchone()
        if prior and (prior[0] != tbl or json.loads(prior[1]) != clean_items):
            raise InboundApplyError('QR_ORDER_ID_CONTENT_CONFLICT')
        c.execute("""
            INSERT OR IGNORE INTO inbound_qr_orders
              (order_id, tbl, items_json, guest_name, note, status, kot_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
        """, (order_id, tbl, json.dumps(clean_items),
              str(payload.get('guest_name') or '')[:80],
              str(payload.get('note') or '')[:200],
              int(payload.get('at') or time.time() * 1000),
              int(time.time() * 1000)))
        # No table_orders, KOT, bill, payment or inventory writes here.

    def _apply_qr_status(self, c, payload):
        """Accepted orders alone reach the running cart and kitchen ticket."""
        order_id = str(payload.get('order_id') or '').strip()
        state = str(payload.get('status') or '').lower()
        if not order_id or state not in ('accepted', 'rejected'):
            raise InboundApplyError('QR_STATUS_INVALID')
        row = c.execute(
            "SELECT tbl,items_json,guest_name,note,status,kot_id FROM inbound_qr_orders "
            "WHERE order_id = ?", (order_id,)
        ).fetchone()
        if not row:
            raise InboundApplyError('QR_STATUS_BEFORE_ORDER')
        tbl, items_json, guest_name, note, current, kot_id = row
        if current == state:
            return  # Same decision delivered again; no double KOT/cart.
        if current != 'pending':
            raise InboundApplyError('QR_DECISION_ALREADY_FINAL')

        now_ms = int(time.time() * 1000)
        if state == 'rejected':
            # Pending order never entered running cart, so waiter quantities
            # and previously billed items remain unchanged.
            c.execute(
                "UPDATE inbound_qr_orders SET status='rejected', updated_at=? "
                "WHERE order_id=? AND status='pending'", (now_ms, order_id)
            )
            return

        items = json.loads(items_json)
        old = c.execute("SELECT data FROM table_orders WHERE tbl = ?", (tbl,)).fetchone()
        order = json.loads(old[0]) if old and old[0] else {
            'cart': [], 'cust': '', 'note': '', 'qr': []
        }
        cart = list(order.get('cart') or [])
        # Do not merge QR quantities with waiter-created lines. Provenance
        # makes later removal/reconciliation possible without guessing.
        for it in items:
            cart.append({
                **it, 'src': 'qr', 'qr_order_id': order_id
            })
        order['cart'] = cart
        order['table'] = tbl
        # The cloud-approved QR quantities already have a kitchen ticket.
        # Extend the prior 'sent' quantities, not every cart line, so waiter
        # items that still need sending are not accidentally marked as sent.
        already_sent = dict(order.get('sent') or {})
        for it in items:
            mid = it['mid']
            already_sent[mid] = round(float(already_sent.get(mid, 0) or 0) + float(it['qty']), 3)
        order['sent'] = already_sent
        if guest_name and not order.get('cust'):
            order['cust'] = guest_name
        if note:
            order['note'] = (str(order.get('note') or '') + ' | ' + note).strip(' |')
        qr_ids = list(order.get('qr') or [])
        if order_id not in qr_ids:
            qr_ids.append(order_id)
        order['qr'] = qr_ids
        # Keep these two data-object keys registered so /api/db and
        # /api/changes can export inbound mutations to all LAN devices.
        self.store.register_key(c, 'kaccha', 'maptable')
        self.store.register_key(c, 'kots', 'spec')
        c.execute("""
            INSERT INTO table_orders (tbl, ord, data) VALUES (?, ?, ?)
            ON CONFLICT(tbl) DO UPDATE SET data=excluded.data
        """, (tbl, now_ms, json.dumps(order)))

        kot_id = 'qrkot_' + hashlib.sha256(order_id.encode('utf-8')).hexdigest()[:24]
        last_no = c.execute(
            "SELECT COALESCE(MAX(CAST(no AS INTEGER)),0) FROM kots"
        ).fetchone()[0]
        seq_row = c.execute(
            "SELECT n FROM sequences WHERE name = 'kot'"
        ).fetchone()
        try:
            configured_kot_no = int(seq_row[0]) if seq_row else 0
        except (TypeError, ValueError):
            configured_kot_no = 0
        kot_no = max(int(last_no), configured_kot_no) + 1
        now = datetime.now()
        # One established serializer owns the arrays flags and child-table
        # rows; raw INSERTs left 'arrays' empty and hid KOT items from exports.
        self.store.upsert(c, 'kots', 'spec', {
            'id': kot_id,
            'no': kot_no,
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%H:%M:%S'),
            'table': tbl,
            'channel': 'Dine-In',
            'status': 'new',
            'at': now_ms,
            'items': [dict(it) for it in items],
            'src': 'qr',
            'qr': order_id,
            'guest_name': guest_name
        })
        # Preserve the existing sequence map and keep KOT numbers unique
        # across waiter-created and cloud-created tickets.
        self.store.register_key(c, 'seq', 'seq')
        if seq_row is None:
            ord_row = c.execute(
                "SELECT COALESCE(MAX(ord),-1)+1 FROM sequences"
            ).fetchone()
            c.execute(
                "INSERT INTO sequences(name,n,t,ord) VALUES('kot',?,NULL,?)",
                (kot_no, int(ord_row[0]))
            )
        else:
            c.execute("UPDATE sequences SET n=?,t=NULL WHERE name='kot'", (kot_no,))
        c.execute("""
            UPDATE inbound_qr_orders SET status='accepted', kot_id=?, updated_at=?
            WHERE order_id=? AND status='pending'
        """, (kot_id, now_ms, order_id))

    def _apply_licence_update(self, c, payload):
        """Fail-closed cryptographic verification of installation-bound SETU keys."""
        if not isinstance(payload, dict):
            raise InboundApplyError("INVALID_LICENCE_PAYLOAD")
        h_id = str(payload.get('hotel_id', '')).strip().upper()
        if h_id != self.hotel:
            raise InboundApplyError("LICENCE_HOTEL_MISMATCH")

        row = c.execute("SELECT v FROM hotel_settings WHERE k = 'settings'").fetchone()
        try:
            local_settings = json.loads(row[0]) if row and row[0] else {}
        except (ValueError, TypeError) as exc:
            raise InboundApplyError("LICENCE_INSTALL_SETTINGS_INVALID") from exc
        install_id = str(local_settings.get('installId') or '')
        if len(install_id) < 8:
            raise InboundApplyError("LICENCE_INSTALL_ID_MISSING")
        cloud_inst = str(payload.get('install_id') or '')
        if cloud_inst and cloud_inst.upper() != install_id.upper():
            raise InboundApplyError("LICENCE_INSTALL_ID_MISMATCH")

        key = str(payload.get('key') or '')
        try:
            licence = verify_signed_license(
                key, install_id,
                public_keys=getattr(self, 'license_public_keys', TRUSTED_PUBLIC_KEYS)
            )
        except InvalidLicence as exc:
            raise InboundApplyError("INVALID_SIGNED_LICENCE: " + str(exc)) from exc

        row = c.execute("SELECT v FROM hotel_settings WHERE k = 'subscription'").fetchone()
        try:
            cur_sub = json.loads(row[0]) if row and row[0] else {}
        except (ValueError, TypeError) as exc:
            raise InboundApplyError("LICENCE_SUBSCRIPTION_CORRUPT") from exc

        if bool(payload.get('lifetime')) and not licence['lifetime']:
            raise InboundApplyError("UNSIGNED_LIFETIME_CLAIM")
        if cur_sub.get('isLifetime') and not licence['lifetime']:
            raise InboundApplyError("LICENCE_LIFETIME_DOWNGRADE")

        keys = list(cur_sub.get('cloudKeys') or [])
        if key in keys:
            return  # Duplicate delivery cannot activate/extend the same key twice.

        new_sub = dict(cur_sub)
        new_sub['planName'] = str(payload.get('plan') or cur_sub.get('planName') or 'active')[:80]
        if licence['lifetime']:
            new_sub.update({'isLifetime': True, 'status': 'lifetime', 'validUntil': '2099-12-31'})
        else:
            signed_until = datetime.fromtimestamp(
                licence['valid_until_ms'] / 1000, timezone.utc
            ).strftime('%Y-%m-%d')
            prev = str(cur_sub.get('validUntil') or '')
            # Never shorten a previously confirmed valid subscription.
            new_sub['validUntil'] = max(prev, signed_until) if len(prev) == 10 else signed_until
            new_sub['status'] = 'active'
        keys.append(key)
        new_sub['cloudKeys'] = keys
        self.store.set_value(c, 'subscription', 'setting', new_sub, cur_sub)

    def _apply_vendor_message(self, c, payload):
        msg_id = payload.get('id')
        row = c.execute("SELECT v FROM hotel_settings WHERE k = 'vendor_notices'").fetchone()
        notices = json.loads(row[0]) if row and row[0] else []
        if not any(n.get('id') == msg_id for n in notices):
            notices.append(payload)
            self.store.set_value(c, 'vendor_notices', 'setting', notices, notices[:-1])

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self.stats['state'] = 'idle'
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name='SetuInboundSync')
            self._thread.start()

    def stop(self, timeout=5.0):
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
            self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self.stats['state'] = 'stopped'

    def wake(self):
        self._wake_event.set()

    def _run_loop(self):
        attempt = 0
        while not self._stop_event.is_set():
            try:
                res = self.fetch_and_apply_once()
                status = res.get('status')
                if status == 'ok':
                    attempt = 0
                    if res.get('processed', 0) >= self.batch_size:
                        if self._stop_event.wait(0.05):
                            break
                        continue
                    self._wake_event.wait(self.poll_interval)
                    self._wake_event.clear()
                elif status in ('idle', 'inactive'):
                    attempt = 0
                    self._wake_event.wait(self.poll_interval)
                    self._wake_event.clear()
                else:
                    attempt += 1
                    backoff = min(self.max_backoff, 1.0 * (2 ** min(attempt - 1, 6)))
                    jitter = random.uniform(0.8, 1.2)
                    self._wake_event.wait(max(0.5, backoff * jitter))
                    self._wake_event.clear()
            except Exception as e:
                attempt += 1
                backoff = min(self.max_backoff, 1.0 * (2 ** min(attempt - 1, 6)))
                self.stats['errors'] += 1
                self.stats['last_error'] = str(e)
                self._wake_event.wait(max(0.5, backoff))
                self._wake_event.clear()
